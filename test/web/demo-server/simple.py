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
from tornadorpc.json import JSONRPCHandler
from tornadorpc import private, start_server
import logging
from PIL import Image
import StringIO

#======================================================================


class Globals(object):
    DBG_LOCK = False
    DBG_FPS = True
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
    FPS_ON = 30  # limit FPS when processing is on
    FPS_OFF = 30
    FPS_RECORD_LEN = 20
    FPS_UPDATE_INTERVAL = 1
    AUTO_CONNECT = True
    FORCE_RESIZE = False

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
        self.frameRaw = C.zeros(depth=3)
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
        if W.cvThread.is_alive():
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
                    self.frameRaw = f
                    if self.FORCE_RESIZE:
                        self.frameRaw = C.resize_fixed(f)
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

W = Webcam()

#======================================================================


class WebServer(object):
    DEFAULT_WEB_PORT = 8080
    #DEFAULT_RPC_PORT = 8081
    SHUTDOWN_TIMEOUT_SEC = 1
    TEMPLATE_PATH = "templates"
    STATIC_PATH = "static"
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

        logging.getLogger().setLevel(logging.DEBUG)

    def io(self):
        if self.server is None:
            logging.warning("IO loop started before server")
        self.io_loop = tornado.ioloop.IOLoop.instance()
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
        self.app = tornado.web.Application(
            self.handlers, debug=self.DEBUG,
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

class FrameViewer(tornado.web.RequestHandler):
    def get(self):
        self.render('ajax.html')
        #self.set_status(200)
        #self.set_header('Content-type','text/html')
        #self.write("<html><head></head><body>")
        #self.write("<a href='/'>Back</a> ")
        #self.write("<a href='#' onclick='frame.src = \"frame.jpg#\" + new Date().getTime();'>Reload</a>")
        #self.write("<br/><img id='frame' src='frame.jpg'></body></html>")
        #self.finish()

class FrameHandler(tornado.web.RequestHandler):
    """Serve the last webcam frame (one-off image)"""
    def get(self):
        #self.redirect("/static/images/frame.jpg")
        with G.frameLock:
            rgb = cv2.cvtColor(W.frameRaw, cv2.COLOR_BGR2RGB)
        jpeg = Image.fromarray(rgb)
        ioBuf = StringIO.StringIO()
        self.set_header('Content-type', 'image/jpg')
        jpeg.save(ioBuf, 'JPEG')
        ioBuf.seek(0)
        self.write(ioBuf.read())
        self.finish()

class RPCHandler(JSONRPCHandler):

    def helloworld(self, *args):
        return "Hello world!"

    def echo(self, s):
        return s

    def shutdown(self):
        WS.stop()
        return 'Server shutdown at '+str(datetime.datetime.now())

    def cycle_webcam(self):
        #
        #TODO disregard if camera not currently running
        #
        return 'Switching to most recently connected video source...'
"""
    def add(self, x, y):
        return x+y

    def ping(self, obj):
        return obj

"""
#======================================================================

if __name__ == "__main__":

    # Webcam
    W.start(auto_connect=True)

    # Webserver
    WS.handlers = [
        #(r'/js/(.*)',  tornado.web.StaticFileHandler, {'path': WS.js_path}),
        #(r'/css/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        #(r'/images/(.*)', tornado.web.StaticFileHandler, {'path': WS.css_path}),
        #(r"/down", ShutdownHandler),
        #(r'/rpc/(.*)', HelloHandler),
        (r'/rpc', RPCHandler),
        (r"/ajax", FrameViewer),
        (r"/frame.jpg", FrameHandler),
        (r"/favicon.ico", tornado.web.StaticFileHandler, {'path': WS.static_path}),
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
"""
