NVIDIA Installation, Rollback, and Recovery Guide
===================================================

## Quick Start

1. Open **Spaced NVIDIA Driver Installer** from the Applications menu or run:
       spaced-nvidia-installer
2. Click "Check Everything and Install" — prerequisites are verified before Nouveau is disabled.
3. When installation and verification succeed, reboot your computer.
4. After login, a second verification checks the running NVIDIA desktop (kernel driver, OpenGL, Compiz).

If everything passes you're done. Sections below cover troubleshooting.

## How Installation Works

The installer follows this verified transaction pipeline:

 1. Detect GPU via `lspci`
 2. Confirm amd64 architecture and free disk space (&gt;= 2 GB root, &gt;= 200 MB /boot)
 3. Download and install exact kernel headers (`linux-headers-$KERNEL`)
 4. Enable NVIDIA's official Debian repository via cuda-keyring
 5. Use `nvidia-driver-assistant` to select the recommended driver (branch 610)
 6. Build DKMS modules, verify module policy, rebuild initramfs
 7. Disable Nouveau blacklist in modprobe.d, write nvidia_drm modeset=1 GRUB args
 8. Install renderer-aware Compiz launcher
 9. Full pre-reboot verification — if any check fails, automatic rollback to Nouveau

Nouveau is **not** disabled until steps 5-8 all succeed.

## Recovery via SSH (Black Screen or No Display)

If the system boots but shows no graphical output:

1. Access via SSH (openssh-server is pre-installed).
2. Check what went wrong — logs are at:
       /var/log/spaced-nvidia-installer.log          # GUI installer log
       /var/lib/spaced-nvidia-installer/runs/        # Per-run backup + install.log
3. Inspect running drivers:
       lspci -nnk -d 10de:            # PCI binding
       lsmod | grep nvidia             # kernel module status
4. If Nouveau is needed, restore it manually:
       pkexec /usr/lib/spaced-linux/spaced-nvidia-helper --rollback
   Or run the same from the GUI app's "Restore Nouveau" button when desktop works.

## Manual NVIDIA Removal

If the helper script is unavailable:

  sudo apt purge 'nvidia-*' 'libnvidia-*' 'xserver-xorg-video-nvidia' \
      firmware-nvidia-gsp glx-alternative-nvidia nvidia-alternative \
      libglx-nvidia libegl-nvidia libgl1-nvidia
  sudo apt install --reinstall xserver-xorg-video-nouveau libgl1-mesa-dri libglx-mesa0

## Restore Old Graphics Configuration

The installer saves a full backup before making changes:

   /var/lib/spaced-nvidia-installer/runs/YYYYMMDD-HHMMSS/backup/config.tar     # config files
                                                         /packages-before.txt    # installed packages list
                                                         /new-nvidia-packages.txt # NVIDIA deb packages added

Restore manually if needed:

  RUN_DIR=/var/lib/spaced-nvidia-installer/runs/<latest-run>
  sudo tar -C / -xpf "$RUN_DIR/backup/config.tar"

## DKMS Failure Recovery

If kernel modules failed to build for your running kernel:

1. Verify headers match the running kernel:
       uname -r                    # e.g. 6.12.9-amd64
       dpkg -l | grep linux-headers
   Headers **must** match exactly (`linux-headers-6.12.9-amd64`).

2. Check DKMS log for errors:
       ls /var/lib/dkms/nvidia/*/build/make.log
       cat /var/lib/spaced-nvidia-installer/runs/.../install.log   # last 30 lines may reveal the issue

3. If a kernel update broke things, uninstall old NVIDIA modules and get matching headers:
       sudo apt install "linux-headers-$(uname -r)"
       sudo dkms autoinstall -k $(uname -r)
       sudo depmod -a "$(uname -r)"
       sudo mkinitramfs -o /boot/initrd.img-"$(uname -r)"

## Secure Boot Limitations

NVIDIA DKMS modules **cannot** be signed automatically under Secure Boot. The installer checks `mokutil --sb-state` before starting and will refuse to run if Secure Boot is enabled (error code 10).

To proceed: disable Secure Boot in your UEFI/BIOS firmware settings, reboot Spaced Linux normally, then rerun the installer.

## Error Code Reference

| Code | Meaning |
|------|---------|
| 10   | Secure Boot is enabled — must be disabled before installing GPU drivers |
| 11   | Only amd64 hardware is currently supported by this installer |
| 12   | No NVIDIA graphics card detected via lspci (check with `lspci -nn \| grep nvidia`) |
| 13   | Cannot identify the desktop user account that will use GPU acceleration |
| 14-15| Insufficient free disk space — need 2 GB root, 200 MB /boot |
| 16   | Package manager could not refresh indexes — check network connection |
| 20   | Exact kernel headers for your running kernel are missing from the APT repository |
| 21-24| Required Devuan or NVIDIA package is unavailable or installation failed |
| 30   | Driver installation failed; Nouveau was automatically restored as rollback |
| 40   | DKMS did not produce expected modules for this kernel; check `/var/lib/dkms/nvidia/*/build/make.log` |
| 41   | Boot image (initramfs) could not be rebuilt or inspected — driver state is unknown, Nouveau restored |
| 42-47| Module policy, initramfs content, Xorg/GLX libraries, Compiz launcher, or GRUB configuration failed a specific verification check; Nouveau restored automatically when possible |
| 50   | Attempted reboot without a prior verified installation — nothing to activate on next boot |
| 51   | No NVIDIA transaction is available to roll back — no saved state found in `/var/lib/spaced-nvidia-installer/` |

## Supported Hardware Policy

The installer runs `nvidia-driver-assistant --distro Debian:<version> --branch 610` against the running kernel. The recommended driver branch targets NVIDIA GeForce GTX and newer GPUs (GTX, RTX series). Drivers that cannot be selected for your GPU model will trigger error code 24 — attempt with the default branch or consult the [NVIDIA Linux Driver Support](https://www.nvidia.com/Download/index.aspx) page.

## Post-Reboot Verification

After rebooting into an NVIDIA installation, Spaced Linux automatically runs:
- PCI driver binding check via `lspci -nnk`
- `nvidia-smi` communication test
- `lsmod` module presence (nvidia loaded, nouveau unloaded)
- OpenGL renderer string verification (`glxinfo -B` must show NVIDIA)
- Compiz active window manager confirmation
- MATE panel and Caja process check

Verification logs are stored at:
   ~/.cache/spaced-nvidia-installer/         # verified-* / failed-*.log files

If verification fails, the system offers to restore Nouveau and reboot.
Detailed failure information is saved under `~/.cache/spaced-nvidia-installer/failed-<id>.log`.