# Spaced Linux help and community

Open **Spaced Linux Help** from the menu for Welcome's local Help tab, or read
[Spaced Help online](https://spacedlinux.com/help.html).

- [Discord community](https://discord.gg/BMW9Y6NB3y)
- [Telegram community](https://t.me/+pjmFzHo-i9A2ZWY5)
- [Report a reproducible issue](https://github.com/crhy/spaced/issues)

For desktop shortcuts and update guidance, see the
[website help source](../website/help.html). For testing status and the VM and
physical-hardware checks still required, see the
[11.26.1 release review](11.26.1-RELEASE-REVIEW.md). Community discussions and
bug reports should identify the Spaced version, whether it is a live or
installed session, and the steps that reproduce the problem.

## Use the live USB to rescue a PC

Boot the Spaced Linux stick and choose **Start Spaced Linux**. Nothing on the
disk changes until you do it. The live desktop signs itself in, and the file
`Live session passwords.txt` on the live Desktop repeats the same facts:

- Live user `user`, password `1`. Root account `root`, password `spaced`.
- `sudo` needs no password in the live session.
- Those accounts exist only on the live USB. An installed system uses the
  passwords you choose in the installer, and its root account is locked.

The recovery tools are on the stick only. The installer removes them, so an
installed system never gets them; an installed system keeps the GParted it
already has.

- **GParted** — see, resize, create and check partitions.
- **TestDisk** (`testdisk`, `photorec`) — recover lost partitions and files.
- **ddrescue** — copy a failing drive to a healthy one before doing anything
  else to it.
- **smartctl** — read the drive's own health report.
- `fsck` through `dosfstools`, `exfatprogs` and `ntfs-3g`, plus `cryptsetup`,
  `lvm2`, `parted` and `rsync` — check FAT/exFAT/NTFS volumes, open encrypted
  volumes and LVM groups, and copy what you have recovered elsewhere.

## Troubleshooting guides

- [Network Servers is empty / cannot open a Windows share](troubleshooting/network-servers.md):
  real-network test checklist for mDNS/DNS-SD and WS-Discovery browsing,
  direct `smb://` connections, diagnostics, and what to include in a bug
  report.
