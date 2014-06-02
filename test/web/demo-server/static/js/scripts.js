
function time_ms() {
	return (new Date()).getTime();
}

function syntaxHighlight(json) {
    if (typeof json != 'string') {
         json = JSON.stringify(json, undefined, 2);
    }
    json = json.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return json.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, function (match) {
        var cls = 'number';
        if (/^"/.test(match)) {
            if (/:$/.test(match)) {
                cls = 'key';
            } else {
                cls = 'string';
            }
        } else if (/true|false/.test(match)) {
            cls = 'boolean';
        } else if (/null/.test(match)) {
            cls = 'null';
        }
        return '<span class="' + cls + '">' + match + '</span>';
    });
}

blocsim_vars = {
	autoexpand_sidebar: false,
	autoexpand_tabs: true,
	rpc_path: "/rpc",
	rpc_debug: false,
	//rpc_url: "http://localhost:8080/rpc"
	event_period: 100,
	webcam: {mode: 1, input_from_file: false},
	cv: {mode: 1},
	bmd: {mode: 1},
	server_running: true,
	frame_reload_delay: 1, //20
	time_last_frame: time_ms(),
	debug_sockjs: false,
	max_resolution: 1
};

 var sliderNames = Object.keys(blocsim_calib);
 sliderNames.sort();

//console.log(blocsim_calib);

//blocsim_config = {};
/*
function load_server_config() {
	$.getJSON("config.json", function(json) {
		console.log("Received server state");
	    console.log(json);
	});
}
*/

var sock = null;

// ====================================================================
/* RPC */
blocsim_rpc = {
	send: {},
	handle: {},
};

function rpc_call_gen(callName, handler) {
	return function(params) {
		var request = {
			method: callName,
			params: params,
			id: 1,
			jsonrpc: "2.0"
		};
		$.post(blocsim_vars.rpc_path, JSON.stringify(request), handler, "json");
	};
}
		//var url = "http://localhost:8080/rpc";
		/*
		var request = {
			url: "/rpc",
			//url: "/rpc/"+callName,
			//url: blocsim_vars.rpc_url + callName,
			//url: blocsim_vars.rpc_url,
			data: JSON.stringify({
				jsonrpc: "2.0", 
				method: callName, 
				params: paramSet, 
				id: 1
			}),
			//success: handler,
			//success: function(response) {
			//	alert(response);
			//}//,
			dataType: "json"
		};
		$.post(request).always( //.done for success, .always for always
			function(response) {
				alert(response.toString());
			}
		);
		return request;
		*/

function rpc_call_gen_all() {
	$.each( blocsim_rpc.handle, function(callName, handler) {
		blocsim_rpc.send[callName] = rpc_call_gen(callName, handler);
	});
}

function rpc_call(name, params) {
	if(typeof(params)==='undefined') params = {};

	if (blocsim_vars.rpc_debug) console.log("rpc call");
	request = blocsim_rpc.send[name](params);
	if (blocsim_vars.rpc_debug) console.log(JSON.stringify(request));
	$( "#callback-sidebar-text" ).html("RPC WAITING: "+name);
}

function rpc_call_alert_handler(response) {
        if (response.result)
        	//alert(response.result);
        	$( "#callback-sidebar-text" ).html(response.result);
        else if (response.error)
            //alert("RPC error: " + response.error.message);
        	$( "#callback-sidebar-text" ).html("RPC error: " + response.error.message);
};

function rpc_call_console_handler(response) {
        if (response.result)
        	console.log(response.result);
        else if (response.error)
            console.log("RPC error: " + response.error.message);
};
// ====================================================================

blocsim_rpc.handle.helloworld = rpc_call_alert_handler;
blocsim_rpc.handle.echo = rpc_call_alert_handler;

