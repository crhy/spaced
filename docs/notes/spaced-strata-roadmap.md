---
name: spaced-strata-roadmap
description: "rhY 2026-11-20 order of work after the harness bench: Spaced Monitor GPU cards, then 11.26.3 with Strata (xkill red X for good), plus Spaced improvement ideas for Strata."
metadata:
  node_type: memory
  type: project
  originSessionId: 0e54f68b-6566-5723-9f47-c2fdc50a1de4
  modified: 2026-11-20T10:17:58.454Z
---

**Order (rhY 2026-11-20):** 1) harness benchmark (f157 kit, then run-all with the fleet paused) and the thermal check;
2) Spaced Monitor: cards for the second GPU ([[spaced-monitor-issue385]]); 3) Strata works Spaced 11.26.3: the milestone issues
([[spaced-11263-release]]) and **#422 xkill red X - must NEVER regress again**; 4) the improvement ideas below, as issues/tasks.

**xkill root cause (2026-11-20, posted on crhy/spaced#422):** the red X exists only as `pirate` in the Spaced-Cursors theme; the
active cursor theme is Adwaita (Xcursor.theme + org.mate.peripherals-mouse cursor-theme). Adwaita has no `pirate`, so libXcursor
falls back to the X server's cursor font glyph 88 = the skull. Any theme switch/reset brings the skull back. Earlier attempt f110
(replace the server cursor font) aborted with no changes. Permanent fix = all layers: (a) Ctrl+Alt+X runs a Spaced wrapper with
`XCURSOR_THEME=Spaced-Cursors` for xkill; (b) the red X also in the server's cursor font (f110's idea: bdftopcf font + Xorg
`-cursorfont` via lightdm), so even the fallback is right; (c) a release-gate test under Xvfb with Adwaita selected that fails the
ISO build if xkill's cursor is not the red X; (d) theme switching must never drop it.

**Spaced improvements Strata can work on (Claude's list, 2026-11-20):**
1. Desktop stays responsive when an app locks lots of RAM: ship `vm.min_free_kbytes` scaled to RAM in /etc/sysctl.d (bigboy froze
   ~1 min while Strata pinned 45 GiB; 1 GiB fixed it).
2. nvidia-persistenced sysvinit script (no systemd): keeps nvidia-smi/driver answering on multi-GPU boxes (nvidia-smi failed
   right after a 45 GiB engine stopped).
3. Drive temperatures: load `drivetemp` at boot so SATA disks show in sensors/Spaced Monitor (none show today).
4. Daemon supervision for sysvinit (spaced-theme-monitor died silently, #398): a small respawn wrapper for Spaced's desktop daemons.
5. Release regression suite: every past high-priority fix (xkill red X, fire shortcut #421, theme follow, LUKS boot) as an
   automated ISO gate, so fixed things stay fixed.
6. Bazaar: prefer AppImage when the flatpak is broken - OrcaSlicer (#423) like FreeCAD (spacedbazaar#35).
7. #424 benchmark vs other OSes: Strata can build the reproducible benchmark kit (boot time, idle RAM, app start, gaming FPS).
8. #417 migration assistant from Devuan/Debian/Ubuntu: design doc + dry-run script that lists what would change.
9. Hardware advisor in Spaced Monitor/Welcome: flag mixed DIMMs running at fallback speed, GPUs in x4 slots, missing GPU arch
   support - things found the hard way on bigboy.
10. Cgroup note: elogind leaves the memory controller off (valid, no limit); keep it so, but document for app developers
   (Strata's RAM-mode bug came from assuming systemd cgroups).
11. **GPU roles (rhY asked 2026-11-20):** desktop/Compiz on the CPU's iGPU, discrete GPU free for AI/games. bigboy facts: Radeon 610M
   (Raphael, 1002:164e, amdgpu loaded, X provider "AMD Ryzen 7 7800X3D", outputs card0 DP-1/HDMI-A-1); today the 1080p monitor is on
   the 4070's HDMI-0 and Xorg+Compiz hold ~310 MiB of its VRAM. Plan: monitor on the board port, xorg.conf.d PrimaryGPU on amdgpu,
   games via PRIME render offload (__NV_PRIME_RENDER_OFFLOAD=1, __GLX_VENDOR_LIBRARY_NAME=nvidia; Vulkan picks NVIDIA) set by
   default for Steam/Lutris/Wine. Costs: few % game FPS + frame-copy latency, no NVIDIA G-Sync/VRR, board-port refresh limits.
   Next: rhY moves the cable; Claude writes the snippet and measures VRAM/tok/s freed; then a Spaced "GPU roles" task for Strata.
