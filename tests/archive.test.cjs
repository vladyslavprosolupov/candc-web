const {test}=require('node:test');
const assert=require('node:assert/strict');
const zlib=require('node:zlib');
const {gxExtractTar,gxArchiveManifest}=require('../engine/web/shell/archive-core.js');
const paths=['INIZH.big','MapsZH.big','TexturesZH.big','W3DZH.big','GameDataGenerals/INI.big'];
function entry(path,data,type='0') {
  const h=Buffer.alloc(512);h.write(path);h.write('0000644\0',100);h.write(data.length.toString(8).padStart(11,'0')+'\0',124);h.fill(32,148,156);h.write(type,156);h.write('ustar\0',257);h.write('00',263);
  h.write(h.reduce((s,b)=>s+b,0).toString(8).padStart(6,'0')+'\0 ',148);
  return Buffer.concat([h,data,Buffer.alloc((512-data.length%512)%512)]);
}
function fixture({files=paths.map(path=>({path,size:20003})),mutate=x=>x,extra=Buffer.alloc(0)}={}) {
  const manifest={format:'generals-web-tar-v1',files};
  return Buffer.concat([entry('generals-manifest.json',Buffer.from(JSON.stringify(manifest))),...files.map((f,i)=>mutate(entry(f.path,Buffer.alloc(f.size,i+1)),i)),extra,Buffer.alloc(1024)]);
}
function run(bytes, compressed=false) {
  let pos=0;const stream=new ReadableStream({pull(c){if(pos===bytes.length)c.close();else {c.enqueue(bytes.subarray(pos,pos+=Math.min(137,bytes.length-pos)));}}});
  const out={files:[],finished:false,maxChunk:0};
  const work=gxExtractTar(compressed?stream.pipeThrough(new DecompressionStream('gzip')):stream,{
    begin(){},async open(e){let size=0;return {write(b){size+=b.length;out.maxChunk=Math.max(out.maxChunk,b.length);},close(){out.files.push({path:e.path,size});},abort(){}};},finish(){out.finished=true;}
  }).then(()=>out);return work;
}
test('streaming gzip import survives arbitrary header/payload boundaries',async()=>{
  const out=await run(zlib.gzipSync(fixture()),true);assert.equal(out.finished,true);assert.equal(out.files.length,5);assert.equal(out.files[0].size,20003);assert.ok(out.maxChunk<=16384);
});
test('reject traversal, duplicates, missing assets and oversized manifest',()=>{
  for(const path of ['../INIZH.big','/INIZH.big','Data/../x','Data\\x','userdata/Save.sav','Data/a.exe']) {
    assert.throws(()=>gxArchiveManifest({format:'generals-web-tar-v1',files:[...paths.map(path=>({path,size:1})),{path,size:1}]}));
  }
  assert.throws(()=>gxArchiveManifest({format:'generals-web-tar-v1',files:paths.map(path=>({path,size:1})).concat({path:'inizh.big',size:1})}));
  assert.throws(()=>gxArchiveManifest({format:'generals-web-tar-v1',files:[{path:'INIZH.big',size:1}]}));
  assert.throws(()=>gxArchiveManifest({format:'generals-web-tar-v1',files:paths.map(path=>({path,size:5*1024**3}))}));
});
test('rejects damaged header, truncation, links and unlisted files',async()=>{
  const bad=fixture();bad[0]^=1;await assert.rejects(run(bad),/header/);
  await assert.rejects(run(fixture().subarray(0,3000)),/Truncated/);
  await assert.rejects(run(fixture({mutate:(b,i)=>i===0?entry(paths[0],Buffer.alloc(20003),'2'):b})),/regular USTAR/);
  await assert.rejects(run(fixture({extra:entry('Data/extra',Buffer.from('x'))})),/Unexpected/);
  await assert.rejects(run(fixture({mutate:(b,i)=>i===0?entry('Data/wrong',Buffer.alloc(20003)):b})),/manifest/);
});
test('gzip CRC corruption is rejected before completion marker',async()=>{
  const bytes=zlib.gzipSync(fixture());bytes[bytes.length-8]^=255;await assert.rejects(run(bytes,true));
});
