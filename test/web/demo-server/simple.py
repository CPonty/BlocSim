#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    BlocSim
"""
from flask import Flask, request
from threading import Thread, RLock, Event, Timer
from collections import deque
from signal import signal, SIGINT
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
from tornadorpc import private, start_server
import logging
from PIL import Image
import StringIO
import shutil
import pickledb
import mosquitto
from time import strftime
import base64

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

#======================================================================


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
        """
        if len(self.db.db) == 0:
            self.load_defaults()
        if len(self.db.db) == 0:
            self.gen_defaults()
            #self.save_defaults()
            #self.save_db()
        """

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
        #
        #TODO generate db
        #
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
            self.db.set("color_sat", ["max", 0,255, 60])
            self.db.set("color_val", ["max", 0,255, 80])
            self.db.set("connector_gap", ["min", 3,100, 20])
            self.db.set("kernel_k", ["min", 3,25, 3])
            self.db.set("dot_size", [True, 5,255, 20,100])
            self.db.set("area_ratio", ["max", 1,100, 80])

            print "regenerating db:"
            print self.db.db

        if Globals.DBG_DB: logging.info("db: gen_defaults ({} items created)".format(len(self.db.db)))

G = Globals()

#======================================================================


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
        im = cv2.medianBlur(im, size)

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


class Webcam(object):
    FPS_ON = 5  # limit FPS when processing is on
    FPS_OFF = 5
    FPS_RECORD_LEN = 20
    FPS_UPDATE_INTERVAL = 1
    AUTO_CONNECT = True
    FORCE_RESIZE = True
    RESIZE_SIZE = 480
    CAMID = 0
    JPEG_COMPRESSION = 50

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

        self.frame = C.zeros(depth=3)
        #self.frameAsJpeg = None
        self.frameN = 1
        self.frameW = C.minW
        self.frameH = C.minH
        self.frameRaw = C.zeros(depth=3)
        self.frameRawW = C.minW
        self.frameRawH = C.minH

        self.resizeSize = Webcam.RESIZE_SIZE

        self.cvThread = Thread(target=self.capture_loop)
        self.timerThread = Thread(target=self.timer_loop)
        self.processThread = Thread(target=self.process_loop)

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
        self.cvThread.start()
        self.timerThread.start()
        self.processThread.start()
        self.captureEvent.set()
        atexit.register(self.stop)

    def stop(self):
        self.stopEvent.set()     # end timer loop
        self.captureEvent.set()  # unblock capture loop
        self.processEvent.set()  # unblock processing loop
        MQ.stop()  # be nice and stop Mosquitto cleanly
        if W.cvThread.is_alive():
            W.cvThread.join(3)
        if self.cam:
            W.cam.release()
        cv2.destroyAllWindows()

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

    def capture_loop(self):
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
                        self.ret, f = self.cam.read()
            if self.stopEvent.isSet(): break
            if (self.ret is False) and self.cam:
                self.cam = None
                logging.warning("CV2 camera disconnect")
                #TODO
            if self.cam and self.do_process_webcam:
                self.frameRawH, self.frameRawW = f.shape[:2]
                f = C.resize_max(f, self.resizeSize)
            if G.DBG_LOCK: print "cv_loop wait frameLock... ",
            with G.frameLock:
                if G.DBG_LOCK: print "using lock"
                if self.cam and self.do_process_webcam:
                    self.frameRaw = f
                    #if self.FORCE_RESIZE:
                        #self.frameRaw = C.resize_max(f, self.resizeSize)
                    self.processEvent.set()
                    """ removed the .copy() - nobody's going to modify f,
                        and it will be discarded next frame anyway.
                        safe enough to directly reference like this"""
                    #
                    #ret, frameAsJpeg = cv2.imencode(".jpg", frameRGB)
                    #self.frameAsJpeg = frameAsJpeg
                    #cv2.imwrite('static/images/frame.jpg', f)
                    #
                    self.fps_update()
            self.captureEvent.wait()
            self.captureEvent.clear()
            if self.stopEvent.isSet(): break


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
        HSV_THRESH = 80
        #
        #TODO cv processing
        #
        """
        self.db.set("bounds_x", [0,100, 0,100, True])
        self.db.set("bounds_y", [0,100, 0,100, True])
        self.db.set("black_sat", [0,255, 0,30, "min"])
        self.db.set("black_val", [0,255, 0,30, "min"])
        self.db.set("green_hue", [0,180, 50,70, True])
        self.db.set("red_hue", [0,180, 0,20, True])
        self.db.set("color_sat", [0,255, 80,255, "max"])
        self.db.set("color_val", [0,255, 80,255, "max"])
        self.db.set("hsv_thresh", [0,255, 0,80, "min"])
        self.db.set("kernel_k", [0,50, 0,10, "min"])
        self.db.set("dot_size", [0,255, 30,100, True])
        self.db.set("area_ratio", [1,100, 90,100, "max"])
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

        with G.frameSetLock:
            self.frameSet[0] = self.frameRaw.copy()
        f = self.frameSet[0].copy()
        w = f.shape[1]
        h = f.shape[0]

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
        f = f[
            int(db.bounds_y[0]/100.0*h) : int(db.bounds_y[1]/100.0*h),
            int(db.bounds_x[0]/100.0*w) : int(db.bounds_x[1]/100.0*w)
        ]
        #cv2.rectangle(f,(0,0),(int(db.bounds_x[0]/100.0*w),h),(255,255,255),-1)
        #cv2.rectangle(f,(0,0),(w,int(db.bounds_y[0]/100.0*h)),(255,255,255),-1)
        #cv2.rectangle(f,(0,int((db.bounds_y[1])/100.0*h)),(w,h),(255,255,255),-1)
        #cv2.rectangle(f,(int((db.bounds_x[1])/100.0*w),0),(w,h),(255,255,255),-1)

        for i in [1,4,7,8,11,12,13,14,15,16]:
            with G.frameSetLock:
                self.frameSet[i] = f.copy()

        #bw_red =         thresh = cv2.inRange(hsv,np.array((h0,s0,v0)), np.array((h0,s1,v1)))

        #histStack = np.vstack((roiHistRed, self.histBar, roiHistGrn, self.histBar, roiHistBlk))
        #with G.frameSetLock:
        #    self.frameSet[1] = cv2.cvtColor(histStack, cv2.COLOR_GRAY2BGR)

        # red
        hsvt = cv2.cvtColor(f,cv2.COLOR_BGR2HSV)
        hue,sat,val = cv2.split(hsvt)
        dst = cv2.calcBackProject([hsvt],[0,1],roiHistRed,[0,180,0,256],1)
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cv2.filter2D(dst,-1,disc,dst)
        vmask = val.copy()
        vmask[vmask < db.color_val] = 0
        vmask[vmask > db.color_val] = 255
        dst= cv2.bitwise_and(dst, vmask)
        ret,thresh = cv2.threshold(dst,HSV_THRESH,255,0)
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(int(db.kernel_k),int(db.kernel_k)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(int(db.kernel_k*1.5),int(db.kernel_k*1.5)))
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_CLOSE,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel2,thresh)
        with G.frameSetLock:
            self.frameSet[2] = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        f2 = cv2.bitwise_and(f,thresh3) #filtered image
        with G.frameSetLock:
            self.frameSet[3] = f2.copy()#cv2.cvtColor(f2, cv2.COLOR_GRAY2BGR)

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
        kernel = cv2.getStructuringElement(cv2.MORPH_CROSS,(int(db.kernel_k),int(db.kernel_k)))
        kernel2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(int(db.kernel_k*1.5),int(db.kernel_k*1.5)))
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_CLOSE,kernel,thresh)
        cv2.morphologyEx(thresh,cv2.MORPH_OPEN,kernel2,thresh)
        with G.frameSetLock:
            self.frameSet[5] = cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR)

        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        f2 = cv2.bitwise_and(f,thresh3) #filtered image
        with G.frameSetLock:
            self.frameSet[6] = f2.copy()#cv2.cvtColor(f2, cv2.COLOR_GRAY2BGR)


        """
        hsvt = cv2.cvtColor(im,cv2.COLOR_BGR2HSV)
        hue,sat,val = cv2.split(hsvt)
        #print "hist avg",np.mean(trackingHist)
        dst = cv2.calcBackProject([hsvt],[0,1],trackingHist,[0,180,0,256],1)
        # Now convolute with circular disc
        disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
        cv2.filter2D(dst,-1,disc,dst)
        #print "dst max",np.max(dst),"hist avg",np.mean(trackingHist)
#TODO minimum brightness
        vmask = val.copy()
        vmask[vmask < HSV_V0] = 0
        vmask[vmask > 0] = 255
        dst= cv2.bitwise_and(dst, vmask)

        # threshold and binary AND
        imArray[2] = dst #grayscale distance
        ret,thresh = cv2.threshold(dst,threshVal,255,0)
        imArray[3] = thresh
        thresh3 = cv2.merge((thresh,thresh,thresh)) #threshold, 3-channel
        img4 = cv2.bitwise_and(im,thresh3) #combined image
        """

        #
        #
        self.fps2_update()
        with G.bmdLock:
            self.bmd_data = {
                "type": "blocsim",
                "blocks": [],
                "connectors": [],
                "nodes": [],
                "timestamp": timestamp(),
                "frame_id": self.frameN
            }
            #
            #TODO populate the BMD lists using cv data
            #

    def sim_process(self):
        with G.bmdLock:
            self.sim_data = {
                "type": "digital-logic",
                "gates": self.bmd_data["blocks"],
                "wiring": self.bmd_data["connectors"],
                "nodes": self.bmd_data["nodes"],
                "timestamp": timestamp(),
                "frame_id": self.frameN
            }
            #
            #TODO populate the SIM lists using BMD data
            #


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
        #self.rpc_port = WebServer.DEFAULT_RPC_PORT
        if 'web_port' in kwargs:
            self.web_port = kwargs['web_port']
        #if 'rpc_port' in kwargs:
        #    self.rpc_port = kwargs['rpc_port']
        self.sockJSRouter = None
        self.app = None
        self.server = None
        self.io_loop = None
        self.handlers = []
        self.shutdown_deadline = time()
        self.root = os.path.dirname(__file__)
        self.template_path = os.path.join(self.root, self.TEMPLATE_PATH)
        self.static_path = os.path.join(self.root, self.STATIC_PATH)
        #self.css_path = os.path.join(self.root, self.CSS_PATH)
        #self.js_path = os.path.join(self.root, self.JS_PATH)
        #self.images_path = os.path.join(self.root, self.IMAGES_PATH)

        #self.rpcThread = Thread(target=self.rpc_loop)

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
        if 'web_port' in kwargs:
            self.web_port = kwargs['web_port']
        #if 'rpc_port' in kwargs:
        #    self.web_port = kwargs['rpc_port']
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
    def rpc_queue_add(name, args=[]):
        #print msg
        for c in SockJSHandler.sock_clients:
            with c.state["rpc_lock"]:
                c.state["rpc_queue"] += [timestamp(False)+"\t"+str(name)+"\t"+str(args)]

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

        #with G.frameLock:
            #rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
            #rgb = C.resize_fixed(W.frameRaw,640,480)
            #rgb = W.frameRaw.copy()

        rgb = W.frame_from_id(self.state["frame_id"])
        ret, JpegData = cv2.imencode(".jpeg",rgb, (int(cv2.IMWRITE_JPEG_QUALITY), W.jpeg_compression))
        JpegData = np.ndarray.tostring(JpegData, np.uint8)

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
            #"frame" : "",
            "errors": []
        }

        sendText = json.dumps(sendData, sort_keys=True)   # , sort_keys=True, indent=4, separators=(',', ': '))
        self.send(sendText)

    def on_message(self, message):
        if G.DBG_SOCKET: logging.debug("SockJSHandler %d rx(%d)" % (self.id, len(message)))

        # Broadcast message
        data = json.loads(message)
        broadcast = dict()

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
        #print message
        """
        "webcam_on" : blocsim_vars.webcam.mode < 3,
        "cv_on" : blocsim_vars.cv.mode < 3,
        "bmd_on" : blocsim_vars.bmd.mode < 3,
        "sim_on" : blocsim_vars.sim.mode < 3,
        "frame_res" : blocsim_vars.max_resolution
        """

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
        #rgb = C.resize_fixed(rgb,640,480)
        #rgb = C.resize_fixed(rgb,320,240)#TODO tiny images = sanic speeds
        #rgb = C.resize_fixed(rgb,160,120)
        jpeg = Image.fromarray(rgb)
        ioBuf = StringIO.StringIO()
        jpeg.save(ioBuf, 'JPEG')
        ioBuf.seek(0)
        self.set_header('Content-type', 'image/jpg')
        self.write(ioBuf.read())
        self.finish()


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

