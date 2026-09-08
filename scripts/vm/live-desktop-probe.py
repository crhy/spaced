#!/usr/bin/env python3
"""Inspect the actual live MATE/Compiz session; execute inside the guest."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

report = {'desktop_ready': False, 'errors': [], 'checks': {}}
def run(*args):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=15)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as error:
        return 1, '', str(error)

def require(condition, message):
    if not condition:
        report['errors'].append(message)

try:
    for name in ('mate-session', 'mate-panel', 'caja', 'compiz'):
        code, output, error = run('pgrep', '-u', 'user', '-x', name)
        report['checks'][name] = output.splitlines()
        require(code == 0, f'{name} is not running for the live user')
    sessions = report['checks']['mate-session']
    if sessions:
        environ = (Path('/proc') / sessions[0] / 'environ').read_bytes().split(b'\0')
        for item in environ:
            key, _, value = item.partition(b'=')
            if key in (b'DISPLAY', b'XAUTHORITY', b'DBUS_SESSION_BUS_ADDRESS'):
                os.environ[key.decode()] = value.decode()
    require(bool(os.environ.get('DISPLAY')), 'Live session has no X display')
    os.environ.setdefault('XAUTHORITY', '/home/user/.Xauthority')
    report['display'] = os.environ.get('DISPLAY', '')
    code, audit, error = run('dpkg', '--audit')
    report['dpkg_audit'] = audit or error
    require(code == 0 and not audit, 'dpkg reports incomplete packages')
    report['os_release'] = Path('/etc/os-release').read_text()
    identity = dict(line.split('=', 1) for line in report['os_release'].splitlines() if '=' in line)
    require(identity.get('ID', '').strip(chr(34)) == 'spaced', 'Live image is not Spaced Linux')
    require(identity.get('VERSION_ID', '').strip(chr(34)) == sys.argv[3],
            f'Live image version does not match expected {sys.argv[3]}')
    for prop in ('_NET_SUPPORTING_WM_CHECK', '_COMPIZ_SUPPORTING_DM_CHECK'):
        code, value, error = run('xprop', '-root', prop)
        report['checks'][prop] = value or error
        match = re.search(r'0x[0-9a-fA-F]+', value)
        require(code == 0 and bool(match) and int(match[0], 16) != 0, f'{prop} missing')
        if match and int(match[0], 16):
            code, details, error = run('xprop', '-id', match[0])
            report['checks'][prop + '_window'] = details or error
            require(code == 0, f'{prop} refers to a destroyed window')
            if prop == '_NET_SUPPORTING_WM_CHECK':
                require('compiz' in details.lower(), 'EWMH window manager is not Compiz')
    code, modes, error = run('xrandr', '--query')
    require(code == 0, f'Cannot query live display modes: {error}')
    desired = f'{sys.argv[1]}x{sys.argv[2]}' if len(sys.argv) > 2 and sys.argv[1] and sys.argv[2] else ''
    if desired:
        # A requested resolution is an explicit display-mode test in this VM.
        outputs = re.findall(r'^(\S+) connected', modes, re.MULTILINE)
        if len(outputs) == 1:
            code, _, error = run('xrandr', '--output', outputs[0], '--mode', desired)
            require(code == 0, f'Requested mode {desired} failed: {error}')
            code, modes, error = run('xrandr', '--query')
        else:
            require(False, 'Resolution smoke test expects exactly one virtual output')
        require(bool(re.search(r' connected[^\n]* ' + re.escape(desired) + r'[+-]', modes)),
                f'Requested resolution {desired} is not active')
    report['xrandr'] = modes or error
    code, renderer, error = run('glxinfo', '-B')
    report['glxinfo'] = renderer or error
    require(code == 0 and 'OpenGL renderer string' in renderer, 'Live desktop has no working GLX renderer')
    report['xset'] = run('xset', 'q')[1]
    report['kernel'] = run('uname', '-r')[1]
    report['versions'] = run('dpkg-query', '-W', '-f=${binary:Package} ${Version}\n',
                             'compiz-core', 'compiz-gtk', 'mate-panel', 'libmarco-private2',
                             'spaced-meta', 'spaced-mate-default-settings')[1]
except Exception as error:
    report['errors'].append(str(error))
report['desktop_ready'] = not report['errors']
print(json.dumps(report, indent=2))
sys.exit(0 if report['desktop_ready'] else 1)
