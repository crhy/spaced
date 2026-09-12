# Diagnosing mounted-share icons, GIMP crashes, and video wallpaper

Investigation date: 2026-09-12. These findings and source fixes are not release
approval. Reproduce on the affected machine before attributing a failure to a
particular GPU, application, or saved setting. Redact share addresses,
usernames, private paths, and image contents before posting diagnostic output.

## Mounted-share desktop icons (#184)

### Evidence and disposition

The reporter still lacked icons after updating and rebooting into 9.26.1;
looking in the Desktop folder did not find shortcuts. The title calls Gigolo a
Flatpak, but the actual installation was not identified.
[Reporter follow-up](https://github.com/crhy/spaced/issues/184#issuecomment-5636184554).

This repository installs native `gigolo`, `caja`, and `gvfs-backends` through
`config/packages.yaml`. Its schema override enables
`org.mate.caja.desktop volumes-visible` and
`org.mate.background show-desktop-icons`. Defaults do not establish the
reporter's effective per-user settings or mount visibility.

Caja creates **virtual** desktop links from its session's `GVolumeMonitor`.
They are not shortcut files in the XDG Desktop directory. A mount must reach
that monitor, not be shadowed, and pass the volume-visibility setting before
Caja creates a link. An empty Desktop directory therefore does not distinguish
an absent mount from an off-screen virtual icon.
[Caja 1.26.4 link monitor](https://github.com/mate-desktop/caja/blob/v1.26.4/libcaja-private/caja-desktop-link-monitor.c).

There was also a concrete limitation in the existing Spaced repair mechanism:
`spaced-desktop-icon-repair` rewrites Caja's `desktop-metadata` file, whereas
Caja 1.26.4 loads that file once into a process-lifetime `GKeyFile`. Later
metadata saves write that cache back. An external edit neither invalidates
the cache nor updates the live virtual icon and can be overwritten. The
Applications-phase repair autostart runs after Caja's Desktop phase. Its
successful disk-edit tests and “Re-placed” message are **not** evidence of a
live mount-icon repair.
[Caja metadata implementation](https://github.com/mate-desktop/caja/blob/v1.26.4/libcaja-private/caja-desktop-metadata.c).

**Disposition: fixed in 9.26.2 source; affected-system acceptance required.**
A new one-shot autostart runs the repair in MATE's Panel phase. For every phase
before Applications, `mate-session-manager` keeps the process pending and does
not advance until it registers or exits. The short repair exits before the
Desktop phase starts Caja, making the metadata edit ordered rather than merely
asynchronous. The existing Applications-phase watcher remains for monitor
changes after login. This does not force Caja to reload virtual-icon metadata
after a live hotplug, so the five-monitor logout/login and reduced-monitor
acceptance checks remain release gates. The fix does not reset preferences,
create duplicate launchers, or kill Caja.
[MATE 1.26.1 startup phase implementation](https://github.com/mate-desktop/mate-session-manager/blob/v1.26.1/mate-session/gsm-manager.c).

### Reproduction and validation

In a terminal belonging to the affected MATE session, before and after
connecting the same share through Gigolo, collect:

```sh
command -v gigolo
dpkg-query -W gigolo caja gvfs gvfs-backends
flatpak list --app --columns=application,version,installation
gsettings get org.mate.caja.desktop volumes-visible
gsettings get org.mate.background show-desktop-icons
gsettings get org.mate.background draw-background
xrandr --query
gio mount -li
```

Use the installed `python3-gi` binding to inspect the same host-session mount
properties Caja tests; this does not mount or unmount anything:

```sh
/usr/bin/python3 - <<'PY'
from gi.repository import Gio
for mount in Gio.VolumeMonitor.get().get_mounts():
    print(mount.get_name(), mount.get_root().get_uri(),
          'shadowed=' + str(mount.is_shadowed()))
PY
```

1. Verify whether the share exists in the host session's mount list. If it
   does not, investigate Gigolo's actual native/sandbox deployment and GVFS
   backend/authentication before touching icon positions. If shadowed, identify
   the replacement mount. These are distinct from an off-screen layout fault.
2. Save a private copy of
   `${XDG_CONFIG_HOME:-$HOME/.config}/caja/desktop-metadata` and the active
   monitor geometry. Compare the share's `caja-icon-position` with active
   rectangles, not the bounding box of monitors with gaps between them.
3. Reproduce the cache limitation in a disposable MATE account/VM: mount a
   test share, stop the repair watcher in that test session, and move a visible
   virtual icon to force Caja to load its metadata. Remove only that icon's
   saved position from the disk file while Caja stays running. A live icon
   update is not expected. Move a different virtual icon and inspect the file
   for the cached position being written back. Do not run this against a real
   user's active transfers or carefully arranged desktop.
4. For an offline-position comparison, save work and fully log out the test
   user. From another account, back up the test user's metadata, remove only
   the suspect position while that user's Caja is absent, then log in with
   the same monitor geometry and reconnect the share. A successful comparison
   supports the position hypothesis; it does not validate runtime hotplug.
5. A candidate fix must show each mounted share once, survive disconnect and
   reconnect, preserve on-screen icon placement, and recover after changing
   from five monitors to fewer and back, as well as logout/login. Check both
   new and upgraded users and retain before/after geometry and mount evidence.

## GIMP Flatpak scale-dialog crash (#164)

### Evidence and disposition

The report describes a crash when changing scaling units from pixels to
percent, continuing with a newer GIMP Flatpak on 9.26.1. It contains no
backtrace, failing image, exact Flatpak commit, or complete interaction
sequence. That is insufficient to identify a driver or GIMP code defect.
[Issue and follow-up](https://github.com/crhy/spaced/issues/164#issuecomment-5638156823).

The checkout contains no GIMP implementation or patch. Its Flatpak wrapper
passes the ordinary `run org.gimp.GIMP ...` invocation to `/usr/bin/flatpak`;
the new boundary tests verify argument, environment, output, and exit-status
preservation using a fake executable, not a simulated GIMP GUI.

Read-only inspection of this workstation found system-installed GIMP **3.2.6**,
runtime `org.gnome.Platform/x86_64/50`, app commit
`2606888d8a6caf8229f5c6e77b2f0b7f72498d0973a9e89adc6280983f6efbcb`.
`readelf -d` on its `files/bin/gimp-3.2` lists `libgtk-3.so.0` and
`libgdk-3.so.0`. This is not the reporter's environment. GIMP's help command
was run successfully; a fresh scale-dialog GUI reproduction was not performed
in this investigation. The older software-rendered non-reproduction recorded
in the repository does not cover this build or the affected hardware.

`GSK_RENDERER=cairo` selects a **GTK4 GSK** renderer, not this GTK3 application's
renderer. Do not present it as a GIMP fix or a meaningful GPU isolation test.
Nor does the current evidence establish that the scale dialog uses OpenGL.
[GTK4 renderer documentation](https://docs.gtk.org/gtk4/running.html#gsk-renderer).

**Disposition: unresolved; needs application/runtime crash evidence.** Route
a reproducible stack to GIMP or Flathub as appropriate; do not downgrade the
runtime, replace the Flatpak with a native package, or add global rendering
overrides without that evidence.

### Reproduction and validation

Save work and close other GIMP instances first. Keep the initially failing
deployment unchanged while collecting evidence:

```sh
/usr/bin/flatpak info org.gimp.GIMP
/usr/bin/flatpak info --show-permissions org.gimp.GIMP
/usr/bin/flatpak override --user --show org.gimp.GIMP
/usr/bin/flatpak override --system --show org.gimp.GIMP
uname -r
```

If there are both user and system installations, add the appropriate `--user`
or `--system` selector to all Flatpak commands and identify the failing one.
Capture a private log from a terminal using Bash:

```bash
umask 077
log=$(mktemp "${TMPDIR:-/tmp}/gimp-scale.XXXXXXXX.log")
/usr/bin/flatpak run org.gimp.GIMP --new-instance --verbose \
    --stack-trace-mode=always >"$log" 2>&1
status=$?
printf 'Exit status: %s\nLog: %s\n' "$status" "$log"
```

These options were verified with the installed application's `--help` and
[GIMP's option definitions](https://github.com/GNOME/gimp/blob/GIMP_3_2_6/app/main.c).
A debug-symbol/runtime setup may still be needed for a useful stack; the
absence of a trace does not disprove a crash. On this sysvinit distribution,
do not assume `journalctl` or `coredumpctl` is available. Include relevant
kernel messages from `/var/log/kern.log` or permitted `dmesg` access if an OOM
kill, segmentation fault, or GPU reset occurs.

1. Create a new 1920×1080 RGB image. Open **Image → Scale Image**, switch the
   width/height unit from px to percent and back five times, then try a 50%
   scale. Record whether the crash occurs on unit selection or on applying
   the scale, along with interpolation, precision, profile, and locale.
2. Repeat with the smallest non-private image that triggers the failure. If
   “scale” means a different tool/dialog, record that exact path instead.
3. Compare the absolute `/usr/bin/flatpak` invocation with the normal `flatpak`
   command on the same commit. If both crash identically, the Spaced launch
   wrapper is not a distinguishing factor.
4. Use a separate test account for a clean-profile comparison; do not delete
   or rename the user's GIMP profile as an automatic repair. Record GPU model,
   driver version, monitor geometry, runtime commit, and desktop compositor.
   Only pursue software-rendering experiments appropriate to the implicated
   graphics API/driver after a trace identifies that path.
5. Accept a candidate fix only when the original reproducer and image pass
   on the affected machine, repeated toggles and scaling succeed, and the
   same test passes with a clean profile. Record old/new app and runtime
   commits rather than attributing an unrelated app update to an OS fix.

## Video wallpaper (#185)

### Evidence and disposition

The reporter tried externally obtained Komorebi, Hidamari, and Wallset, then
got a custom xwinwrap/mpv setup working across five monitors. Its script is
not attached. Later feedback reports choppy window dragging only while the
wallpaper runs. Neither a RAM shortage nor a compositor/driver defect is
established by that comparison.
[Issue](https://github.com/crhy/spaced/issues/185),
[performance follow-up](https://github.com/crhy/spaced/issues/185#issuecomment-5610452165).

This repository has no video-wallpaper implementation or configured player.
`config/desktop.yaml`, the MATE schema override, and `spaced-theme-monitor`
describe/preserve static wallpaper. MATE background drawing and Caja desktop
icons are deliberately enabled. A separately installed player fighting for
the same desktop surface is not evidence that those defaults should be
disabled for every user.

**Disposition: feature request plus external-player performance investigation,
not an implemented or validated fix.** Do not add an unreviewed launcher,
player dependency, compositor switch, or global background-setting change.
Track any integration separately from regression closure.

### Reproduction and acceptance criteria

1. Obtain the actual launcher/script and all arguments, xwinwrap/mpv versions,
   video codec/resolution/frame rate, number of player processes, window
   placement, decode mode, GPU/driver, Compiz configuration, and `xrandr --query`
   output. Review scripts before executing them. Screenshots alone are not a
   reproducible implementation.
2. In a disposable test session, compare static wallpaper, the reported video
   workload, and a reduced-resolution/frame-rate version. Keep monitor layout,
   compositor, and other applications unchanged. Record CPU/GPU utilization,
   `free -h`, `vmstat 1`, player dropped-frame statistics, and dragging behavior
   for each. More RAM is justified only if memory-pressure evidence supports it.
3. Separate rendering-order failure (wallpaper hidden by the desktop) from
   decode/compositing cost (visible wallpaper with slow dragging). Record
   which process owns each desktop window and whether input or icons are
   obscured; do not mask either failure by disabling desktop icons globally.
4. A future optional integration must retain icon visibility, desktop input,
   the static-wallpaper choice, and acceptable interactive performance. Test
   five displays, mixed geometry, hotplug, login/logout, player crash, and
   clean stop/restart with no orphaned processes or permanent setting changes.
   Restore static wallpaper when disabled. No such acceptance test ran here.

## Repository-only validation

```sh
python3 -B -m unittest discover -s tests -p 'test_external_desktop_boundaries.py' -v
python3 -B -m unittest discover -s tests -p 'test_desktop_reliability.py' -k DesktopIcon -v
```

The added tests cover selective offline metadata editing, monitor gaps,
idempotence, malformed/missing metadata, and the GIMP launch boundary. They
never connect to a share, start Caja/GIMP, alter a real desktop, or exercise a
GPU. Passing them must not close any of these three issues. Real Caja cache
invalidation, the reported GIMP crash, and multi-monitor video performance
remain the explicit external validation work above.