"""
class MJPEGHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        loop = tornado.ioloop.IOLoop.current()
        self.t = time()
        i = 0
        self.set_status(200)
        self.add_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
        while True:
            i += 1
            logging.info("looping "+str(i))
            with G.frameLock:
                rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
            jpeg = Image.fromarray(rgb)
            ioBuf = StringIO.StringIO()
            jpeg.save(ioBuf, 'JPEG')
            ioBuf.seek(0)
            self.write("--jpgboundary\n")
            self.add_header("Content-type", "image/jpeg")
            self.add_header("Content-length", str(ioBuf.len))
            self.write(ioBuf.read())
            yield tornado.gen.Task(self.flush)
"""

"""
    def gen_image(self, arg, callback):
        if arg<150:
            self.arg += 1
            logging.info("gen_image "+str(arg) )
            with G.frameLock:
                rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
            jpeg = Image.fromarray(rgb)
            ioBuf = StringIO.StringIO()
            jpeg.save(ioBuf, 'JPEG')
            ioBuf.seek(0)
            self.write("--jpgboundary\n")
            self.write("Content-type: image/jpeg\r\n")
            self.write("Content-length: %s\r\n\r\n" % str(ioBuf.len))
            logging.info("bytes: "+str(arg) )
            self.write(ioBuf.read())
            #self.flush()
            response = True
        else:
            response = None
        callback(response)

    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        logging.info("starting mjpeg")
        self.arg = 1
        self.set_status(200)
        self.set_header('Content-type','multipart/x-mixed-replace; boundary=--jpgboundary')
        #self.flush()

        while True:
            response = yield tornado.gen.Task(self.gen_image, self.arg)
            response2 = yield tornado.gen.Task(self.flush)
            logging.info("flush says "+str(response2))
            self.arg += 1
            if response:
                pass
                #self.write(response)
            else:
                break
        self.finish()
"""

