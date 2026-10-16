const {test} = require('node:test');
const assert = require('node:assert/strict');
const {gxPlanLocalFiles, gxCheckBig} = require('../engine/web/shell/local-data.js');
const {gxValidateBackup} = require('../engine/web/shell/save-backup.js');
const fs = require('node:fs');
const path = require('node:path');
const f = p => ({name: p.split('/').pop(), webkitRelativePath: p, size: 10});
const installation = () => ['INI.big','Maps.big'].map(n => f('root/Generals/'+n)).concat(
  ['INIZH.big','MapsZH.big','TexturesZH.big','W3DZH.big','Data/INI/GameData.ini','game.exe','Data/hack.dll'].map(n => f('root/Zero Hour/'+n)));
test('disc layout maps base game separately and excludes executables', () => {
  const paths = gxPlanLocalFiles(installation()).map(e => e.path);
  assert(paths.includes('GameDataGenerals/INI.big'));
  assert(paths.includes('INIZH.big'));
  assert(paths.includes('Data/INI/GameData.ini'));
  assert(!paths.some(p => /exe|dll/.test(p)));
});
test('rejects ambiguous roots, partial installations and traversal', () => {
  assert.throws(() => gxPlanLocalFiles(installation().concat(f('other/INIZH.big'))));
  assert.throws(() => gxPlanLocalFiles(installation().filter(f => f.name !== 'MapsZH.big')));
  assert.throws(() => gxPlanLocalFiles(installation().concat(f('root/Zero Hour/Data/../evil'))));
});
test('BIG rejects out-of-bounds payload and missing terminator', async () => {
  const bytes = Buffer.alloc(33); bytes.write('BIGF');bytes.writeUInt32BE(1,8);bytes.writeUInt32BE(29,12);
  bytes.writeUInt32BE(29,16);bytes.writeUInt32BE(4,20);bytes.write('test',24);
  await gxCheckBig(new Blob([bytes]));
  bytes.writeUInt32BE(0,16);bytes.writeUInt32BE(0,20);await gxCheckBig(new Blob([bytes])); // Retail tombstone entry
  bytes.writeUInt32BE(29,16);
  bytes.writeUInt32BE(5,20);await assert.rejects(gxCheckBig(new Blob([bytes])));
  bytes.writeUInt32BE(4,20);bytes[28]=1;await assert.rejects(gxCheckBig(new Blob([bytes])));
});
test('save backup roundtrip bytes and traversal validation', () => {
  const value = {format:'generals-web-userdata-v1',files:[{path:'GeneralsZH/Save/Test.sav',data:Buffer.from([0,1,255,2]).toString('base64')}]};
  assert.deepEqual(Buffer.from(gxValidateBackup(value)[0].data,'base64'),Buffer.from([0,1,255,2]));
  for (const bad of ['../Options.ini','/tmp/test','x/../../GameData/INI.big','x\\y','x/./y'])
    assert.throws(()=>gxValidateBackup({...value, files:[{...value.files[0],path:bad}]}));
  assert.throws(()=>gxValidateBackup({...value,files:[value.files[0],value.files[0]]}));
});
test('real supplied BIG headers satisfy browser validation', async () => {
  const root = path.join(__dirname,'../.local/staged');
  if (!fs.existsSync(root)) return;
  for (const name of fs.readdirSync(root).filter(n=>n.endsWith('.big'))) {
    const file = path.join(root,name), stat = fs.statSync(file);
    const handle = fs.openSync(file,'r');
    const blob = {name,size:stat.size,slice(start,end) {const b=Buffer.alloc(Math.min(end,stat.size)-start);fs.readSync(handle,b,0,b.length,start);return new Blob([b]);}};
    try {await gxCheckBig(blob);} finally {fs.closeSync(handle);}
  }
});
