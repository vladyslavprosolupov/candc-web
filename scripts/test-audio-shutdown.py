#!/usr/bin/env python3
"""Test exact production manager shutdown methods with the current cache and real SDK OpenAL.

Run normally for the fix. --engine-ref 89faf56 extracts historical manager
methods only (expected failure); the cache and external fixture remain current.
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path('Core/GameEngineDevice/Source/OpenALAudioDevice')


def extract_method(source, signature):
    """Preserve exact method bytes, balancing braces outside comments/strings."""
    match = re.search(r'^' + re.escape(signature) + r'\s*\{', source, re.MULTILINE)
    if not match:
        raise ValueError('Method signature not found: ' + signature)
    index = source.index('{', match.start())
    depth, state = 0, None
    while index < len(source):
        char, pair = source[index], source[index:index + 2]
        if state == 'line':
            if char == '\n': state = None
        elif state == 'block':
            if pair == '*/': state = None; index += 1
        elif state in ('"', "'"):
            if char == '\\': index += 1
            elif char == state: state = None
        elif pair == '//': state = 'line'; index += 1
        elif pair == '/*': state = 'block'; index += 1
        elif char in ('"', "'"): state = char
        elif char == '{': depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0: return source[match.start():index + 1]
        index += 1
    raise ValueError('Unbalanced method body: ' + signature)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-ref', help='Historical manager-method ref; current cache stays unchanged')
    args = parser.parse_args()
    manager = CACHE / 'OpenALAudioManager.cpp'
    source = (subprocess.check_output(['git', '-C', str(ROOT / 'engine'), 'show', args.engine_ref + ':' + str(manager)])
              if args.engine_ref else (ROOT / 'engine' / manager).read_bytes()).decode('utf-8')
    methods = [extract_method(source, signature) for signature in
               ('OpenALAudioManager::~OpenALAudioManager()', 'void OpenALAudioManager::closeDevice(void)')]
    out = ROOT / '.local/audio-shutdown-regression'
    out.mkdir(parents=True, exist_ok=True)
    fixtures = ROOT / 'tests/audio-cache-fixtures'
    with tempfile.TemporaryDirectory(prefix='actual-audio-shutdown-') as temporary:
        temp = Path(temporary)
        for name in ('OpenALAudioCache.cpp', 'OpenALAudioCache.h'):
            (temp / name).write_bytes((ROOT / 'engine' / CACHE / name).read_bytes())
        header = (fixtures / 'OpenALAudioDevice/OpenALAudioManager.h').read_text()
        anchor = 'class OpenALAudioManager {\npublic:'
        declaration = '''class OpenALAudioFileCache;
class OpenALAudioManager {
public:
    OpenALAudioFileCache *m_audioCache = nullptr;
    ALCdevice *m_alcDevice = nullptr;
    ALCcontext *m_alcContext = nullptr;
    void *m_binkAudio = nullptr;
    ALuint fixtureSource = 0, fixtureBuffer = 0;
    ~OpenALAudioManager();
    void closeDevice(void);
    void releaseHandleForBink() {}
    void unselectProvider() {}
    void stopAllAudioImmediately();'''
        if header.count(anchor) != 1:
            parser.error('Fixture manager declaration changed; update shutdown adapter')
        (temp / 'OpenALAudioDevice').mkdir()
        (temp / 'OpenALAudioDevice/OpenALAudioManager.h').write_text(header.replace(anchor, declaration))
        (temp / 'manager-methods.cpp').write_bytes(('#include "OpenALAudioCache.h"\n' + '\n\n'.join(methods) + '\n').encode('utf-8'))
        emcc = ROOT / '.tools/emsdk/upstream/emscripten/em++'
        subprocess.run([str(emcc), '-std=c++20', '-O1', '-g', '-fwasm-exceptions',
                        '-I' + str(temp), '-I' + str(fixtures), str(ROOT / 'tests/audio-shutdown.cpp'),
                        str(temp / 'OpenALAudioCache.cpp'), str(temp / 'manager-methods.cpp'),
                        '-lopenal', '-sENVIRONMENT=node', '-sEXIT_RUNTIME=1', '-sINITIAL_MEMORY=33554432',
                        '--pre-js', str(fixtures / 'audio-context.js'), '-o', str(out / 'test.js')], check=True, cwd=ROOT)
    print('Manager shutdown methods: ' + (args.engine_ref or 'working tree') + '; current production cache', flush=True)
    node = shutil.which('node')
    if not node: parser.error('Node.js is required')
    subprocess.run([node, str(out / 'test.js')], check=True, cwd=ROOT, timeout=30)


if __name__ == '__main__':
    main()