"""
   def get(self):
       respose = yield tornado.gen.Task(self.renderFrames)

   def renderFrames(self):
       while True:
       with G.frameLock:
           rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
       jpeg = Image.fromarray(rgb)
       ioBuf = StringIO.StringIO()
       jpeg.save(ioBuf, 'JPEG')
       ioBuf.seek(0)
       self.write()
   """

"""
        loop = tornado.ioloop.IOLoop.current()
        self.served_image_timestamp = time.time()
        my_boundary = "--myboundary--\n"
        while True:
          timestamp, img = detector.current_jpeg()
          if self.served_image_timestamp < timestamp:
            self.write(my_boundary)
            self.write("Content-type: image/jpeg\r\n")
            self.write("Content-length: %s\r\n\r\n" % len(img.data))
            self.write(str(img.data))
            self.served_image_timestamp = timestamp
            yield gen.Task(self.flush)
          else:
            yield gen.Task(loop.add_timeout, loop.time() + 0.02)
        """

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
        SockJSHandler.rpc_queue_add("helloworld", args)
        return msg

    def echo(self, s):
        msg = s
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def shutdown(self):
        WS.stop()
        msg = 'Server shutdown at '+str(datetime.datetime.now())
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def save_image(self):
        fname = "static/images/"+str(timestamp_ms())+".jpg"
        with G.frameLock:
            cv2.imwrite("static/images/frame.jpg", W.frameRaw)
            cv2.imwrite(fname, W.frameRaw)
        msg = "Image saved: "+fname
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
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
            json.dump(W.bmd_data, f)
        f.close()
        msg = "State saved: "+dname
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def get_config(self):
        with G.dbLock:
            db = G.db.db.copy()
        msg = json.dumps(db)
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def set_config(self, k, val):
        with G.dbLock:
            G.db.set(k, val)
        msg = "Key %s set to %s" % (str(k), str(val))
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def db_load(self):
        with G.dbLock:
            G.load_db()
        msg = "Keystore database config.db reloaded"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def db_save(self):
        with G.dbLock:
            G.save_db()
        msg = "Keystore database config.db saved"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def db_defaults(self):
        with G.dbLock:
            G.gen_defaults()
        msg = "Keystore database regenerated"
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def cycle_webcam(self):
        #
        #TODO disregard if camera not currently running
        #
        #self.cam = cv2.VideoCapture(self.cam_id)
        camId = 0
        ret = False
        with G.camLock:
            startCamId = W.cam_id
            W.cam = None
            while not ret:
                W.cam_id += 1
                W.cam = cv2.VideoCapture(W.cam_id)
                ret, f = W.cam.read()
                if not ret:
                    W.cam_id = -1
                if (W.cam_id == startCamId) and (not ret):
                    break
            camId = W.cam_id
        if (W.cam is None) or (not ret):
            msg = "Failed to find a video source"
        else:
            msg = 'Switched to next available video source: '+str(camId)
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg

    def disconnect_webcam(self):
        with G.camLock:
            W.cam = None
        msg = 'Disconnected video source'
        if G.DBG_RPC: logging.info("RPC: "+msg)
        SockJSHandler.rpc_queue_add(msg)
        return msg
