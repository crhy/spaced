---
name: spaced-no-systemd
description: Spaced Linux is Devuan-based and sysvinit-only; systemd must never be introduced, and even naming it as a design reference is unwelcome.
metadata:
  pinned: false
---

# Spaced Linux has no systemd, and that is non-negotiable

Spaced Linux is built on Devuan Ceres and runs sysvinit with elogind. rhY
treats the absence of systemd as a defining property of the distribution
rather than a preference: "And remember, this is devuan. THERE IS NO SYSTEMD.
If any of this OS has been tainted by systemd, we'll have to start over from
scratch."

The practical consequences when working on Spaced Linux:

- Never propose, install, or depend on systemd, systemd-sysv, or any component
  that would pull them in. The Spaced Update privileged helper already refuses
  any APT plan containing `Inst systemd`, `Inst systemd-sysv`, `Inst
  runit-init` or `Inst openrc`, and that guard exists for exactly this reason.
- Solve init- and session-level problems with sysvinit mechanisms: `/etc/init.d`
  scripts, `/etc/default/rcS` (sourced by `/etc/init.d/rc` before any service
  starts), PAM via `/etc/security/limits.d`, and elogind. There is no
  `journalctl`, no `systemctl`, and no user-level systemd, so tools and
  diagnostics must not assume them.
- Do not reach for systemd even as an explanatory analogy. I described a piped
  `core_pattern` — a plain kernel feature — by noting that systemd-coredump
  relies on it, and that alone prompted the warning above. Explain such
  mechanisms on their own terms instead.

When something on a Spaced machine looks like it may have pulled in systemd,
check it and report the finding explicitly rather than assuming it is benign,
because rhY considers contamination grounds for rebuilding the OS.
