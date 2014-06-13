#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    BlocSim
"""

#======================================================================

"""
    Imports
"""
from math import hypot
from threading import Thread, RLock, Event, Timer
from collections import deque
import sys
import atexit
import os
import json
import cv2
import numpy as np
from time import time, sleep
import datetime
import tornado.gen
import tornado.httpserver
import tornado.ioloop
import tornado.web
import sockjs.tornado
import sockjs.tornado.periodic
from tornadorpc.json import JSONRPCHandler
import logging
from PIL import Image
import StringIO
import shutil
import pickledb
import mosquitto
import base64
import re

def purge_pyc():
    global dbg_file
    folder=os.path.dirname(os.path.realpath(__file__))
    pat=".*\.pyc"
    for f in os.listdir(folder):
        if re.search("^.*\.pyc$",f):
            os.remove(os.path.join(folder,f))

purge_pyc()
from cvcommon import *
purge_pyc()

#======================================================================
"""
    Utility functions
"""

def timestamp(include_ms=True):
    if include_ms:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S%.%f")
    else:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def timestamp_ms():
    return int(round(time() * 1000))

def recursive_tuples(arr):
    try:
        return tuple(recursive_tuples(i) for i in arr)
    except TypeError:
        return arr

class TimedOutException(Exception):
    pass

#======================================================================

"""
    Global variables, configuration constants & handling the keystore database
"""
class Globals(object):
    DBG_CV = True
    DBG_MQTT = False
    DBG_LOCK = False
    DBG_DB = True
    DBG_FPS = False
    DBG_SOCKET = False
    DBG_RPC = True
    LOG_LEVEL = logging.DEBUG

    TEST_CV = False
    TEST_MQTT = False

    PATH_DEFAULTS = "config/defaults.db"
    PATH_CONFIG = "config/config.db"
    PERSISTENCE = True
    AUTO_SYNC_WITH_DISK = False
    FORCE_REGEN = False

    def __init__(self):
        self.camLock = RLock()
        self.frameLock = RLock()
        self.frameSetLock = RLock()
        self.dbLock = RLock()
        self.bmdLock = RLock()
        self.db = None
        logging.getLogger().setLevel(Globals.LOG_LEVEL)

        if not os.path.isdir("config"):
            logging.error("/config folder missing. Exiting...")
            exit(1)
        if not os.path.exists(Globals.PATH_DEFAULTS):
            logging.error(Globals.PATH_DEFAULTS + " file missing. Exiting...")
            exit(1)
        if (not Globals.PERSISTENCE) or (not os.path.exists(Globals.PATH_CONFIG)):
            shutil.copyfile(Globals.PATH_DEFAULTS, Globals.PATH_CONFIG)

        self.load_db()
        #if len(self.db.db) == 0:
        #    self.load_defaults()
        #if len(self.db.db) == 0:
        #    self.gen_defaults()
        #    #self.save_defaults()
        #    #self.save_db()

        if Globals.FORCE_REGEN:
            self.gen_defaults()
            #self.save_db()

        #if self.DBG_DB: print self.db.db

    def load_db(self):
        with self.dbLock:
            self.db = pickledb.load(Globals.PATH_CONFIG, Globals.AUTO_SYNC_WITH_DISK)
        if Globals.DBG_DB: logging.info("db: load_db ({} items loaded)".format(len(self.db.db)))

    def load_defaults(self):
        with self.dbLock:
            self.db = pickledb.load(Globals.PATH_DEFAULTS, Globals.AUTO_SYNC_WITH_DISK)
        if Globals.DBG_DB: logging.info("db: load_defaults ({} items loaded)".format(len(self.db.db)))

    def save_db(self):
        with self.dbLock:
            self.db.dump()
        if Globals.DBG_DB: logging.info("db: save_db ({} items saved)".format(len(self.db.db)))

    def save_defaults(self):
        if Globals.DBG_DB: logging.info("db: save_defaults ...")
        with self.dbLock:
            db_defaults = pickledb.load(Globals.PATH_DEFAULTS, False)
            db_defaults.db = self.db.db
            db_defaults.dump()

    def gen_defaults(self):
        """
        all of these auto-generate a slider & are passed as a map of name: {min,max,val}
            black_sat max/min
            black_val max/min
            green_hue max/min
            red_hue max/min
            color_sat max/min
            color_val max/min
            connector_gap
            kernel_k
            dot_size max/min (%)
            rectangle_area_ratio max/min (%)
        """
        #self.db.set("hello", "world")
        #self.db.set("key", "value")
        #self.db.set("text", "sample text here")
        with self.dbLock:
            self.db.deldb()

            # min, max, v1, v2, range_type
            #
            self.db.set("bounds_x", [True, 0,100, 0,100])
            self.db.set("bounds_y", [True, 0,100, 0,100])
            self.db.set("black_sat", ["min", 0,255, 30])
            self.db.set("black_val", ["min", 0,255, 30])
            self.db.set("green_hue", [True, 0,180, 82,94])
            self.db.set("red_hue", [True, 0,180, 10,170])
            self.db.set("color_sat", ["max", 0,255, 22])
            self.db.set("color_val", ["max", 0,255, 70])
            self.db.set("connector_gap", ["min", 3,100, 20])
            self.db.set("kernel_k", ["min", 3,25, 3])
            self.db.set("dot_size", [True, 5,255, 10,100])
            self.db.set("area_ratio", ["max", 1,100, 80])

            print "regenerating db:"
            print self.db.db

        if Globals.DBG_DB: logging.info("db: gen_defaults ({} items created)".format(len(self.db.db)))

G = Globals()

#======================================================================

"""
    Handling mosquitto messages
"""
class MQTT(object):
    TOPIC_BLOCSIM = "blocsim"
    TOPIC_ADAPTERS = ["blocsim/adapters/digital"]
    IP = "127.0.0.1"
    PORT = 1883
    QOS = 1

    def __init__(self):
        self.mqttclient = mosquitto.Mosquitto() #no client id = randomly generated
        self.mqttclient.on_message = self.on_message
        self.mqttclient.on_connect = self.on_connect
        self.mqttclient.on_disconnect = self.on_disconnect
        self.mqttclient.on_subscribe = self.on_subscribe
        self.mqttclient.on_unsubscribe = self.on_unsubscribe
        self.mqttclient.on_publish = self.on_publish

        self.ip = MQTT.IP
        self.port = MQTT.PORT
        self.qos = MQTT.QOS
        self.maintopic = MQTT.TOPIC_BLOCSIM
        self.message = "{}"

        self.mqttThread = Thread(target=self.mqtt_loop)
        self.run = False

    def on_message(self, mosq, obj, msg):
        if G.DBG_MQTT: logging.debug("MQTT Received\t'%s' | topic '%s' qos %d" % (msg.topic, msg.payload, msg.qos))

    def on_connect(self, mosq, obj, rc):
        if G.DBG_MQTT: logging.debug("MQTT Connected\tstatus %d" % rc)

    def on_disconnect(self, mosq, obj, rc):
        if G.DBG_MQTT: logging.debug("MQTT Disconnected\tstatus %d" % rc)

    def on_subscribe(self, mosq, obj, mid, qos_list):
        if G.DBG_MQTT: logging.debug("MQTT Subscribed\tmid %s" % mid)

    def on_unsubscribe(self, mosq, obj, mid):
        if G.DBG_MQTT: logging.debug("MQTT Unsubscribed\tmid %s" % mid)

    def on_publish(self, mosq, obj, mid):
        if G.DBG_MQTT: logging.debug("MQTT Published\tmid %s" % mid)

    #==================================================================

    def mqtt_loop(self):
        while self.run:
            result = self.mqttclient.loop(0.1, 1)
            if result != 0:
                logging.warning("MQTT network disconnect/error")
                self.stop()
        #logging.info("MQTT loop finish")

    def start(self):
        logging.info("MQTT Connecting to %s:%d" % (self.ip, self.port))
        self.mqttclient.connect(self.ip, self.port)
        self.run = True

        self.mqttThread.start()

        if G.TEST_MQTT: self.test()

    def stop(self):
        self.run = False
        logging.info("MQTT Stop...")
        self.mqttclient.disconnect()
        self.mqttThread.join(3)

    def publish(self, topic=None, msg=None):
        if topic is None: topic = self.maintopic
        if msg is None:   msg   = self.message
        if not self.run:
            logging.warning("MQTT Trying to publish without a connection")
            return
        if G.DBG_MQTT: logging.info("MQTT Publishing: qos %d | topic %s | '%s'" % (self.qos, topic, msg))
        self.mqttclient.publish(topic, msg, self.qos)

    def subscribe(self, topic=None):
        if topic is None: topic = self.maintopic
        logging.info("MQTT Subscribed to %s" % topic)
        self.mqttclient.subscribe(topic, self.qos)

    def unsubscribe(self, topic=None):
        if topic is None: topic = self.maintopic
        logging.info("MQTT Unsubscribing from %s" % topic)
        self.mqttclient.unsubscribe(topic)

    def test(self):
        self.subscribe()
        self.publish()
        self.unsubscribe()

MQ = MQTT()

"""
try:
    while True:
        msg="{x:5,y:10,o:90,d:35}"
        topic="mqtttest"
        qos=1
        print "Publishing '%s' to topic '%s', qos%d" %(msg, topic, qos)
        mqttclient.publish(topic, msg, qos)
        if (mqttclient.loop() != 0):
            print "<Network Disconnect/Error>"
            stop()
        time.sleep(1)
