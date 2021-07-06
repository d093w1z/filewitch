function redirect(path) {
  window.location(path);
}
function shareViaTwitter(path) {
  window.open(path);
}

function shareViaFacebook() {
  window.open("https://facebook.com/sharer/sharer.php?u=" +
      "https://developer.mozilla.org/en/HTML/Element/Using_HTML_context_menus");
}

function incFont(path) {
  document.getElementById("fontSizing").style.fontSize = "larger";
  window.open(path);

}

function decFont() {
  document.getElementById("fontSizing").style.fontSize = "smaller";
}

function changeImage() {
  var index = Math.ceil(Math.random() * 39 + 1);
  document.images[0].src =
      "https://developer.mozilla.org/media/img/promote/promobutton_mdn" +
      index + ".png";
}

function toggle(source) {
  checkboxes = document.getElementsByClassName('file-check');
  for(var i=0, n=checkboxes.length;i<n;i++) {
    checkboxes[i].checked = source.checked;
  }
}
