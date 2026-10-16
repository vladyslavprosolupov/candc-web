const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const source = fs.readFileSync('engine/web/shell/pointer-lock.js', 'utf8');
function setup(includeFullscreen = false) {
  function target(extra = {}) {
    const handlers = {};
    return Object.assign({style:{}, hidden:false, attributes:{},
      addEventListener(k,f){(handlers[k] ||= []).push(f);},
      emit(k,e={}){for(const f of handlers[k] || []) f(e);},
      setAttribute(k,v){this.attributes[k]=v;},
      getAttribute(k){return k==='src' ? this.src : this.attributes[k];},
      removeAttribute(k){delete this[k];delete this.attributes[k];}}, extra);
  }
  const canvas = target({getBoundingClientRect:()=>({left:10,top:20,width:1600,height:900})});
  const overlay = target({style:{display:''}}), status = target(), button = target();
  let cursor, observer, requests=0, exits=0;
  const document = target({fullscreenElement:null,pointerLockElement:null,
    body:{appendChild(e){cursor=e;}},createElement:()=>target(),
    getElementById:id=>({'canvas':canvas,'gx-overlay':overlay,'gx-fullscreen-status':status,'gx-fullscreen':button}[id]),
    exitPointerLock(){exits++;this.pointerLockElement=null;this.emit('pointerlockchange');}});
  canvas.requestPointerLock=async()=>{requests++;document.pointerLockElement=canvas;document.emit('pointerlockchange');};
  const window=target();
  vm.runInNewContext(source,{window,document,console,MutationObserver:class{constructor(f){observer=f;}observe(){}}});
  if (includeFullscreen) withFullscreen({window,document,canvas,requests:()=>requests});
  window.emit('DOMContentLoaded');
  const api=window.gxPointerLock;
  const ready=()=>{overlay.style.display='none';api.frame(400,300,800,600);};
  const event=(extra={})=>Object.assign({target:canvas,button:0,prevented:false,stopped:false,
    preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}},extra);
  return {window,document,canvas,overlay,status,button,api,ready,event,observer,cursor,
    requests:()=>requests,exits:()=>exits};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('launcher never captures the mouse, even when fullscreen',async()=>{
  const s=setup();s.document.fullscreenElement={};
  await s.api.request(true);s.window.emit('pointerdown',s.event());
  assert.equal(s.requests(),0);assert.equal(s.cursor.hidden,true);
});
test('windowed play never captures the mouse, including stale fullscreen-entry requests',async()=>{
  const s=setup();s.ready();await s.api.request();assert.equal(s.requests(),0);
  await s.api.request(true);assert.equal(s.requests(),0);assert.equal(s.document.pointerLockElement,null);
});
test('activation click and release are consumed; subsequent clicks reach SDL',async()=>{
  const s=setup();s.ready();s.document.fullscreenElement={};
  const down=s.event(),up=s.event();s.window.emit('pointerdown',down);await settle();s.window.emit('pointerup',up);
  assert.ok(down.prevented&&down.stopped&&up.stopped);
  const next=s.event();s.window.emit('pointerdown',next);assert.equal(next.stopped,false);assert.equal(s.requests(),1);
});
test('cursor uses original SDL image/hotspot and matches scaled hit-test coordinates',async()=>{
  const s=setup();s.ready();s.document.fullscreenElement={};
  s.canvas.style.cursor='url("data:image/png;base64,AA==") 5 7, auto';s.observer();
  await s.api.request();s.api.frame(799,0,800,600);
  assert.equal(s.cursor.hidden,false);assert.equal(s.cursor.src,'data:image/png;base64,AA==');
  assert.equal(s.cursor.style.transform,'translate(1603px, 13px)');
  assert.equal(s.button.style.visibility,'hidden');
  s.canvas.style.cursor='url(data:image/png;base64,BB==), auto';s.observer();
  assert.equal(s.cursor.src,'data:image/png;base64,BB==');assert.equal(s.cursor.style.transform,'translate(1608px, 20px)');
});
test('Esc release restores controls and requires a fresh click, without automatic relock',async()=>{
  const s=setup();s.ready();s.document.fullscreenElement={};await s.api.request();
  s.document.exitPointerLock();
  assert.equal(s.cursor.hidden,true);assert.equal(s.button.style.visibility,'');assert.match(s.status.textContent,/Щёлкните/);
  s.api.frame(400,300,800,600);assert.equal(s.requests(),1);
  s.window.emit('pointerdown',s.event());await settle();assert.equal(s.requests(),2);
});
test('fullscreen exit, blur and hidden document release mouse',async()=>{
  for(const trigger of ['fullscreenchange','blur','visibilitychange']){
    const s=setup();s.ready();s.document.fullscreenElement={};await s.api.request();
    if(trigger==='fullscreenchange')s.document.fullscreenElement=null;
    if(trigger==='visibilitychange')s.document.hidden=true;
    (trigger==='blur'?s.window:s.document).emit(trigger);
    assert.equal(s.exits(),1);assert.equal(s.cursor.hidden,true);
  }
});
test('denied permission is visible and can be retried',async()=>{
  const s=setup();s.ready();s.document.fullscreenElement={};
  const accept=s.canvas.requestPointerLock;s.canvas.requestPointerLock=async()=>{throw Error('Denied');};
  await s.api.request();assert.match(s.status.textContent,/Разрешите/);assert.equal(s.cursor.hidden,true);
  s.canvas.requestPointerLock=accept;await s.api.request();assert.equal(s.requests(),1);
});
test('original three-pixel edge scrolling is unchanged',()=>{
  const cpp=fs.readFileSync('engine/GeneralsMD/Code/GameEngine/Source/GameClient/MessageStream/LookAtXlat.cpp','utf8');
  assert.match(cpp,/static const Int edgeScrollSize = 3;/);
});