"""
    def add(self, x, y):
        return x+y

    def ping(self, obj):
        return obj

"""
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

    # Handle webcam disconnect/reconnect in the main thread
    # - CV doesn't like having the capture device threaded
    #TODO

    # Cleanup
    logging.info("stop "+str(datetime.datetime.now()))
    print "Cleanup"
    W.stop()

#======================================================================
"""
 - get a couple of whiteboard pics
 - start github repo; move examples over to it
 - consider using binary websockets for image passing
    - make a super simple jpeg streaming demo from the chat example
 - seriously consider using redis for pub/sub
 - switch to tornado

 - html design ||  >
   stackoverflow.com/questions/12971187/what-would-be-the-unicode-character-for-big-bullet-in-the-middle-of-the-characte
   http://www.fileformat.info/info/unicode/char/27f3/index.htm
   http://www.fileformat.info/info/unicode/char/221f/index.htm
   http://www.fileformat.info/info/unicode/char/2610/index.htm
   http://www.fileformat.info/info/unicode/category/Sm/list.htm
   http://ajaxload.info
   fb gray: 228,229,233 | #e4e5e9
 - accordions
 - socketio
 - jpeg frame
 - fabric area

 - cycle cameras

 N      - cli parsing class

 - lock on shared class variables ('lock', one per class)
    - processing frame: duplicate the whole set of variables at the start of the function.
        Don't want to keep cv config locked for extended amount of time; that would force
         socket-triggered config updates to block & result in mid-frame-processing config changes (bad!)

 X      - make timing class

 - make a frame class to extend ndarray for images
    - add w,h,d
    - ...

 - make a gist for python timing

X - use better FPS counting

X    - don't limit the framerate while not processing!
X       max=20 while not processing
X       max=5 while processing

 - CV class (cv methods calib values. default constants for operations stored in class)
X       blur(size=)
X       size_set(w=, h=)
X       size_limit(maxHeight=)
X    get_aspect(im)
    (brightness, contrast etc)

 - add webcam frame grab check, startup check, 'select next' function. test.
X - add fps timer; make sure it actually works.
X       - /down: shutdown server
 - /index: list of 'pages' (with hyperlinks) and their description
 - /frame: current webcam frame
 - /stream: raw frame streamed with socketio to a jpeg

"""

