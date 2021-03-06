
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
    "triangle-1-s", "stop", "play", "triangle-1-w", "triangle-1-e",
    "radio-on", "cancel", "eject", "arrow-4-diag", "extlink", "arrow-4",
    "triangle-1-n", "arrow-2-ne-sw"
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

  /* Having to do this is silly - it's automated above
    $( ".pause-icon" ).button({text: false, icons: {primary: "ui-icon-pause"}});
    $( ".pause-text" ).button({text: true, icons: {primary: "ui-icon-pause"}});
    $( ".pause-icon" ).button({text: false, icons: {primary: "ui-icon-pause"}});
    $( ".close-text" ).button({text: true, icons: {primary: "ui-icon-closethick"}});
    $( ".close-icon" ).button({text: false, icons: {primary: "ui-icon-closethick"}});
    $( ".refresh-text" ).button({text: true, icons: {primary: "ui-icon-arrowrefresh-1-w"}});
    ...
  */
  $( ".accordion" ).accordion({heightStyle: "content"});
  $( ".buttonset" ).buttonset();
  $( ".tabs" ).tabs({event: "click"}).css("border", "none"); // mouseover for hover-tabs
  $( "#server-indicator" ).css("background-color", "#00cc00");
  $( "#webcam-indicator" ).css("background-color", "#f6931f");
  /*
  $('.tab-header.a').click(function(e) {
    e.preventDefault();
    var id = '#' + $(this).attr('href');
    $('.show').removeClass('show');
    $(id).addClass('show');
  });
  */

  // shrink all the 'skinny' buttons
  $( ".skinny-button" ).animate({width: "-=2"});

  // do/don't start accordions collapsed
  if (blocsim_vars.autoexpand_sidebar==false)
    $( ".sidebar-table" ).hide();
  if (blocsim_vars.autoexpand_tabs==false)
    $( ".tab-accordion-area" ).hide();
  $( "#keystore-tab-panel" ).hide();


  /* Bind some animation-related click events */

  // for each accordion hyperlink, hide/show the matching div
  // can use -sidebar-group for the whole block, or just
  // -sidebar-table to preserve the control bar
  $( ".sidebar-accordion" ).click(function() {
    var name = this.id.toString().split("-")[0];
    $( "#"+name+"-sidebar-table" ).toggle();
    var arrow = $(this).find(">:first-child").find(">:first-child");
    arrow.toggleClass("ui-icon-triangle-1-n ui-icon-triangle-1-s");
    console.log(arrow);
    //$(this).find(">:first-child").find(">:first-child")
      //.toggleClass("icon-triangle-1-s icon-triangle-1-n");
  });
  //element.find(">:first-child").toggleClass("redClass");
  //$("i",this).toggleClass("icon-circle-arrow-up icon-circle-arrow-down");
  $( ".tab-accordion" ).click(function() {
    var name = this.id.toString().split("-")[0];
    $( "#"+name+"-tab-panel" ).toggle();
  });

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
  
  /* UI events */

  // setup some dropdown menus
  // Disabled
  /*
  $( "#cv-sidebar-resolution-dropdown" ).button().click(function() { //dropdownbtn
    if (! (typeof window.activemenu === 'undefined') ) {
      window.activemenu.hide();
      delete window.activemenu;
    } else {
      window.activemenu = $(this).parent().next().show().position({ //theOptionsListDiv
        my: "right top",
        at: "right bottom",
        of: this
      });
      $(document).one( "click", function() {
        window.activemenu.hide();
        delete window.activemenu;
      });
    }
    return false;
  }).parent().buttonset().next().hide().menu();
  */

  // Finally - animation / effects
  $( "#callback-sidebar-text" ).bind("DOMSubtreeModified",function(){
    $( this ).effect( "highlight", {color: '#b8ec79'}, 1000); 
  });

});