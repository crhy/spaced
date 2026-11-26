#!/usr/bin/python3
"""Spaced GPU Manager - your graphics, in control.

The rhY-approved family look (docs/design/gpu-manager, FAMILY-LOOK) on top of
the 11.26.4 safety backend: journaled Xorg changes, the sysvinit boot guard,
the confirmation deadline, rollback, PCI addresses as identities and
UUID-based CUDA selection. Pages: Overview / Roles / Move monitor / Drivers,
plus a first-run card. Colours follow the live desktop theme; no timers while
the window is hidden; discovery at most every 2 s; first paint under a second.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from spaced_gpu import (STATE, discover, recommendation, boot_seconds, pcie_generation)
import spaced_family_style as family

HELPER = '/usr/lib/spaced-linux/spaced-gpu-helper'
NVIDIA_HELPER = '/usr/lib/spaced-linux/spaced-nvidia-helper'
NVIDIA_INSTALLER = '/usr/lib/spaced-linux/spaced-nvidia-installer.py'
LOGFILE = '/var/log/spaced-nvidia-installer.log'
TAGLINE = 'Your graphics, in control.'
PAGES = (('overview', 'Overview', 'tab-overview'),
         ('roles', 'Roles', 'tab-roles'),
         ('move', 'Move monitor', 'tab-move'),
         ('drivers', 'Drivers', 'tab-drivers'))
ROLES = ('Desktop', 'AI & compute', 'Games', 'Off')
ROLE_PILL = {'Desktop': 'pill-ok', 'AI & compute': 'pill-ai',
             'Games': 'pill-games', 'Off': 'pill-off'}
ROLE_ICON = {'Desktop': 'role-desktop', 'AI & compute': 'role-ai',
             'Games': 'role-games', 'Off': 'role-off'}
ROLE_COST = {
    'Desktop': 'Draws your screen. Everything you see runs on this card. Your screen '
               'must be plugged into this card first; only one card can have it.',
    'AI & compute': 'Saves this card for your AI work. Spaced gives your AI programs '
                    'this card by its real name, so they can\'t end up on the wrong one. '
                    'Two AI programs cannot both own one card exclusively; your program '
                    'decides. Flatpak and container programs must allow GPU access.',
    'Games': 'Games start on this card automatically; your screen stays on the other '
             'one. Games run a few percent slower when a different card draws the '
             'screen, and some NVIDIA features (G-Sync) don\'t work across cards.',
    'Off': 'Leave it alone. Nothing starts here unless you say so. The card can still '
           'be used for your screen. Spaced 11.26.4 cannot switch a graphics card off '
           'to save power.',
}


# ---------------------------------------------------------------- theme tokens
def _hex(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class Palette:
    """Kept for callers that already name it; the tokens now live in the shared
    spaced_family_style module so the GPU and Sound managers never drift."""


# The navy family tokens, single-sourced in spaced_family_style.
DARK = family.DARK
LIGHT = family.LIGHT


def _mix(base, target, amount):
    return family.mix(base, target, amount)


def _light(c):
    return family.lightness(c)


def palette_from_gtk(context):
    """Navy on every dark desktop theme, light tokens on a light one - exactly
    like Spaced Monitor (spaced_monitor/theme.py). Only dark/light is read from
    the desktop; the family navy card/page/band, the cyan accent and the pill
    colours are fixed, because a grey card is wrong in every dark theme (issue
    #426 review, G1)."""
    def lookup(name):
        found, rgba = context.lookup_color(name)
        return (rgba.red, rgba.green, rgba.blue) if found else None

    bg = lookup('theme_bg_color')
    dark = (family.lightness(bg) < 0.5) if bg is not None else True
    return family.palette_for(dark)


def _css_colour(c):
    return '#{:02x}{:02x}{:02x}'.format(*(min(255, max(0, int(v * 255))) for v in c))


def _rgba(c, a):
    colour = _css_colour(c)
    r, g, b = (colour[i:i + 2] for i in (1, 3, 5))
    return 'rgba({},{},{},{})'.format(int(r, 16), int(g, 16), int(b, 16), a)


def build_css(p):
    w, band, card = map(_css_colour, (p.window, p.band, p.card))
    border, text, muted = map(_css_colour, (p.border, p.text, p.muted))
    accent, ok, warn = map(_css_colour, (p.accent, p.ok, p.warn))
    ai, off, track = map(_css_colour, (p.ai, p.off, p.track))
    ink = _css_colour(p.accent_ink)
    return f"""
window, .background {{ background-color: {w}; color: {text}; font-size: 13px; }}
/* The page area behind the cards is the navy page token, not the GTK theme's
   grey base colour: scrolledwindow/viewport/stack all paint the family bg. */
scrolledwindow, viewport, stack, stack > box, .page {{ background-color: {w}; }}
.band {{ background-color: {band}; border-bottom: 1px solid {border}; }}
.band-title {{ font-weight: bold; font-size: 16px; color: {text}; }}
.tagline {{ font-size: 11px; color: {muted}; }}
.vdiv {{ background-color: {border}; }}
.tab {{ background-color: transparent; border: none; border-radius: 999px;
  padding: 4px 12px; color: {muted}; min-height: 0; }}
.tab:hover {{ background-color: {_rgba(p.accent, 0.12)}; color: {text}; }}
.tab-active {{ background-color: {ink}; color: #ffffff; }}
.tab-active:hover {{ background-color: {ink}; color: #ffffff; }}
.tab-underline {{ min-height: 2px; background-color: transparent; }}
.tab-underline-active {{ min-height: 2px; border-radius: 2px;
  background-image: linear-gradient(to right, {accent}, {_rgba(p.accent, 0.1)}); }}
.hbar {{ min-height: 1px; background-color: {border}; }}
.accent-bar {{ background-color: {accent}; border-radius: 2px; }}
.page-title {{ font-weight: bold; font-size: 22px; color: {text}; }}
.page-sub {{ font-size: 11px; color: {muted}; }}
.dot {{ background-color: {ok}; border-radius: 999px; min-width: 9px; min-height: 9px; }}
.trial {{ background-color: {card}; border: 1px solid {warn}; border-radius: 10px;
  padding: 8px 10px; color: {text}; }}
.card {{ background-color: {card}; border: 1px solid {border}; border-radius: 12px;
  padding: 10px; color: {text}; }}
.card-primary {{ background-color: {card}; border: 1px solid {accent};
  box-shadow: 0 0 14px {_rgba(p.accent, 0.35)}; border-radius: 12px; padding: 10px;
  color: {text}; }}
.name {{ font-weight: bold; font-size: 16px; color: {text}; }}
.detail {{ font-size: 11px; color: {muted}; }}
.value {{ font-size: 12px; color: {text}; }}
.muted {{ font-size: 11px; color: {muted}; }}
.pill {{ border-radius: 999px; padding: 1px 10px; font-size: 11px; color: {text}; }}
.pill-ok {{ background-color: {_rgba(p.ok, 0.18)}; border: 1px solid {ok}; }}
.pill-ai {{ background-color: {_rgba(p.ai, 0.20)}; border: 1px solid {ai}; }}
.pill-games {{ background-color: {_rgba(p.accent, 0.18)}; border: 1px solid {accent}; }}
.pill-off {{ background-color: {card}; border: 1px solid {border}; color: {muted}; }}
button {{ background-image: none; background-color: {card}; color: {text};
  border: 1px solid {border}; border-radius: 6px; padding: 4px 10px; min-height: 0; }}
button:hover, button:active, button:focus {{ background-color: {card}; color: {text}; }}
button:disabled {{ color: {muted}; }}
button:disabled:hover {{ background-color: {card}; }}
.icon-button {{ padding: 3px; border-radius: 6px; }}
/* Header buttons are compact rounded outline buttons (~36 px), not full-height
   grey boxes (issue #426 review, G3). */
button.compact, button.compact:active, button.compact:hover,
button.compact:focus {{ min-height: 24px; padding: 5px 12px; border-radius: 8px;
  border: 1px solid {border}; background-color: {card}; color: {text};
  background-image: none; }}
progressbar.vram progress {{ background-image: linear-gradient(to right, {ai},
  #c084fc); border-radius: 3px; min-height: 6px; }}
progressbar.vram trough {{ background-color: {track}; border: none; min-height: 6px;
  border-radius: 3px; }}
.footer {{ border-top: 1px solid {border}; }}
"""


# ------------------------------------------------------------------- helpers
def human_connector(name):
    """'HDMI-A-2' -> 'HDMI 2': the honest kind-number spelling (DESIGN 6)."""
    kind, _, number = name.partition('-')
    kind = {'HDMI': 'HDMI', 'DP': 'DisplayPort', 'DVI': 'DVI', 'eDP': 'built-in screen',
            'VGA': 'VGA', 'TV': 'TV', 'Unknown': 'socket'}.get(kind, kind)
    if kind == 'built-in screen':
        return kind
    digits = ''.join(ch for ch in number if ch.isdigit())
    return f'{kind} {digits}' if digits else kind


def mode_text(mode):
    return mode.replace('x', ' \u00d7 ') if mode else ''


def connector_type(name):
    """'HDMI-A-2' -> 'HDMI', 'DP-0' -> 'DisplayPort', 'eDP-1' -> 'built-in
    screen': the plain connector family, so ports are grouped by type (issue
    #426 review, G6) rather than listed one numbered socket at a time."""
    kind = name.split('-', 1)[0].split('_')[0]
    return {'HDMI': 'HDMI', 'DP': 'DisplayPort', 'DVI': 'DVI',
            'eDP': 'built-in screen', 'VGA': 'VGA', 'TV': 'TV',
            'Unknown': 'socket'}.get(kind, kind)


def pcie_fact(gpu):
    """Max capability in big text; the narrower live link when it runs smaller.
    An integrated GPU is built into the CPU, not slotted (issue #426 review,
    G6): 'PCIe 4.0 · ×4 link' when a card runs narrower than it can."""
    if gpu.get('integrated'):
        return ('Built into your CPU',
                'Your processor has its own graphics; it is not a separate card.')
    gen = pcie_generation(gpu.get('link_speed_max', ''))
    try:
        width = int(str(gpu.get('link_width', '0')) or 0)
        width_max = int(str(gpu.get('link_width_max', '0')) or 0)
    except ValueError:
        width = width_max = 0
    if not gen or not width_max:
        return 'PCIe \u00d7?', 'This card or slot does not report its PCI Express link'
    if width and width < width_max:
        return (f'{gen} \u00b7 \u00d7{width} link',
                f'Its own speed is {gen}; it runs at {width} lanes because of the slot it is in')
    return (f'{gen} \u00b7 \u00d7{width_max}', f'{gen}, {width_max} lanes')


def vram_pair(gpu):
    total, used = gpu.get('vram_total'), gpu.get('vram_used')
    if not total:
        return None
    # vram values are MiB; show used/total in GB with one decimal on the used
    # side (issue #426 review, G4): 300 MiB of 16 GiB is "0.3 / 16 GB", not
    # "300 / 16 GB".
    total_gb = round(total / 1024)
    used_gb = round((used or 0) / 1024, 1)
    fraction = min(1.0, max(0.0, (used or 0) / total)) if used is not None else 0
    return f'{used_gb:.1f} / {total_gb:d} GB', fraction, total_gb


def trial_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def roles_path():
    base = os.environ.get('XDG_DATA_HOME') or str(Path.home() / '.local' / 'share')
    return Path(base) / 'spaced-linux' / 'gpu-roles.json'


def load_roles():
    try:
        data = json.loads(roles_path().read_text())
        if isinstance(data, dict) and isinstance(data.get('roles'), dict):
            return data
    except (OSError, ValueError):
        pass
    return {'roles': {}, 'undo': {}}


# -------------------------------------------------------------------- widgets
# issue #439: when the shipped asset folder is missing (the 11.26.4 update package
# did not ship /usr/share/spaced-gpu-manager), never show the no-entry image:
# fall back to a themed symbolic icon name. SPACED_GPU_MANAGER_ASSETS points the
# asset lookup somewhere else (empty-folder test).
ICON_FALLBACK = {
    'logo': 'preferences-desktop-display',
    'band': 'image-x-generic-symbolic',
    'info': 'dialog-information-symbolic',
    'refresh': 'view-refresh-symbolic',
    'chip-nvidia': 'video-display-symbolic', 'chip-amd': 'video-display-symbolic',
    'chip-intel': 'video-display-symbolic', 'chip-other': 'video-display-symbolic',
    'fact-display': 'video-display-symbolic', 'fact-ports': 'video-display-symbolic',
    'fact-pcie': 'drive-harddisk-symbolic',
    'tab-overview': 'view-list-symbolic', 'tab-roles': 'preferences-system-symbolic',
    'tab-move': 'go-next-symbolic', 'tab-drivers': 'application-x-executable-symbolic',
    'role-desktop': 'video-display-symbolic', 'role-ai': 'utilities-system-monitor-symbolic',
    'role-games': 'application-x-executable-symbolic',
    'role-off': 'process-stop-symbolic', 'dot': 'object-select-symbolic',
}


class SvgImage(Gtk.Image):
    """Repo-shipped line icons, one stroke width, tinted with a theme colour;
    no icon-theme or network lookup."""

    registry = []

    @staticmethod
    def assets_dir():
        from spaced_gpu import __file__ as backend
        override = os.environ.get('SPACED_GPU_MANAGER_ASSETS')
        if override:
            return Path(override)
        return Path(backend).resolve().parents[2] / 'share' / 'spaced-gpu-manager'

    def __init__(self, name, pixels=16, tint=None, height=None):
        super().__init__()
        self.icon_name, self.pixels, self.height = name, pixels, height or pixels
        self.tint = tint
        SvgImage.registry.append(self)
        self.reload()

    def reload(self):
        path = self.assets_dir() / f'{self.icon_name}.svg'
        if not path.is_file():
            # issue #439: a missing file must never paint the no-entry image.
            fallback = ICON_FALLBACK.get(self.icon_name, 'video-display-symbolic')
            if not Gtk.IconTheme.get_default().has_icon(fallback):
                fallback = 'video-display-symbolic'  # a theme without that name
            self.set_from_icon_name(fallback, Gtk.IconSize.BUTTON)
            return
        data = path.read_bytes()
        if self.tint is not None:
            data = data.replace(b'currentColor', _css_colour(self.tint).encode())
        loader = GdkPixbuf.PixbufLoader.new_with_type('svg')
        loader.set_size(self.pixels, self.height)
        loader.write(data)
        loader.close()
        self.set_from_pixbuf(loader.get_pixbuf())


def tinted_images():
    return SvgImage.registry


def label(text, css_class='value', wrap=True, select=False):
    item = Gtk.Label(label=text)
    item.set_xalign(0)
    item.get_style_context().add_class(css_class)
    if wrap:
        item.set_line_wrap(True)
        item.set_max_width_chars(70)
    if select:
        item.set_selectable(True)
    return item


def vdiv():
    box = Gtk.Box()
    box.get_style_context().add_class('vdiv')
    box.set_size_request(1, 24)
    return box


class Card(Gtk.Box):
    """One card per graphics card: chip icon, name + role pill, "NVIDIA 16 GB"
    line, VRAM label + bar, a facts row, and right-aligned outline buttons."""

    def __init__(self, app, gpu, primary):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.app, self.gpu = app, gpu
        self.get_style_context().add_class('card-primary' if primary else 'card')
        tint = app.palette.text

        head = Gtk.Box(spacing=10)
        vendor = gpu.get('vendor', 'Other')
        chip = {'NVIDIA': 'chip-nvidia', 'AMD': 'chip-amd',
                'Intel': 'chip-intel'}.get(vendor, 'chip-other')
        chip_icon = SvgImage(chip, 56, tint)
        chip_icon.set_valign(Gtk.Align.CENTER)
        head.pack_start(chip_icon, False, False, 0)
        head.pack_start(vdiv(), False, False, 0)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        middle.set_valign(Gtk.Align.CENTER)
        # name bold, with the small role pill right after it on the same row
        name_row = Gtk.Box(spacing=8)
        name_row.pack_start(label(gpu.get('name', 'Graphics card'), 'name'),
                            False, False, 0)
        name_row.pack_start(app.pill(app.role_of(gpu)), False, False, 0)
        middle.pack_start(name_row, False, False, 0)
        pair = vram_pair(gpu)
        if gpu.get('integrated'):
            detail = f'{vendor} \u00b7 built into your'
            detail += ' CPU' if gpu.get('family') in ('Intel', 'AMD') else ' board'
        elif pair:
            kind = gpu.get('memory_kind')
            detail = f'{vendor} \u00b7 {pair[2]} GB' + (f' {kind}' if kind else '')
        else:
            detail = f'{vendor} \u00b7 graphics memory not reported'
        middle.pack_start(label(detail, 'detail'), False, False, 0)
        head.pack_start(middle, True, True, 0)
        # VRAM label/value over a thin rounded bar, right side of the top row
        if pair:
            right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            right.set_valign(Gtk.Align.CENTER)
            vram_row = Gtk.Box(spacing=6)
            vram_row.pack_start(label('VRAM', 'muted'), False, False, 0)
            vram_row.pack_start(label(pair[0], 'value'), False, False, 0)
            right.pack_start(vram_row, False, False, 0)
            bar = Gtk.ProgressBar.new()
            bar.get_style_context().add_class('vram')
            bar.set_fraction(pair[1])
            bar.set_size_request(150, -1)
            right.pack_start(bar, False, False, 0)
            head.pack_start(right, False, False, 0)
        elif gpu.get('integrated'):
            shared = label('Shared with your PC \u00b7 about 2 GB available to '
                           'graphics', 'muted')
            shared.set_valign(Gtk.Align.CENTER)
            head.pack_start(shared, False, False, 0)
        self.pack_start(head, False, False, 0)

        facts = Gtk.Box(spacing=10)
        pcie_text, pcie_tip = pcie_fact(gpu)
        for icon, text, tip in (('fact-pcie', pcie_text, pcie_tip),
                                self.display_fact(), self.ports_fact()):
            if not text:
                continue
            facts.pack_start(vdiv(), False, False, 0)
            cell = Gtk.Box(spacing=4)
            cell.pack_start(SvgImage(icon, 13, app.palette.muted), False, False, 0)
            cell.pack_start(label(text, 'muted'), False, False, 0)
            cell.set_tooltip_text(tip)
            facts.pack_start(cell, False, False, 0)
        self.pack_start(facts, False, False, 0)

        buttons = Gtk.Box(spacing=8)
        buttons.set_homogeneous(True)
        buttons.set_halign(Gtk.Align.END)
        configure = Gtk.Button(label='Configure')
        configure.set_tooltip_text('Choose what this card does.')
        app.insensitive_if_preview(configure)
        configure.connect('clicked', lambda *_: app.role_picker(self.gpu))
        buttons.pack_start(configure, False, False, 0)
        role = app.role_of(self.gpu)
        if role == 'Desktop':
            button = Gtk.Button(label='Display settings')
            button.set_tooltip_text('Open the desktop display settings.')
            button.connect('clicked', lambda *_: app.display_settings())
        elif role == 'Off':
            button = Gtk.Button(label='Enable GPU')
            button.set_tooltip_text('Let programs use this card again; nothing starts '
                                    'here until you choose a role for it.')
            button.connect('clicked', lambda *_: app.enable_gpu(self.gpu))
        else:
            button = Gtk.Button(label='Move display here')
            button.set_tooltip_text('Plug your screen into this card first, then press '
                                    'Refresh, then confirm the move below.')
            button.connect('clicked', lambda *_: app.go_move(self.gpu['pci']))
        app.insensitive_if_preview(button)
        buttons.pack_start(button, False, False, 0)
        self.pack_start(buttons, False, False, 0)

    def display_fact(self):
        connected = [c for c in self.gpu.get('connectors', []) if c['status'] == 'connected']
        if connected:
            name = human_connector(connected[0]['name'])
            mode = mode_text(connected[0].get('mode', ''))
            return ('fact-display', f'{name} \u00b7 {mode}' if mode else name,
                    'Your display signal comes from this socket')
        return ('fact-display', 'No display connected',
                'Nothing is reporting a screen on this card')

    def ports_fact(self):
        # Plain words, grouped by connector type (issue #426 review, G6):
        # "DisplayPort + HDMI · 2 free", never "DisplayPort 0, DisplayPort 1".
        connectors = self.gpu.get('connectors', [])
        if not connectors:
            return ('fact-ports', '', '')
        types = []
        for c in connectors:
            t = connector_type(c['name'])
            if t not in types:
                types.append(t)
        free = sum(1 for c in connectors if c['status'] == 'disconnected')
        label_text = ' + '.join(types)
        label_text += f' \u00b7 {free} free' if free else ' \u00b7 in use'
        return ('fact-ports', label_text,
                'Sockets on this card; a free one is ready for a screen')


class Backend:
    """Real machine, or --fake-data for design renders and UI tests. The fake
    hook never runs privileged helpers: capture mode is read-only."""

    def __init__(self, fake_path=None):
        self.fake = json.loads(Path(fake_path).read_text()) if fake_path else None

    def discover(self):
        if self.fake:
            return self.fake['gpus']
        return discover()

    def trial(self):
        if self.fake:
            return self.fake.get('trial', {})
        return trial_state()

    def roles(self):
        if self.fake:
            return {'roles': self.fake.get('roles', {}),
                    'seen': self.fake.get('seen', False), 'undo': {}}
        return load_roles()

    def save_roles(self, data):
        if self.fake:
            self.fake['roles'] = data.get('roles', {})
            self.fake['seen'] = bool(data.get('seen'))
            return
        path = roles_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1) + '\n')


