"""GPU discovery and conservative desktop trials (no GTK dependency).

PCI addresses are identities; DRM and NVIDIA enumeration order is not.
"""
import csv
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


PCI = re.compile(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$")
STATE = Path('/var/lib/spaced-gpu-manager/trial.json')
CONFIG = Path('/etc/X11/xorg.conf.d/90-spaced-gpu-manager.conf')


def boot_seconds():
    """Elapsed boot time, including suspend; independent of wall-clock corrections."""
    return time.clock_gettime(time.CLOCK_BOOTTIME)


def read(path, default=''):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return default


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True,
                                errors='replace', timeout=8, check=False)
        return result.stdout if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def normalize_pci(value):
    value = value.strip().lower()
    if re.fullmatch(r'[0-9a-f]{8}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', value):
        value = value[4:]
    return value if PCI.fullmatch(value) else None


def discover(sysroot=Path('/sys'), runner=command):
    names = {}
    for line in runner(['lspci', '-Dnn']).splitlines():
        address, _, description = line.partition(' ')
        names[address.lower()] = description
    nvidia = {}
    uuids = {}
    for row in csv.reader(runner(['nvidia-smi', '--query-gpu=pci.bus_id,uuid',
                                 '--format=csv,noheader']).splitlines()):
        if len(row) == 2 and normalize_pci(row[0]):
            value = row[1].strip()
            if re.fullmatch(r'GPU-[0-9a-fA-F-]{36}', value):
                uuids[normalize_pci(row[0])] = value
    output = runner(['nvidia-smi', '--query-gpu=pci.bus_id,name,memory.total,memory.used,driver_version',
                     '--format=csv,noheader,nounits'])
    for row in csv.reader(output.splitlines()):
        if len(row) == 5 and normalize_pci(row[0]):
            nvidia[normalize_pci(row[0])] = [item.strip() for item in row[1:]]
    result = []
    for device in sorted((sysroot / 'bus/pci/devices').glob('*')):
        if not PCI.fullmatch(device.name) or not read(device / 'class').startswith('0x03'):
            continue
        vendor = {'0x10de': 'NVIDIA', '0x1002': 'AMD', '0x8086': 'Intel'}.get(read(device / 'vendor'), 'Other')
        driver = (device / 'driver').resolve().name if (device / 'driver').exists() else 'Not bound'
        connectors = []
        for card in sorted((device / 'drm').glob('card[0-9]*')):
            if not re.fullmatch(r'card\d+', card.name):
                continue
            for connector in sorted((sysroot / 'class/drm').glob(card.name + '-*')):
                connectors.append({'name': connector.name[len(card.name)+1:],
                                   'status': read(connector / 'status', 'unknown'),
                                   'enabled': read(connector / 'enabled', 'unknown')})
        gpu = dict(pci=device.name, vendor=vendor, name=names.get(device.name, vendor + ' graphics'),
                   driver=driver, driver_version=read(sysroot / 'module' / driver / 'version', 'Kernel driver'),
                   boot_vga=read(device / 'boot_vga') == '1', connectors=connectors,
                   vram_total=None, vram_used=None, uuid=uuids.get(device.name),
                   link=read(device / 'current_link_speed', 'Unknown') + ' × ' + read(device / 'current_link_width', '?'))
        for field, attribute in [('vram_total', 'mem_info_vram_total'), ('vram_used', 'mem_info_vram_used')]:
            value = read(device / attribute)
            if value.isdigit():
                gpu[field] = int(value) / (1024 * 1024)
        if device.name in nvidia:
            gpu['name'], total, used, gpu['driver_version'] = nvidia[device.name]
            for field, value in [('vram_total', total), ('vram_used', used)]:
                try:
                    gpu[field] = float(value)
                except ValueError:
                    pass
        result.append(gpu)
    return sorted(result, key=lambda gpu: (not any(c['enabled'] == 'enabled' for c in gpu['connectors']),
                                            not gpu['boot_vga'], gpu['pci']))


