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


def verify_runtime_gate(base, release, environment):
    """Check the predeclared Pages environment against the exact build mode."""
    if type(release.get('diagnosticsCompiled')) is not bool or type(release.get('diagnosticsEnabled')) is not bool:
        raise ValueError('Cloud build manifest must contain boolean diagnostics gates')
    compiled = release.get('diagnosticsCompiled') is True
    enabled = release.get('diagnosticsEnabled') is True
    if compiled != enabled:
        raise ValueError('Cloud build compile/export diagnostics gates disagree')
    override = base.get('env', {}).get(environment, {})
    variables = override.get('vars', base.get('vars', {}))
    runtime = variables.get('DIAGNOSTICS_ENABLED') == 'true'
    if runtime != enabled:
        raise ValueError('Diagnostics mismatch: ' + environment + ' runtime=' + str(runtime) +
                         ', build/export=' + str(enabled) +
                         '. Set both the explicit build command flag and production runtime override together')
    return runtime


def disabled_config(base, release_dir):
    result = json.loads(json.dumps(base))
    result.setdefault('vars', {})['DIAGNOSTICS_ENABLED'] = 'false'
    for environment in result.get('env', {}).values():
        environment.setdefault('vars', {})['DIAGNOSTICS_ENABLED'] = 'false'
    result['pages_build_output_dir'] = str(release_dir.resolve())
    result.pop('$schema', None)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.local/debug-deployment/wrangler.jsonc')
    parser.add_argument('--verify-runtime', action='store_true', help='Validate the selected Cloudflare runtime gate without changing config')
    parser.add_argument('--requested-mode', help='Validate the requested compile mode before bootstrapping')
    parser.add_argument('--disable', action='store_true', help='Generate an explicit OFF runtime config for all environments')
    args = parser.parse_args()
    if args.verify_runtime:
        if os.environ.get('CF_PAGES') != '1':
            print('Local build: versioned runtime configuration stays unchanged')
            return
        try:
            branch = os.environ.get('CF_PAGES_BRANCH')
            if not branch:
                raise ValueError('CF_PAGES_BRANCH is required to select production or preview')
            environment = 'production' if branch == 'main' else 'preview'
            if args.requested_mode is not None:
                import runpy
                enabled = runpy.run_path(str(ROOT / 'scripts/write-build-manifest.py'))['cmake_enabled'](args.requested_mode)
                release = {'diagnosticsCompiled': enabled, 'diagnosticsEnabled': enabled}
            else:
                release = json.loads((ROOT / 'release/build.json').read_text())
            runtime = verify_runtime_gate(json.loads((ROOT / 'wrangler.jsonc').read_text()), release, environment)
        except (OSError, ValueError) as error:
            parser.error(str(error))
        phase = 'Requested' if args.requested_mode is not None else 'Compiled/exported'
        print(phase + ' Cloudflare diagnostics gates verified: ' + environment + '=' + str(runtime))
        return
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / '.local'):
        parser.error('Temporary deployment config must stay inside ignored .local/')
    try:
        base = json.loads((ROOT / 'wrangler.jsonc').read_text())
        config = disabled_config(base, ROOT / 'release') if args.disable else debug_config(
            base, json.loads((ROOT / 'release/build.json').read_text()), ROOT / 'release')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2) + '\n')
    print(output)


if __name__ == '__main__':
    main()