except KeyboardInterrupt:
    stop()
"""

#======================================================================


"""
    Very useful for testing performance of some piece of code
"""
class Timing(object):
    def __init__(self):
        self.t = datetime.datetime.now()

    def start_timing(self):
        """start_timing()

        Save the current time
        """
        self.t = datetime.datetime.now()

    def stop_timing(self, show=False):
        """stop_timing([show]) -> us

        Return the time delta in microseconds. Print if show.
        """
        t = datetime.datetime.now()
        dt = t - self.t
        dt = dt.microseconds
        if show:
            print "timing: %.4fms"%(dt/1000.)
        return dt

    def repeat_timing(self, func, args=(), kwargs={}, nrepeats=100, show=False):
        """repeat_timing(func[, args[, kwargs[, repeats[, show]]]]) -> (avg, med, tot)

        Time execution of func(*args, **kwargs) n times.
        Return the average, median, total time deltas in microseconds.
        Print if show.
        """
        if not nrepeats > 0:
            raise ValueError("#repeats must be >0")
        times = []
        for i in xrange(nrepeats):
            self.start_timing()
            func(*args, **kwargs)
            times.append(self.stop_timing())
        tot = sum(times)
        avg = tot/float(nrepeats)
        times.sort()
        med = times[nrepeats/2]
        if show:
            print "test %s (%d repeats)" % (func.__name__, nrepeats)
            print "    avg time: %.4fms" % (avg/1000.)
            print "    med time: %.4fms" % (med/1000.)
            print "    tot time: %.4fms" % (tot/1000.)
        return avg, med, tot

T = Timing()

#======================================================================


"""
    Consider making a convenient wrapper for OpenCV images,
        with common actions built in & controlled by object variables
"""
class CVFrame(np.ndarray):

    def w(self):
        return self.shape[1]

    def h(self):
        return self.shape[0]

    def d(self):
        if len(self.shape) < 3:
            return 1
        return self.shape[2]

#======================================================================


"""
    Some shorthand OpenCV functionality
"""
class CV(object):
    minW = 640
    minH = 480
    maxW = 1920
    maxH = 1080
    blurSize = 5

    def __init__(self):

        self.w = CV.minW
        self.h = CV.minH
        self.depth = 3

        self.timer = datetime.datetime.now()
        if G.TEST_CV: self.test()

    def shape(self):
        return [self.h, self.w, self.depth]

    #==================================================================

    @staticmethod
    def blur(self, im, size=blurSize):
        """blur(im[, size]) -> im

        MedianBlur the image"""
        return cv2.medianBlur(im, size)

    def zeros(self, w=None, h=None, depth=3, shape=()):
        """zeros([ w[, h[, depth[, shape]]]]) -> dst

        Return np.zeros((h,w,depth), np.uint8)  # or...
        Return np.zeros(shape, np.uint8)  # if shape not empty

        w,h default to CV.w, CV.h
        """
        if len(shape) > 0:
            return np.zeros(shape, np.uint8)
        if w is None:
            w = self.w
        if h is None:
            h = self.h
        if depth == 1:
            return np.zeros((h, w), np.uint8)
        return np.zeros((h, w, depth), np.uint8)

    def resize_fixed(self, im, w=None, h=None):
        """resize_fixed(im[, w[, h]]) -> im

        Resize to exactly w*h
        w,h default to CV.w(), CV.h()
        """
        if w is None:
            w = self.w
        if h is None:
            h = self.h
        return cv2.resize(im, (w, h))

    def resize_max(self, im, maxH=None):
        """resize_max(im[, maxH]) -> im

        Resize to be no taller than maxH, maintaining aspect ratio.
        maxH default to CV.maxH
        """
        if maxH is None:
            maxH = self.maxH
        if im.shape[0] <= maxH:
            return im
        w = int(1.*im.shape[1]*maxH/im.shape[0])
        return cv2.resize(im, (w, maxH))

    #==================================================================

    def test(self):
        """Test functionality and speed.

        Don't re-use image references:
         >> im = self.zeros(1920,1080)
        ...
         >> im = self.ones(1920,1080)
        The garbage collector will gobble the (large) de-referenced memory
            while later tests are running and spoil the time.
        """
        self.maxW, self.maxH = 1280, 720
        im = self.zeros(1920, 1080)
        im2 = self.resize_max(im)
        print "reshaped:", im.shape, "->", im2.shape
        im3 = self.zeros()
        im4 = self.resize_fixed(im)
        print "reshaped:", im3.shape, "->", im4.shape
        im5 = self.zeros(shape=(1080, 1920, 3))
        self.w, self.h = 640, 480
        im6 = self.resize_max(im)
        print "reshaped:", im5.shape, "->", im6.shape
        #
        sys.stdout.flush()
        #self.repeat_timing(self.zeros, kwargs={'w':1920, 'h':1080}, show=True)
        T.repeat_timing(self.zeros, args=(1920, 1080), show=True)
        exit(0)

C = CV()

#======================================================================


"""
    Everything related to the webcam and image processing