def recommendation(gpus):
    display = [g for g in gpus if any(c['status'] == 'connected' for c in g['connectors'])]
    alternatives = [g for g in gpus if g['vendor'] in ('AMD', 'Intel') and g not in display]
    if any(g['vendor'] == 'NVIDIA' for g in display) and alternatives:
        return ('An AMD/Intel GPU may be able to drive the desktop and leave more NVIDIA VRAM for games or AI. '
                'Move the monitor cable to that GPU first and refresh. A connected port is required for a desktop trial. '
                'Port names identify connectors, not their physical location on your case; memory savings are workload-dependent.')
    return ('Keep a monitor connected to the desktop GPU. Games can use render offload; compute applications '
            'select their own devices. Connected outputs do not prove which GPU renders every application.')


def offload_environment(gpu, gpus):
    if gpu['driver'] == 'nvidia':
        if sum(g['driver'] == 'nvidia' for g in gpus) != 1:
            raise ValueError('Multiple NVIDIA GPUs: automatic provider-to-PCI mapping is not verified. '
                             'Choose the provider in the application; this launcher will not guess.')
        return {'__NV_PRIME_RENDER_OFFLOAD': '1', '__GLX_VENDOR_LIBRARY_NAME': 'nvidia',
                '__VK_LAYER_NV_optimus': 'NVIDIA_only'}
    if gpu['driver'] in ('amdgpu', 'radeon', 'i915', 'xe', 'nouveau'):
        return {'DRI_PRIME': 'pci-' + gpu['pci'].replace(':', '_').replace('.', '_')}
    raise ValueError('Render offload is unavailable for this driver.')


def compute_environment(gpu):
    """Select one physical CUDA device without relying on unstable GPU indices."""
    uuid = gpu.get('uuid') or ''
    if gpu['driver'] != 'nvidia':
        raise ValueError('This device does not use the NVIDIA CUDA driver. Select it inside your '
                         'ROCm, OpenCL or other compute application; those device indices are not PCI indices.')
    if not re.fullmatch(r'GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', uuid):
        raise ValueError('A verified NVIDIA GPU UUID is unavailable. Refresh after repairing the driver; '
                         'GPU Manager will not guess a compute device index.')
    return {'CUDA_VISIBLE_DEVICES': uuid}


def xorg_config(gpu):
    if not PCI.fullmatch(gpu['pci']):
        raise ValueError('Invalid PCI address')
    domain, bus, slot = gpu['pci'].split(':')
    device, function = slot.split('.')
    bus_id = f"PCI:{int(bus, 16)}@{int(domain, 16)}:{int(device, 16)}:{int(function, 16)}"
    driver = {'amdgpu': 'amdgpu', 'radeon': 'radeon', 'i915': 'modesetting',
              'xe': 'modesetting', 'nvidia': 'nvidia'}.get(gpu['driver'])
    if not driver:
        raise ValueError('This GPU has no supported active desktop driver. Repair drivers first.')
    return (f'# Managed by Spaced GPU Manager; use Revert to restore the previous configuration.\n'
            f'Section "Device"\n    Identifier "SpacedDesktopGPU"\n    Driver "{driver}"\n'
            f'    BusID "{bus_id}"\nEndSection\n'
            'Section "Screen"\n    Identifier "SpacedDesktopScreen"\n'
            '    Device "SpacedDesktopGPU"\nEndSection\n'
            'Section "ServerLayout"\n    Identifier "SpacedDesktopLayout"\n'
            '    Screen 0 "SpacedDesktopScreen"\n    Option "AllowNVIDIAGPUScreens" "true"\nEndSection\n')


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.gpu-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def driver_reboot_pending(directory, boot, boot_started, runner=command):
    """Legacy recovery markers are empty; use their mtime, never a user's ack."""
    for name in ('reboot-required', 'recovery-reboot-required'):
        marker = directory / name
        if not marker.exists():
            continue
        values = dict(line.split('=', 1) for line in read(marker).splitlines() if '=' in line)
        if values.get('boot_id') == boot or marker.stat().st_mtime >= boot_started:
            return True
        if name == 'reboot-required' and not runner(['nvidia-smi', '-L']).strip():
            return True
    return False