class Manager(Gtk.Window):
    def __init__(self, preview=False, backend=None, capture=None, out=None,
                 self_check=False, palette=None):
        super().__init__(title='Spaced GPU Manager')
        self.preview = preview
        self.backend = backend or Backend()
        self.capture, self.out, self.self_check = capture, out, self_check
        self._forced_palette = palette
        self.busy = False
        self.gpus = []
        self.target_pci = None
        self.move_checked = False
        self.role_data = self.backend.roles()
        self._t0 = time.monotonic()
        self._painted = False
        self._renders = 0
        self._grabbed = False
        self._last_discovery = 0.0
        self._poll = None
        self.palette = (family.palette_for(palette == 'dark')
                        if palette in ('dark', 'light') else DARK)
        self.set_default_size(900, 680)
        self.set_size_request(720, 540)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        self.connect('delete-event', lambda *_: self.busy)
        self.connect('map-event', lambda *_: self.set_timer(True))
        self.connect('unmap-event', lambda *_: self.set_timer(False))
        self.connect('realize', self.apply_theme)
        self.connect('style-set', self.apply_theme)
        self._css = None

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)
        root.pack_start(self.header_band(), False, False, 0)
        root.pack_start(self.tab_bar(), False, False, 0)
        hbar = Gtk.Box()
        hbar.get_style_context().add_class('hbar')
        hbar.set_size_request(-1, 1)
        root.pack_start(hbar, False, False, 0)
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.headings = {}
        self.trial_bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.trial_bar.set_no_show_all(True)
        for name, *_ in PAGES:
            inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            inner.set_margin_top(12)
            inner.set_margin_bottom(12)
            inner.set_margin_start(14)
            inner.set_margin_end(14)
            inner.pack_start(self.headings.setdefault(name, self.page_heading(name)),
                             False, False, 0)
            if name == 'overview':
                inner.pack_start(self.trial_bar, False, False, 0)
            inner.pack_start(self.page_body(name), True, True, 0)
            scroller = Gtk.ScrolledWindow()
            scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scroller.add(inner)
            self.stack.add_named(scroller, name)
        self.stack.add_named(self.page_first_run(), 'first-run')
        root.pack_start(self.stack, True, True, 0)
        root.pack_start(self.footer(), False, False, 0)
        self.go(capture or 'overview')
        GLib.idle_add(lambda: (self.refresh(force=True), False)[1])

    # ---------------------------------------------------------------- chrome
    def apply_theme(self, *_):
        if self._forced_palette in ('dark', 'light'):
            self.palette = family.palette_for(self._forced_palette == 'dark')
        else:
            self.palette = palette_from_gtk(self.get_style_context())
        provider = Gtk.CssProvider()
        provider.load_from_data(build_css(self.palette).encode())
        screen = Gdk.Screen.get_default()
        if self._css is not None:
            Gtk.StyleContext.remove_provider_for_screen(screen, self._css)
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self._css = provider
        for image in tinted_images():
            image.reload()

    def header_band(self):
        band = Gtk.Box(spacing=10)
        band.get_style_context().add_class('band')
        band.set_margin_start(12)
        band.set_margin_end(12)
        band.set_size_request(-1, 72)
        band.pack_start(SvgImage('logo', 40), False, False, 0)
        divider = Gtk.Box()
        divider.get_style_context().add_class('vdiv')
        divider.set_size_request(1, 40)
        band.pack_start(divider, False, False, 0)
        titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        titles.set_valign(Gtk.Align.CENTER)
        titles.pack_start(label('Spaced GPU Manager', 'band-title', wrap=False),
                          False, False, 0)
        titles.pack_start(label(TAGLINE, 'tagline', wrap=False), False, False, 0)
        band.pack_start(titles, False, False, 0)
        band.pack_end(SvgImage('band', 420, height=64), False, False, 0)
        self.refresh_button = Gtk.Button(label='Refresh')
        self.refresh_button.get_style_context().add_class('compact')
        self.refresh_button.set_valign(Gtk.Align.CENTER)
        self.refresh_button.connect('clicked', lambda *_: self.refresh(force=True))
        band.pack_end(self.refresh_button, False, False, 0)
        info = Gtk.Button()
        info.get_style_context().add_class('icon-button')
        info.get_style_context().add_class('compact')
        info.set_valign(Gtk.Align.CENTER)
        info.add(SvgImage('info', 16, self.palette.text))
        info.set_tooltip_text('About Spaced GPU Manager')
        info.connect('clicked', lambda *_: self.message(
            'Spaced GPU Manager',
            'See your graphics cards, choose what each one does, and move your screen '
            'between them.\n\nNothing happens until you press a button. Changing which '
            'card draws your screen can switch your display off for a few seconds; '
            'Spaced puts everything back if you do not confirm it.\n\nSpaced Linux '
            '11.26.4 (issue #426). Colours follow your desktop theme.'))
        band.pack_end(info, False, False, 0)
        return band

    def tab_bar(self):
        bar = Gtk.Box(spacing=2)
        bar.set_margin_top(6)
        bar.set_margin_start(12)
        self.tabs = {}
        for name, text, icon in PAGES:
            button = Gtk.Button()
            button.get_style_context().add_class('tab')
            cell = Gtk.Box(spacing=6)
            cell.pack_start(SvgImage(icon, 15, self.palette.text), False, False, 0)
            cell.pack_start(Gtk.Label(label=text), False, False, 0)
            button.add(cell)
            button.connect('clicked', lambda _, page=name: self.go(page))
            underline = Gtk.Box()
            underline.get_style_context().add_class('tab-underline')
            wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            wrap.pack_start(button, False, False, 0)
            wrap.pack_start(underline, False, False, 0)
            self.tabs[name] = (button, underline)
            bar.pack_start(wrap, False, False, 0)
        return bar

    def page_heading(self, name):
        box = Gtk.Box(spacing=10)
        accent = Gtk.Box()
        accent.get_style_context().add_class('accent-bar')
        accent.set_size_request(4, 26)
        box.pack_start(accent, False, False, 0)
        middle = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        middle.pack_start(label({'overview': 'Graphics overview',
                                 'roles': 'Card roles',
                                 'move': 'Move your display',
                                 'drivers': 'Drivers & recovery'}[name],
                                'page-title', wrap=False), False, False, 0)
        sub_row = Gtk.Box(spacing=6)
        sub_row.pack_start(self.dot_box(), False, False, 0)
        subtitle = label('', 'page-sub', wrap=False)
        sub_row.pack_start(subtitle, False, False, 0)
        middle.pack_start(sub_row, False, False, 0)
        box.pack_start(middle, True, True, 0)
        box.show_all()
        box.set_no_show_all(True)
        box._subtitle = subtitle
        return box

    def dot_box(self):
        dot = Gtk.Box()
        dot.get_style_context().add_class('dot')
        dot.set_valign(Gtk.Align.CENTER)
        return dot

    def footer(self):
        box = Gtk.Box(spacing=8)
        box.get_style_context().add_class('footer')
        box.set_margin_top(8)
        box.set_margin_start(14)
        box.set_margin_end(14)
        box.pack_start(self.dot_box(), False, False, 0)
        box.pack_start(label('All systems ready', 'muted', wrap=False), False, False, 0)
        self.footer_status = label('Last checked just now', 'muted', wrap=False)
        self.footer_status.set_xalign(1.0)
        box.pack_end(self.footer_status, False, False, 0)
        return box

    # ----------------------------------------------------------------- pages
    def page_body(self, name):
        if name == 'overview':
            self.cards_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            return self.cards_box
        if name == 'roles':
            self.roles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            return self.roles_box
        if name == 'move':
            self.move_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            return self.move_box
        self.drivers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        return self.drivers_box

    def page_first_run(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(24)
        box.set_margin_bottom(24)
        box.set_margin_start(24)
        box.set_margin_end(24)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.get_style_context().add_class('card-primary')
        card.pack_start(label('Spaced GPU Manager', 'name'), False, False, 0)
        card.pack_start(label('See your graphics cards, choose what each one does, and '
                              'move your screen between them.', 'value'), False, False, 0)
        for line in ('Nothing happens until you press a button. Spaced never changes '
                     'your graphics setup on its own.',
                     'Changing which card draws your screen switches your screen off for '
                     "a few seconds and restarts your desktop. Spaced puts everything "
                     "back if you don't confirm it.",
                     'Save your work before you change anything.'):
            card.pack_start(label('\u2022 ' + line, 'value'), False, False, 0)
        buttons = Gtk.Box(spacing=8)
        look = Gtk.Button(label='Look around')
        look.connect('clicked', lambda *_: self.finish_first_run('overview'))
        choose = Gtk.Button(label='Choose my setup')
        choose.connect('clicked', lambda *_: self.finish_first_run('roles'))
        buttons.pack_start(look, False, False, 0)
        buttons.pack_start(choose, False, False, 0)
        card.pack_start(buttons, False, False, 8)
        box.pack_start(card, False, False, 0)
        return box

    # ----------------------------------------------------------- navigation
    def go(self, page):
        self.stack.set_visible_child_name(page)
        for name, (button, underline) in self.tabs.items():
            style = button.get_style_context()
            if name == page:
                style.add_class('tab-active')
                underline.get_style_context().add_class('tab-underline-active')
            else:
                style.remove_class('tab-active')
                underline.get_style_context().remove_class('tab-underline-active')

    def go_move(self, pci):
        self.target_pci = pci
        self.move_checked = False
        self.go('move')

    def finish_first_run(self, page):
        self.role_data['seen'] = True
        self.backend.save_roles(self.role_data)
        self.go(page)

    def insensitive_if_preview(self, widget):
        if self.preview:
            widget.set_sensitive(False)
            widget.set_tooltip_text('Read-only: this copy of GPU Manager cannot change '
                                    'anything.')

    def pill(self, role):
        box = Gtk.Box(spacing=5)
        box.get_style_context().add_class('pill')
        box.get_style_context().add_class(ROLE_PILL.get(role, 'pill-off'))
        box.pack_start(SvgImage(ROLE_ICON.get(role, 'role-off'), 11, self.palette.text),
                       False, False, 0)
        box.pack_start(Gtk.Label(label=role or 'Not set'), False, False, 0)
        return box

    # ---------------------------------------------------------------- polling
    def set_timer(self, on):
        if on and self._poll is None:
            self._poll = GLib.timeout_add_seconds(2, self.poll_trial)
        elif not on and self._poll is not None:
            GLib.source_remove(self._poll)
            self._poll = None

    def poll_trial(self):
        state = self.backend.trial()
        if state.get('phase') == 'trial' and hasattr(self, 'countdown_label'):
            remaining = max(0, int(state.get('deadline_boot_seconds', 0) - boot_seconds()))
            self.countdown_label.set_text(
                f'Trying a new setup \u2014 it goes back in '
                f'{remaining // 60}:{remaining % 60:02d}. Keep this desktop now, or '
                'Spaced puts the old one back and ends this session.')
            self.keep_button.set_sensitive(not self.preview and remaining > 0)
        return True

    # ------------------------------------------------------------- discovery
    def refresh(self, force=False):
        if self.busy:
            return
        now = time.monotonic()
        if not force and now - self._last_discovery < 2.0:
            GLib.timeout_add(int((2.0 - (now - self._last_discovery)) * 1000),
                             lambda: self.refresh(True))
            return
        self.busy = True
        self._last_discovery = now
        self.refresh_button.set_sensitive(False)

        def work():
            try:
                gpus = self.backend.discover()
                GLib.idle_add(self.render, gpus, None)
            except Exception as error:
                GLib.idle_add(self.render, [], str(error))
        threading.Thread(target=work, daemon=True).start()

    def role_of(self, gpu):
        state = self.backend.trial()
        if state.get('phase') in ('staged', 'trial', 'confirmed') and \
                state.get('pci') == gpu['pci']:
            return 'Desktop'
        role = self.role_data['roles'].get(gpu['pci'])
        if role:
            return role
        if any(c['enabled'] == 'enabled' for c in gpu.get('connectors', [])):
            return 'Desktop'
        return None

    def desktop_gpu(self):
        return next((g for g in self.gpus if any(
            c['enabled'] == 'enabled' for c in g.get('connectors', []))), None)

    def render(self, gpus, error):
        self.busy = False
        self._renders += 1
        self.refresh_button.set_sensitive(True)
        self.gpus = gpus
        self.last_error = error
        self.role_data = self.backend.roles()
        self.render_pages()
        self.update_trial()
        if not self._painted:
            self._painted = True
            print(f'FIRST_PAINT {time.monotonic() - self._t0:.3f}', flush=True)
            if self.self_check:
                self.unmap()
                GLib.timeout_add(3000, self.self_report)
        if self.capture and not self._grabbed:
            self._grabbed = True
            GLib.timeout_add(650, self.grab)
        return False

    def self_report(self):
        extra = self._renders - 1
        self.set_timer(False)
        print(f'HIDDEN_RENDERS {extra}', flush=True)
        Gtk.main_quit()
        return False

    def render_pages(self):
        desktop = self.desktop_gpu()
        for child in self.cards_box.get_children():
            child.destroy()
        for gpu in self.gpus:
            self.cards_box.pack_start(Card(self, gpu, primary=gpu is desktop),
                                      False, False, 0)
        if not self.gpus:
            self.cards_box.pack_start(label(
                self.last_error or 'No PCI graphics devices could be read. Press '
                                   'Refresh, or check Drivers & Recovery.'),
                False, False, 0)
        else:
            self.cards_box.pack_start(label(recommendation(self.gpus), 'muted'),
                                      False, False, 0)
        for child in self.roles_box.get_children():
            child.destroy()
        for child in self.move_box.get_children():
            child.destroy()
        for child in self.drivers_box.get_children():
            child.destroy()
        self.render_roles()
        self.render_move(desktop)
        self.render_drivers()
        count = len(self.gpus)
        self.headings['overview']._subtitle.set_text(
            f'{count} GPU{"s" if count != 1 else ""} detected \u00b7 Desktop running on '
            f'{desktop["name"]}' if desktop else
            (self.last_error or 'No card reports a display signal'))
        self.headings['roles']._subtitle.set_text(
            f'{count} cards \u00b7 each card gets one of four roles')
        self.headings['move']._subtitle.set_text(
            f'Your display is on the {desktop["name"]} right now' if desktop
            else 'No card reports a display signal')
        nvidia = next((g for g in self.gpus if g.get('driver') == 'nvidia'), None)
        self.headings['drivers']._subtitle.set_text(
            f'NVIDIA driver {nvidia["driver_version"]} \u00b7 working' if nvidia
            else 'No NVIDIA driver installed')
        self.footer_status.set_text('Last checked just now')
        if self.is_first_run_state() and not self.capture:
            self.stack.set_visible_child_name('first-run')
        self.show_all()
        self.trial_bar.hide() if not self.trial_bar.get_children() else self.trial_bar.show()

    # ------------------------------------------------------------------ roles
    def render_roles(self):
        for gpu in self.gpus:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.get_style_context().add_class('card')
            head = Gtk.Box(spacing=8)
            head.pack_start(label(gpu['name'], 'name'), False, False, 0)
            head.pack_end(self.pill(self.role_of(gpu)), False, False, 0)
            card.pack_start(head, False, False, 0)
            role = self.role_of(gpu)
            card.pack_start(label(
                ROLE_COST.get(role, 'No role chosen yet. Choose one; nothing about your '
                                    'other cards changes.'), 'value'), False, False, 0)
            buttons = Gtk.Box(spacing=8)
            change = Gtk.Button(label='Change role\u2026')
            change.set_tooltip_text('Choose what this card does; costs are stated '
                                    'before you apply.')
            self.insensitive_if_preview(change)
            change.connect('clicked', lambda _, g=gpu: self.role_picker(g))
            buttons.pack_start(change, False, False, 0)
            undo = Gtk.Button(label='Undo')
            undo.set_sensitive(self.role_data.get('undo', {}).get(gpu['pci'], False)
                               is not False)
            undo.set_tooltip_text('Put back the role this card had before the change.'
                                  if undo.get_sensitive() else
                                  'No role change to undo for this card yet.')
            undo.connect('clicked', lambda _, g=gpu: self.undo_role(g))
            buttons.pack_start(undo, False, False, 0)
            card.pack_start(buttons, False, False, 0)
            self.roles_box.pack_start(card, False, False, 0)
        igpu = self.suggestion()
        if igpu:
            hint = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            hint.get_style_context().add_class('card-primary')
            hint.pack_start(label(
                f"Your CPU has its own graphics ({igpu['name']}). If you plug your "
                "screen into the motherboard's socket, your desktop moves onto it and "
                'the whole graphics memory of your other card is free for AI and games.',
                'value'), False, False, 0)
            row = Gtk.Box(spacing=8)
            move = Gtk.Button(label='Move my screen to the CPU\'s graphics')
            self.insensitive_if_preview(move)
            move.connect('clicked', lambda _, g=igpu: self.go_move(g['pci']))
            row.pack_start(move, False, False, 0)
            row.pack_start(label('Spaced 11.26.4 cannot switch a graphics card off to '
                                 'save power.', 'muted'), False, False, 0)
            hint.pack_start(row, False, False, 0)
            self.roles_box.pack_start(hint, False, False, 0)

    def suggestion(self):
        desktop = self.desktop_gpu()
        if not desktop:
            return None
        return next((g for g in self.gpus
                     if g is not desktop and g.get('integrated')
                     and g.get('family') in ('Intel', 'AMD')
                     and not any(c['status'] == 'connected'
                                 for c in g.get('connectors', []))), None)

    def role_picker(self, gpu):
        current = self.role_of(gpu)
        dialog = Gtk.Dialog(title='What should this card do?', transient_for=self,
                            modal=True)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button('Set this role', Gtk.ResponseType.OK)
        area = dialog.get_content_area()
        area.set_spacing(6)
        # GTK 3 has no set_margin(): role_picker crashed here on every click, so
        # Configure and "Change role" did nothing at all (issue #439).
        for margin in (area.set_margin_top, area.set_margin_bottom,
                       area.set_margin_start, area.set_margin_end):
            margin(12)
        area.pack_start(label(f"{gpu['name']} \u00b7 {gpu['pci']}", 'value'),
                        False, False, 0)
        radios, chosen = [], {'role': current}
        group = None
        for role in ROLES:
            radio = Gtk.RadioButton.new_with_label_from_widget(group, role)
            if group is None:
                group = radio
            radios.append(radio)
            radio.set_active(role == current)
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            row.pack_start(radio, False, False, 0)
            row.pack_start(label(ROLE_COST[role], 'muted'), False, False, 0)
            area.pack_start(row, False, False, 0)
        def sync(*_):
            for radio, role in zip(radios, ROLES):
                if radio.get_active():
                    chosen['role'] = role
                    confirm.set_sensitive(role != current and not self.preview)
        for radio in radios:
            radio.connect('toggled', sync)
        if self.preview:
            for radio in radios:
                radio.set_sensitive(False)
            confirm.set_sensitive(False)
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        role = chosen['role']
        if role == 'Desktop':
            self.message('Desktop is set by moving your display',
                         'Desktop means "the card drawing your screen right now". You '
                         'cannot set it from here: your screen must be plugged into '
                         'this card first. Use the Move monitor page and follow the '
                         'three steps.')
            self.go('move')
            return
        if len(self.gpus) == 1:
            # issue #439: on an Intel-only PC there is no second card to take a
            # role; say so in plain words instead of quietly saving a nonsense one.
            self.message('Only one graphics card',
                         f"{gpu['name']} is the only graphics card in this PC. It "
                         'draws your screen and runs your programs; there is no '
                         'second card to give a different role to. Nothing changed.')
            return
        self.set_role(gpu['pci'], role)

    def set_role(self, pci, role):
        previous = self.role_data['roles'].get(pci)
        self.role_data['roles'][pci] = role
        self.role_data.setdefault('undo', {})[pci] = previous
        self.backend.save_roles(self.role_data)
        self.render_pages()

    def undo_role(self, gpu):
        previous = self.role_data.get('undo', {}).get(gpu['pci'])
        self.role_data['roles'].pop(gpu['pci'], None)
        if previous:
            self.role_data['roles'][gpu['pci']] = previous
        self.role_data.get('undo', {}).pop(gpu['pci'], None)
        self.backend.save_roles(self.role_data)
        self.render_pages()

    def enable_gpu(self, gpu):
        self.role_data['roles'].pop(gpu['pci'], None)
        self.backend.save_roles(self.role_data)
        self.render_pages()

    def display_settings(self):
        for command in ('mate-display-properties', 'arandr'):
            executable = shutil.which(command)
            if executable:
                subprocess.Popen([executable])
                return
        self.message('Display settings',
                     'Spaced could not open a display settings app.')

    # ------------------------------------------------------------ move monitor
    def render_move(self, desktop):
        state = self.backend.trial()
        target = next((g for g in self.gpus if g['pci'] == self.target_pci), None) \
            or self.suggestion()
        if not target:
            box = self.card_box()
            box.pack_start(label('Move your display', 'name'), False, False, 0)
            box.pack_start(label('Only one graphics card: nothing to move \u2014 your '
                                 'display is already on the card that reports it.',
                                 'value'),
                           False, False, 0)
            self.move_box.pack_start(box, False, False, 0)
            return
        why = self.card_box()
        why.pack_start(label('Move your screen onto '
                             + ("the CPU's graphics" if target.get('integrated')
                                else f"the {target['name']}"), 'name'), False, False, 0)
        why.pack_start(label(
            f'Your desktop uses some of the {desktop["name"] if desktop else "your card"}'
            f'. Moving it onto the {target["name"]} frees that card for AI and games.',
            'value'), False, False, 0)
        why.pack_start(label(
            'Cost, honestly: games on the other card run a few percent slower and a '
            'little laggier, some NVIDIA features (G-Sync) don\'t work across cards, '
            'and your motherboard\'s socket may support fewer screens. Spaced measures '
            'nothing until it is done and will show you what changed.', 'muted'),
            False, False, 0)
        self.move_box.pack_start(why, False, False, 0)

        step1 = self.card_box()
        step1.pack_start(label('1 \u00b7 Find the right socket', 'name'), False, False, 0)
        step1.pack_start(label('This card\'s sockets, near the USB ports:', 'value'),
                         False, False, 0)
        for connector in target.get('connectors', []):
            status = {'connected': 'a screen could go here',
                      'disconnected': 'nothing plugged in'}.get(connector['status'],
                                                                'status unknown')
            step1.pack_start(label(f"\u2022 {human_connector(connector['name'])} "
                                   f"({status})", 'value'), False, False, 0)
        if desktop:
            here = [human_connector(c['name']) for c in desktop.get('connectors', [])
                    if c['status'] == 'connected']
            if here:
                step1.pack_start(label(f'Your screen is in: {here[0]} \u2014 on the '
                                       f'{desktop["name"]}.', 'value'), False, False, 0)
        step1.pack_start(label('Sockets are grouped by card on the back of every PC; '
                               'the motherboard\'s group is next to the USB and audio '
                               'jacks.', 'muted'), False, False, 0)
        self.move_box.pack_start(step1, False, False, 0)

        step2 = self.card_box()
        step2.pack_start(label('2 \u00b7 Move the cable', 'name'), False, False, 0)
        step2.pack_start(label('Turn the PC down but leave it on, or do it after a '
                               'reboot \u2014 Spaced will tell you which socket it wants '
                               'before it changes anything.', 'value'), False, False, 0)
        self.move_box.pack_start(step2, False, False, 0)

        step3 = self.card_box()
        step3.pack_start(label('3 \u00b7 Tell Spaced', 'name'), False, False, 0)
        row = Gtk.Box(spacing=8)
        moved_now = any(c['status'] == 'connected' for c in target.get('connectors', []))
        i_moved = Gtk.Button(label='\u27f3 I\'ve moved the cable')
        self.insensitive_if_preview(i_moved)
        i_moved.connect('clicked', lambda *_: (
            setattr(self, 'move_checked', True), self.refresh(force=True)))
        row.pack_start(i_moved, False, False, 0)
        use = Gtk.Button(label='Use it for the desktop')
        self.insensitive_if_preview(use)
        if state.get('phase') in ('staged', 'trial'):
            use.set_sensitive(False)
            use.set_tooltip_text('Another setup is waiting to be confirmed \u2014 '
                                 'finish it first.')
        else:
            use.set_sensitive(self.move_checked and moved_now and target.get('driver')
                              in ('amdgpu', 'radeon', 'i915', 'xe', 'nvidia', 'ast',
                                  'nouveau'))
            use.set_tooltip_text('Your screen must report a live socket on this card '
                                 'after the move. Press "\u27f3 I\'ve moved the cable" '
                                 'first.')
            use.connect('clicked', lambda _, g=target: self.stage(g))
        row.pack_start(use, False, False, 0)
        step3.pack_start(row, False, False, 0)
        step3.pack_start(label('Then: your screen goes blank for a few seconds while '
                               'Spaced restarts the desktop. Log in within 3 minutes '
                               'and press \u201cKeep this\u201d. If you do nothing, '
                               'Spaced puts everything back on its own.', 'muted'),
                         False, False, 0)
        self.move_box.pack_start(step3, False, False, 0)

    def card_box(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class('card')
        return box

    # -------------------------------------------------------------- drivers
    def render_drivers(self):
        nvidia = next((g for g in self.gpus if g.get('driver') == 'nvidia'), None)
        state = self.backend.trial()
        status = self.card_box()
        status.pack_start(label(f'NVIDIA driver: NVIDIA {nvidia["driver_version"]} '
                                '\u00b7 working' if nvidia else
                                'NVIDIA driver: no driver installed', 'name'),
                          False, False, 0)
        status.pack_start(label('Installed by Spaced \u00b7 verified after the last '
                                'startup' if nvidia else
                                'Spaced can install the official NVIDIA driver when '
                                'you choose.', 'muted'), False, False, 0)
        self.drivers_box.pack_start(status, False, False, 0)

        actions = self.card_box()
        actions.pack_start(label('Graphics setup', 'name'), False, False, 0)
        row = Gtk.Box(spacing=8)
        check = Gtk.Button(label='Check graphics')
        check.set_tooltip_text('Read-only check of the driver, modules and desktop; '
                               'nothing changes.')
        check.connect('clicked', lambda *_: self.audit())
        row.pack_start(check, False, False, 0)
        install = Gtk.Button(label='Replace working NVIDIA driver' if nvidia else
                             'Install NVIDIA driver')
        self.insensitive_if_preview(install)
        install.connect('clicked', lambda *_: self.ask_driver_install('NVIDIA'))
        row.pack_start(install, False, False, 0)
        amd = Gtk.Button(label='Install / repair AMD drivers')
        self.insensitive_if_preview(amd)
        amd.connect('clicked', lambda *_: self.ask_driver_install('AMD'))
        row.pack_start(amd, False, False, 0)
        restore = Gtk.Button(label='Restore graphics')
        self.insensitive_if_preview(restore)
        restore.set_tooltip_text('Undo the last driver transaction Spaced recorded.')
        restore.connect('clicked', lambda *_: self.run_privileged(
            [NVIDIA_HELPER, '--rollback'], 'Restore graphics'))
        row.pack_start(restore, False, False, 0)
        actions.pack_start(row, False, False, 0)
        actions.pack_start(label(
            'Before a reboot, Spaced checks: the exact kernel headers, Secure Boot, '
            'that the packages exist, that the modules were built, that nothing blocks '
            'them, that the boot image contains them, the desktop libraries, the '
            'start-up options, and the window-session launcher. After a reboot it '
            'checks the card driver again, the NVIDIA tools, 3D, the window session, '
            'the panel and the file manager.', 'muted'), False, False, 0)
        if state.get('phase') in ('staged', 'trial'):
            actions.pack_start(label('A desktop setup is waiting to be confirmed '
                                     '\u2014 finish it before changing drivers.',
                                     'muted'), False, False, 0)
        log = Gtk.Button(label='Copy log')
        log.connect('clicked', lambda *_: self.copy_log())
        actions.pack_start(log, False, False, 0)
        self.drivers_box.pack_start(actions, False, False, 0)

        links = self.card_box()
        row = Gtk.Box(spacing=8)
        for url, text in (('https://spacedlinux.com/help.html', 'Online Help'),
                          ('https://discord.gg/BMW9Y6NB3y', 'Discord'),
                          ('https://t.me/+pjmFzHo-i9A2ZWY5', 'Telegram')):
            row.pack_start(Gtk.LinkButton.new_with_label(url, text), False, False, 0)
        links.pack_start(row, False, False, 0)
        self.drivers_box.pack_start(links, False, False, 0)

    def audit(self):
        try:
            result = subprocess.run([NVIDIA_HELPER, '--audit'], capture_output=True,
                                    text=True, timeout=120)
            self.message('Graphics check', (result.stdout.strip() or
                                            result.stderr.strip() or
                                            'No report produced.'))
        except (OSError, subprocess.SubprocessError) as error:
            self.message('Graphics check', str(error))

    def has_vendor(self, vendor):
        return any(vendor in (g.get('vendor'), g.get('family')) for g in self.gpus)

    def ask_driver_install(self, vendor):
        # issue #439: on an Intel-only PC the NVIDIA/AMD buttons must explain
        # themselves instead of opening an installer for a card this PC hasn't got.
        if not self.has_vendor(vendor):
            self.message(f'No {vendor} card',
                         f'This PC has no {vendor} graphics card: no {vendor} driver '
                         'to install or repair. The graphics card it does have already '
                         'runs on its own driver. Nothing changed.')
            return
        self.open_installer()

    def open_installer(self):
        try:
            subprocess.Popen(['/usr/bin/python3', NVIDIA_INSTALLER])
        except OSError as error:
            self.message('Cannot open the driver installer', str(error))

    def copy_log(self):
        try:
            text = Path(LOGFILE).read_text(errors='replace')[-20000:]
        except OSError:
            self.message('Driver log', 'No driver log yet.')
            return
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self.message('Driver log', 'The driver log is on your clipboard.')

    # ------------------------------------------------------------------ trial
    def update_trial(self):
        for child in self.trial_bar.get_children():
            child.destroy()
        self.keep_button = None
        self.countdown_label = None
        state = self.backend.trial()
        phase = state.get('phase')
        if phase not in ('staged', 'trial', 'confirmed', 'reverted'):
            return
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class('trial')
        if phase == 'trial':
            self.countdown_label = label('', 'value')
            box.pack_start(self.countdown_label, False, False, 0)
        else:
            messages = {
                'staged': 'Save your work and reboot. Confirm within 3 minutes of '
                          'start-up or everything goes back.',
                'confirmed': 'Desktop setup kept. \u201cPut it back\u201d restores the '
                             'configuration from before this assignment.',
                'reverted': 'Spaced put the old desktop back. Reboot when ready.'}
            box.pack_start(label(messages[phase], 'value'), False, False, 0)
        row = Gtk.Box(spacing=8)
        if phase == 'trial':
            self.keep_button = Gtk.Button(label='Keep this desktop')
            self.keep_button.connect('clicked', lambda *_: self.action('confirm'))
            row.pack_start(self.keep_button, False, False, 0)
        if phase in ('staged', 'trial', 'confirmed'):
            back = Gtk.Button(label='Put it back')
            self.insensitive_if_preview(back)
            back.connect('clicked', lambda *_: self.action('revert'))
            row.pack_start(back, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.trial_bar.pack_start(box, False, False, 0)
        self.trial_bar.show_all()

    def is_first_run_state(self):
        return (not self.role_data.get('seen') and not self.role_data.get('roles')
                and not self.backend.trial()
                and not Path('/etc/X11/xorg.conf.d/90-spaced-gpu-manager.conf').exists())

    def stage(self, gpu):
        if self.busy:
            return
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   buttons=Gtk.ButtonsType.CANCEL,
                                   message_type=Gtk.MessageType.WARNING,
                                   text='Try this card for the desktop?')
        dialog.format_secondary_text(
            f"{gpu['name']} \u00b7 {gpu['pci']}\n\nYour screen must already report a "
            'live socket on this card. Save all work before rebooting. At next startup '
            'you have three minutes to log in and keep the desktop; without '
            'confirmation Spaced restores the previous configuration and restarts the '
            'desktop session by itself. Your own graphics settings are never '
            'overwritten. This does not disable other cards.')
        dialog.add_button('Stage next-boot trial', Gtk.ResponseType.OK)
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
                result = subprocess.run(['pkexec', HELPER, action] +
                                        ([pci] if pci else []),
                                        capture_output=True, text=True, timeout=120)
                text = result.stdout.strip() or result.stderr.strip() or \
                    'Authentication cancelled.'
            except (OSError, subprocess.SubprocessError) as error:
                text = str(error)
            GLib.idle_add(self.finished, text)
        threading.Thread(target=work, daemon=True).start()

    def finished(self, text):
        self.busy = False
        self.set_sensitive(True)
        self.message('Desktop assignment', text)
        self.refresh(force=True)
        return False

    def run_privileged(self, argv, title):
        if self.busy or self.preview:
            return
        argv = ['pkexec'] + argv
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=300)
            self.message(title, (result.stdout.strip() or result.stderr.strip() or
                                 'Done.'))
        except (OSError, subprocess.SubprocessError) as error:
            self.message(title, str(error))

    # ------------------------------------------------------------------- dialogs
    def message(self, title, text):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

    # ------------------------------------------------------------- screenshots
    def grab(self):
        window = self.get_window()
        width, height = self.get_size()
        pixbuf = Gdk.pixbuf_get_from_window(window, 0, 0, width, height) if window else None
        if pixbuf is None:
            print('FAIL: no pixbuf', file=sys.stderr)
        else:
            pixbuf.savev(str(self.out), 'png', [], [])
            print(f'WROTE {self.out} ({width}x{height})', flush=True)
        Gtk.main_quit()
        return False


class CountDown(Gtk.Window):
    """The trial countdown window the autostart entry reopens (DESIGN 8)."""

    def __init__(self):
        super().__init__(title='Spaced GPU Manager \u2014 trial')
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect('destroy', Gtk.main_quit)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(14)
        box.set_margin_bottom(14)
        box.set_margin_start(14)
        box.set_margin_end(14)
        self.add(box)
        self.title_label = label('', 'name')
        box.pack_start(self.title_label, False, False, 0)
        box.pack_start(label('Keep this desktop, or Spaced will put the old one back '
                             'and end this session.', 'value'), False, False, 0)
        row = Gtk.Box(spacing=8)
        keep = Gtk.Button(label='Keep this desktop')
        keep.connect('clicked', lambda *_: self.act('confirm'))
        back = Gtk.Button(label='Put it back')
        back.connect('clicked', lambda *_: self.act('revert'))
        row.pack_start(keep, False, False, 0)
        row.pack_start(back, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.busy = False
        GLib.timeout_add_seconds(1, self.tick)
        self.tick()

    def tick(self):
        state = trial_state()
        if state.get('phase') != 'trial':
            Gtk.main_quit()
            return False
        remaining = max(0, int(state.get('deadline_boot_seconds', 0) - boot_seconds()))
        self.title_label.set_text('New desktop setup is being tried \u2014 '
                                  f'{remaining // 60}:{remaining % 60:02d} left')
        return True

    def act(self, action):
        if self.busy:
            return
        self.busy = True
        try:
            subprocess.run(['pkexec', HELPER, action], timeout=120)
        except (OSError, subprocess.SubprocessError):
            pass
        Gtk.main_quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true',
                        help='Read-only: never invoke privileged operations')
    parser.add_argument('--confirm-trial', action='store_true',
                        help='Autostart only during an active desktop trial')
    parser.add_argument('--fake-data', metavar='FILE',
                        help='Design and test mode: show this fake GPU set instead of '
                             'reading the machine; privileged actions are disabled')
    parser.add_argument('--capture', choices=('overview', 'roles', 'move', 'drivers',
                                              'first-run'),
                        help='Render one page to --out as a PNG and exit')
    parser.add_argument('--out', metavar='FILE',
                        help='PNG path for --capture')
    parser.add_argument('--self-check', action='store_true',
                        help='After first paint, hide the window and report that no '
                             'timer ran (used by the UI budget test)')
    parser.add_argument('--palette', choices=('auto', 'dark', 'light'),
                        default='auto',
                        help='Force the family dark (navy) or light tokens instead of '
                             'following the desktop; auto follows the desktop like '
                             'Spaced Monitor. Renders use dark/light.')
    args = parser.parse_args()
    if args.confirm_trial and trial_state().get('phase') != 'trial':
        sys.exit(0)
    preview = args.preview or args.fake_data or args.capture or \
        Path(__file__).resolve().parent != Path('/usr/lib/spaced-linux')
    if args.capture and not args.out:
        parser.error('--capture needs --out')
    if args.confirm_trial:
        window = CountDown()
    else:
        window = Manager(preview, Backend(args.fake_data),
                         capture=args.capture, out=args.out,
                         self_check=args.self_check,
                         palette=None if args.palette == 'auto' else args.palette)
    window.show_all()
    Gtk.main()
