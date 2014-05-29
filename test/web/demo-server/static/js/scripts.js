
blocsim_vars = {
	autoexpand_sidebar: false,
	autoexpand_tabs: true,
	rpc_path: "/rpc",
	rpc_debug: false,
	//rpc_url: "http://localhost:8080/rpc"
	player_fullscreen: false
};

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
}

function rpc_call_alert_handler(response) {
        if (response.result)
        	alert(response.result);
        else if (response.error)
            alert("RPC error: " + response.error.message);
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

blocsim_rpc.handle.shutdown = rpc_call_alert_handler;
blocsim_rpc.handle.cycle_webcam = rpc_call_console_handler;

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

$(function() {

	$( "#server-sidebar-shutdown" ).click(function() {
		rpc_call("shutdown");
	});


	$("input[name=webcam-tab-drawsize]:radio").change(function () {
		alert('drawsize');
	});

	$("input[name=webcam-sidebar-radio1]:radio").change(function () {
		alert('webcam-radio-connection');
	});

	$("input[name=cv-sidebar-radio1]:radio").change(function () {
		alert('cv-radio-connection');
	});

	$("input[name=bmd-sidebar-radio1]:radio").change(function () {
		alert('bmd-radio-connection');
	});


	$('#webcam-sidebar-eject:checkbox').change(function() {
		$( "#webcam-sidebar-cycle" ).attr("disabled", this.checked);
		alert('webcam-checked-eject');
	}); 

	$('#bmd-sidebar-mqtt:checkbox').change(function() {
		alert('bmd-checked-mqtt');
	}); 

	$('#bmd-sidebar-simulation:checkbox').change(function() {
		alert('bmd-checked-simulation');
	});


	$('#webcam-sidebar-cycle:button').click(function() {
		//alert('webcam-button-cycle');
		rpc_call("cycle_webcam");
	}); 



});

// ====================================================================

function load_server_config() {
	$.getJSON("config.json", function(json) {
		console.log("Received server state");
	    console.log(json); // this will show the info it in firebug console
	});
}

/* Background tasks */

function blocsim_event_loop() {
	//window.setInterval(blocsim_event_loop, 100);
}

$(function() {
	blocsim_event_loop();
	load_server_config();

	var conn = null;

	function connect() {
		conn = new SockJS('http://' + window.location.host + '/socket', ["websocket"]);

		conn.onopen = function() {
	    	console.log('Connected.');
	    };
	    conn.onmessage = function(e) {
          console.log(e.data);
        };
		conn.onclose = function() {
			console.log('Disconnected.');
			conn = null;
		};
	}

	function disconnect() {
		if (conn != null) {
			console.log('Disconnecting...');

			conn.close();
			conn = null;
		}
	}
	window.set

	window.setTimeout(function(){
		console.log("First connect attempt");
		connect();
	}, 100);
	
});