class Trial:
    """Callers hold the shared driver lock. Root is injectable for isolated tests only."""
    def __init__(self, root=Path('/')):
        self.root = root
        self.state = root / str(STATE).lstrip('/')
        self.config = root / str(CONFIG).lstrip('/')

    def load(self):
        if not self.state.exists():
            return {}
        return json.loads(self.state.read_text())

    def save(self, state):
        atomic_write(self.state, json.dumps(state, indent=2) + '\n')

    def stage(self, gpu, boot):
        state = self.load()
        if state.get('phase') in ('staged', 'trial'):
            raise ValueError('Confirm or revert the existing desktop trial first.')
        if self.config.is_symlink():
            raise ValueError('The managed Xorg path is a symlink. Leave administrator configuration unchanged.')
        for path in [self.root / 'etc/X11/xorg.conf',
                     *(self.root / 'etc/X11/xorg.conf.d').glob('*.conf'),
                     *(self.root / 'usr/share/X11/xorg.conf.d').glob('*.conf')]:
            if path == self.config:
                continue
            if re.search(r'^\s*Section\s+"(?:Device|Screen|ServerLayout)"', read(path), re.I | re.M):
                raise ValueError(f'Custom Xorg layout in {path.name}; manual review is required.')
        expected = state.get('previous') if state.get('phase') == 'reverted' else state.get('candidate')
        if self.config.exists() and (not state or self.config.read_text() != expected):
            raise ValueError('The managed Xorg file has external edits. It will not be overwritten.')
        if not any(c['status'] == 'connected' for c in gpu['connectors']):
            raise ValueError('Connect a monitor to this GPU, then refresh before trying it as the desktop GPU.')
        candidate = xorg_config(gpu)
        state = dict(phase='staged', pci=gpu['pci'], staged_boot=boot,
                     previous=self.config.read_text() if self.config.exists() else None,
                     candidate=candidate)
        # Journal before configuration: a power loss is recoverable at every step.
        self.save(state)
        atomic_write(self.config, candidate)
        return state

    def revert(self):
        state = self.load()
        if state.get('phase') not in ('staged', 'trial', 'confirmed'):
            raise ValueError('No desktop assignment is available to revert.')
        if self.config.is_symlink():
            raise ValueError('Refusing to replace an administrator symlink.')
        current = self.config.read_text() if self.config.exists() else None
        if current not in (state['candidate'], state['previous']):
            raise ValueError('Xorg configuration changed outside GPU Manager; automatic rollback cannot overwrite it.')
        if state['previous'] is None:
            self.config.unlink(missing_ok=True)
            if self.config.parent.exists():
                directory = os.open(self.config.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
        else:
            atomic_write(self.config, state['previous'])
        state['phase'] = 'reverted'
        self.save(state)
        return state

    def begin_boot(self, boot):
        state = self.load()
        if state.get('phase') == 'staged' and state['staged_boot'] != boot:
            state.update(phase='trial', trial_boot=boot, deadline_boot_seconds=boot_seconds() + 180)
            self.save(state)
            return True
        return state.get('phase') == 'trial'

    def confirm(self, boot):
        state = self.load()
        if state.get('phase') != 'trial' or state.get('trial_boot') != boot:
            raise ValueError('Boot into the desktop trial before confirming it.')
        if boot_seconds() >= state.get('deadline_boot_seconds', 0):
            raise ValueError('The desktop trial has expired. Wait for recovery before trying again.')
        if self.config.is_symlink() or read(self.config) != state['candidate'].strip():
            raise ValueError('The trial configuration changed; confirmation is unsafe.')
        state['phase'] = 'confirmed'
        self.save(state)


def driver_lock(wait=False):
    path = Path('/var/lib/spaced-nvidia-installer/transaction.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
    except OSError:
        lock.close()
        raise ValueError('Another graphics operation is running. Try again after it finishes.')
    return lock
