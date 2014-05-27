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
import tornado.httpserver
import tornado.ioloop
import tornado.web
import sockjs.tornado
import logging
from PIL import Image
import StringIO

#======================================================================


class Globals(object):
    DBG_LOCK = False
    DBG_FPS = False
    TEST_CV = False

    def __init__(self):
        self.camLock = RLock()
        self.frameLock = RLock()

G = Globals()

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
    FPS_ON = 5
    FPS_OFF = 15
    FPS_RECORD_LEN = 20
    FPS_UPDATE_INTERVAL = 1
    AUTO_CONNECT = True

    resolutions = [480, 720, 1080]

    def __init__(self):
        self.processing = False

        self.timerCounter = 0
        self.fps = 0.0
        self.frameTimes = deque([0]*self.FPS_RECORD_LEN)
        self.fpsLimit = self.FPS_OFF

        self.auto_connect = Webcam.AUTO_CONNECT
        self.cam = None

        self.frame = C.zeros(depth=3)
        #self.frameAsJpeg = None
        self.frameN = 1
        self.frameW = C.minW
        self.frameH = C.minH
        self.frameRawW = C.minW
        self.frameRawH = C.minH

        self.cvThread = Thread(target=self.capture_loop)
        self.timerThread = Thread(target=self.timer_loop)

        self.captureEvent = Event()
        self.captureEvent.clear()

        self.stopEvent = Event()
        self.stopEvent.clear()

    def start(self, **args):
        if 'auto_connect' in args:
            self.auto_connect = args['auto_connect']
        if self.auto_connect:
            self.cam = cv2.VideoCapture(0)
        self.cvThread.start()
        self.timerThread.start()
        self.captureEvent.set()
        atexit.register(self.stop)

    def stop(self):
        self.stopEvent.set()     # end timer loop
        self.captureEvent.set()  # unblock capture loop
        W.cvThread.join()
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
        self.frameN += 1

    def capture_loop(self):
        while True:
            if G.DBG_LOCK: print "cv_loop wait camLock... ",
            with G.camLock:
                if G.DBG_LOCK: print "using lock"
                if self.cam:
                    ret, f = self.cam.read()
                    self.frameRawH, self.frameRawW = f.shape[:2]
            if self.stopEvent.isSet(): break
            if G.DBG_LOCK: print "cv_loop wait frameLock... ",
            with G.frameLock:
                if G.DBG_LOCK: print "using lock"
                if self.cam:
                    self.frameRaw = f.copy()
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

W = Webcam()

#======================================================================


class WebServer(object):
    DEFAULT_PORT = 8080
    SHUTDOWN_TIMEOUT_SEC = 1
    TEMPLATE_PATH = "templates"
    STATIC_PATH = "static"
    CSS_PATH = "css"
    JS_PATH = "js"
    IMAGES_PATH = "images"
    DEBUG = True

    def __init__(self, **args):
        self.port = WebServer.DEFAULT_PORT
        if 'port' in args:
            self.port = args['port']
        self.app = None
        self.server = None
        self.io_loop = None
        self.handlers = []
        self.shutdown_deadline = time()
        self.root = os.path.dirname(__file__)
        self.template_path = os.path.join(self.root, self.TEMPLATE_PATH)
        self.static_path = os.path.join(self.root, self.STATIC_PATH)
        self.css_path = os.path.join(self.root, self.CSS_PATH)
        self.js_path = os.path.join(self.root, self.JS_PATH)
        self.images_path = os.path.join(self.root, self.IMAGES_PATH)

        logging.getLogger().setLevel(logging.DEBUG)

    def io(self):
        if self.server is None:
            logging.warning("IO loop started before server")
        self.io_loop = tornado.ioloop.IOLoop.instance()
        try:
            self.io_loop.start()
        except KeyboardInterrupt:
            self.io_loop.stop()

    def start(self, **args):
        if 'port' in args:
            self.port = args['port']
        if len(self.handlers)==0:
            logging.warning("no request handlers defined!")
        self.app = tornado.web.Application(
            self.handlers, static_path=self.static_path,
            template_path=self.template_path, debug=self.DEBUG
        )
        self.server = tornado.httpserver.HTTPServer(self.app)
        self.server.listen(self.port)

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


class IndexHandler(tornado.web.RequestHandler):
    """Regular HTTP handler to serve the page"""
    def get(self):
        self.render('index.html')

class ShutdownHandler(tornado.web.RequestHandler):
    """Remote shutdown server"""
    def get(self):
        self.write('Server shutdown at '+str(datetime.datetime.now()))
        WS.stop()

    def post(self):
        self.write('Server shutdown at '+str(datetime.datetime.now()))
        WS.stop()

class FrameHandler(tornado.web.RequestHandler):
    """Serve the last webcam frame (one-off image)"""
    def get(self):
        #self.redirect("/static/images/frame.jpg")
        self.set_header('Content-type', 'image/jpg')
        with G.frameLock:
            rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
            jpeg = Image.fromarray(rgb)
            ioBuf = StringIO.StringIO()
            jpeg.save(ioBuf, 'JPEG')
            ioBuf.seek(0)
            self.write(ioBuf.read())
        self.finish()

#======================================================================

if __name__ == "__main__":

    # Webcam
    W.start(auto_connect=True)

    # Webserver
    WS.handlers = [
        #(r'/js/(.*)',  tornado.web.StaticFileHandler, {'path': WS.js_path}),
        #(r'/css/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        #(r'/images/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        (r"/down", ShutdownHandler),
        (r"/frame", FrameHandler),
        (r"/", IndexHandler)
    ]

    logging.info("start "+str(datetime.datetime.now()))
    WS.start(port=8080)
    WS.io()
    logging.info("stop "+str(datetime.datetime.now()))

    # Cleanup
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