blocsim_rpc.handle.shutdown = function(response) {
        rpc_call_alert_handler(response);
        if (response.result) {
		    $( "#server-indicator" ).css("background-color", "#cc0000");
		    $( "#cv-indicator" ).css("background-color", "#cc0000");
		    $( "#bmd-indicator" ).css("background-color", "#cc0000");
		    $( "#webcam-indicator" ).css("background-color", "#cc0000");
		    blocsim_vars.server_running = false;
        }
};
blocsim_rpc.handle.db_load = function(response) {
        rpc_call_alert_handler(response);
        location.reload(true);
};
blocsim_rpc.handle.db_save = function(response) {
        rpc_call_alert_handler(response);
        window.setTimeout(function(){location.reload(true);}, 1000);
};
blocsim_rpc.handle.db_defaults = function(response) {
        rpc_call_alert_handler(response);
        window.setTimeout(function(){location.reload(true);}, 1000);
};
blocsim_rpc.handle.db_save = rpc_call_alert_handler;
blocsim_rpc.handle.cycle_webcam = rpc_call_alert_handler;
blocsim_rpc.handle.disconnect_webcam = rpc_call_alert_handler;
blocsim_rpc.handle.save_image = rpc_call_alert_handler;

/*
blocsim_rpc.handle.helloworld = function(response) {
	console.log("response");
	console.log(JSON.stringify(response));
}
*/

// ====================================================================
rpc_call_gen_all(); // call after defining all the handlers
// ====================================================================

//rpc_call("helloworld");

/*
var url = "http://localhost:8080/rpc";

var request = {};
request.method = "helloworld";
request.params = {};
request.id = 1;
request.jsonrpc = "2.0";

function displaySearchResult(response) {

        if (response.result)
                alert(response.result);

        else if (response.error)
                alert("Search error: " + response.error.message);
};
console.log("ready to go!");
//console.log(JSON.stringify(request));
//$.post(url, JSON.stringify(request), displaySearchResult, "json");
*/
// make a shutdown() rpc call - nice test
// fix the ajax call for the image
	// then swap it with a base64 rpc

// ====================================================================

/*
blocsim_rpc.send.shutdown = function() {
	$.post({ //$.post
		url: "/rpc",
		data: "", //JSON.stringify(request)
		success: blocsim_rpc.handle.shutdown,
		dataType: "json"
	});
}
*/

// ====================================================================

/* UI events */
/*
function shutdown() {
  $.ajax({
    url : "/down",
    type: "POST",
    data : "",
    success: function(reply, status, _) {
      alert(reply);
    }
  });
}
*/

function frame_reload() {
    //$( "#frame" ).attr('src', 
    //	"frame.jpg?id="+$( "#webcam-tab-frame-name" )[0].selectedIndex.toString()+"#"+time_ms()
	    //);
}

function frame_loaded() {
    //if ( blocsim_vars.webcam.mode == 1 ) {
    //    window.setTimeout(frame_reload, blocsim_vars.frame_reload_delay);
    //}
}

