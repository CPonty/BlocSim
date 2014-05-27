
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

  // generate icons for buttons with shorthand classnames
  var button_icons = [
    "pause", "close", "refresh", "power", "transferthick-e-w",
    "triangle-1-s", "stop", "play", "triangle-1-w", "triangle-1-e"
  ];
  for (var i=0; i<button_icons.length; i++) {
    $( "."+button_icons[i]+"-text" ).button({
      text: true, icons: {primary: "ui-icon-"+button_icons[i]}
    });
    $( "."+button_icons[i]+"-icon" ).button({
      text: false, icons: {primary: "ui-icon-"+button_icons[i]}
    });
  }
  // remove all effects, events from 'fake' buttons  
  $('.not-button').unbind();
  /*
  $( ".not-button" ).click(function() { 
    $(this).removeClass("ui-state-active"); 
    return false; 
  });
  */
  //$( ".not-button" ).off("click");
  //$( ".not-button" ).removeClass("ui-state-active"); 
  /*
  $( ".not-button" ).focus(function () {
    $(this).removeClass("ui-state-focus");
  });
  */
  /*
  $( ".not-button" ).active(function () {
    $(this).removeClass("ui-state-active");
  });
  */
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

  /* Bind some click events */

  // for each accordion hyperlink, hide/show the matching div
  // can use -sidebar-group for the whole block, or just
  // -sidebar-table to preserve the control bar
  $( ".custom-accordion" ).click(function() {
    var name = this.id.toString().split("-")[0];
    $( "#"+name+"-sidebar-table" ).toggle();
  });
  // do/don't start collapsed
  if (false)
    $( ".sidebar-table" ).hide();

  // setup the collapse/expand button for the sidebar
  $( "#sidebar-collapsebtn" ).button().click(function() {
    var myLeft = $(this).position().left;
    var rightLeft = $(".right-wrap").position().left;
    var pixelDistance = $(".left").width()
    if (myLeft > 100) {
      // already expanded - collapse
      $(".left").toggle();
      $(this).css({left: "0"});
      $(".right-wrap").css({left: rightLeft-pixelDistance*1.1});
      $(this).button({ icons: { primary: "ui-icon-triangle-1-e" } });
    } else {
      // already collapsed - expand
      $(".left").toggle();
      $(this).css({left: "25.5em"});
      $(".right-wrap").css({left: rightLeft+pixelDistance*1.1});
      $(this).button({ icons: { primary: "ui-icon-triangle-1-w" } });
    }
  });
  // the button itself only appears when hovering on the sidebar
  
  $('#sidebar-collapsebtn').css('visibility', 'hidden');
  $('.left').mouseenter(function() {
      $('#sidebar-collapsebtn').css('visibility', 'visible');
  }).mouseleave(function() {
    if ($('#sidebar-collapsebtn').position().left > 100)
      $('#sidebar-collapsebtn').css('visibility', 'hidden');
  });
  $('#sidebar-collapsebtn').mouseenter(function() {
      $('#sidebar-collapsebtn').css('visibility', 'visible');
  }).mouseleave(function() {
    if ($(this).position().left > 100)
      $('#sidebar-collapsebtn').css('visibility', 'hidden');
  });
  
  /*
  $('#whichTabBtn').click(function(e){
    alert($("#tabs").tabs('option', 'active'));
  });
  */
  
  //$(".tab-header").appendTo('.header');

  //$("#tabs").tabs('option', 'active')
  
  /* UI events */

  // setup the dropdown menus
  $( "#cv-sidebar-resolution-dropdown" ).button().click(function() { //dropdownbtn
    if (! (typeof window.activemenu === 'undefined') ) {
      window.activemenu.hide();
      delete window.activemenu;
    } else {
      window.activemenu = $(this).parent().next().show().position({ //theOptionsListDiv
        my: "left top",
        at: "left bottom",
        of: this
      });
      $(document).one( "click", function() {
        window.activemenu.hide();
        delete window.activemenu;
      });
    }
    return false;
  }).parent().buttonset().next().hide().menu();

});