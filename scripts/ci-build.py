#!/usr/bin/env python3
"""Keep CI output bounded while retaining compiler logs and real failures."""
import argparse
from collections import deque
import os
from pathlib import Path
import re
import selectors
import subprocess
import time

ERROR = re.compile(r'FAILED:|fatal error:|\berror:|CMake Error|undefined (symbol|reference)|ninja: build stopped', re.I)
PROGRESS = re.compile(r'^\[\d+/\d+\]')


def build(command, logfile, heartbeat=30):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    started = last_notice = time.monotonic()
    tail, errors = deque(maxlen=80), deque(maxlen=32)
    latest = 'starting build'
    pending = ''
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    with logfile.open('wb') as log:
        while selector.get_map():
            for key, _ in selector.select(timeout=1):
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                log.write(data)
                pending += data.decode('utf-8', errors='replace')
                lines = pending.split('\n')
                pending = lines.pop()
                for line in lines:
                    tail.append(line)
                    if ERROR.search(line):
                        errors.append(line)
                    if PROGRESS.match(line):
                        latest = line
            if time.monotonic() - last_notice >= heartbeat:
                print('Engine build ' + str(round(time.monotonic() - started)) + 's: ' + latest[:500], flush=True)
                last_notice = time.monotonic()
    if pending:
        tail.append(pending)
        if ERROR.search(pending):
            errors.append(pending)
    process.stdout.close()
    selector.close()
    code = process.wait()
    print('Engine build ' + ('passed' if code == 0 else 'FAILED') + ' in ' +
          str(round(time.monotonic() - started, 1)) + 's; full log: ' + str(logfile), flush=True)
    if code:
        print('Compiler errors and final build context:', flush=True)
        for line in list(errors) + list(tail):
            print(line[:1500], flush=True)
    return code if code >= 0 else 128 - code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A build command is required')
    raise SystemExit(build(command, args.log))


if __name__ == '__main__':
    main()
