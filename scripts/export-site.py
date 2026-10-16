#!/usr/bin/env python3
"""Assemble an asset-free static release with a stripped engine and source bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'engine'
OUT = ROOT / 'release'

def diagnostics_config(enabled=False):
    return '// TEMPORARY diagnostics: explicit export opt-in.\nwindow.gxDiagnosticsConfig = Object.freeze({enabled: ' + ('true' if enabled else 'false') + '});\n'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostics', action='store_true', help='Enable temporary input-freeze diagnostics (server gate also required)')
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    # No broad dist copy: dist/assets contains the private game installation.
    for path in (ENGINE / 'web/shell').glob('*.js'):
        shutil.copy2(path, OUT / path.name)
    (OUT / 'diagnostics-config.js').write_text(diagnostics_config(args.diagnostics))
    for name in ['index.html', 'saves.html', 'launcher.css', 'launcher-config.json', 'brotli_bg.wasm', 'ice.json']:
        shutil.copy2(ENGINE / 'web/shell' / name, OUT / name)
    shutil.copytree(ENGINE / 'web/shell/art', OUT / 'art', dirs_exist_ok=True)
    shutil.copytree(ENGINE / 'web/shell/i18n', OUT / 'i18n', dirs_exist_ok=True)
    shutil.copy2(ENGINE / 'build/emscripten/GeneralsMD/GeneralsXZH.js', OUT)
    subprocess.run([str(ROOT / '.tools/emsdk/upstream/bin/wasm-opt'), '--all-features', '--strip-debug',
                    str(ENGINE / 'build/emscripten/GeneralsMD/GeneralsXZH.wasm'), '-o', str(OUT / 'GeneralsXZH.wasm')], check=True)
    digest = hashlib.sha256((OUT / 'GeneralsXZH.wasm').read_bytes()).hexdigest()[:12]
    (OUT / 'build.json').write_text(json.dumps({'buildId': digest}) + '\n')
    (OUT / 'assets').mkdir(exist_ok=True)
    # Host operators may edit this after export to opt into their own asset server.
    (OUT / 'assets/builds.json').write_text('[]\n')
    (OUT / 'fonts').mkdir(exist_ok=True)
    for name in ['arial.ttf', 'arialbold.ttf', 'couriernew.ttf', 'timesnewroman.ttf']:
        shutil.copy2(ROOT / '.local/staged/fonts' / name, OUT / 'fonts' / name)
    shutil.copy2(ROOT / 'hosting/Liberation-LICENSE', OUT / 'fonts/LICENSE.txt')
    shutil.copy2(ENGINE / 'LICENSE.md', OUT / 'LICENSE.md')
    shutil.copy2(ROOT / 'hosting/_headers', OUT / '_headers')
    (OUT / '.nojekyll').touch()
    (OUT / '_routes.json').write_text(json.dumps({'version': 1, 'include': ['/api/diagnostics'], 'exclude': []}) + '\n')
    source_dir = OUT / 'source'
    source_dir.mkdir(exist_ok=True)
    tracked = subprocess.check_output(['git', '-C', str(ENGINE), 'ls-files', '-z']).decode().split('\0')
    extra = ['Core/GameEngineDevice/Include/WebInputDiagnostics.h', 'web/shell/diagnostics.js', 'web/shell/diagnostics-config.js', 'web/shell/pointer-lock.js', 'web/shell/local-data.js', 'web/shell/fullscreen.js', 'web/shell/save-backup.js',
             'web/shell/saves.html', 'web/shell/saves-page.js',
             'docs/DEV_BLOG/2026-10-DIARY.md', 'web/shell/archive-core.js', 'web/shell/archive-worker.js',
             'web/shell/launcher.css', 'web/shell/launcher-config.json']
    extra += [str(p.relative_to(ENGINE)) for p in (ENGINE / 'web/shell/art').glob('*')]
    # Archive working source, including local modifications, not the pristine upstream tree.
    with tempfile.TemporaryDirectory(prefix='generals-source-') as temp:
        archive = Path(temp) / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name in sorted(set(tracked + extra)):
                path = ENGINE / name
                if name and path.is_file(): tar.add(path, arcname='generals-web/engine/' + name, recursive=False)
            for folder in ['scripts', 'patches', 'tests', 'hosting', 'functions']:
                for path in (ROOT / folder).rglob('*'):
                    if path.is_file() and '__pycache__' not in path.parts:
                        tar.add(path, arcname='generals-web/' + str(path.relative_to(ROOT)), recursive=False)
            for name in ['README.md', 'package.json', 'package-lock.json', 'wrangler.jsonc']:
                tar.add(ROOT / name, arcname='generals-web/' + name)
            # Bundled dependency source and notices; omit checkout metadata and build outputs.
            for dep in (ENGINE / 'build/emscripten/_deps').glob('*-src'):
                for path in dep.rglob('*'):
                    if path.is_file() and not {'.git', '__pycache__', 'node_modules'} & set(path.relative_to(dep).parts):
                        tar.add(path, arcname='generals-web/dependencies/' + dep.name + '/' + str(path.relative_to(dep)), recursive=False)
            cache = (ENGINE / 'build/emscripten/CMakeCache.txt').read_text()
            ffmpeg_prefix = next(line.split('=', 1)[1] for line in cache.splitlines() if line.startswith('FFMPEG_EM_PREFIX:PATH='))
            tar.add(Path(ffmpeg_prefix) / 'src/ffmpeg-7.1.tar.xz', arcname='generals-web/dependencies/ffmpeg-7.1.tar.xz')
        parts = []
        with archive.open('rb') as stream:
            while data := stream.read(20 * 1024 * 1024):
                name = f'generals-source.tar.gz.part{len(parts):03}'
                (source_dir / name).write_bytes(data)
                parts.append({'file': name, 'sha256': hashlib.sha256(data).hexdigest()})
        valid_parts = {p['file'] for p in parts}
        for old in source_dir.glob('generals-source.tar.gz.part*'):
            if old.name not in valid_parts: old.unlink()
        (source_dir / 'manifest.json').write_text(json.dumps(parts, indent=2) + '\n')
        links = ''.join(f'<li><a href="{p["file"]}">{p["file"]}</a></li>' for p in parts)
        (source_dir / 'index.html').write_text('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Исходный код Generals Web</title><h1>Исходный код и скрипты сборки</h1>'
            '<p>Независимая модификация. Не является официальным продуктом EA. Исходный код и лицензии зависимостей включены.</p>'
            '<p>Скачайте все части в одну папку и выполните:</p><pre>cat generals-source.tar.gz.part* &gt; generals-source.tar.gz\ntar -xzf generals-source.tar.gz</pre>'
            '<ul>' + links + '</ul><a href="manifest.json">Контрольные суммы SHA-256</a>')
    files = [p for p in OUT.rglob('*') if p.is_file()]
    private = [p for p in files if p.suffix.lower() in {'.big', '.data', '.iso', '.exe'}]
    if private: raise SystemExit('Refusing release with private assets: ' + str(private))
    large = [p for p in files if p.stat().st_size > 25 * 1024 * 1024]
    if large: raise SystemExit('Files exceed Cloudflare Pages limit: ' + str(large))
    print(f'Ready: {OUT} ({sum(p.stat().st_size for p in files) / 1024**2:.1f} MiB, {len(files)} files). No game assets included.')

if __name__ == '__main__': main()
