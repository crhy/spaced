---
name: spaced-never-means-never
description: On Spaced Linux, a user-facing "Never" setting must be absolute, even when honouring it costs related behaviour like the idle screen lock.
metadata:
  pinned: false
---

# On Spaced Linux, "Never" means never

When a Spaced Linux setting offers "Never", it has to actually mean never, and
that outranks whatever related behaviour has to be given up to achieve it.

This came up fixing issue #189, where choosing "Never" for display sleep still
let the screen go dark after five minutes. The cause was that MATE splits the
behaviour across two subsystems: mate-power-manager honours the display-sleep
choice correctly and never touches DPMS without a timeout, but mate-screensaver
activates on its own `org.mate.session idle-delay` — five minutes by default —
and blanks the screen regardless. Nothing in Power Preferences can reach that
key, so "Never" had never worked in any release.

The fix makes "Never" suspend the screensaver's idle activation. In MATE the
idle blank and the idle lock are the same activation, so this necessarily also
suspends auto-lock while Never is selected. I flagged that trade-off and
offered to preserve the lock instead; rhY's answer was: "No, never should mean
never."

The general lesson is that when honouring an absolute user choice conflicts
with a secondary convenience or even a security-adjacent default, honour the
choice and say plainly what it costs. Do not quietly water the setting down to
preserve the other behaviour, and do not leave the setting broken because a
faithful implementation has a side effect.
