# Session regression investigation: #202, #200, #198

Scope: working tree based on `bb98a01`, inspected 12 September 2026. No OS
version changes, new background services, systemd dependencies, or hardware
workarounds are required by these changes.

## #202: remember the selected sound output

The fallback in `spaced-audio-restore` saved only volume and mute, then applied
them to whichever sink happened to be the default at login. It never recorded
or restored the selected output. The original helper is in `dd6c869`; the
event-burst debounce in `ab01fa4` did not change that omission.

The state is now `volume mute sink-name`, with the selected sink restored
before its volume and mute. Old two-field files remain readable and migrate
on the next successful save. Existing intentional mute/zero-volume choices
remain intact. Locale-independent parsing, atomic replacement, logout-signal
flushing, and rejection of the dummy `auto_null` output protect the saved
preference. Existing event debouncing remains in place.

If the saved device is absent, its volume is not applied to an unrelated
fallback and its preference is retained. A subsequent change of default output
can replace that preference. Selecting the already-active fallback cannot be
distinguished from leaving it unchanged; select a different available output
first if that preference needs replacing. Reconnection alone does not force an
output switch during the session; the stored output is retried at next login.

This repairs the verified omission in the fallback, not every possible
PulseAudio/card-profile/port/hardware failure. Sink names, not numeric indexes,
are persisted; profile and port selection are outside this change.

Manual acceptance on the affected machine, as the desktop user:

1. Choose a non-default output and set a recognizable volume/mute state.
2. After the debounce interval, collect:

   ```sh
   pactl get-default-sink
   pactl list short sinks
   cat "${XDG_CONFIG_HOME:-$HOME/.config}/spaced/audio-state"
   ```

3. Log out/in, confirm the same named sink, volume and mute, and play audio.
4. Repeat with intentional mute and zero volume; neither should be repaired.
5. Repeat with the preferred removable output disconnected: the fallback
   must not receive the saved output's volume or overwrite its preference.

If the default changes again after restoration, capture `pactl subscribe` and
`pactl list cards` alongside the state file. Investigate session startup ordering
and PulseAudio policy rather than adding an unconditional output-switch loop.

## #200: missing blinking cursor in Pluma

The report supplies no reproducer, theme, style scheme, or cursor settings.
Inspection found no Spaced override disabling cursor blinking or setting a
transparent caret. The shared GTK overrides' history (`065f77f`, `dd6c869`)
does not establish a cursor regression. A focused GtkSourceView 4 render check
with the classic scheme draws a visible caret under all eleven Spaced palettes
on GTK 3.24.52 / GtkSourceView 4.8.4 (installed Pluma 1.28.0).

The regression test deliberately disables blinking while comparing pixels with
the caret hidden and shown. It tests caret rendering, not the blink timer,
Pluma's complete application, Compiz, custom schemes, or a user's XSettings.
A headless timer-sampling experiment did not produce reliable blink evidence;
it is not used to infer a product defect or as a timing-sensitive release test.
There is not enough evidence for a responsible theme or settings source fix.

Collect the following in the affected user's graphical session, without sudo:

```sh
pluma --version
dpkg-query -W pluma libgtk-3-0t64 libgtksourceview-4-0
gsettings get org.mate.interface cursor-blink
gsettings get org.mate.interface cursor-blink-time
gsettings get org.mate.interface gtk-theme
gsettings get org.mate.pluma color-scheme
gsettings get org.mate.pluma editor-font
gsettings get org.mate.pluma use-default-font
pgrep -a mate-settings-daemon
```

Record whether the caret is completely absent or merely stationary, whether
typing restores it, how long it takes to stop blinking, and whether Pluma has
keyboard focus. Compare a blank document and a syntax-highlighted file; compare
Pluma with a GTK text entry in another application. Record any user GTK CSS
in `~/.config/gtk-3.0/gtk.css` and `settings.ini`. Use a temporary clean test user
to compare the same Spaced theme with Adwaita and the classic Pluma scheme;
do not reset the affected user's dconf or overwrite their accessibility settings.
Capture the effective `gtk-cursor-blink`, `gtk-cursor-blink-time`, and
`gtk-cursor-blink-timeout` from GTK Inspector's settings page as well as the
stored MATE values. A screen recording with the settings/theme and focus steps
is needed before deciding whether the fault is theme contrast, XSettings,
GtkSourceView, application focus, or compositing.