$(function() {

    $( "#frame" ).load( function() {
    	blocsim_vars.server_running = true;
	    $( "#server-indicator" ).css("background-color", "#00cc00");
	    blocsim_vars.time_last_frame = time_ms();
    	frame_loaded();
    });
    /*
    $( "#refresh-check" ).change( function() {
        do_stream = $(this).is(":checked");
        reload();
    });
	*/
    window.setTimeout(frame_reload, 500);




	$( "#server-sidebar-shutdown" ).click(function() {
		rpc_call("shutdown");
	});


	$("input[name=webcam-tab-drawsize]:radio").change(function () {
		alert('drawsize');
	});

	$("input[name=webcam-sidebar-radio1]:radio").change(function () {
		//alert('webcam-radio-connection '+$(this).val());
		blocsim_vars.webcam.mode = parseInt($(this).val());
		frame_loaded();
	});

	$("input[name=cv-sidebar-radio1]:radio").change(function () {
		//alert('cv-radio-connection '+$(this).val());
		blocsim_vars.cv.mode = parseInt($(this).val());
	});

	$("input[name=cv-sidebar-radio2]:radio").change(function () {
		//alert('cv-radio-res '+$(this).val());
		blocsim_vars.max_resolution = parseInt($(this).val());
	});

	$("input[name=bmd-sidebar-radio1]:radio").change(function () {
		//alert('bmd-radio-connection '+$(this).val());
		blocsim_vars.bmd.mode = parseInt($(this).val());
	});

	/*
	$('#webcam-sidebar-eject:checkbox').change(function() {
		$( "#webcam-sidebar-cycle" ).attr("disabled", this.checked);
		alert('webcam-checked-eject');
	}); 
	*/

	$('#frame-save:button').click(function() {
		//alert('webcam-button-eject');
		rpc_call("save_image");
	});

	$('#db-load:button').click(function() {
		//alert('webcam-button-eject');
		rpc_call("db_load");
	});

	$('#db-save:button').click(function() {
		//alert('webcam-button-eject');
		rpc_call("db_save");
	});

	$('#db-defaults:button').click(function() {
		//alert('webcam-button-eject');
		rpc_call("db_defaults");
	});

	$('#webcam-sidebar-eject:button').click(function() {
		//alert('webcam-button-eject');
		rpc_call("disconnect_webcam");
	});

	/*
	$('#frame').click(function() {
		//alert('webcam-button-eject');
		$("#sidebar-collapsebtn").click();
	});
	*/

	$('#bmd-sidebar-mqtt:checkbox').change(function() {
		//alert('bmd-checked-mqtt');
	}); 

	$('#bmd-sidebar-simulation:checkbox').change(function() {
		//alert('bmd-checked-simulation');
	});

	$('#server-sidebar-eject:checkbox').change(function() {
		//alert('server-checked-eject');
		//.is(':checked')
		if (this.checked) {
			sockjs_disconnect();
		} else {
			sockjs_connect();
		}
	});

	$('#webcam-sidebar-cycle:button').click(function() {
		//alert('webcam-button-cycle');
		rpc_call("cycle_webcam");
	}); 



});

// ====================================================================

/* Background tasks */

function blocsim_event_loop() {

	//console.log("window.sock", window.sock);
	//console.log("sock", sock);
	//
	//console.log('blocsim_event_loop');
	if (sock == null) return;
	calib = {};
	for (var i=0; i<sliderNames.length; i++) {
		var slider = $( "#sliderrange-"+i.toString() );
		calib[sliderNames[i]] = [
			slider.slider("option", "min"),
			slider.slider("option", "max"),
			slider.slider("option", "values")[0],
			slider.slider("option", "values")[1],
			slider.slider("option","range")
		];
   	}
   	//console.log(calib);
	var msg = {
        "frame_id" : $( "#webcam-tab-frame-name" )[0].selectedIndex,
        "webcam_on" : blocsim_vars.webcam.mode < 3,
        "cv_on" : blocsim_vars.cv.mode < 3,
        "bmd_on" : blocsim_vars.bmd.mode < 3 && $('#bmd-sidebar-mqtt:checkbox')[0].checked,
        "sim_on" : blocsim_vars.bmd.mode < 3 && $('#bmd-sidebar-simulation:checkbox')[0].checked,
        "frame_res" : blocsim_vars.max_resolution, 
        "calib" : calib,
        "input_from_file": $("#webcam-tab-check-fromfile")[0].checked
    }
    msg = JSON.stringify(msg);
    sock.send(msg);
}

function blocsim_tick_loop() {
	frame_loaded();

	if ((sock == null) && (!($("#server-sidebar-eject:checkbox").is(':checked'))))  {
		sockjs_connect();
	}

	if ((sock==null) && (blocsim_vars.webcam.mode!=1 || (time_ms() - blocsim_vars.time_last_frame) > 1500)) {
		blocsim_vars.server_running = false;
		$( "#server-indicator" ).css("background-color", "#f6931f");
	}
}


// ====================================================================

/* Websockets */