// Exercise both controllers together: fullscreen owns its gesture; mouse capture
// gets the next deliberate canvas gesture after fullscreen has actually opened.
function withFullscreen(s) {
  s.canvas.focus=()=>{};
  s.document.documentElement={requestFullscreen:async()=>{
    assert.equal(s.requests(),0,'fullscreen must be requested before any mouse capture');
    s.document.fullscreenElement=s.document.documentElement;
    s.document.emit('fullscreenchange');
  }};
  s.document.exitFullscreen=async()=>{
    s.document.fullscreenElement=null;
    s.document.emit('fullscreenchange');
  };
  vm.runInNewContext(fs.readFileSync('engine/web/shell/fullscreen.js','utf8'),
    {window:s.window,document:s.document,console});
}
test('fullscreen succeeds before canvas gesture captures the pointer',async()=>{
  const s=setup(true);s.ready();
  s.button.emit('click',{stopPropagation(){}});await settle();
  assert.equal(s.document.fullscreenElement,s.document.documentElement);
  assert.equal(s.document.pointerLockElement,null);
  assert.notEqual(s.button.style.visibility,'hidden');
  const down=s.event();s.window.emit('pointerdown',down);await settle();
  assert.equal(s.requests(),1);assert.equal(s.document.pointerLockElement,s.canvas);
  assert.ok(down.prevented&&down.stopped);
});
test('refused fullscreen never captures the pointer or hides the control',async()=>{
  const s=setup(true);s.ready();
  s.document.documentElement.requestFullscreen=async()=>{throw Error('Fullscreen denied');};
  s.button.emit('click',{stopPropagation(){}});await settle();
  assert.equal(s.requests(),0);assert.equal(s.document.pointerLockElement,null);
  assert.notEqual(s.button.style.visibility,'hidden');
  assert.match(s.status.textContent,/Браузер не разрешил полный экран/);
});
test('pointer lock granted after fullscreen exit is immediately released',async()=>{
  const s=setup();s.ready();s.document.fullscreenElement={};
  let grant;
  s.canvas.requestPointerLock=()=>new Promise(resolve=>{grant=()=>{
    s.document.pointerLockElement=s.canvas;s.document.emit('pointerlockchange');resolve();
  };});
  const pending=s.api.request();
  s.document.fullscreenElement=null;s.document.emit('fullscreenchange');
  grant();await pending;
  assert.equal(s.document.pointerLockElement,null);assert.equal(s.exits(),1);
  assert.equal(s.cursor.hidden,true);assert.notEqual(s.button.style.visibility,'hidden');
});
