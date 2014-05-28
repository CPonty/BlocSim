
blocsim_vars = {
	autoexpand_sidebar: false,
	autoexpand_tabs: true,
	rpc_path: "/rpc",
	rpc_debug: true
	//rpc_url: "http://localhost:8080/rpc"
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
	console.log("rpc call");
	request = blocsim_rpc.send[name](params);
	console.log(JSON.stringify(request));
}

function rpc_call_test_handler(response) {
        if (response.result)
        	alert(response.result);
        else if (response.error)
            alert("Search error: " + response.error.message);
};
// ====================================================================

blocsim_rpc.handle.helloworld = function(response) {
	console.log("response");
	console.log(JSON.stringify(response));
}

// ====================================================================
rpc_call_gen_all(); // call after defining all the handlers
// ====================================================================

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
rpc_call("helloworld", {});
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



/* Background tasks */

function blocsim_event_loop() {
	//window.setInterval(blocsim_event_loop, 100);
}

console.log(window.blocsim);

$(function() {
	blocsim_event_loop();
});