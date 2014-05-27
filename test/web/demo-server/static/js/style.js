
$(function() {

  /* AJAX: Populate panels */
  /*{
    event: "mouseover",
    beforeLoad: function( event, ui ) {
      ui.jqXHR.error(function() {
        ui.panel.html(
          "ERROR: Failed to load tab" );
      });
    }
  }
  */

  /* Apply JQuery UI styling & actions */
  $( "input[type=submit], button, .button" ).button();

  var button_icons = [
    "pause", "close", "refresh", "power", "transferthick-e-w",
    "triangle-1-s"
  ];
  for (var i=0; i<button_icons.length; i++) {
    $( "."+button_icons[i]+"-text" ).button({
      text: true, icons: {primary: "ui-icon-"+button_icons[i]}
    });
    $( "."+button_icons[i]+"-icon" ).button({
      text: false, icons: {primary: "ui-icon-"+button_icons[i]}
    });
  }
  /*
  $( ".pause-icon" ).button({text: false, icons: {primary: "ui-icon-pause"}});
  $( ".pause-text" ).button({text: true, icons: {primary: "ui-icon-pause"}});
  $( ".pause-icon" ).button({text: false, icons: {primary: "ui-icon-pause"}});
  $( ".close-text" ).button({text: true, icons: {primary: "ui-icon-closethick"}});
  $( ".close-icon" ).button({text: false, icons: {primary: "ui-icon-closethick"}});
  $( ".refresh-text" ).button({text: true, icons: {primary: "ui-icon-arrowrefresh-1-w"}});
  $( ".refresh-icon" ).button({text: false, icons: {primary: "ui-icon-arrowrefresh-1-w"}});
  $( ".power-text" ).button({text: true, icons: {primary: "ui-icon-power"}});
  */
  $( ".accordion" ).accordion({heightStyle: "content"});
  $( ".buttonset" ).buttonset();
  $( ".tabs" ).tabs({event: "mouseover"}).css("border", "none");
  $( "#server-indicator" ).css("background-color", "#00cc00");
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
  
  /* UI events */

  // operate the CV resolution select
  $( "#cv-sidebar-resolution-dropdown" ).button().click(function() { //dropdownbtn
    var menu = $(this).parent().next().show().position({ //theOptionsListDiv
      my: "left top",
      at: "left bottom",
      of: this
    });
    $( document ).one( "click", function() {
      menu.hide();
    });
    return false;
  }).parent().buttonset().next().hide().menu();

});