#!/usr/bin/python3
"""Spaced GPU Manager: hardware identities, desktop trials and driver recovery."""
import argparse
import json
from pathlib import Path
import shlex
import subprocess
import sys
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk
from spaced_gpu import STATE, discover, offload_environment, compute_environment, recommendation, boot_seconds

HELPER = '/usr/lib/spaced-linux/spaced-gpu-helper'


def trial_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def label(text, title=False):
    item = Gtk.Label(label=text, xalign=0)
    item.set_line_wrap(True)
    item.set_max_width_chars(78)
    item.set_selectable(not title)
    if title:
        item.get_style_context().add_class('gpu-title')
    return item


def countdown(state):
    remaining = max(0, int(state.get('deadline_boot_seconds', 0) - boot_seconds()))
    return remaining, (f'DESKTOP TRIAL: {remaining // 60}:{remaining % 60:02d} remaining. '
                       'Keep this desktop now or recovery will end this session. Do not start work yet.')


class Manager(Gtk.Window):
    def __init__(self, preview=False):
        super().__init__(title='Spaced GPU Manager')
        self.preview = preview
        self.busy = False
        self.gpus = []
        self.set_default_size(880, 680)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        self.connect('delete-event', lambda *_: self.busy)
        css = Gtk.CssProvider()
        css.load_from_data(b'.gpu-title { font-size: 18px; font-weight: bold; } '
                           b'.gpu-card { border-radius: 12px; }')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.add(root)
        header = Gtk.Box(spacing=12)
        header.pack_start(label('Spaced GPU Manager', True), True, True, 0)
        self.refresh_button = Gtk.Button(label='Refresh')
        self.refresh_button.connect('clicked', lambda *_: self.refresh())
        header.pack_end(self.refresh_button, False, False, 0)
        self.driver_button = Gtk.Button(label='Drivers & Recovery')
        self.driver_button.set_sensitive(not preview)
        self.driver_button.connect('clicked', self.drivers)
        header.pack_end(self.driver_button, False, False, 0)
        root.pack_start(header, False, False, 0)
        self.status = label('Reading PCI devices, drivers and monitor connections…')
        root.pack_start(self.status, False, False, 0)
        self.trial_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.pack_start(self.trial_bar, False, False, 0)
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        scroller.add(self.cards)
        root.pack_start(scroller, True, True, 0)
        self.advice = label('')
        root.pack_start(self.advice, False, False, 0)
        root.pack_start(label('GPU roles are task-specific: desktop assignment does not disable compute. '
                              'Powering a GPU off is not supported in this version.'), False, False, 0)
        self.refresh()
        GLib.timeout_add_seconds(2, self.poll_trial)
        self.last_phase = None

    def poll_trial(self):
        state = trial_state()
        phase = state.get('phase')
        if not self.busy and phase != self.last_phase:
            self.update_trial()
        elif not self.busy and phase == 'trial':
            # Preserve keyboard focus; do not recreate buttons on each tick.
            remaining, message = countdown(state)
            self.countdown_label.set_text(message)
            self.keep_button.set_sensitive(not self.preview and remaining > 0)
        return True

    def update_trial(self):
        for child in self.trial_bar.get_children():
            child.destroy()
        state = trial_state()
        phase = state.get('phase')
        self.last_phase = phase
        self.driver_button.set_sensitive(not self.preview and phase not in ('staged', 'trial'))
        self.driver_button.set_tooltip_text('Confirm or revert a pending desktop trial before changing drivers.')
        messages = {
            'staged': 'Desktop trial staged for the next boot. Save your work, reboot and confirm promptly.',
            'trial': 'DESKTOP TRIAL: keep this configuration within three minutes of startup. '
                     'Otherwise the previous configuration returns and this session ends. Do not start work yet.',
            'confirmed': 'Desktop assignment confirmed. Revert restores the configuration from before this assignment.',
            'reverted': 'Previous desktop configuration restored. If you reverted manually, reboot when ready.'}
        if phase == 'trial':
            remaining, messages['trial'] = countdown(state)
        if phase in messages:
            self.countdown_label = label(messages[phase])
            self.trial_bar.pack_start(self.countdown_label, False, False, 0)
        row = Gtk.Box(spacing=8)
        if phase == 'trial':
            button = Gtk.Button(label='Keep This Desktop')
            self.keep_button = button
            button.set_sensitive(not self.preview and remaining > 0)
            button.connect('clicked', lambda *_: self.action('confirm'))
            row.pack_start(button, False, False, 0)
        if phase in ('staged', 'trial', 'confirmed'):
            button = Gtk.Button(label='Revert Desktop Assignment')
            button.set_sensitive(not self.preview)
            button.connect('clicked', lambda *_: self.action('revert'))
            row.pack_start(button, False, False, 0)
        self.trial_bar.pack_start(row, False, False, 0)
        self.trial_bar.show_all()

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        def work():
            try:
                gpus = discover()
                GLib.idle_add(self.render, gpus, None)
            except Exception as error:
                GLib.idle_add(self.render, [], str(error))
        threading.Thread(target=work, daemon=True).start()

    def render(self, gpus, error):
        self.busy = False
        self.refresh_button.set_sensitive(True)
        self.gpus = gpus
        for child in self.cards.get_children():
            child.destroy()
        self.status.set_text(('Read-only source preview • ' if self.preview else '') +
                             (f'{len(gpus)} GPU(s) detected • identified by PCI address' if not error else error))
        if not gpus:
            self.cards.pack_start(label('No PCI graphics devices could be read. Refresh or use Drivers & Recovery.'), False, False, 0)
        for gpu in gpus:
            frame = Gtk.Frame()
            frame.get_style_context().add_class('gpu-card')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=14)
            frame.add(box)
            box.pack_start(label(gpu['name'], True), False, False, 0)
            outputs = gpu['connectors']
            role = ('Active display output' if any(c['enabled'] == 'enabled' for c in outputs)
                    else 'Monitor connected (scanout unverified)' if any(c['status'] == 'connected' for c in outputs)
                    else 'No connected monitor reported')
            box.pack_start(label(f"{role} • {gpu['vendor']} • PCI {gpu['pci']}"), False, False, 0)
            grid = Gtk.Grid(column_spacing=28, row_spacing=6)
            fields = [('Driver', gpu['driver']), ('Version', gpu['driver_version']), ('PCIe link', gpu['link']),
                      ('Firmware primary', 'Yes (not necessarily desktop renderer)' if gpu['boot_vga'] else 'No')]
            for index, (name, value) in enumerate(fields):
                grid.attach(label(name), (index % 2) * 2, index // 2, 1, 1)
                grid.attach(label(value), (index % 2) * 2 + 1, index // 2, 1, 1)
            box.pack_start(grid, False, False, 0)
            total, used = gpu['vram_total'], gpu['vram_used']
            if total is not None and total > 0:
                memory = Gtk.ProgressBar(show_text=True)
                memory.set_fraction(min(1, max(0, used / total)) if used is not None else 0)
                memory.set_text(f'VRAM: {used:,.0f} / {total:,.0f} MiB' if used is not None else f'VRAM: {total:,.0f} MiB total; usage unavailable')
                box.pack_start(memory, False, False, 0)
            else:
                box.pack_start(label('VRAM usage unavailable (shared memory or driver does not expose it).'), False, False, 0)
            box.pack_start(label('Ports: ' + (' • '.join(f"{c['name']}: {c['status']} ({c['enabled']})" for c in outputs)
                                            or 'Not exposed by this driver')), False, False, 0)
            buttons = Gtk.Box(spacing=8)
            desktop = Gtk.Button(label='Use for Desktop…')
            connected = any(c['status'] == 'connected' for c in outputs)
            desktop.set_sensitive(not self.preview and connected and
                                  gpu['driver'] in ('amdgpu', 'radeon', 'i915', 'xe', 'nvidia') and
                                  trial_state().get('phase') not in ('staged', 'trial'))
            desktop.set_tooltip_text('Connect a monitor to this GPU, then refresh before staging a desktop trial.')
            desktop.connect('clicked', lambda _, g=gpu: self.stage(g))
            buttons.pack_start(desktop, False, False, 0)
            games = Gtk.Button(label='Games / Offload…')
            games.connect('clicked', lambda _, g=gpu: self.offload(g))
            buttons.pack_start(games, False, False, 0)
            compute = Gtk.Button(label='AI / Compute…')
            compute.connect('clicked', lambda _, g=gpu: self.compute(g))
            buttons.pack_start(compute, False, False, 0)
            box.pack_start(buttons, False, False, 0)
            self.cards.pack_start(frame, False, False, 0)
        self.advice.set_text(recommendation(gpus))
        self.update_trial()
        self.cards.show_all()
        return False

    def message(self, title, text):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

    def offload(self, gpu):
        try:
            env = offload_environment(gpu, self.gpus)
        except ValueError as error:
            self.message('Offload needs manual selection', str(error))
            return
        prefix = 'env ' + ' '.join(shlex.quote(f'{key}={value}') for key, value in env.items())
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.CLOSE,
                                   text='Launch a game on this GPU')
        dialog.format_secondary_text('Use this prefix before a native application command, or paste the Steam launch option below. '
                                     'Flatpak games may require per-application overrides; no global environment is changed.')
        entry = Gtk.Entry(text=prefix + ' %command%')
        entry.set_editable(False)
        dialog.get_content_area().pack_start(entry, False, False, 8)
        dialog.add_button('Copy Steam Launch Option', Gtk.ResponseType.APPLY)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.APPLY:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(entry.get_text(), -1)
        dialog.destroy()

    def compute(self, gpu):
        try:
            env = compute_environment(gpu)
        except ValueError as error:
            self.message('Compute device selection', str(error))
            return
        prefix = 'env ' + ' '.join(shlex.quote(f'{key}={value}') for key, value in env.items())
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.CLOSE,
                                   text='Use this GPU for CUDA / AI')
        dialog.format_secondary_text(
            f"{gpu['name']} • PCI {gpu['pci']}\n\n"
            'Paste this prefix before your native compute application command. Its CUDA device 0 will '
            'be this GPU, even if NVIDIA enumeration order changes. Only that newly launched process '
            'and its children are affected. Existing applications and desktop assignment are unchanged. '
            'The application must support CUDA; this does not install a toolkit, reserve VRAM, '
            'or configure Flatpak/container access. MIG applications require their own device selection.')
        entry = Gtk.Entry(text=prefix)
        entry.set_editable(False)
        dialog.get_content_area().pack_start(entry, False, False, 8)
        dialog.add_button('Copy Launch Prefix', Gtk.ResponseType.APPLY)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.APPLY:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(prefix, -1)
        dialog.destroy()

    def stage(self, gpu):
        if self.busy:
            return
        dialog = Gtk.MessageDialog(transient_for=self, modal=True, buttons=Gtk.ButtonsType.CANCEL,
                                   message_type=Gtk.MessageType.WARNING, text='Try this GPU for the desktop?')
        dialog.format_secondary_text(f"{gpu['name']} • {gpu['pci']}\n\nConnect your monitor to this GPU first. "
            'Save all work before rebooting. At next startup you have three minutes to log in and keep the desktop. '
            'Without confirmation the previous Xorg configuration is restored and LightDM restarts, ending the trial session. '
            'If the display is black, wait for recovery, then move the cable back if needed. Custom Xorg layouts are not overwritten. '
            'This does not migrate applications or disable other GPUs.')
        dialog.add_button('Stage Next-Boot Trial', Gtk.ResponseType.OK)
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.action('stage', gpu['pci'])

    def action(self, action, pci=None):
        if self.busy or self.preview:
            return
        self.busy = True
        self.set_sensitive(False)
        def work():
            try:
                result = subprocess.run(['pkexec', HELPER, action] + ([pci] if pci else []),
                                        capture_output=True, text=True, timeout=120)
                text = result.stdout.strip() or result.stderr.strip() or 'Authentication cancelled.'
            except (OSError, subprocess.SubprocessError) as error:
                text = str(error)
            GLib.idle_add(self.finished, text)
        threading.Thread(target=work, daemon=True).start()

    def finished(self, text):
        self.busy = False
        self.set_sensitive(True)
        self.message('Desktop assignment', text)
        self.refresh()
        return False

    def drivers(self, *_):
        if not self.preview and not self.busy:
            try:
                subprocess.Popen(['/usr/bin/python3', '/usr/lib/spaced-linux/spaced-nvidia-installer.py'])
            except OSError as error:
                self.message('Cannot open Drivers & Recovery', str(error))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='Read-only: never invoke privileged operations')
    parser.add_argument('--confirm-trial', action='store_true', help='Autostart only during an active desktop trial')
    args = parser.parse_args()
    if args.confirm_trial and trial_state().get('phase') != 'trial':
        sys.exit(0)
    preview = args.preview or Path(__file__).resolve().parent != Path('/usr/lib/spaced-linux')
    window = Manager(preview)
    window.show_all()
    Gtk.main()
