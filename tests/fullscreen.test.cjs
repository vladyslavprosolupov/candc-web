const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
function setup() {
  const events={}; const attributes={}; let options;
  const status={textContent:''}; const overlay={style:{display:''}}; let canvasFocused=false;
  const button={addEventListener:(k,f)=>events[k]=f,setAttribute:(k,v)=>attributes[k]=v};
  const document={fullscreenElement:null,documentElement:{requestFullscreen:async o=>{options=o;document.fullscreenElement={};events.fullscreenchange();}},
    exitFullscreen:async()=>{document.fullscreenElement=null;events.fullscreenchange();},
    addEventListener:(k,f)=>events[k]=f,
    getElementById:id=>id==='gx-fullscreen'?button:id==='gx-fullscreen-status'?status:id==='gx-overlay'?overlay:{focus(){canvasFocused=true;}}};
  const window={addEventListener:(k,f)=>events[k]=f};
  vm.runInNewContext(fs.readFileSync('engine/web/shell/fullscreen.js','utf8'),{window,document,console});events.DOMContentLoaded();
  return {document,events,status,attributes,options:()=>options,overlay,canvasFocused:()=>canvasFocused};
}
const settle=()=>new Promise(resolve=>setImmediate(resolve));
test('fullscreen click requests hidden browser navigation and exits',async()=>{
  const s=setup();s.events.click({stopPropagation(){}});await settle();
  assert.equal(s.options().navigationUI,'hide');assert.equal(s.attributes['aria-label'],'Выйти из полного экрана');
  s.events.click({stopPropagation(){}});await settle();assert.equal(s.document.fullscreenElement,null);
});
test('fullscreen refusal is visible, rather than silently changing a tooltip',async()=>{
  const s=setup();s.document.documentElement.requestFullscreen=async()=>{throw new Error('Denied');};
  s.events.click({stopPropagation(){}});await settle();assert.match(s.status.textContent,/Браузер не разрешил полный экран/);
});
test('Alt+Enter consumes the real gesture before SDL and ignores repeats',async()=>{
  const s=setup();let prevented=0,stopped=0;
  const event={key:'Enter',altKey:true,repeat:false,preventDefault(){prevented++;},stopImmediatePropagation(){stopped++;}};
  s.events.keydown(event);await settle();assert.equal(prevented,1);assert.equal(stopped,1);assert.ok(s.document.fullscreenElement);
  s.events.keydown({...event,repeat:true});await settle();assert.ok(s.document.fullscreenElement);
});

test('physical Enter works when macOS/keyboard layout reports another key', async()=>{
  for (const code of ['Enter','NumpadEnter']) {
    const s=setup();
    s.events.keydown({key:'Unidentified',code,altKey:true,repeat:false,preventDefault(){},stopImmediatePropagation(){}});
    await settle(); assert.ok(s.document.fullscreenElement);
    assert.equal(s.canvasFocused(),false,'launcher focus must not move to hidden game canvas');
  }
});
test('game canvas regains focus only after the launcher closes', async()=>{
  const s=setup();s.overlay.style.display='none';
  s.events.click({stopPropagation(){}});await settle();assert.equal(s.canvasFocused(),true);
});
test('fullscreen control is available before boot and does not cover launcher footer',()=>{
  const html=fs.readFileSync('engine/web/shell/index.html','utf8');
  const control=html.match(/<button id="gx-fullscreen"[^>]*>/)[0];
  assert.doesNotMatch(control,/\bhidden\b/);
  assert.match(html,/#gx-fullscreen \{[^}]*top: 8px/);
});
