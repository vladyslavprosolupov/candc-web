#!/usr/bin/env python3
"""Prepare pinned source, toolchain and open fonts; never download game assets."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, check=True)


def git(directory, *args):
    return subprocess.check_output(['git', '-C', str(directory), *args], text=True).strip()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_engine(root, version):
    """Stage new patch files in Git's index so source export includes them."""
    engine = root / 'engine'
    expected = version['sourceTree']
    if engine.exists():
        if git(engine, 'write-tree') != expected or subprocess.run(
                ['git', '-C', str(engine), 'diff', '--quiet']).returncode:
            raise ValueError('Existing engine differs from engine-version.json; preserve it and use a clean checkout')
        return
    (root / '.tools').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='engine-bootstrap-', dir=root / '.tools') as temp:
        checkout = Path(temp) / 'engine'
        run('git', 'init', checkout)
        run('git', '-C', checkout, 'remote', 'add', 'origin', version['origin'])
        run('git', '-C', checkout, 'fetch', '--depth', '1', 'origin', version['upstreamCommit'])
        run('git', '-C', checkout, 'checkout', '--detach', 'FETCH_HEAD')
        run('git', '-C', checkout, 'apply', '--index', '--whitespace=nowarn', root / version['sourcePatch'])
        if git(checkout, 'write-tree') != expected:
            raise ValueError('Patched engine tree does not match pinned sourceTree')
        checkout.rename(engine)


def install_fonts(archive, destination, config):
    """Read only the named font members; never extract arbitrary archive paths."""
    if sha256(archive) != config['sha256']:
        raise ValueError('Liberation archive SHA-256 mismatch')
    with tarfile.open(archive) as source:
        for name, spec in config['files'].items():
            matches = [member for member in source.getmembers()
                       if member.isfile() and Path(member.name).name == spec['source']]
            if len(matches) != 1:
                raise ValueError('Missing or ambiguous Liberation font: ' + spec['source'])
            data = source.extractfile(matches[0]).read()
            if hashlib.sha256(data).hexdigest() != spec['sha256']:
                raise ValueError('Liberation font SHA-256 mismatch: ' + name)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / name).write_bytes(data)


def prepare_fonts(root, config):
    destination = root / '.tools/fonts'
    if all((destination / name).is_file() and sha256(destination / name) == spec['sha256']
           for name, spec in config['files'].items()):
        return
    with tempfile.TemporaryDirectory(prefix='fonts-bootstrap-') as temp:
        archive = Path(temp) / 'liberation.tar.gz'
        for url in config['urls']:
            result = subprocess.run(['curl', '--fail', '--location', '--retry', '3',
                                     '--output', str(archive), url])
            if result.returncode == 0:
                install_fonts(archive, destination, config)
                return
        raise ValueError('Could not download pinned Liberation fonts')


def prepare_toolchain(root, config):
    tools = root / '.tools'
    tools.mkdir(exist_ok=True)
    emsdk = tools / 'emsdk'
    sdk = config['emsdk']
    if not emsdk.exists():
        run('git', 'init', emsdk)
        run('git', '-C', emsdk, 'remote', 'add', 'origin', sdk['origin'])
        run('git', '-C', emsdk, 'fetch', '--depth', '1', 'origin', sdk['commit'])
        run('git', '-C', emsdk, 'checkout', '--detach', 'FETCH_HEAD')
    if git(emsdk, 'rev-parse', 'HEAD') != sdk['commit']:
        raise ValueError('Existing emsdk installer differs from build-lock.json')
    run(emsdk / 'emsdk', 'install', sdk['version'])
    run(emsdk / 'emsdk', 'activate', sdk['version'])
    environment = tools / 'build-tools'
    python = environment / 'bin/python'
    if not python.exists():
        run('python3', '-m', 'venv', environment)
    run(python, '-m', 'pip', 'install', '--disable-pip-version-check', '--only-binary=:all:',
        *[name + '==' + version for name, version in config['tools'].items()])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', choices=['engine', 'fonts', 'toolchain'])
    args = parser.parse_args()
    try:
        lock = json.loads((ROOT / 'build-lock.json').read_text())
        if args.only in (None, 'engine'):
            prepare_engine(ROOT, json.loads((ROOT / 'engine-version.json').read_text()))
        if args.only in (None, 'fonts'):
            prepare_fonts(ROOT, lock['fonts'])
        if args.only in (None, 'toolchain'):
            prepare_toolchain(ROOT, lock)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