## #198: e-poweroff segfault after successful shutdown

The report identifies elogind `257.13-1`, a null-address access in `e-poweroff`,
and successful shutdown. It does not contain a core or a repeatable triggering
action. This is a strong match, not yet a symbolized confirmation, for
[upstream elogind #341](https://github.com/elogind/elogind/issues/341): the
immediate-action child logs through a null delayed-action pointer after doing
the shutdown. Upstream uses the already-validated action argument instead.
[The upstream release notes](https://github.com/elogind/elogind/releases)
list the correction in 257.14, together with related fork-failure cleanup.
Do not attribute the kernel's CPU number to defective hardware.

There is no elogind source in this repository to patch. The inspected local
APT cache offered only `257.13-1`; that is not a refreshed repository availability
check. The appropriate package-level resolution is a Devuan-compatible release
containing upstream #341, or a reviewed backport to the distro source package.
Check package changelogs/source for the fix rather than relying solely on the
version number. Validate the complete elogind/libelogind/PAM package set in a
sysvinit VM before adoption; do not binary-patch elogind, replace the poweroff
command, mask failures, disable logind power policy, or add arbitrary delays.

### Verify existing diagnostic work before trying to reproduce

History already contains core-capture work in `8f3eb3b` (PR #197) and its
sysvinit correction in `6310ae9` (PR #199), beyond the inspected working-tree
base. These are diagnostic prerequisites, not fixes for the null dereference.
Do not merge their release-version changes as part of this scoped work.

The first change supplies a bounded PAM limit, a `/var/crash/core.%e.%p.%t`
pattern and seven-day cleanup. PAM limits alone do not reach boot-started
elogind. The second raises the daemon limit through `/etc/default/rcS`, sourced
by `/etc/init.d/rc`. Under dash, `ulimit -c 1048576` represents 512 MiB;
do not substitute Bash's units. Verify actual daemon limits after a VM reboot:

```sh
dpkg-query -W elogind libelogind0 libpam-elogind spaced-mate-default-settings
apt-cache policy elogind libelogind0 libpam-elogind
cat /proc/sys/kernel/core_pattern
for daemon_pid in $(pgrep -x elogind); do
    printf '\nPID %s\n' "$daemon_pid"
    readlink -f "/proc/$daemon_pid/exe"
    awk '/Max core file size/' "/proc/$daemon_pid/limits"
done
ls -ld /var/crash
df -h /var/crash
```

A shell's `ulimit` is not evidence of the daemon's inherited limit. Verify the
packaged sysctl, rcS limit and cleanup are actually installed and that the core
destination exists with the intended permissions. Do not restart elogind in an
active desktop session to test this. Do not automatically shut down the host.

### Evidence and closure

On a disposable VM, save work and record the exact initiator (MATE menu,
physical power button, or explicit loginctl request), timestamp and whether an
inhibitor was active. After a deliberately authorized shutdown and next boot,
collect the surrounding kernel/syslog messages and any new `core.e-poweroff.*`
or `core.e-reboot.*`. Preserve the matching elogind executable, package version,
Build ID (`readelf -n /usr/lib/elogind/elogind`) and debug symbols before upgrading;
use the executable path reported by `/proc` if different. With a matching core
and binary, inspect in GDB using `thread apply all bt full` and `info registers`.
Core files and full backtraces can contain credentials and private session data;
keep them access-restricted and share only reviewed, redacted evidence privately.

Close only after package provenance confirms the upstream fix and the affected
shutdown path passes VM/affected-machine retesting. If it recurs on a fixed
build, use the symbolized stack to distinguish #341 from another defect.
No core from a one-off shutdown is insufficient evidence for a hardware fix.

## Focused automated validation

```sh
bash -n overlays/usr/local/bin/spaced-audio-restore
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_audio_restore.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_desktop_reliability.py
xvfb-run -a /usr/bin/python3 tests/gtk_desktop.py
```

The audio tests use a fake pactl, including output migration, missing devices,
session changes, logout signals, dummy sinks and failed reads. The GTK check
requires the distro Python GI bindings, GTK 3, `gir1.2-gtksource-4` and Xvfb.
A skipped GtkSourceView test is not cursor validation. Neither suite substitutes
for real login/logout audio playback or controlled shutdown testing.