"""
CV:
    - distance between contour and line
        - get region of connector contour/approxpoly
            ? plus x pixels of dilation
        - work out tangent for each bbox edge
        - get a quadrilateral bbox around each block edge
            - take the corner, move corners in/out x/y pixels away from centroid
        - check which bboxes the connector contour intersects
            - use image masks (draw the boxes as fill) and cv2.AND; detect contours again;
                work out which bboxes the centroids fall in using pointPolygonTest
        - work out the intersection point
            - midpoint of earlier contour
        ( try performance using approxpolydp, the original contour, the dilated contour mask )

Server:
    - stateless clients
UI:
    - click updates UI, sends instruction to server
    - server processes it, updates all clients (broadcast)
      ============
    - image displayed in scrollable div; buttons for small/large 'player'


CV General:
    - white-out coloured regions when detecting black/white
    - red border, green topleft dot, black corners, black outside lines
    - detect colour using backprojection
    - calibration 1: pure fabric.js hue/sat drag box and 2d visualiser for green & red; min. value drag bar
    - calibration 2: hold up sheet with two boxes of solid green & red; autodetect; histogram; bbox
    - use trigonometry to work out where along the border of a block a line has intersected
        (3 points are intersection blob moment and the two corners)

Fiducials:
    - print at CEIT (get setup)
    - can potentially draw them - should still work

Nice-to-have:
    - distortion correction
        - red dots on corners, autodetect largest 4 red circles above threshold
        - use rectangle to auto-adjust
    - javascript: track bandwidth
        - timer displays I/O for each socket in KB/sec (simple sum of message sizes read every x ms)
"""
"""
Short term:
    - json config file
        use it for python too - very valuable, easy to configure both
    - frame supplied from file
        - UI: use file browser object - only care about the file name, folder is fixed
        - cli: first argument
    - server shutdown
        - RPC shutdown
    - set up pub/sub ( blocsim and blocsim/adapters/digital-logic )
        add 'test with:' strings to the web ui
    - fast PoC of fabric.js
    - fast PoC (on streaming page): base64 image via socket
    - fast PoC (on webcam panel): resizable image
    - dynamic accordions (walk up to the parent div, just like dropdown menus)
    - delete a heap of comments to make it more readable
    - socket basics
        - server counts as connected again when sockets reconnect
    - dynamic dropdown menu formatting

    storing config

    sync between ui and server
        N- when the server goes down, lock the page, otherwise ui elements will go out of sync
        - when server is down, poll the server
        - if it responds, refresh the page
        - ui elements updated by server: RPC adds key-value pairs to a 'server update' keystore

    config save button
        - RPC to save (server's) json object to file
    config load on start
        - server loads it from saved file. if that doesn't exist, it copies it there from the defaults folder
        - users ask for it when the page loads - add a special handler for it, serve the current state

    frame rate
        - capture thread always runs at max FPS, but does no work
        - timer thread sets the FPS for the processing thread
        - in the processing thread we do the CV (if needed) and pub/sub services
        - broadcast the currently selected frame and update keystore to evvveryone!

    serving frames
        ! go async with tornado - http://papercruncher.com/2013/01/15/truly-async-with-tornado/
            - maybe only for big calls
        ! replace the weird jpeg socket streaming with /stream/<raw|thumb|cv>.mjpeg[?clientid=<id>]
            - now everyone can have images (multiple?) easily, in a way controlled by the server
            - clientid maps to the cv sourceid and max resolution; tells it when to pause
            - on socket disconnect, set a 'stop' class flag (detect it in the serving loop)
            - on clientid's websocket disconnect, set the 'stop' flag (actually, poll the value in the loop)
            - in browser: display in iframe; iframe should start as .jpg and reload as .mjpeg on client connect
            - sync access to resources with an event and/or RLock
            - only send the image if the corresponding clientid is set to play
                - store the event & lock against the websocket
    actually is MLG ^^^
    do it first, do it now :D

    now, all the syncing stuff.
    python
        - store in RAM - pickleDB *2
            one is the server state, loaded from file and stored to file
            one is the 'inbound from clients' queue - cleared every time a socket message is sent (needs RLock)
        - listen for changes - pypubsub
            take any special actions needed (including value validation), store by default
        - use - load all as a python object at the start of the processing loop; everything else done with callback
    javascript
        - store in global json object *4
            one is the client state, loaded from server file then updated by UI and server
                this only cover stuff synced with the server
            one is the server outbound set
                both plain json objects, no callbacks

    ?        // one is the 'inbound from server' queue
    ?        // one is the 'inbound from self' queue
            when UI updates, handle the value locally, store it locally and add it to the server outbound queue
            when server updates, handle the value locally, store it locally, update the UI

            need a value-callbacks set

             - get the list of variables to track (aka, get the keys from the server)
             - define generic setters and getters by running .each -> defineProperty on the keys
                setup empty functions: this.property.validate(), this.property.ui()
                getters: just get the _value from itself
                setters:    _value = incomingValue
                            _value = this.property.validate(_value)
                            if this._send_server: (update the server outbound queue's key, _value)
                            if this._update_ui: this.property.ui(_value)
                            client_state.value = _value
                UI: set_fromui() - add to server queue if not matching global
                SRV: set_fromserver() - change ui if not matching global
                [ combine into one 'setter' object ]

                where the value needs validating (UI), define from_ui.<value>.validate
                where widgets needs updating(SRV), define from_srv.<value>.ui

                now we can create a function for value validation and any extra work in <set>.<value>.ui()
                ui.fpslimit.validate = function(val) {}
                ----------------------------------------------------

                simpler (but shitter), avoids loop of ui update -> send -> client receive -> ui update -> ...
                    server outbound queue
                        plain set {}
                    received queue processing
                        set global values

                        call ui update functions for each (stored in their own set {})
                    send-to-server loop
                        scrape all ui values (functions stored in their own set {})
                        compare to global values
                        if changed, set global & add to server outbound queue


                    local client state:
                        - load defaults

                ----------------------------------------------------
                either way, be careful of loops, don't let server updates to UI trigger server sending
             -

            after startup, ask for the server state (again)
             - upon getting it we automatically loop through and update UI

       // - listen for changes

    split javascript into more files

    ? keep rpc's - shutdown, switch camera, 'off' and 'pause' buttons on sidebar
      implement camera threading structure as above
      implement switch camera
      run basically everything through the sockets
        don't send socket data if socketID is null - set null on disconnect
    ? dialog
      click events for panel scaling
      make fabric.js widgets (x2)
      implement player resizing
        split expand and contract events for sidebar resize, need to call it when we minimise/maximise
        iframe dynamically resizes to fit (on window resize, on load, and when the checkbox changes)

      write gen_defaults
        store:
            #shape.{x1,x2,y1,y2} (%)
            [green,red].{h_min,h_max,s_min,s_max,v_min}
            [black].{s_max,v_max}
            [white].{s_max,v_min}
            hsv_thresh
            kernel_k
            min_object_size
            max_image_size

      make their UI elements

        implement such that all missing values get replaced -> fill_missing_defaults
      implement open_db such that, if it opened it with sync set to false, but db says sync is true... set sync to true
      UI: <fake>Storage:|<radio>Volatile|<radio>Persistent|<rpc-btn>Save Now|<rpc-btn>Save to Defaults
      add a 'persistent storage' checkbox in UI; on change, runs RPC



      split int two: control and config
        config is cv
        control is anything that has to sync between clients, but not get stored.
        it gets emptied every time we push data to client
            [webcam,cv,bmd,mqtt,simulation].{set_halted}
            [webcam].{disconnect}
            // paused processing, webcam state, webcam size, server start time, fps, camera res, #frames since
        everything we need to tell clients in one-directional broadcast is simply cobbled together in a batch
      //  defaults in a defaults folder with same name
      //  separate 'persistent' checkboxes

      cleanup sidebar, rename socket tx to Streaming Tx

      next
        N   implement publish/subscribe (just install and test)
            N   not actually that useful as services are spread across threads & it's really thread-safe
        camera auto-reconnect
        image streaming (incl. thumbnail) with get-values (which frame ID)
        .json settings web request & the initial loading of them in the client
        more buttons & associated RPCs implemented
        X       super basic sockjs with periodic 'hello world' broadcast
        add basic features (connect/disconnect events, handler structure on each end)
        add client & server side handling to process and display every-time periodic data
            split FPS: apparent vs actual
        fabric.js areas incl. thumbnail load on a timer (always the same one)
        slider placement (use tables and fixed values)
        slider code (UI and values)
        processing thread on server (incl. placeholder broadcast data & some images)
        implement initial db values function (fills them in if not there)
        opencv color tracking (just the visual frames)

        start implementing server/client sync

        be careful with server's internal pubsub, the server and e.g. opencv loop are on different threads
            - add an internal RLock to the global keystore (the config one and the temporary inbound queue)
            - inbound queue gets processed in opencv thread
"""