"""
class Webcam(object):
    FPS_ON = 5  # limit FPS when processing is on
    FPS_OFF = 5
    FPS_RECORD_LEN = 20
    FPS_UPDATE_INTERVAL = 1
    AUTO_CONNECT = True
    FORCE_RESIZE = True
    RESIZE_SIZE = 480
    CAMID = 0
    JPEG_COMPRESSION = 95

    resolutions = [480, 720, 1080]

    def __init__(self):
        self.processing = False
        self.jpeg_compression = Webcam.JPEG_COMPRESSION

        self.timerCounter = 0
        self.fps = 0.0
        self.fps2 = 0.0
        self.frameTimes = deque([0]*self.FPS_RECORD_LEN)
        self.processedTimes = deque([0]*self.FPS_RECORD_LEN)
        self.fpsLimit = self.FPS_OFF

        self.auto_connect = Webcam.AUTO_CONNECT
        self.cam = None
        self.cam_id = Webcam.CAMID
        self.ret = True

        self.histBar = np.zeros((5,256),np.uint8)
        self.histBar.fill(255)

        self.inputFromFile = False

        self.frameSet = {}
        self.bmd_data = {}
        self.sim_data = {}

        self.do_process_webcam = True
        self.do_process_cv = True
        self.do_process_bmd = True
        self.do_process_sim = True

        self.f = C.zeros(depth=3)
        self.frame = C.zeros(depth=3)
        self.frameN = 1
        self.frameW = C.minW
        self.frameH = C.minH
        self.frameRaw = C.zeros(depth=3)
        self.frameRawW = C.minW
        self.frameRawH = C.minH

        self.resizeSize = Webcam.RESIZE_SIZE

        self.camThread = Thread(target=self.cam_read_loop)
        self.camThread.daemon = True
        self.cvThread = Thread(target=self.capture_loop)
        self.timerThread = Thread(target=self.timer_loop)
        self.processThread = Thread(target=self.process_loop)

        self.camDoReadEvent= Event()
        self.camDoReadEvent.clear()
        self.camDoneReadEvent= Event()
        self.camDoneReadEvent.clear()

        self.captureEvent = Event()
        self.captureEvent.clear()

        self.processEvent = Event()
        self.processEvent.clear()

        self.stopEvent = Event()
        self.stopEvent.clear()

    def start(self, **args):
        if 'auto_connect' in args:
            self.auto_connect = args['auto_connect']
        if self.auto_connect:
            self.cam = cv2.VideoCapture(self.cam_id)
        self.camThread.start()
        self.cvThread.start()
        self.timerThread.start()
        self.processThread.start()
        self.captureEvent.set()
        atexit.register(self.stop)

    def stop(self):
        self.stopEvent.set()     # end timer loop
        self.captureEvent.set()  # unblock capture loop
        self.camDoReadEvent.set()  # unblock capture loop
        self.camDoneReadEvent.set()  # unblock capture loop
        self.processEvent.set()  # unblock processing loop
        MQ.stop()  # be nice and stop Mosquitto cleanly
        if W.cvThread.is_alive():
            print "Joining CV thread"
            W.cvThread.join(3)
        if self.cam:
            W.cam.release()
        cv2.destroyAllWindows()
        print "Webcam stopped"

    def fps_update(self):
        self.frameTimes.rotate()
        self.frameTimes[0] = time()
        sum_timedelta = self.frameTimes[0] - self.frameTimes[-1]
        if sum_timedelta > 0:
            self.fps = float(self.FPS_RECORD_LEN) / sum_timedelta
        else:
            self.fps = 0.0
        #self.frameN += 1  # doesn't count unless it gets processed

    def fps2_update(self):
        self.processedTimes.rotate()
        self.processedTimes[0] = time()
        sum_timedelta = self.processedTimes[0] - self.processedTimes[-1]
        if sum_timedelta > 0:
            self.fps2 = float(self.FPS_RECORD_LEN) / sum_timedelta
        else:
            self.fps2 = 0.0
        self.frameN += 1

    """
        Separate from the main webcam thread to avoid unrecoverable lockup
        when the webcam is disconnected mid-operation (read() never returns)
    """
    def cam_read_loop(self):
        #def raise_ioerr():
        #    raise IOError("Reading from device timed out")
        #logging.warning("cam_read_loop()")
        while True:
            self.camDoReadEvent.wait()
            self.camDoReadEvent.clear()
            if self.stopEvent.isSet(): break
            #print "reading"
            self.ret, self.f = self.cam.read()
            #signal.signal(signal.SIGALRM, raise_ioerr)
            #signal.alarm(1)
            #try:
            #    self.ret, self.f = self.cam.read()
            #except IOError as e:
            #    self.ret = False
            #    self.cam = None
            #    logging.error(e.message)
            #signal.alarm(0)
            #print "read"
            self.camDoneReadEvent.set()
            if self.stopEvent.isSet(): break
        logging.warning("cam_read_loop instance exiting")


    def capture_loop(self):
        #sched = Scheduler()
        #sched.start()
        while True:
            if G.DBG_LOCK: print "cv_loop wait camLock... ",
            with G.camLock:
                if G.DBG_LOCK: print "using lock"
                if self.cam and self.do_process_webcam:
                    if self.inputFromFile:
                        self.ret = True
                        try:
                            f = cv2.imread('frame.jpg')
                        except:
                            logging.error("Could not load frame.jpg")
                            WS.stop()
                            break
                    else:
                        """
                            A graveyard of failed attempts at recovering from camera lockup lies here.
                            Tread carefully!
                        """

                        #pool = multiprocessing.Pool(1, maxtasksperchild=1)
                        #result = pool.apply_async(self.cam.read)
                        #pool.close()
                        #self.ret, f = self.cam.read()
                        #try:
                        #    self.ret, f = result.get(0.5)
                        #except multiprocessing.TimeoutError:
                        #    pool.terminate()
                        #    self.ret = False

                        #timeout_t = datetime.datetime.now() + datetime.timedelta(3)
                        #timeout_job = sched.add_date_job(self.cam_read, timeout_t)

                        self.camDoReadEvent.set()
                        self.camDoneReadEvent.wait(1)
                        if self.stopEvent.isSet(): break
                        if self.camDoneReadEvent.isSet():
                            f = self.f
                            self.camDoneReadEvent.clear()
                        else:
                            self.camDoneReadEvent.clear()
                            logging.error("OpenCV camera interface hanging - did you disconnect the webcam?")
                            #logging.warning("Unrecoverable error in camera read thread - creating a new one...")
                            #self.cam = None
                            #self.camThread = Thread(target=self.cam_read_loop)
                            #self.camThread.daemon = True
                            #self.camThread.start()
                            #logging.warning("thread.start()")
                            logging.error("Unrecoverable error - exiting")
                            #logging.error("Unrecoverable error - restarting")
                            self.cam = None
                            sleep(1.0)
                            os.system("kill %d" % os.getpid())

                            #os.execl(sys.executable, sys.executable, * sys.argv)
                            #self.camDoneReadEvent.clear()
                            #break
                            #raise KeyboardInterrupt()
                            #sys.exit(1)

                if G.DBG_LOCK: print "done with lock"
            if self.stopEvent.isSet(): break
            if (self.ret is False) and self.cam:
                self.cam = None
                logging.warning("CV2 camera disconnect")
            if self.cam and self.do_process_webcam:
                self.frameRawH, self.frameRawW = f.shape[:2]
                f = C.resize_max(f, self.resizeSize)
            if G.DBG_LOCK: print "cv_loop wait frameLock... ",
            with G.frameLock:
                if G.DBG_LOCK: print "using lock"
                if self.cam and self.do_process_webcam:
                    self.frameRaw = f
                    # This v is done in image processing now.
                    #if self.FORCE_RESIZE:
                        #self.frameRaw = C.resize_max(f, self.resizeSize)
                    self.processEvent.set()
                    """ removed the f.copy() - nobody's going to modify f,
                        and it will be discarded next frame anyway.
                        safe enough to directly reference like this"""
                    #
                    #ret, frameAsJpeg = cv2.imencode(".jpg", frameRGB)
                    #self.frameAsJpeg = frameAsJpeg
                    #cv2.imwrite('static/images/frame.jpg', f)
                    #
                    self.fps_update()
            if G.DBG_LOCK: print "wait 4 capture"
            self.captureEvent.wait()
            self.captureEvent.clear()
            if G.DBG_LOCK: print "got capture"
            if self.stopEvent.isSet(): break
        if G.DBG_LOCK: print "loop's done"


    def timer_loop(self):
        while not self.stopEvent.wait(1./self.fpsLimit):
            self.captureEvent.set()
            self.timerCounter +=1
            if G.DBG_FPS:
                if self.timerCounter % self.FPS_UPDATE_INTERVAL == 0:
                    print "fps: %.2f" % self.fps

    def process_loop(self):
        while True:
            # Wait for frame
            self.processEvent.wait()
            self.processEvent.clear()
            if self.stopEvent.isSet(): break

            if self.do_process_cv:
                self.cv_process()
            if self.stopEvent.isSet(): break

            if self.do_process_bmd:
                with G.bmdLock:
                    blocsim_msg = json.dumps(self.bmd_data)
                MQ.publish(topic=MQ.TOPIC_BLOCSIM, msg=blocsim_msg)
            if self.stopEvent.isSet(): break

            if self.do_process_sim:
                self.sim_process()
                with G.bmdLock:
                    adapter_msg = json.dumps(self.sim_data)
                MQ.publish(topic=MQ.TOPIC_ADAPTERS[0], msg=adapter_msg)
            if self.stopEvent.isSet(): break

    def cv_process(self):
        HSV_THRESH = 150
        COLOR_VAL_MAX = 255
        frameSet = {}
        """ Commonly used:
        ("bounds_x", [0,100, 0,100, True])
        ("bounds_y", [0,100, 0,100, True])
        ("black_sat", [0,255, 0,30, "min"])
        ("black_val", [0,255, 0,30, "min"])
        ("green_hue", [0,180, 50,70, True])
        ("red_hue", [0,180, 0,20, True])
        ("color_sat", [0,255, 80,255, "max"])
        ("color_val", [0,255, 80,255, "max"])
        ("hsv_thresh", [0,255, 0,80, "min"])
        ("kernel_k", [0,50, 0,10, "min"])
        ("dot_size", [0,255, 30,100, True])
        ("area_ratio", [1,100, 90,100, "max"])
        """
        with G.dbLock:
            dbcopy = G.db.db.copy()
        db = type('', (), {})()
        for k,v in dbcopy.iteritems():
            #db.k = v[2:4]
            #print k, v[0], type(v[0])
            if type(v[0]) is bool:
                setattr(db, k, v[3:5])
            elif type(v[0]) is str or type(v[0]) is unicode:
                setattr(db, k, v[3])
            else:
                raise TypeError(str(type(v[0]))+" - Unexpected type for range in keystore")

        with G.frameLock:
            frameSet[0] = self.frameRaw.copy()
        f = frameSet[0].copy()
        w = f.shape[1]
        h = f.shape[0]
        #f = C.blur(f, 5)
        #f = cv2.blur(f, (3,3))
        #f = cv2.medianBlur(f, 3)

        black=np.zeros((h,w),np.uint8)
        hist=np.zeros((180,256),np.uint8)
        roiHistRed= cv2.calcHist(black, [0,1], None, [180,256], [0,180,0,256])
        roiHistRed[:,:] = 0
        roiHistGrn = roiHistRed.copy()
        roiHistBlk = cv2.calcHist(black, [1,2], None, [256,256], [0,256,0,256])
        roiHistBlk[:,:] = 0
        # colors use sat, hue
        cv2.rectangle(roiHistRed,(db.color_sat,0),(255,db.red_hue[0]),255,-1)
        cv2.rectangle(roiHistRed,(db.color_sat,db.red_hue[1]),(255,180),255,-1)
        cv2.rectangle(roiHistGrn,(db.color_sat,db.green_hue[0]),(255,db.green_hue[1]),255,-1)
        # black uses val, sat
        cv2.rectangle(roiHistBlk,(0,0),(db.black_val,db.black_sat),255,-1)
        #cv2.rectangle(roiHist2,(140,174),(250,180),255,-1)
        #cv2.rectangle(roiHist2,(140,0),(250,3),255,-1)
        """
        print db.bounds_x, db.bounds_y, f.shape, w,h
        print int(db.bounds_y[0]/100.0*h), int(db.bounds_y[1]/100.0*h)
        print int(db.bounds_x[0]/100.0*w), int(db.bounds_x[1]/100.0*w)
        print db.bounds_x
        print db.bounds_y
        """
        fx0, fx1 = int(db.bounds_x[0]/100.0*w), int(db.bounds_x[1]/100.0*w)
        fy0, fy1 = int(db.bounds_y[0]/100.0*h), int(db.bounds_y[1]/100.0*h)
        f = f[fy0:fy1, fx0:fx1]
        w = f.shape[1]
        h = f.shape[0]
        cv2.rectangle(frameSet[0],(fx0-1,fy0-1),(fx1+1,fy1+1),(0,0,255),2)
        #cv2.rectangle(f,(0,0),(int(db.bounds_x[0]/100.0*w),h),(255,255,255),-1)
        #cv2.rectangle(f,(0,0),(w,int(db.bounds_y[0]/100.0*h)),(255,255,255),-1)
        #cv2.rectangle(f,(0,int((db.bounds_y[1])/100.0*h)),(w,h),(255,255,255),-1)
        #cv2.rectangle(f,(int((db.bounds_x[1])/100.0*w),0),(w,h),(255,255,255),-1)

        for i in [1,4,7,8,11,12,13,14,15]:
            frameSet[i] = f.copy()
        frameSet[16] = np.ones(frameSet[1].shape)*255

        # red
        hsvt = cv2.cvtColor(f,cv2.COLOR_BGR2HSV)
        hue,sat,val = cv2.split(hsvt)
        dst = cv2.calcBackProject([hsvt],[0,1],roiHistRed,[0,180,0,256],1)
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cv2.filter2D(dst,-1,disc,dst)
        vmask = val.copy()
        vmask[vmask < db.color_val] = 0
        vmask[vmask > COLOR_VAL_MAX] = 0
        vmask[vmask > 0] = 255
        dst= cv2.bitwise_and(dst, vmask)
        ret,thresh = cv2.threshold(dst,HSV_THRESH,255,0)
        #thresh = cv2.dilate(thresh,None)
        thresh = cv2.erode(thresh,None)
        kernel = cv2.getStructuringElement(cv2.MORPH_OPEN,(int(db.kernel_k),int(db.kernel_k)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_OPEN,(int(db.kernel_k*1.5),int(db.kernel_k*1.5)))
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel,thresh)
        ##cv2.morphologyEx(thresh,cv2.MORPH_CLOSE,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel2,thresh)
        frameSet[2] = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        f2 = cv2.bitwise_and(f,thresh3) #filtered image
        frameSet[3] = f2.copy()#cv2.cvtColor(f2, cv2.COLOR_GRAY2BGR)

        # get hollow contours, discard everything too small or too big
        # get their min bounding rects, ellipses, areas, centres
        # discard everything with an area ratio too low
        #### get the median size (sort a list of areas)(round down) & discard anything more than 50% off the median one

        # Find contours with cv2.RETR_CCOMP
        thresh2 = thresh.copy()
        contours,hierarchy = cv2.findContours(thresh2,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)

        # find internal contours & accept their parents
        blocks = []
        for i,cnt_inner in enumerate(contours):
            # Check if it is an external contour and its area is more than 100
            #if hierarchy[0,i,3] == -1 and cv2.contourArea(cnt)>100:
            #print "hierachy", hierarchy[0,i,3]
            area = cv2.contourArea(cnt_inner)
            parent = hierarchy[0,i,3]
            parentArea = area
            if parent != -1:
                cnt = contours[parent]
                parentArea = cv2.contourArea(cnt)
                rect = cv2.minAreaRect(cnt)
                rect = np.int0(cv2.cv.BoxPoints(rect))
                rectArea = cv2.contourArea(rect)
                (blockw,blockh),wl,hl = cv2_minRectAxes(rect)
            if (parent != -1
                and cv2.contourArea(cnt_inner)>int((w*0.03)*(h*0.03))
                and area > parentArea*0.4
                and parentArea > rectArea*0.8
                and hierarchy[0,parent,3] == -1 # ensure parent is top-level
            ):
                xx,yy,ww,hh = cv2.boundingRect(cnt)
                m = cv2.moments(cnt)
                cx,cy = m['m10']/m['m00'],m['m01']/m['m00']
                blocks += [{
                    "cnt": cnt,
                    "x": xx,
                    "y": yy,
                    "w": blockw,
                    "h": blockh,
                    "cx": cx,
                    "cy": cy,
                    "rect": rect,
                    "id": len(blocks),
                    "type": -1,
                    "dot": -1,
                    "node_connections": []
                }]
        #print "====="
        for i,block in enumerate(blocks):
            cv2.drawContours(frameSet[4], [block["rect"]], -1, (0,255,0), 2)
            #cv2.rectangle(frameSet[4],(block["x"],block["y"]),(block["x"]+block["w"],block["y"]+block["h"]),(0,255,0),2)
            cv2.circle(frameSet[4],(int(block["cx"]),int(block["cy"])),3,255,-1)
            #cv2.circle(frameSet[7],(int(dot["x"]),int(dot["y"])),int(dot["rr"]),(0,255,0),2)
            #cv2.circle(frameSet[7],(int(dot["cx"]),int(dot["cy"])),3,255,-1)

        # =============================================================
        # green
        hsvt = cv2.cvtColor(f,cv2.COLOR_BGR2HSV)
        hue,sat,val = cv2.split(hsvt)
        dst = cv2.calcBackProject([hsvt],[0,1],roiHistGrn,[0,180,0,256],1)
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cv2.filter2D(dst,-1,disc,dst)
        vmask = val.copy()
        vmask[vmask < db.color_val] = 0
        vmask[vmask > db.color_val] = 255
        dst= cv2.bitwise_and(dst, vmask)
        ret,thresh = cv2.threshold(dst,HSV_THRESH,255,0)
        thresh = cv2.erode(thresh,None)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(int(db.kernel_k),int(db.kernel_k)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(int(db.kernel_k*1.5),int(db.kernel_k*1.5)))
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel,thresh)
        #cv2.morphologyEx(thresh,cv2.MORPH_CLOSE,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel2,thresh)
        frameSet[5] = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        f2 = cv2.bitwise_and(f,thresh3) #filtered image
        frameSet[6] = f2.copy()#cv2.cvtColor(f2, cv2.COLOR_GRAY2BGR)

        # Find contours with cv2.RETR_CCOMP
        thresh2 = thresh.copy()
        contours,hierarchy = cv2.findContours(thresh2,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)

        # find internal contours & accept their parents
        dots = []
        for i,cnt in enumerate(contours):
            # Check if it is an external contour and its area is more than 100
            #if hierarchy[0,i,3] == -1 and cv2.contourArea(cnt)>100:
            #print "hierachy", hierarchy[0,i,3]
            parent = hierarchy[0,i,3]
            xx,yy,ww,hh = cv2.boundingRect(cnt)
            if (parent == -1
                and cv2.contourArea(cnt)>int((ww*0.01)*(hh*0.01))
                and ww>5 and hh>5
                and 1.0*ww/hh > (60./100) and 1.0*ww/hh < (100/60.)
            ):
                (xx,yy),rr = cv2.minEnclosingCircle(cnt)
                m = cv2.moments(cnt)
                cx,cy = m['m10']/m['m00'],m['m01']/m['m00']
                dots += [{
                    "cnt": cnt,
                    "x": xx,
                    "y": yy,
                    "r": rr,
                    "cx": cx,
                    "cy": cy,
                    "id": len(dots),
                    "type": -1,
                    "dot": -1
                }]
        """ Don't use this radius filtering code. Depending on what the camera's looking at,
            it can be too strict or too lenient by a mile & mess up detection badly.
        """
        if len(dots) > 2:
            radii = [(d["id"], d["r"]) for d in dots]
            radii.sort()
            #reference_r = radii[len(radii)/2][1]
            #print radii[0], radii[-1]
            reference_r = radii[-3][1]
            """
            usedDots = []
            for i,dot in enumerate(dots):
                if dot["r"] > reference_r*2 or dot["r"] < reference_r/4:
                    #dots.pop(i)
                    pass
                else:
                    usedDots += [dot]
            dots = usedDots
            """

        for i,dot in enumerate(dots):
            cv2.circle(frameSet[7],(int(dot["x"]),int(dot["y"])),int(dot["r"]),(0,255,0),2)
            cv2.circle(frameSet[7],(int(dot["cx"]),int(dot["cy"])),3,255,-1)

        usedBlocks = dict()
        usedDots = dict()
        #oldDotList = list(dots)
        oldDotList = dict()
        for dot in dots:
            oldDotList[dot["id"]] = dot
        #oldBlockList = list(blocks)
        oldBlockList = dict()
        for block in blocks:
            oldBlockList[block["id"]] = block

        #print len(oldDotList), len(oldBlockList)
        #print len(dots), len(blocks)

        for i,block in oldBlockList.iteritems():
            for j,dot in oldDotList.iteritems():
                #print block
                #print dot
                if cv2.pointPolygonTest(block["rect"], (dot["cx"],dot["cy"]), False) > 0:
                    add = False
                    if block["dot"] == -1:
                        add = True
                    elif oldDotList[block["dot"]]["r"] < dot["r"]:
                        add = True
                    if add:
                        usedBlocks[i] = block
                        usedDots[j] = dot
                        block["dot"] = dot["id"]
                        if (dot["cx"] < block["cx"]):
                            if (dot["cy"] < block["cy"]):
                                block["type"] = 0
                            else:
                                block["type"] = 3
                        else:
                            if (dot["cy"] < block["cy"]):
                                block["type"] = 1
                            else:
                                block["type"] = 2
                        break
        blocks = usedBlocks
        dots = usedDots
        usedBlocks = dict()
        for i,block in blocks.iteritems():
            cv2.drawContours(frameSet[8], [block["rect"]], -1, (0,255,0), 2)
            cv2.circle(frameSet[8],(int(block["cx"]),int(block["cy"])),3,255,-1)
            dot = dots[block["dot"]]
            cv2.line(frameSet[8], (int(dot["cx"]),int(dot["cy"])), (int(block["cx"]),int(block["cy"])), (255,0,0), 2)
            cv2.circle(frameSet[8],(int(dot["x"]),int(dot["y"])),int(dot["r"]),(0,255,0),2)
            cv2.circle(frameSet[8],(int(dot["cx"]),int(dot["cy"])),3,255,-1)
            dot_dist = hypot( dot["cx"]-block["cx"], dot["cy"]-block["cy"] )
            #print block["id"], dot_dist, block["w"], block["h"]
            if dot_dist < block["w"]*0.3 or dot_dist < block["h"]*0.3:
                cv2.drawContours(frameSet[8], [block["rect"]], -1, (0,0,255), 2)
                cv2.line(frameSet[8], (int(dot["cx"]),int(dot["cy"])), (int(block["cx"]),int(block["cy"])), (0,0,255), 2)
                cv2.circle(frameSet[8],(int(dot["x"]),int(dot["y"])),int(dot["r"]),(0,0,255),2)
            else:
                usedBlocks[i] = block
                cv2.putText(frameSet[8], "id: %s | type: %d" % (block["id"], block["type"]), (int(block["x"]),int(block["cy"])), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255))

        blocks = usedBlocks

        avg_block_wh = 5
        for i,block in blocks.iteritems():
            avg_block_wh += block["w"]
            avg_block_wh += block["h"]
        if len(blocks) > 0:
            avg_block_wh /= float(len(blocks)*2)

        #print "====="

        # get solid contours, discard everything too small or too big
        # get their min bounding circles, areas, centres
        # discard everything with an area ratio too low

        # for each rectangle, loop through green centroids, add inside ones to a list
        # build up a list of 'used' green dots, discard the old list
        # remove the rectangles that don't have a green dot

        # =============================================================
        # black

        hsvt = cv2.cvtColor(f,cv2.COLOR_BGR2HSV)
        hue,sat,val = cv2.split(hsvt)
        dst = cv2.calcBackProject([hsvt],[1,2],roiHistBlk,[0,256,0,256],1)
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cv2.filter2D(dst,-1,disc,dst)
        #vmask = val.copy()
        #vmask[vmask < db.color_val] = 0
        #vmask[vmask > db.color_val] = 255
        #dst= cv2.bitwise_and(dst, vmask)
        ret,thresh = cv2.threshold(dst,HSV_THRESH,255,0)
        #thresh = cv2.erode(thresh,None)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(int(db.kernel_k),int(db.kernel_k)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(int(db.kernel_k*1.5),int(db.kernel_k*1.5)))
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_CLOSE,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel2,thresh)

        for i,block in oldBlockList.iteritems():
            cv2.drawContours(thresh, [block["rect"]], -1, 0, -1)

        frameSet[9] = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        f2 = cv2.bitwise_and(f,thresh3) #filtered image
        frameSet[10] = f2.copy()#cv2.cvtColor(f2, cv2.COLOR_GRAY2BGR)

        # skip to 12
        b_disc_w = int(avg_block_wh*0.3)
        b_disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(b_disc_w, b_disc_w))
        thresh = cv2.dilate(thresh,b_disc)

        # Find contours with cv2.RETR_CCOMP
        thresh2 = thresh.copy()
        b_contours,b_hierarchy = cv2.findContours(thresh2,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)

        threshb = np.zeros(thresh.shape, np.uint8)
        for i,block in blocks.iteritems():
            cv2.drawContours(threshb, [block["rect"]], -1, 255, -1)
        threshc = cv2.bitwise_and(thresh, threshb)

        threshc_bgr = cv2.cvtColor(threshc, cv2.COLOR_GRAY2BGR)
        frameSet[12] = cv2.bitwise_or(frameSet[12], threshc_bgr)
        frameSet[12] = cv2.bitwise_or(frameSet[12], frameSet[9])

        threshc2 = threshc.copy()
        c_contours,c_hierarchy = cv2.findContours(threshc2,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)

        nodes = dict()
        for i,cnt in enumerate(c_contours):
            # Check if it is an external contour and its area is more than 100
            #if hierarchy[0,i,3] == -1 and cv2.contourArea(cnt)>100:
            #print "hierachy", hierarchy[0,i,3]
            parent = c_hierarchy[0,i,3]
            xx,yy,ww,hh = cv2.boundingRect(cnt)
            if (parent == -1
                and cv2.contourArea(cnt)>int((ww*0.01)*(hh*0.01))
                and ww>5 and hh>5
            ):
                (xx,yy),rr = cv2.minEnclosingCircle(cnt)
                m = cv2.moments(cnt)
                cx,cy = m['m10']/m['m00'],m['m01']/m['m00']
                nodes[i] = {
                             "cnt": cnt,
                             "x": xx,
                             "y": yy,
                             "r": rr,
                             "cx": cx,
                             "cy": cy,
                             "id": len(nodes),
                             "type": -1,
                             "dot": -1,
                             "node_connections": [],
                             "block_connections": []
                         }
        for i,node in nodes.iteritems():
            #cv2.drawContours(frameSet[13], [node["cnt"]], -1, (255,255,255), -1)
            for j in xrange(13,15):
                cv2.circle(frameSet[j],(int(node["cx"]),int(node["cy"])),int(node["r"]/2 + 1),255,-1)
                cv2.circle(frameSet[j],(int(node["cx"]),int(node["cy"])),3,(0,0,255),-1)

        # X generate the node set
        # X 13 - nodes

        # for each block, check for nodes
        # for each b_contour, get a list of nodes. connect them all to each other
        # draw all the connections

        for i,cnt in enumerate(b_contours):
            connected_nodes=[]
            for j,node in nodes.iteritems():
                #print block
                #print dot
                if cv2.pointPolygonTest(cnt, (node["cx"],node["cy"]), False) >= 0:
                    connected_nodes += [j]
            for k in connected_nodes:
                for l in connected_nodes:
                    if k != l:
                        nodes[k]["node_connections"] += [l]
                        for m in xrange(14,17):
                            cv2.line(frameSet[m],
                                     (int(nodes[k]["cx"]),int(nodes[k]["cy"])),
                                     (int(nodes[l]["cx"]),int(nodes[l]["cy"])),
                                     (0,0,255), 2)
            #if len(connected_nodes) > 0: print "connected %d nodes" % len(connected_nodes)

        for i,block in blocks.iteritems():
            connected_nodes=[]
            for j,node in nodes.iteritems():
                #print block
                #print dot
                if cv2.pointPolygonTest(block["rect"], (node["cx"],node["cy"]), False) >= 0:
                    connected_nodes += [j]
            for k in connected_nodes:
                nodes[k]["block_connections"] += [i]
                block["node_connections"] += [k]
                for m in xrange(14,17):
                    cv2.circle(frameSet[m],(int(block["cx"]),int(block["cy"])),3,(0,0,255),-1)
                    cv2.line(frameSet[m],
                             (int(nodes[k]["cx"]),int(nodes[k]["cy"])),
                             (int(block["cx"]),int(block["cy"])),
                             (0,0,255), 2)

        # 14,15,16 - connection lines

        for i,block in blocks.iteritems():
            for j in xrange(15,17):
                cv2.drawContours(frameSet[j], [block["rect"]], -1, (0,255,0), 2)
                #cv2.circle(frameSet[j],(int(block["cx"]),int(block["cy"])),3,255,-1)
                dot = dots[block["dot"]]
                #if j==15: cv2.line(frameSet[j], (int(dot["cx"]),int(dot["cy"])), (int(block["cx"]),int(block["cy"])), (255,0,0), 2)
                cv2.circle(frameSet[j],(int(dot["x"]),int(dot["y"])),int(dot["r"]),(0,255,0),2)
                if j==15: cv2.circle(frameSet[j],(int(dot["cx"]),int(dot["cy"])),3,255,-1)
                #dot_dist = hypot( dot["cx"]-block["cx"], dot["cy"]-block["cy"] )
                #print block["id"], dot_dist, block["w"], block["h"]
        for i,node in nodes.iteritems():
            for j in xrange(15,17):
                if j==15: cv2.circle(frameSet[j],(int(node["cx"]),int(node["cy"])),int(node["r"]/2 + 1),255,2)
                cv2.circle(frameSet[j],(int(node["cx"]),int(node["cy"])),3,(0,0,255),-1)
        for i,block in blocks.iteritems():
            cv2.putText(frameSet[15], "id: %s | type: %d" % (block["id"], block["type"]), (int(block["x"]),int(block["cy"])), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255,255,255))
            cv2.putText(frameSet[16], "id: %s | type: %d" % (block["id"], block["type"]), (int(block["x"]),int(block["cy"])), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,0))

        # X 15 - draw all
        # X 16 - draw all, no back image

        # =====================================================================
        # get solid contours, discard everything too small or too big

        # copy results to frame set
        with G.frameSetLock:
            for k,v in frameSet.iteritems():
                self.frameSet[k] = v
        #
        #
        self.fps2_update()
        with G.bmdLock:
            self.bmd_data = {
                "type": "blocsim",
                "blocks": [{
                    "id": block["id"],
                    "type": block["type"],
                    "x": int(block["cx"]),
                    "y": int(block["cy"]),
                    "w": int(block["w"]),
                    "h": int(block["h"]),
                    "node_connections": block["node_connections"]
                } for i,block in blocks.iteritems()],
                "nodes": [{
                               "id": node["id"],
                               "x": int(node["cx"]),
                               "y": int(node["cy"]),
                               "node_connections": node["node_connections"],
                               "block_connections": node["block_connections"]
                           } for i,node in nodes.iteritems()],
                "timestamp": timestamp(),
                "frame_id": self.frameN
            }

    def sim_process(self):
        with G.bmdLock:
            self.sim_data = {
                "type": "digital-logic",
                "gates": self.bmd_data["blocks"],
                "nodes": self.bmd_data["nodes"],
                "timestamp": timestamp(),
                "frame_id": self.frameN
            }

    def frame_from_id(self, frameId):
        #if G.DBG_CV: logging.debug("frame_from_id %d" % frameId)
        if frameId in self.frameSet:
            with G.frameSetLock:
                #rgb = cv2.cvtColor(W.frameSet[frameId], cv2.COLOR_BGR2RGB)
                rgb = W.frameSet[frameId].copy()
        else:
            # serve a 'blank' type screen
            with G.frameLock:
                rgb = W.frameRaw.copy()
            h, w = rgb.shape[:2]
            rgb /= 2
            cv2.line(rgb, (0+10, 0+10), (w-10, h-10), (125,255,125), 2)
            cv2.line(rgb, (w-10, 0+10), (0+10, h-10), (125,255,125), 2)
            cv2.putText(rgb, str(frameId), (0, int(h*0.5)+30), cv2.FONT_HERSHEY_SIMPLEX, 5, (255,255,255))
            #rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)

        return rgb

W = Webcam()

#======================================================================


class WebServer(object):
    DEFAULT_WEB_PORT = 8080
    #DEFAULT_RPC_PORT = 8081
    SHUTDOWN_TIMEOUT_SEC = 1
    TEMPLATE_PATH = "templates"
    STATIC_PATH = "static"
    SOCKJS_PATH = "socket"
    #CSS_PATH = "css"
    #JS_PATH = "js"
    #IMAGES_PATH = "images"
    DEBUG = True

    def __init__(self, **kwargs):
        self.web_port = WebServer.DEFAULT_WEB_PORT
        if 'web_port' in kwargs:
            self.web_port = kwargs['web_port']
        """ No longer hosting RPC server individually, it falls under the main web app.
            No more RPC port!
        """
        #self.rpc_port = WebServer.DEFAULT_RPC_PORT
        #if 'rpc_port' in kwargs:
        #    self.rpc_port = kwargs['rpc_port']
        #self.rpcThread = Thread(target=self.rpc_loop)
        self.sockJSRouter = None
        self.app = None
        self.server = None
        self.io_loop = None
        self.handlers = []
        self.shutdown_deadline = time()
        self.root = os.path.dirname(__file__)
        self.template_path = os.path.join(self.root, self.TEMPLATE_PATH)
        self.static_path = os.path.join(self.root, self.STATIC_PATH)
        # No need to specify these; worked out how to use the collective static path
        #self.css_path = os.path.join(self.root, self.CSS_PATH)
        #self.js_path = os.path.join(self.root, self.JS_PATH)
        #self.images_path = os.path.join(self.root, self.IMAGES_PATH)


    def io(self):
        if self.server is None:
            logging.warning("IO loop started before server")
        self.io_loop = tornado.ioloop.IOLoop.instance()
        logging.info("IO loop starting")

        try:
            self.io_loop.start()
        except KeyboardInterrupt:
            self.io_loop.stop()

    def start(self, **kwargs):
        #if 'rpc_port' in kwargs:
        #    self.web_port = kwargs['rpc_port']
        if 'web_port' in kwargs:
            self.web_port = kwargs['web_port']
        if len(self.handlers) == 0:
            logging.warning("no request handlers defined!")

        self.sockJSRouter = sockjs.tornado.SockJSRouter(SockJSHandler, '/'+self.SOCKJS_PATH)
        self.app = tornado.web.Application(
            self.handlers + self.sockJSRouter.urls, debug=self.DEBUG,
            static_path=self.static_path, template_path=self.template_path
        )
        self.server = tornado.httpserver.HTTPServer(self.app)
        self.server.listen(self.web_port)

        #self.rpcThread.start()

    #def rpc_loop(self):
    #    start_server(RPCHandler, port=self.rpc_port)

    def stop_loop(self):
        now = time()
        if now < self.shutdown_deadline and \
                (self.io_loop._callbacks or self.io_loop._timeouts):
            self.io_loop.add_timeout(now + 1, self.stop_loop)
        else:
            self.io_loop.stop()

    def stop(self):
        logging.info('stopping http server')
        if self.server is None:
            return
        self.server.stop()
        if self.io_loop is None:
            return
        logging.info('shutdown in %s seconds ...', self.SHUTDOWN_TIMEOUT_SEC)
        self.shutdown_deadline = time() + self.SHUTDOWN_TIMEOUT_SEC
        self.stop_loop()

WS = WebServer()

#======================================================================


class SockJSHandler(sockjs.tornado.SockJSConnection):
    """Chat connection implementation"""
    # Class level variable
    BROADCAST_PERIOD = 200  # ms
    DBG_VERBOSE = False
    sock_clients = set()
    data = dict()
    ID = 0

    def __init__(self, session):
        super(SockJSHandler, self).__init__(session)
        SockJSHandler.ID += 1
        self.id = SockJSHandler.ID
        self.state = dict()
        self.state["frame_id"] = 0
        self.state["rpc_lock"] = RLock()
        self.state["rpc_queue"] = []
        #self.state["message"] = ""
        if G.DBG_SOCKET: logging.debug("SockJSHandler %d init" % self.id)

        # Setup the endless socket broadcast
        self.broadcast_timer = sockjs.tornado.periodic.Callback(
            self.on_periodic, SockJSHandler.BROADCAST_PERIOD, WS.io_loop
        )
        self.broadcast_timer.start()

    @staticmethod
    def rpc_queue_add(name, msg, args=()):
        #print msg
        for c in SockJSHandler.sock_clients:
            with c.state["rpc_lock"]:
                c.state["rpc_queue"] += [timestamp(False)+"\t"+str(name)+"\t"+str(args)+"\t"+str(msg)]

    def on_open(self, info):
        if G.DBG_SOCKET: logging.debug("SockJSHandler %d open" % self.id)

        # Send that someone joined
        self.broadcast(self.sock_clients, "Client %d joined." % self.id)

        # Add client to the clients list
        self.sock_clients.add(self)

    def on_periodic(self):
        if G.DBG_SOCKET and SockJSHandler.DBG_VERBOSE:  # printing this is pretty spammy...
            logging.debug("SockJSHandler %d broadcast: %s" % (self.id, str(datetime.datetime.now())))

        with G.dbLock:
            db = G.db.db.copy()
        with G.bmdLock:
            bmd = W.bmd_data
            sim = W.sim_data

        """ Use frame_from_id now - more flexible """
        #with G.frameLock:
            #rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
            #rgb = C.resize_fixed(W.frameRaw,640,480)
            #rgb = W.frameRaw.copy()

        rgb = W.frame_from_id(self.state["frame_id"])
        ret, JpegData = cv2.imencode(".jpeg",rgb, (int(cv2.IMWRITE_JPEG_QUALITY), W.jpeg_compression))
        JpegData = np.ndarray.tostring(JpegData, np.uint8)

        """ This conversion method is slower than using CV's library! """
        #rgb = C.resize_fixed(rgb,320,240)
        #jpeg = Image.fromarray(rgb)
        #ioBuf = StringIO.StringIO()
        #jpeg.save(ioBuf, 'JPEG')
        #ioBuf.seek(0)
        #encoded = base64.b64encode(ioBuf.read())

        encoded = base64.b64encode(JpegData)

        with self.state["rpc_lock"]:
            rpc_queue = list(self.state["rpc_queue"])
            self.state["rpc_queue"] = []

        sendData = {
            "type": "periodic",
            "data": {
                    "client_id": self.id,
                    "time": timestamp(),
                    "webcam_connected": not(W.cam is None) and W.ret,
                    "fps_webcam": "%.2f" % W.fps,
                    "fps_processing": "%.2f" % W.fps2,
                    "frame_counter": W.frameN,
                    "frame_size": "%.2f KB (%d%% compression)" % (len(JpegData)/1024., W.jpeg_compression),
                    "frame_shape": "%d x %d (raw) / %d x %d (processed)" % (
                        W.frameRawW, W.frameRawH, rgb.shape[1], rgb.shape[0])
            },
            "rpc" : rpc_queue,
            "frame": encoded,
            "db": db,
            "bmd": bmd,
            "sim": sim,
            "errors": []
        }

        sendText = json.dumps(sendData, sort_keys=True)   # , sort_keys=True, indent=4, separators=(',', ': '))
        self.send(sendText)

    def on_message(self, message):
        if G.DBG_SOCKET: logging.debug("SockJSHandler %d rx(%d)" % (self.id, len(message)))

        # Broadcast message
        data = json.loads(message)
        broadcast = dict()

        # Overkill debugging prints
        #for key, val in data.iteritems():
        #    if key in self.state:
        #        self.state[key] = val
        #        print "SOCKJS client %d: %s = %s" % (self.id, str(key), str(val))
        #        broadcast[key] = val
        #    else:
        #        print "message %s: rejected key %s" % (message, key)
        #reply = json.dumps(broadcast)
        self.state["frame_id"] = data["frame_id"]
        try:
            res = int(data["frame_res"])
            W.resizeSize = res
        except:
            logging.error("on_message: Frame resolution is not an integer")
        try:
            res = int(data["frame_fps"])
            W.fpsLimit = res
        except:
            logging.error("on_message: FPS is not an integer")
        W.do_process_webcam = data["webcam_on"]
        W.do_process_cv= data["cv_on"]
        W.do_process_bmd= data["bmd_on"]
        W.do_process_sim= data["sim_on"]
        W.inputFromFile= data["input_from_file"]
        with G.dbLock:
            G.db.db = data["calib"]
        # Overkill debugging prints
        #print message
        #self.broadcast(self.sock_clients, "Client %d:%s says: %s" % (self.id, self.state["name"], reply))

    def on_close(self):
        if G.DBG_SOCKET: logging.debug("SockJSHandler %d close" % self.id)

        # Remove client from the clients list and broadcast leave message
        self.sock_clients.remove(self)

        self.broadcast(self.sock_clients, "Client %d left." % self.id)
        self.broadcast_timer.stop()

