#!/usr/bin/env python3
"""Generate an explicit, ignored diagnostics config for the existing Pages project."""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def debug_config(base, release, release_dir):
    if release.get('diagnosticsCompiled') is not True or release.get('diagnosticsEnabled') is not True:
        raise ValueError('Export an explicitly diagnostics-enabled engine release first')
    result = json.loads(json.dumps(base))
    result['pages_build_output_dir'] = str(release_dir.resolve())
    result.setdefault('vars', {})['DIAGNOSTICS_ENABLED'] = 'true'
    result.pop('$schema', None)  # Base schema path is relative to the project root.
    return result


def cloud_runtime_config(base, release):
    """Generate only the ephemeral runtime gate after the OFF source export."""
    compiled = release.get('diagnosticsCompiled') is True
    enabled = release.get('diagnosticsEnabled') is True
    if enabled and not compiled:
        raise ValueError('Diagnostics-enabled export requires a compiled-on engine')
    result = json.loads(json.dumps(base))
    result.setdefault('vars', {})['DIAGNOSTICS_ENABLED'] = 'true' if enabled else 'false'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/debug-deployment/wrangler.jsonc')
    parser.add_argument('--cloud-runtime', action='store_true', help='After export, set only the runtime gate in an ephemeral CF_PAGES=1 checkout')
    args = parser.parse_args()
    if args.cloud_runtime:
        if os.environ.get('CF_PAGES') != '1':
            print('Local build: versioned runtime configuration stays unchanged')
            return
        try:
            path = ROOT / 'wrangler.jsonc'
            config = cloud_runtime_config(json.loads(path.read_text()),
                                          json.loads((ROOT / 'release/build.json').read_text()))
        except (OSError, ValueError) as error:
            parser.error(str(error))
        path.write_text(json.dumps(config, indent=2) + '\n')
        print('Ephemeral Cloudflare runtime diagnostics: ' + config['vars']['DIAGNOSTICS_ENABLED'])
        return
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local'):
        parser.error('Temporary deployment config must stay inside ignored .local/')
    try:
        config = debug_config(json.loads((ROOT / 'wrangler.jsonc').read_text()),
                              json.loads((ROOT / 'release/build.json').read_text()), ROOT / 'release')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
