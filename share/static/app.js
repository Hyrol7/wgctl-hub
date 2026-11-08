document.addEventListener('submit',function(ev){var m=ev.target.getAttribute('data-confirm');
var b=ev.submitter;if(b&&b.getAttribute('data-confirm'))m=b.getAttribute('data-confirm');
if(m&&!window.confirm(m)){ev.preventDefault();return;}
/* double-click guard: a second submit of the same form is ignored */
var f=ev.target;if(f.dataset.busy){ev.preventDefault();return;}f.dataset.busy='1';
if(b){b.classList.add('busy');}setTimeout(function(){delete f.dataset.busy;if(b)b.classList.remove('busy');},8000);});
/* key and site names: capitals, spaces and _ are converted as you type */
document.querySelectorAll('input[data-name]').forEach(function(i){i.addEventListener('input',function(){
var p=i.selectionStart,v=i.value.toLowerCase().replace(/[\s_.]+/g,'-');if(v!==i.value){i.value=v;i.setSelectionRange(p,p);}});});
if(document.body.getAttribute('data-refresh')){var t0=Date.now(),k='vpnadmin-act';
try{var v=+sessionStorage.getItem(k);if(v&&!performance.getEntriesByType('navigation').some(function(n){return n.type!=='reload'}))t0=v;}catch(e){}
/* human actions only; scroll does not count, the browser scrolls by itself after a reload */
['pointerdown','keydown','touchstart','wheel'].forEach(function(n){addEventListener(n,function(){t0=Date.now()},{passive:true})});
setInterval(function(){try{sessionStorage.setItem(k,t0)}catch(e){}
/* after 25 minutes without human action auto-refresh stops, so an open tab does not keep the session alive forever */
if(Date.now()-t0<1500000&&!document.hidden&&!document.querySelector('input:focus,textarea:focus,details[open]'))location.reload();},15000);}
var all=document.getElementById('all-sites');if(all){var g=function(){document.querySelectorAll('.site-cb')
.forEach(function(c){c.disabled=all.checked;});};all.addEventListener('change',g);g();}
