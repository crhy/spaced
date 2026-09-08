# Spaced Video Drivers: installation and recovery

Open **Spaced Video Drivers** from the menu or run `spaced-nvidia-installer`.
Use **Check Graphics** to collect a read-only report before changing drivers.
It includes PCI IDs, connected displays, desktop and NVIDIA PRIME renderers,
kernel boot arguments, and AMD TearFree configuration. **Copy Log** copies the report.

Choose **Install NVIDIA Driver** on supported NVIDIA hardware, or **Update AMD
Drivers** on AMD hardware. Finish all updates in Spaced Update and reboot into
the updated kernel first. The NVIDIA installer requires matching kernel headers
and rejects Secure Boot until it is disabled in firmware. Spaced does not manage
MOK enrollment automatically.

The NVIDIA path checks free space, verifies NVIDIA's downloaded repository
keyring package against its SHA-256, refreshes authenticated APT metadata,
and checks every NVIDIA display PCI ID against the support database supplied
by the signed `nvidia-driver-assistant` package. It accepts one validated
package recommendation and installs it with APT's removal prohibition.
Package conflicts stop the operation for review. There is no forced driver branch.

NVIDIA's upstream assistant selects a module flavor but can recommend the latest
package even for a legacy GPU. Spaced checks `legacybranch` separately: GT 730
Fermi variants require 390.xx; Kepler variants require 470.xx. These are not
compatible with the current repository driver. Such cards keep their existing
driver; unknown PCI IDs also stop safely. A modern card's successful check does
not override a second incompatible GPU. A 4K or five-monitor limit still requires
the actual connector, EDID, cable and PCI variant to diagnose.

Before offering reboot, the installer checks DKMS modules for the running
kernel, modprobe policy, initramfs, Xorg libraries, GRUB and the maintained
Compiz launcher. A failed transaction attempts recovery and reports any step
that did not complete. Do not assume recovery succeeded from the original
error code: **error 52 means recovery remains incomplete**, and no automatic
reboot is offered.

After reboot, startup checks verify NVIDIA PCI binding, `nvidia-smi`, loaded
modules, hardware OpenGL, Compiz, MATE panel and Caja. Hybrid Intel/AMD systems
may correctly render the desktop on the integrated GPU; a separate NVIDIA
PRIME test verifies the discrete GPU. Verification is tied to the individual
installation, so a successful reboot does not cause repeated reboot prompts.

If the screen is black, try a text console with **Ctrl+Alt+F2**. SSH is another
option only if you previously enabled and secured an SSH server; it is not
installed by default on the installed OS. From the console, inspect:

```sh
sudo tail -100 /var/log/spaced-nvidia-installer.log
lspci -nnk -d 10de:
sudo dkms status
```

To recover the last transaction, choose **Restore Graphics** in the application,
or run this from the console:

```sh
sudo /usr/lib/spaced-linux/spaced-nvidia-helper --rollback
```

The helper records its work under `/var/lib/spaced-nvidia-installer/runs/`.
Each run contains `configuration.json`, the installed package list and previous
NVIDIA package versions. Recovery attempts to restore those exact versions,
removes newly added driver packages, and restores only files changed by that
transaction. Later administrator edits and unrelated files remain intact.
The CUDA repository source and public key are included in that backup. Missing
old packages, missing backups, or boot-image failures require attention before
reboot; blanket package purges and extracting an old full-system config archive
are not recovery steps for this release.

For DKMS build failures, inspect `/var/lib/dkms/` for the NVIDIA build's
`make.log`, compare `uname -r` with installed `linux-headers` packages, and
include the log in a support request. Kernel compatibility needs an actual
successful module build; a package download alone does not establish it.

| Code | Meaning |
| --- | --- |
| 10 | Secure Boot enabled; disable it before using this installer |
| 11–15 | Unsupported architecture, absent GPU/user, or insufficient disk space |
| 16–17 | Repository refresh failed or another graphics transaction is running |
| 20–23 | Headers, prerequisites, verified repository keyring, or assistant unavailable |
| 24 | Unsupported/unknown GPU or invalid package recommendation |
| 30 | Driver APT transaction failed; review the separate recovery result |
| 40–47 | Module, initramfs, Xorg, Compiz or GRUB verification failed |
| 50–51 | No verified reboot state or saved recovery transaction |
| 52 | Recovery incomplete; repair the reported failures before reboot |

Postboot details are saved in `~/.cache/spaced-nvidia-installer/verified-*`
or `failed-*.log`. Hardware reports should include the OS version, complete
PCI IDs, connection types and these logs.

AMD issue [#177](https://github.com/crhy/spaced/issues/177) is addressed by
`/etc/X11/xorg.conf.d/20-spaced-amdgpu.conf`: an AMDGPU-only `OutputClass`
enables `TearFree`. It carries the reporter's option while preserving automatic
GPU and monitor discovery. The native update package delivers the same file
to older installations. Reboot or log out and back in to apply it, then inspect
`xrandr --verbose` for the connected outputs' TearFree state. RX 7600 scrolling,
gaming and resume still require physical-hardware validation.

[Online help](https://spacedlinux.com/help.html) ·
[Discord](https://discord.gg/BMW9Y6NB3y) ·
[Telegram](https://t.me/+pjmFzHo-i9A2ZWY5)
