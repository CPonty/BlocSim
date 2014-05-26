
$(function() {

  /* AJAX: Populate panels */
  
  
  $( ".tabs" ).tabs({
    event: "mouseover",
    beforeLoad: function( event, ui ) {
      ui.jqXHR.error(function() {
        ui.panel.html(
          "ERROR: Failed to load tab" );
      });
    }
  }).css("border", "none");


  /* Apply JQuery UI styling & actions */
  $( "input[type=submit], button, .button" ).button();
  $(".refresh-text").button({text: true, icons: {primary: "ui-icon-arrowrefresh-1-w"}});
  $(".refresh-icon").button({text: false, icons: {primary: "ui-icon-arrowrefresh-1-w"}});
  $(".power-text").button({text: true, icons: {primary: "ui-icon-power"}});
  $( ".accordion" ).accordion({heightStyle: "content"});
  $( ".buttonset" ).buttonset();
  //console.log($(".tabs a"))
  //$(".tabs").css('height', $(".tabs").height());
  /*
  $('.tab-header.a').click(function(e) {
    e.preventDefault();
    var id = '#' + $(this).attr('href');
    $('.show').removeClass('show');
    $(id).addClass('show');
  });
  */

  /*
  $('#whichTabBtn').click(function(e){
    alert($("#tabs").tabs('option', 'active'));
  });
  */
  
  //$(".tab-header").appendTo('.header');

  //$("#tabs").tabs('option', 'active')
  

});