sockjs_connect = function() {
	sockjs_disconnect();

	sock = new SockJS('http://' + window.location.host + '/socket');

	sock.onopen = function() {
		console.log('websocket open');
		blocsim_vars.server_running = true;
	    $( "#server-indicator" ).css("background-color", "#00cc00");
	    //$( "#cv-indicator" ).css("background-color", "#f6931f");
	    //$( "#bmd-indicator" ).css("background-color", "#f6931f");
	    $( "#cv-indicator" ).css("background-color", "#00cc00");
	    $( "#bmd-indicator" ).css("background-color", "#00cc00");
	    $( "#webcam-indicator" ).css("background-color", "#f6931f");
	    //load_server_config();
	};
	sock.onmessage = function(e) {
	    //console.log('message', e.data);
	    if (blocsim_vars.debug_sockjs) console.log('websocket rx');
	    var received = $.parseJSON(e.data);

	    if (received["type"] == "periodic") {
		    var allMinusBigData = jQuery.extend(true, {}, received);
		    allMinusBigData.db = "...";
		    allMinusBigData.frame = "...";
		    var allText = JSON.stringify(allMinusBigData, undefined, 4);
		    var dbText = JSON.stringify(received.db, undefined, 4);
		    var bmdText = JSON.stringify(received.bmd, undefined, 4);
		    var simText = JSON.stringify(received.sim, undefined, 4);
		    $( "#test-tab-sockjs-text" ).html(syntaxHighlight(allText));
		    $( "#test-tab-db-text" ).html(syntaxHighlight(dbText));
		    if (blocsim_vars.bmd.mode == 1) {
		    	if ($('#bmd-sidebar-simulation:checkbox')[0].checked) {
		    		$( "#simTextBmd-tab-panel" ).html(syntaxHighlight(bmdText));
		    		$( "#simTextLogic-tab-panel" ).html(syntaxHighlight(simText));
		    	}
		    	if ($('#bmd-sidebar-mqtt:checkbox')[0].checked) {
		    		$( "#bmdTextBmd-tab-panel" ).html(syntaxHighlight(bmdText));
		    	}
		    }
		    $( "#client-id-span" ).html(' # '+received.data.client_id);
		    if (received.data.webcam_connected) {
		    	$( "#webcam-indicator" ).css("background-color", "#00cc00");
		    } else {
		    	$( "#webcam-indicator" ).css("background-color", "#cc0000");
		    }
		    if ("frame" in received) {
		    	if ( blocsim_vars.webcam.mode == 1 && blocsim_vars.cv.mode == 1 ) {
		    		$( "#frame" ).attr('src',
		    			"data:image/jpg;base64,"+received.frame);
		    	}
			}
		}
	    
	    //console.log(html);
	    //console.log(e.data);
	    //$( "#test-tab-sockjs-text" ).html(syntaxHighlight(e.data));
	    
	    //console.log(received.db);
	};
	sock.onclose = function() {
	    if (blocsim_vars.debug_sockjs) console.log('websocket close');
	    sock = null;
	    if (blocsim_vars.server_running) {
		    $( "#server-indicator" ).css("background-color", "#f6931f");
		    $( "#cv-indicator" ).css("background-color", "#f6931f");
		    $( "#bmd-indicator" ).css("background-color", "#f6931f");
		    $( "#webcam-indicator" ).css("background-color", "#f6931f");
		    $( "#client-id-span" ).html("");
		}
	};
};

sockjs_disconnect = function() {
	if (sock != null) {
		console.log('Disconnecting...');

		sock.close();
		sock = null;
	}
}

$(function() {
	sockjs_connect();

	//var conn = null;

/*
	connect = function() {
		disconnect();

		conn = new SockJS('http://' + window.location.host + '/socket', ["websocket"]);

		conn.onopen = function() {
	    	console.log('Connected.');
	    };
	    conn.onmessage = function(e) {
          //console.log(e.data);
          //console.log('data');
        };
		conn.onclose = function() {
			console.log('Disconnected.');
			conn = null;
		};
	};

	disconnect = function() {
		if (conn != null) {
			console.log('Disconnecting...');

			conn.close();
			conn = null;
		}
	}
*/

	window.setTimeout(function() {
		window.setInterval(blocsim_event_loop, blocsim_vars.event_period);
	}, 1000);
	window.setInterval(blocsim_tick_loop, 1000);

	//window.setTimeout(function(){
	//	console.log("First connect attempt");
	//	connect();
	//}, 100);
	
});