class IndexHandler(tornado.web.RequestHandler):
    """Regular HTTP handler to serve the page"""
    def get(self):
        self.render('index.html')

class HelloHandler(tornado.web.RequestHandler):
    def get(self, *args):
        self.write('howdy :)')

    def post(self, *args):
        self.write('howdy :)')

class ShutdownHandler(tornado.web.RequestHandler):
    """Remote shutdown server"""
    def get(self):
        self.write('Server shutdown at '+str(datetime.datetime.now()))
        WS.stop()

    def post(self):
        self.write('Server shutdown at '+str(datetime.datetime.now()))
        WS.stop()

class AjaxViewer(tornado.web.RequestHandler):
    def get(self):
        self.render('ajax.html')
        # No need to do it manually
        #self.set_status(200)
        #self.set_header('Content-type','text/html')
        #self.write("<html><head></head><body>")
        #self.write("<a href='/'>Back</a> ")
        #self.write("<a href='#' onclick='frame.src = \"frame.jpg#\" + new Date().getTime();'>Reload</a>")
        #self.write("<br/><img id='frame' src='frame.jpg'></body></html>")
        #self.finish()

class StreamViewer(tornado.web.RequestHandler):
    def get(self):
        self.render('stream.html')

class FrameHandler(tornado.web.RequestHandler):
    """Serve the last webcam frame (one-off image)"""
    def get(self):
        frameId = self.get_argument("id", default=None, strip=False)
        rgb = None
        if frameId is None:
            logging.debug("Serving raw frame")
            with G.frameLock:
                rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
        else:
            #if G.DBG_CV: logging.debug("Serving frame ID "+str(frameId))
            try:
                frameId=int(frameId)
                rgb = W.frame_from_id(frameId)
            except TypeError:
                logging.warning("Invalid frame ID: must be numeric")
                rgb = C.zeros()
        rgb = C.resize_max(rgb,W.resizeSize)
        """ Bandwidth test at unrealistically low resolution """
        #rgb = C.resize_fixed(rgb,640,480)
        #rgb = C.resize_fixed(rgb,320,240) # tiny images = sanic speeds
        #rgb = C.resize_fixed(rgb,160,120)
        jpeg = Image.fromarray(rgb)
        ioBuf = StringIO.StringIO()
        jpeg.save(ioBuf, 'JPEG')
        ioBuf.seek(0)
        self.set_header('Content-type', 'image/jpg')
        self.write(ioBuf.read())
        self.finish()

