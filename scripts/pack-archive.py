#!/usr/bin/env python3
"""Create the versioned download package from validated staged game data."""
import argparse, gzip, hashlib, importlib.util, io, json, tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def package(source, output):
    spec=importlib.util.spec_from_file_location('assets',ROOT/'scripts/import-assets.py')
    assets=importlib.util.module_from_spec(spec);spec.loader.exec_module(assets)
    files=[]
    for path in sorted(source.rglob('*')):
        if not path.is_file(): continue
        rel=path.relative_to(source).as_posix()
        if rel.startswith('fonts/'): continue
        parts=rel.split('/'); sub=parts[1:] if parts[0]=='GameDataGenerals' else parts
        if not (len(sub)==1 and path.suffix.lower()=='.big' or sub[0] in ('Data','Maps')): continue
        if path.suffix.lower() in ('.exe','.dll','.sys','.com','.bat','.cmd','.ps1','.sh','.lnk'):continue
        if path.suffix.lower()=='.big': assets.validate_big(path)
        files.append({'path':rel,'size':path.stat().st_size})
    names={f['path'].lower() for f in files}
    required={'inizh.big','mapszh.big','textureszh.big','w3dzh.big','gamedatagenerals/ini.big'}
    if not required<=names:raise ValueError('Missing required archives: '+str(required-names))
    manifest=json.dumps({'format':'generals-web-tar-v1','files':files},separators=(',',':')).encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    partial=output.with_suffix(output.suffix+'.partial')
    with partial.open('wb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=6,mtime=0) as gz, tarfile.open(fileobj=gz,mode='w|',format=tarfile.USTAR_FORMAT) as tar:
        item=tarfile.TarInfo('generals-manifest.json');item.size=len(manifest);item.mode=0o644;tar.addfile(item,io.BytesIO(manifest))
        for f in files:
            item=tarfile.TarInfo(f['path']);item.size=f['size'];item.mode=0o644
            with (source/f['path']).open('rb') as stream:tar.addfile(item,stream)
    partial.replace(output)
    with output.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    output.with_suffix(output.suffix+'.sha256').write_text(digest+'  '+output.name+'\n')
    print(json.dumps({'file':str(output),'bytes':output.stat().st_size,'unpackedBytes':sum(f['size'] for f in files),'files':len(files),'sha256':digest}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=ROOT/'.local/staged');p.add_argument('--output',type=Path,default=ROOT/'.local/downloads/generals-zero-hour-v1.tar.gz');a=p.parse_args();package(a.source,a.output)
