
print "Notes.py"

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