"""
    Do not use MJPEG streaming. High load on browser & difficult to manage connections.
    There are active bugs with MJPEG streaming with Webkit (Chrome and other browsers)
      as of June 2014
"""
class MJPEGHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        loop = tornado.ioloop.IOLoop.current()
        self.served_image_timestamp = time()
        my_boundary = "--myboundary--\n"
        while True:
            timestamp = time()
            rgb = W.frame_from_id(0)
            rgb = C.resize_fixed(rgb,320,240)#TODO tiny images = sanic speeds
            jpeg = Image.fromarray(rgb)
            ioBuf = StringIO.StringIO()
            jpeg.save(ioBuf, 'JPEG')
            ioBuf.seek(0)
            buf = ioBuf.read()

            if self.served_image_timestamp < timestamp:
                self.write(my_boundary)
                self.write("Content-type: image/jpeg\r\n")
                self.write("Content-length: %s\r\n\r\n" % len(buf))
                self.write(str(buf))
                self.served_image_timestamp = timestamp
                yield tornado.gen.Task(self.flush)
            else:
                yield tornado.gen.Task(loop.add_timeout, loop.time() + 0.02)


class JSONConfigHandler(tornado.web.RequestHandler):
    def get(self):
        self.write('blocsim_calib = ')
        with G.dbLock:
            dbstr = json.dumps(G.db.db)
        self.write(dbstr)
        logging.debug("Serving keystore as javascript header")
        logging.debug(dbstr)
        self.write(';')


