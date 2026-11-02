---
name: spacedrgb-lcd-ghosting
description: Lian Li GA II Vision LCD panel is faulty (holds images after 30 s); RMA advised. Spaced RGB got Clean LCD (10 min) and looping video (2026-10-31)
metadata:
  type: project
---

rhY's cooler (USB 0416:7395) is a **Galahad II Vision** per its firmware (`CA_II-Vision V2.01.041, 1.6`), not the "Galahad II LCD" that Spaced RGB's code/docs name.

2026-10-31: the boot logo and old digits ghosting through every image also appeared under the upstream sgtaziz/lian-li-linux v1.2.4 driver, so it is not a Spaced RGB bug. Upstream's `lianli-daemon lcd clean` (pixel conditioning, 75% brightness, H.264 animation) cleared it; rhY saw it gone after about 10 minutes (stopped at 12.5 min).

**Why:** this was the open Spaced RGB LCD defect; docs/ga2-firmware-protocol.md suspected panel damage/RMA.
**How to apply:** Spaced RGB should get a "Clean LCD" button, **10 minutes by default** (rhY's choice), with progress and Stop, optional longer pass. Upstream is MIT (Spaced RGB is GPLv3): reuse is fine with credit in THIRD_PARTY.md. Test kit (unpacked, never installed: the .deb depends on systemd) is in `~/lianli-test`; it needs `/run/lianli-daemon.lock` + `/run/lianli-control.lock` (mode 0666, made with sudo, gone after reboot). Fix the model name in the docs. Spaced RGB lives in ~/spaced-10.26/components/spacedrgb. Related: [[spaced-no-systemd]].

**Later the same night (verdict):** a labelled colour test card showed every colour correctly, so our H.264 data is right (the "negative" look was the old S image stuck on the panel). After only 30 s on screen the test card was still ghosting through the next video, which healthy LCDs don't do: the panel is faulty, RMA advised. Shipped in the repo (uncommitted at first) and copied to `~/.local/share/spaced-rgb` (backup `~/lianli-test/spaced-rgb-installed-backup.tgz`): **Clean LCD (10 min)** and **Video (loops)** (24 fps, first 30 s, converted with libx264 and split at access unit delimiters).

**RMA filed 2026-10-31** via Lian Li support form (GA II LCD SL-INF 360, white, serial C5717240319101413, no invoice: bought on Amazon by a client of rhY). Evidence and texts in `~/lianli-test/rma/`. Also reported: not all SL-INF fan LEDs light.
