#!/usr/bin/python3
"""Read-only CUDA device selection test; no context, kernel or driver changes."""
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'overlays/usr/lib/spaced-linux'))
from spaced_gpu import compute_environment, discover, normalize_pci

# CUDA reads the environment at initialization; use a fresh process per GPU.
probe = '''
import ctypes as c
import json
cuda = c.CDLL('libcuda.so.1')
def check(result):
    if result:
        raise RuntimeError('CUDA driver returned ' + str(result))
check(cuda.cuInit(0))
count = c.c_int()
check(cuda.cuDeviceGetCount(c.byref(count)))
devices = []
for ordinal in range(count.value):
    device = c.c_int()
    check(cuda.cuDeviceGet(c.byref(device), ordinal))
    pci = c.create_string_buffer(32)
    check(cuda.cuDeviceGetPCIBusId(pci, len(pci), device))
    devices.append(pci.value.decode())
print(json.dumps(devices))
'''
cards = [card for card in discover() if card['driver'] == 'nvidia' and card.get('uuid')]
if not cards:
    raise SystemExit('SKIP: no NVIDIA GPU UUIDs available')
for card in cards:
    result = subprocess.run([sys.executable, '-c', probe],
                            env={**os.environ, **compute_environment(card)},
                            capture_output=True, text=True, timeout=30, check=True)
    visible = [normalize_pci(pci) for pci in json.loads(result.stdout)]
    assert visible == [card['pci']], (card['pci'], visible)
    print(f"PASS: {card['name']} → CUDA device 0 → {visible[0]}")