class RPCHandler(JSONRPCHandler):

    def helloworld(self, *args):
        msg = "Hello world!"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add("helloworld", msg, args)
        return msg

    def echo(self, s):
        msg = s
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("echo", msg, [s])
        return msg

    def shutdown(self):
        WS.stop()
        msg = 'Server shutdown at '+str(datetime.datetime.now())
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("shutdown", msg)
        return msg

    def save_image(self):
        fname = "static/images/"+str(timestamp_ms())+".jpg"
        with G.frameLock:
            cv2.imwrite("static/images/frame.jpg", W.frameRaw)
            cv2.imwrite(fname, W.frameRaw)
        msg = "Image saved: "+fname
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("save_image", msg)
        return msg

    def save_state(self):
        dname = "static/saves/state_"+str(timestamp_ms())
        if not os.path.exists(dname):
            os.makedirs(dname)
        # save the keystore
        f = open(os.path.join(dname, "config.db"), "wb")
        with G.dbLock:
            json.dump(G.db.db, f)
        f.close()
        # save images - raw and processed
        with G.frameLock:
            cv2.imwrite(os.path.join(dname, "frameRaw.jpg"), W.frameRaw)
        with G.frameSetLock:
            for i in W.frameSet.keys():
                cv2.imwrite(os.path.join(dname, "frame%d.jpg" % i), W.frameSet[i])
        # save the block diagram model
        f = open(os.path.join(dname, "block-model.json"), "wb")
        with G.bmdLock:
            json.dump(W.bmd_data, f, sort_keys=True, indent=4, separators=(',', ': '))
        f.close()
        msg = "State saved: "+dname
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("save_state", msg)
        return msg

    def get_config(self):
        with G.dbLock:
            db = G.db.db.copy()
        msg = json.dumps(db)
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("get_config", msg)
        return msg

    def set_config(self, k, val):
        with G.dbLock:
            G.db.set(k, val)
        msg = "Key %s set to %s" % (str(k), str(val))
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("set_config", msg, [k, val])
        return msg

    def db_load(self):
        with G.dbLock:
            G.load_db()
        msg = "Keystore database config.db reloaded"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("db_load", msg)
        return msg

    def db_save(self):
        with G.dbLock:
            G.save_db()
        msg = "Keystore database config.db saved"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("db_save", msg)
        return msg

    def db_defaults(self):
        with G.dbLock:
            G.gen_defaults()
        msg = "Keystore database regenerated"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("db_defaults", msg)
        return msg

    def db_save_defaults(self):
        with G.dbLock:
            G.save_defaults()
        msg = "Keystore database defaults.db saved"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("db_save_defaults", msg)
        return msg

    def db_load_defaults(self):
        with G.dbLock:
            G.load_defaults()
        msg = "Keystore database defaults.db reloaded"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("db_load_defaults", msg)
        return msg

    def cycle_webcam(self):
        #self.cam = cv2.VideoCapture(self.cam_id)
        ret = False
        with G.camLock:
            startCamId = W.cam_id
            W.cam = None
            while not ret:
                W.cam_id += 1
                W.cam = cv2.VideoCapture(W.cam_id)
                ret, f = W.cam.read()
                if (W.cam_id == startCamId) and (not ret):
                    break
                if not ret:
                    W.cam_id = -1
            camId = W.cam_id
        if (W.cam is None) or (not ret):
            msg = "Failed to find a video source"
        else:
            msg = 'Switched to next available video source: '+str(camId)
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("cycle_webcam", msg)
        return msg

    def disconnect_webcam(self):
        with G.camLock:
            W.cam = None
        msg = 'Disconnected video source'
        if G.DBG_RPC: logging.info("RPC: "+msg)
        #SockJSHandler.rpc_queue_add(msg)
        SockJSHandler.rpc_queue_add("disconnect_webcam", msg)
        return msg

    #def add(self, x, y):
    #    return x+y

    #def ping(self, obj):
    #    return obj

