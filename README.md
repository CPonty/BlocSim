BlocSim
=======

UQ Engineering Thesis: [Bridging Sketch and Simulation of Block Diagram Modelled Systems (pdf)](https://dl.dropboxusercontent.com/u/39512614/github/blocsim/blocsim.pdf)

----

Installation
------------

BlocSim is a webserver running Python 2.7. It requires a webcam and a number of third-party Python packages.

<br/>

###Mosquitto

You may wish to install a [Mosquitto](http://mosquitto.org) client to view/verify the Publish/Subscribe block model output.

Regardless, you *do* have to install a [Mosquitto](http://mosquitto.org) broker.

 - Ubuntu:

        sudo apt-get install mosquitto mosquitto-clients

 - OSX:

        brew install c-ares mosquitto mosquitto-clients
        /usr/local/sbin/mosquitto -c /usr/local/etc/mosquitto/mosquitto.conf
        mkdir -p ~/Library/LaunchAgents
        ln -sfv /usr/local/opt/mosquitto/*.plist ~/Library/LaunchAgents
        launchctl load ~/Library/LaunchAgents/homebrew.mxcl.mosquitto.plist

<br/>

###Pip Package Manager

Most packages can be installed using [pip](http://pip.readthedocs.org/en/latest/quickstart.html), a python package installer.

 - `pip install <package>` - [install](http://pip.readthedocs.org/en/latest/installing.html)

<br/>

###Virtualenv

You may wish to install BlocSim's dependencies in a standalone python installation using [virtualenv](http://virtualenv.readthedocs.org/en/latest/virtualenv.html).

 - `virtualenv` - [install](http://www.pythonforbeginners.com/basics/how-to-use-python-virtualenv)

<br/>

###OSX - Homebrew

You'll need to install [Homebrew](http://brew.sh), an extremely useful general-purpose install tool.

        ruby -e "$(curl -fsSL https://raw.github.com/Homebrew/homebrew/go/install)" && brew doctor
        brew install python

Usage:

        brew install <program/library>

<br/>

###Windows - Binaries

[Pre-compiled executable installers](http://www.lfd.uci.edu/~gohlke/pythonlibs/) are available for many packages

<br/>

###Package listing

- `OpenCV 2.4` - [info](http://opencv.org/)

    - [ubuntu install script](https://help.ubuntu.com/community/OpenCV) (downloads & compiles source)
    - [osx install](http://www.jeffreythompson.org/blog/2013/08/22/update-installing-opencv-on-mac-mountain-lion/) - `brew tap homebrew/science && brew install opencv`
    - [windows install](http://www.lfd.uci.edu/~gohlke/pythonlibs/#opencv)

- `numpy` - [package](http://www.numpy.org/)

- `tornado` - [package](http://www.tornadoweb.org/en/stable/#installation)

- `sockjs-tornado`  - [package](https://github.com/joshmarshall/tornadorpc)

- `jsonrpclib` - [package](https://github.com/joshmarshall/jsonrpclib/)

- `tornadorpc` - [package](https://github.com/joshmarshall/tornadorpc)

- `Pillow` - [package](https://github.com/python-pillow/Pillow)

    - osx install:

            brew install libtiff libjpeg webp littlecms && sudo pip install Pillow

    - Ubuntu install:

            sudo apt-get install tk-dev
            sudo apt-get install tcl-dev
            sudo pip install python-tk
            sudo pip install -I Pillow

- `pickleDB` - [package](https://pythonhosted.org/pickleDB/)

- `mosquitto` - [package](http://mosquitto.org/documentation/python/)

----

Run Demo
--------

 - Start the webserver

        cd demo && ./blocsim.py

 - Open the control panel in your browser (Chrome, Firefox or Safari)

        localhost:8080

 - Subscribe to the [Mosquitto](http://mosquitto.org) messages being published

        mosquitto_sub -t "blocsim"

 - Control BlocSim remotely via [JSON-RPC](http://en.wikipedia.org/wiki/JSON-RPC) calls

        localhost:8080/rpc

        shutdown
        save_image
        save_state
        get_config
        set_config( key, value )
        db_load
        db_save
        db_defaults
        db_load_defaults
        db_save_defaults
        cycle_webcam
        disconnect_webcam

----

File Structure
--------------

 - `README.md` - you are here

 - `LICENSE` - GPL v2 license

 - `test/` - pre-demo testing files

 - `demo/` - prototype used for thesis demonstration
    - `config/` - keystore database is saved here
        - `config.db`, `defaults.db` - JSON keystores for configuration/calibration options
    - `static/` - static files available to webserver
        - `css/` - stylesheets
            - `style.css` - custom styles
            - `blocsim-style/` - customised JQuery-UI theme [built here](http://jqueryui.com/download/)
        - `images/` - saved webcam images appear here
            - `<timestamp>.jpg`
            - `frame.jpg` - copy of most recently saved image
        - `js/` - folder containing `jquery`, `jquery-ui`, `sockjs` and custom javascript
            - `style.js` - UI configuration & visuals
            - `scripts.js` - UI function & server interaction
        - `saves/` - saved states appear here in `state_<timestamp>/` style folders
            - `frame[1..16].jpg` - images showing all computer vision steps
            - `config.db` - exported config keystore (JSON)
            - `block-model.json` - exported block diagram model (JSON)
    - `templates/` - dynamic 'template' files available to webserver (html files)
        - `*.html`
    - `cvcommon.py` - opencv utility file
    - `notes.py` - note-taking, in python comment form
    - **`blocsim.py` - main executable file; majority of Python code**


