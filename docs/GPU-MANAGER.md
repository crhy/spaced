# Spaced GPU Manager — local candidate

Working-tree candidate for 11.26.3 / #426, not a published release. The application
is now named **Spaced GPU Manager**. Existing `spaced-gpu-driver-manager` and
`spaced-nvidia-installer` commands remain compatible.

## Try the read-only preview first

From `/home/rhy/spaced1126`, in a normal desktop terminal:

```sh
python3 overlays/usr/lib/spaced-linux/spaced-gpu-manager.py --preview
```

Preview reads actual PCI devices, drivers, VRAM and monitor connections. It does
not install drivers, change Xorg, restart the desktop or require root. Privileged
buttons are disabled. Source-tree launches automatically use preview mode.

## Install the candidate for interactive testing

Save work first. The existing maintainer installer now installs the complete GPU
Manager and registers its SysV recovery service without starting it or changing
the current graphics configuration:

```sh
sudo bash scripts/spaced-nvidia-installer.sh
spaced-gpu-manager
```

The installer prints its backup directory under `/root`. This is a local source
installation, not an APT release. Drivers & Recovery opens the existing driver
installer/recovery UI; merely installing or opening the manager does not install
a driver. Do not run the installer during an existing driver operation or trial.

## Desktop trial safety and test sequence

1. Check the inventory against the physical cards and ports. PCI addresses, not
   NVIDIA enumeration indices, are the identity. Connected does not necessarily
   mean active scanout; the UI distinguishes these observations.
2. Connect a monitor to the intended desktop GPU, refresh, and choose **Use for
   Desktop**. Existing custom Device/Screen/ServerLayout Xorg sections are refused
   for manual review. Only the manager-owned Xorg file can be changed.
3. Save all work and reboot. Log in promptly and select **Keep This Desktop**.
   Administrator authentication must complete within **three minutes of service
   startup**, not three minutes after login. Do not start other work during the
   trial. The confirmation window opens automatically in the new session.
4. Without confirmation, the guard restores the previous configuration and
   restarts LightDM, ending the trial session. If the screen is black, wait for
   that recovery, then reconnect the monitor to the previous GPU if necessary.
   A second boot with an unconfirmed trial also triggers rollback.
5. **Revert** restores the previous configuration without immediately terminating
   the session; reboot when ready. For recovery from a text console:

   ```sh
   sudo /usr/lib/spaced-linux/spaced-gpu-helper revert
   sudo reboot
   ```

Do not deliberately test a broken desktop until a working text console or SSH
recovery route is available. The guard cannot repair a kernel hang, failed boot,
or administrator edits made after staging. It deliberately refuses to overwrite
such edits. Driver transactions and desktop trials share a lock; pending trials
block driver changes, and pending driver reboots block new desktop trials.

## Implemented and remaining gray areas

- Inventory and VRAM readings work on the local 4070 Ti SUPER, 3050 OEM and
  Radeon 610M. The 4070's connected HDMI port is correctly associated with it.
- Desktop assignments are journaled and recoverable, but real reboot, cable
  movement, confirmation and black-screen rollback still require local testing.
- Games/Offload provides launch settings for Mesa PCI selection and a single
  proprietary NVIDIA device. Multiple proprietary NVIDIA devices are explicitly
  refused until PCI-to-RandR-provider mapping is verified; no guessed indices.
- AI/Compute currently explains application-specific device selection; it does
  not assign devices to applications or install CUDA/ROCm. Desktop assignment
  does not disable another GPU's compute capability.
- Hard GPU power-off is not implemented. Neither compute assignment nor hard-off
  is represented as an operational role toggle.
- Before release, measure desktop VRAM before/after under equivalent workloads,
  verify the actual renderer, test game offload and driver recovery, and exercise
  the timeout and manual revert on real hardware. Moving the desktop does not
  promise a particular VRAM saving.

## Automated evidence

Full host suite: 540 tests passed, including 34 GPU Manager tests. These cover
PCI normalization, offload refusal, Xorg preservation, journaling, reboot
interlocks, confirmation, rollback and watchdog restart behavior. The GTK/Xvfb
smoke test detects three local GPUs and verifies an 880 × 680 preview window.
`scripts/check.sh` passes. These are not substitutes for the physical trial gates.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 xvfb-run -a python3 scripts/tests/test-gpu-manager-ui.py
bash scripts/check.sh
```