#======================================================================

if __name__ == "__main__":

    # MQTT
    MQ.start()

    # Webcam
    W.start(auto_connect=True)

    # Webserver
    WS.handlers = [
        #(r'/js/(.*)',  tornado.web.StaticFileHandler, {'path': WS.js_path}),
        #(r'/css/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        #(r'/images/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        #(r"/down", ShutdownHandler),
        #(r'/rpc/(.*)', HelloHandler),
        (r'/config.js', JSONConfigHandler),
        (r'/stream.mjpg', MJPEGHandler),
        (r"/stream", StreamViewer),
        (r'/rpc', RPCHandler),
        (r"/ajax", AjaxViewer),
        (r"/frame.jpg", FrameHandler),
        (r"/favicon.ico", tornado.web.StaticFileHandler, {'path': WS.static_path}),
        (r"/", IndexHandler)
    ]

    logging.info("start "+str(datetime.datetime.now()))
    WS.start(port=8080)
    WS.io()

    # Webcam disconnect/reconnect Handled in the main thread
    #  CV doesn't like having the capture device threaded.
    # The action is handled by a call to the RPC server, which interrupts the IO loop here in __main__.
    #  Good enough!

    # Cleanup
    logging.info("stop "+str(datetime.datetime.now()))
    print "Cleanup"
    W.stop()
    print "Cleanup finished"

#======================================================================
"""
    Notes moved to notes.py
"""

