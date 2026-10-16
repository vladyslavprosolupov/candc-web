#!/usr/bin/env python3
"""Stage owned installed game data, validate BIG directories, and pack for OPFS.

Only BIG archives and Data/Maps/fonts files are read. Original files are never
modified. Windows executable files are neither executed nor imported.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = Path.home() / 'Downloads/R.G. Mechanics/Command and Conquer - Generals'


def validate_big(path):
    size = path.stat().st_size
    with path.open('rb') as f:
        header = f.read(16)
        if len(header) != 16 or header[:4] not in (b'BIGF', b'BIG4'):
            raise ValueError(f'Invalid BIG archive: {path}')
        count, index_end = struct.unpack('>II', header[8:])
        if index_end > size or count > 1_000_000:
            raise ValueError(f'Invalid BIG directory: {path}')
        for _ in range(count):
            record = f.read(8)
            if len(record) != 8:
                raise ValueError(f'Truncated BIG record: {path}')
            offset, length = struct.unpack('>II', record)
            name = bytearray()
            while True:
                char = f.read(1)
                if not char or len(name) > 4096 or f.tell() > size:
                    raise ValueError(f'Invalid BIG filename: {path}')
                if char == b'\0':
                    break
                name.extend(char)
            if offset + length > size:
                raise ValueError(f'BIG entry outside archive: {path}')
    return count


def stage(source, dest):
    if not source.is_dir():
        raise ValueError(f'Game directory does not exist: {source}')
    files = []
    for path in sorted(source.rglob('*')):
        if not path.is_file() or path.name.startswith('.'):
            continue
        rel = path.relative_to(source)
        if not (len(rel.parts) == 1 and path.suffix.lower() == '.big' or
                rel.parts[0].lower() in ('data', 'maps', 'fonts')):
            continue
        if path.suffix.lower() in ('.exe', '.dll', '.sys', '.com', '.bat'):
            continue
        entries = validate_big(path) if path.suffix.lower() == '.big' else None
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.parts[0].lower() == 'fonts':
            import shutil
            shutil.copy2(path, target)
        else:
            target.symlink_to(path.resolve())
        files.append({'path': str(rel), 'size': path.stat().st_size, 'entries': entries})
    if not any(item['entries'] is not None for item in files):
        raise ValueError(f'No BIG archives in {source}')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT)
    parser.add_argument('--quality', type=int, choices=range(12), default=4)
    args = parser.parse_args()
    stage_dir = ROOT / '.local/staged'
    if stage_dir.exists():
        # Only remove our generated links, never the files they refer to.
        import shutil
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    report = {
        'Zero Hour': stage(args.source / 'Command and Conquer Generals Zero Hour', stage_dir),
        'Generals': stage(args.source / 'Command and Conquer Generals', stage_dir / 'GameDataGenerals'),
    }
    fonts = stage_dir / 'fonts'
    fonts.mkdir(exist_ok=True)
    env = dict(os.environ, GX_FONTS=str(fonts))
    subprocess.run(['bash', str(ROOT / 'engine/scripts/build/ios/stage-fonts.sh')], env=env, check=True)
    (ROOT / '.local/asset-audit.json').write_text(json.dumps(report, indent=2))
    sys.path.insert(0, str(ROOT / 'engine/scripts/web'))
    import packer
    packer.BROTLI_QUALITY = args.quality
    # macOS spawn processes re-import modules; propagate settings via env.
    os.environ['GX_BROTLI_QUALITY'] = str(args.quality)
    os.environ['GX_PACK_CACHE'] = str(ROOT / '.local/pack-cache')
    out = ROOT / 'engine/web/dist/assets/default_ru'
    out.mkdir(parents=True, exist_ok=True)
    packer.pack(str(stage_dir), str(out / 'build.data'))
    (out.parent / 'builds.json').write_text(json.dumps([
        {'name': 'default_ru', 'label': 'Local disc installation', 'size': (out / 'build.data').stat().st_size}
    ]))
    print('Local game data ready. Audit: .local/asset-audit.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
