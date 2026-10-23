#!/usr/bin/env python3
"""Exercise every preset in a disposable live session and retain screenshots."""
import configparser
import json
import os
from pathlib import Path
import pwd
import subprocess
import time

# Refuse installed systems: this deliberately changes the live user's theme.
if not Path('/run/live/medium').is_dir():
    raise SystemExit('Theme review requires a disposable live system')
account = pwd.getpwnam('user')
pid = subprocess.check_output(['pgrep', '-u', 'user', '-x', 'mate-session'], text=True).split()[0]
for entry in (Path('/proc') / pid / 'environ').read_bytes().split(b'\0'):
    key, _, value = entry.partition(b'=')
    if key in (b'DISPLAY', b'XAUTHORITY', b'DBUS_SESSION_BUS_ADDRESS', b'XDG_RUNTIME_DIR'):
        os.environ[key.decode()] = value.decode()
os.initgroups(account.pw_name, account.pw_gid)
os.setgid(account.pw_gid)
os.setuid(account.pw_uid)
os.environ.update(HOME=account.pw_dir, USER='user', LOGNAME='user')
os.chdir(account.pw_dir)

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, Gtk

output = Path('/tmp/spaced-theme-review')
output.mkdir(exist_ok=True)
reports = []

def run(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=30)

def setting(schema, key):
    result = run('gsettings', 'get', schema, key)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result.stdout.strip().strip("'")

def settle(seconds):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(.05)

window = Gtk.Window(title='Spaced Linux — theme review')
window.set_default_size(440, 340)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
window.add(box)
box.pack_start(Gtk.Label(label='Readable text, controls and selection'), False, False, 0)
entry = Gtk.Entry(text='Selected text and insertion cursor')
box.pack_start(entry, False, False, 0)
box.pack_start(Gtk.CheckButton(label='Enabled checkbox', active=True), False, False, 0)
combo = Gtk.ComboBoxText()
combo.append_text('A choice in a dropdown')
combo.set_active(0)
box.pack_start(combo, False, False, 0)
box.pack_start(Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1), False, False, 0)
buttons = Gtk.Box(spacing=12)
buttons.pack_start(Gtk.Button(label='Normal button'), True, True, 0)
disabled = Gtk.Button(label='Disabled button', sensitive=False)
buttons.pack_start(disabled, True, True, 0)
box.pack_start(buttons, False, False, 0)
window.show_all()
window.move(70, 65)
entry.grab_focus()
entry.select_region(0, 13)

processes = [subprocess.Popen(['caja', '--no-desktop', account.pw_dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
             subprocess.Popen(['mate-terminal', '--disable-factory', '--title=Theme review terminal',
                               '--geometry=52x12+540+410', '-e',
                               "bash -c 'printf \"Readable terminal text\\nSpaced Linux 10.26.6\\n\"; sleep 600'"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)]
settle(3)

for theme in json.loads(Path('/usr/share/spaced-themes/themes.json').read_text())['themes']:
    report = {'id': theme['id'], 'errors': []}
    try:
        index = configparser.ConfigParser()
        index.read('/usr/share/themes/' + theme['gtk_theme'] + '/index.theme')
        meta = index['X-GNOME-Metatheme']
        for schema, key, value in (
            ('org.mate.interface', 'icon-theme', meta['IconTheme']),
            ('org.mate.peripherals-mouse', 'cursor-theme', meta['CursorTheme']),
            ('org.mate.Marco.general', 'theme', meta['MetacityTheme']),
            ('org.mate.interface', 'gtk-theme', meta['GtkTheme']),
        ):
            result = run('gsettings', 'set', schema, key, value)
            if result.returncode:
                report['errors'].append(result.stderr)
        # Exercise the monitor triggered by Appearance, not just the switcher.
        settle(8)
        actual = {'gtk_theme': setting('org.mate.interface', 'gtk-theme'),
                  'wallpaper': setting('org.mate.background', 'picture-filename')}
        for key in ('gtk_theme', 'wallpaper'):
            if actual[key] != theme[key]:
                report['errors'].append(f'{key}: {actual[key]} != {theme[key]}')
        import ast
        panels = ast.literal_eval(setting('org.mate.panel', 'toplevel-id-list'))
        actual['panels'] = []
        if len(panels) != 1:
            report['errors'].append(f'Expected one panel, found {panels}')
        for panel in panels:
            schema = f'org.mate.panel.toplevel:/org/mate/panel/toplevels/{panel}/'
            position, size = setting(schema, 'orientation'), int(setting(schema, 'size'))
            actual['panels'].append({'id': panel, 'position': position, 'size': size})
            if position != theme['panel_position'] or size != theme['panel_size']:
                report['errors'].append('Panel position or size did not follow the preset')
        actual['dock'] = run('pgrep', '-u', 'user', '-x', 'cairo-dock').returncode == 0
        if actual['dock'] != theme['cairo_dock']:
            report['errors'].append('Dock visibility did not follow the preset')
        for process in ('mate-panel', 'caja', 'compiz', 'gtk-window-decorator'):
            if run('pgrep', '-u', 'user', '-f', process).returncode:
                report['errors'].append(process + ' is not running')
        wm = run('wmctrl', '-m')
        actual['window_manager'] = wm.stdout.strip()
        if wm.returncode or 'name: compiz' not in wm.stdout.lower():
            report['errors'].append('Compiz does not own the desktop')
        report['actual'] = actual
        # Address Caja by its WM_CLASS: a title substring can select another
        # window, and a newly opened window may not exist at the first attempt.
        root = Gdk.get_default_root_window()
        right = min(540, root.get_width() - 490)
        for target, geometry in (
            ('caja.Caja', f'0,{right},65,480,300'),
            ('mate-terminal.Mate-terminal', f'0,{right},420,430,220'),
        ):
            result = run('wmctrl', '-x', '-r', target, '-e', geometry)
            if result.returncode:
                report['errors'].append('Cannot arrange ' + target + ': ' + result.stderr)
        window.move(80 if theme['panel_position'] == 'left' else 35, 65)
        window.present()
        settle(1)
        capture = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height())
        capture.savev(str(output / (theme['id'] + '.png')), 'png', [], [])
    except Exception as error:
        report['errors'].append(str(error))
    reports.append(report)
    (output / 'results.json').write_text(json.dumps(reports, indent=2) + '\n')
    print(theme['id'] + ': ' + ('FAIL ' + '; '.join(report['errors']) if report['errors'] else 'PASS'), flush=True)

for process in processes:
    if process.poll() is None:
        process.terminate()
raise SystemExit(1 if any(row['errors'] for row in reports) else 0)
