# ARCHITECTURE.md — how Spaced Sound Manager talks to sound safely (11.26.4)

Design only; rhY approves before any code. No shipped code changes in this task.

Spaced is **sysvinit only** (`docs/notes/spaced-no-systemd.md`): nothing here installs,
names or calls an init system beyond sysvinit and elogind. Everything runs as the
desktop user; the single root step is a polkit-authorized helper verb. The sound server
Spaced ships is **PulseAudio 17** (pinned in `scripts/check.sh`: `pulseaudio`,
`pulseaudio-module-bluetooth`, `pulseaudio-utils`), autospawned by
`/etc/xdg/autostart/pulseaudio.desktop` and `/etc/init.d/pulseaudio-enable-autospawn`.
The same code must work unchanged on **PipeWire's PulseAudio server**: every call is the
PulseAudio native protocol, which PipeWire implements, and no module name, driver string
or `pactl` subcommand that PipeWire lacks is used (TODAY.md §7).

## 1. Components

| File (installed) | Privilege | Job |
|---|---|---|
| `usr/lib/spaced-linux/spaced-sound-manager.py` | user | the GTK3 UI: Output · Input · Applications · Effects · Advanced, the not-reachable card (§6), headerbar + stack switcher (STYLE.md §1) |
| `usr/lib/spaced-linux/spaced_sound.py` | user | the backend: `pactl`/`pacmd` discovery + control, `pactl subscribe` event pump, the naming layer (§3), state read/write shared with `spaced-audio-restore` (§7). `--preview` = read-only for source trees, `--fake` = the mockup data |
| `usr/bin/spaced-sound-meter` | user | tiny C helper (libpulse) that opens a **monitor** record stream on one sink/source and prints peak levels at ~20 Hz; built like `src/spaced-nm-focus` |
| `usr/bin/spaced-sound-test` | user | plays `paplay /usr/share/sounds/spaced/sound-test.wav` on one named sink, one-shot, `--stream-name="Spaced sound test"`; refuses to run without a TTY/flag from the UI |
| `usr/share/sounds/spaced/sound-test.wav` | — | the shipped 2 s left/right/both test clip (no runtime generation, no network) |
| `usr/lib/spaced-linux/spaced-sound-helper` | root via polkit | exactly the four verbs in §6: `check` · `restore-run-dir` · `restart-server` · `log`. Never a path, never a shell string |
| `usr/share/polkit-1/actions/com.spacedlinux.sound.policy` | — | one action `com.spacedlinux.sound.fix`, `allow_active=auth_admin`, exec path pinned to the helper |
| `usr/bin/mate-volume-control` (wrapper) | user | compatibility launcher: runs Spaced Sound Manager; `--classic` execs `mate-volume-control-classic` (the real upstream binary, kept) |
| `usr/share/applications/spaced-sound-manager.desktop` | — | Name "Sound Manager", Icon `multimedia-volume-control`, the comment from DESIGN.md §2 |

Nothing else is installed: `pactl`, `paplay`, `libcanberra`, GTK3 and the theme already
ship. `libmatemixer` is not used by the new app (no GIR bindings exist, TODAY.md §7), and
upstream `mate-volume-control` keeps its own copy.

## 2. Data plane: `pactl` + native protocol, never ALSA

- **Read**: `pactl list short …` + `pactl list …` for sinks, sources, sink-inputs,
  source-outputs, cards, profiles, ports, and `pactl info` for the server itself;
  `pacmd list-cards` only where `pactl` does not expose a field. All parsing is one
  function with tests that feed recorded outputs (both PulseAudio 17 and PipeWire's
  `pactl`, captured on bigboy).
- **Events**: one long-lived `pactl subscribe` reader per app window (the same pattern
  `spaced-audio-restore` already uses), with the burst-settle timer so a slider drag does
  not spawn three processes per event.
- **Write**: `pactl set-default-sink|source`, `set-sink-volume`, `set-sink-mute`,
  `set-source-volume`, `set-card-profile`, `set-sink-input-*`, `move-sink-input`. Values
  are normalised (`--`-terminated args, numeric volume, profile names matched against the
  card's own list — nothing is interpolated into a shell).
- **Never**: `~/.asoundrc`, `amixer`, `alsactl`, `/proc/asystem` writes, PipeWire-only
  `wpctl`, or an ALSA path that would double-control the same hardware. The sound server
  is the only writer (TODAY.md §9).
- The app must tolerate a **missing** `pactl` (refuses, says what to install, exits 1) and
  a **missing server** (the §6 state) — both are already unit-tested paths for
  `spaced-audio-restore`.

## 3. The naming layer (issue #429's "friendly names and icons")

`spaced_sound.py name(...)` builds one name per device, in this order, and keeps every raw
string for tooltips/log:

1. **Server strings**: `device.description`, `device.string`, port `description`, card
   `alsa.card_name`, `alsa.driver_name`, `alsa.card_id`, `device.bus` (`usb`, `pci`).
2. **ALSA card facts**: `/proc/asound/cards`, `/sys/class/sound/card*/{device,driver}`
   (vendor of the codec, e.g. Realtek), `driver` (e.g. `snd_hda_intel`).
3. **PCI/USB identity**: sysfs `device`/`subsystem` for PCI, udev `ID_MODEL`,
   `ID_VENDOR`, `ID_SERIAL_SHORT` for USB ("Blue Microphones Yeti").
4. **GPU ownership for HDMI/DP audio** — the piece that makes
   "LG monitor (HDMI on RTX 4070 Ti SUPER)" possible:
   - the audio device's PCI slot: `alsa_card.pci-0000:01:00.1` → function `01:00.1`;
   - its sibling GPU function `01:00.0` → `/sys/bus/pci/devices/0000:01:00.0/drm/cardN`
     → the DRM card that actually drives the connector;
   - the connector status/name from `/sys/class/drm/cardN-< connector >/`
     (`status`, `modes`, and `enable`), matching the PulseAudio port index
     (`pactl list sinks` port `available` + `profile` names);
   - the GPU's human name from `lspci -nn` **through the GPU Manager's own mapping**
     (`spaced_gpu.py`, #426) so "RTX 4070 Ti SUPER" is spelled the same in both apps —
     one function, not two implementations that can drift;
   - the monitor's own name from its **EDID**: `/sys/class/drm/card*/edid` decoded
     (vendor + product + monitor range), falling back to `xrandr --prop` `EDID` and
     `xr_randr` output names. When EDID is unreadable, "monitor" is used rather than a
     guess; the name never contains a connector code alone.
5. **Plug state**: port `available` (`plugged in` / "nothing plugged in"), and for the
   jack, the codec's jack detection reported by the server.

`icons.py` maps the resolved *kind* (not the raw string) to the symbolic icons in
DESIGN.md §4 with fallbacks; nothing is chosen by vendor colour.

Honesty rules carried from STYLE.md §6: the raw server name is shown only in Advanced
(muted) and in tooltips/log; a name is never invented when a layer is missing ("Monitor
(HDMI, name unknown)"), and the app never claims a device it has not seen.

## 4. Live level meters

- `spaced-sound-meter <sink|source>` opens a **monitor** record stream the same way
  libmatemixer's `backends/pulse/pulse-monitor.c` does (`pa_stream_connect_record` on the
  sink's monitor source; `PA_STREAM_PEAK_READ`), reads peak levels, prints
  `<ms> <ch1> <ch2> …` at ~20 Hz, exits when the sink disappears. Output meters use the
  sink's monitor only — no microphone, no playback.
- Input meters: the app shows levels of **streams that already exist**
  (`source-output`s); the extra "Show my microphone level" button opens the monitor of the
  selected source and shows the red-tinted "Spaced is listening to your microphone" line
  plus Stop (DESIGN.md §7). Closing the window or losing focus closes the helper
  (`SIGTERM`, plus `pactl kill` of the monitor stream) so no meter keeps running.
- GTK draws the meter with the tokens in DESIGN.md §6; peak-hold decays; a meter with no
  data prints an em dash, never a fake bar.
- The helper is a separate process so a hung PulseAudio cannot hang the UI: the UI shows
  "no level" and the §6 state after the timeout.

## 5. Test sound: only ever on user click

- The button is the only thing that can start it; there is no `--test-on-start`, no
  timer, no autostart entry, and the page never plays on open (mockups contain static
  meter pictures and never call `paplay`).
- `spaced-sound-test <sink>`: refuses unless it is given `--i-was-clicked`, refuses when
  the sink list is empty, and refuses when the not-reachable state is active. It calls
  `paplay --stream-name="Spaced sound test" /usr/share/sounds/spaced/sound-test.wav` on
  the named sink, waits for EOF, and exits with paplay's code.
- If the sink is muted or 0 %, the UI unmutes to 50 % first (a change it reverts on close
  and never writes into `spaced-audio-restore`'s saved state), then plays.
- A Stop button appears while playing; closing the window stops it. The stream is named so
  it shows up honestly in the Applications page.

## 6. The "sound server not reachable" fix (#427)

Detection, cheap and always safe: `pactl info` (exit code + `Server Name`),
`$XDG_RUNTIME_DIR` and `$XDG_RUNTIME_DIR/pulse/native`, `pgrep -u $UID pulseaudio`,
`ls -d /run/user/$UID`. Nothing is restarted until the user presses **Fix it for me**.

Steps, each announced before it runs, each verified after:

1. `spaced-sound-helper check` (unprivileged read-only report; the details expander).
2. `spaced-sound-helper restore-run-dir` (**root**, polkit `auth_admin`): recreates
   `/run/user/<uid>` with mode `0700`, owner `<uid>:<group>`, and the `pulse`/`dconf`
   subdirectories that MATE expects. This is the elogind-created login folder that
   #427's update wiped; the verb accepts **only** a numeric uid it gets from `PKEXEC_UID`,
   never a path, never a shell string. No systemd, no `loginctl`: plain `mkdir`/`chown`
   (`docs/notes/spaced-elogind-*` ordering notes apply — the helper never restarts
   elogind, it only repairs the folder).
3. `spaced-sound-helper restart-server` (**root**, polkit): as the desktop user with
   `runuser`-style env (`HOME`, `XDG_RUNTIME_DIR`, `DBUS_SESSION_BUS_ADDRESS`),
   `pulseaudio --kill` if it answers, else `pkill -u <uid> -TERM pulseaudio`; then
   `pulseaudio --start` (autospawn semantics, `/etc/init.d/pulseaudio-enable-autospawn`
   left untouched). The PipeWire-pulse case is handled by the user's own session service,
   which the app restarts with the documented per-session command rather than a system
   service — never a global `service` restart, never a system-wide daemon.
4. Verify: `pactl info` answers, sinks reappear, and the sinks compare against
   `~/.config/spaced/audio-state` + `audio-card-profiles` (the files
   `spaced-audio-restore` owns). Restoring the default sink/volume/mute/profiles is done
   **by `spaced-audio-restore`'s own code path**, not by a second writer.
5. Tell the truth about what cannot be undone: apps that started during the outage keep
   their dead connection; the app lists them from `pactl list sink-inputs` (`application-name`,
   `media.name`) and says "These apps may need to be restarted once: Firefox, VLC".

Safety rules: nothing runs without the click; the window is modal for those seconds;
`Ctrl+C` on the terminal cannot leave a half-done fix (each step is idempotent, the
helper logs to syslog and to `~/.local/state/spaced-sound-manager/fix.log`, and re-running
`Fix it for me` resumes at step 2); no reboot is ever required, and no logout is forced.

## 7. State ownership with `spaced-audio-restore`

`spaced-audio-restore` keeps the default sink, its volume/mute, and per-card profiles
through `pactl` (TODAY.md §9). The new app reads the same files at startup and writes
through the same keys only when the user changes something; the watcher's settle timer
keeps saving. The test-sound temporary 50 % restore is explicitly **not** persisted.
`scripts/check.sh` keeps pinning `pulseaudio*`, and the applet stays installed so panel
layouts, `config/desktop.yaml` and `spaced-first-login-repair` do not change.

## 8. Privilege model

- UI unprivileged; in `--preview` (source trees, tests) every control is insensitive, not
  just hidden.
- The only root path is `pkexec` → `spaced-sound-helper` → one of **four** verbs with
  normalised arguments (`PKEXEC_UID` numeric uid; no paths, no shell, fixed `PATH`,
  `LC_ALL=C`, `-I` interpreter flag, failures to syslog).
- `mate-volume-control-classic` is a plain copy of the upstream binary, no wrapper magic
  other than the `--classic` exec.

## 9. Test plan for 11.26.4

Host, in the existing suite (`python3 -m unittest discover -s tests`):

1. `test_sound_manager_design.py` — this design's own guards: the three docs exist, every
   user-facing string set from DESIGN.md is present in the prototype, the design never
   names a foreign init system or an out-of-band write path, and the prototype never
   touches playback or capture unless `--i-was-clicked` is present.
2. `test_sound_naming.py` — recorded `pactl list` output (PulseAudio 17 **and** PipeWire)
   plus fake `/sys` and `lspci` roots → exact expected friendly names:
   "LG monitor (HDMI on RTX 4070 Ti SUPER)", "TCL TV (HDMI on RTX 4070 Ti SUPER)",
   "Speakers (onboard audio)", "Headphones (onboard audio, green jack)",
   "Blue Yeti microphone (USB)", "Galyimage webcam microphone"; and the fallbacks when
   EDID, udev or the GPU sibling function is missing.
3. `test_sound_state.py` — the six not-reachable states of DESIGN.md §11, each with its
   fake `pactl`/`/run/user`/`pgrep` fixtures, and the fix sequence: helper verbs called in
   order, `restore-run-dir` refuses a non-numeric uid and any path, no verb runs without
   the click flag.
4. `test_sound_meters.py` — the meter protocol parser, em-dash on no data, timeout
   handling, and that an input monitor stream is opened **only** when the
   microphone-level flag is set.
5. GTK/Xvfb smoke test — the prototype under `Spaced-Dark` and `Spaced-Linux-Light`
   (720×540 minimum): pages build, strings fit at 880 px, meter widget paints, no crash
   with `--fake`; asserts no audio device is opened (the helper is stubbed).
6. `test_audio_restore.py` (already passing) stays green and gains one case: the new app
   and the restore watcher do not fight over `audio-state` when a sink disappears and
   comes back.

VM / hardware:

7. **VM test of the #427 fix** (the only test that proves it): a KVM VM with PulseAudio
   running, `rm -rf /run/user/1001` while the session lives, open the app → the
   not-reachable card appears with the right diagnosis → Fix it for me → folder restored
   with `0700`, server restarted, sinks back at the saved volume, and the honest "apps may
   need restarting" list. Second case: server killed instead of the folder.
8. **bigboy physical test with rhY** (the machine #429 and #427 were reported on): names
   for the two NVIDIA HDMI outputs on the RTX 4070 Ti SUPER, the Blue Microphones USB mic,
   the Galyimage webcam and onboard analog; test sound on each output (left/right/both);
   no sound or microphone activity while merely browsing; the #427 repair after a real
   Spaced Update. Record the measured names/behaviour — the design promises no numbers it
   did not measure.

## 10. Ship checklist for 11.26.4

- Design approved by rhY first (this task); backend and UI in the next task on the same
  branch family; never a PR (`docs/notes/spaced-no-prs-batch-into-release.md`), issue #429
  closed only after merge to `main` (AGENTS.md).
- `mate-volume-control.desktop` removed from menus, `mate-volume-control` becomes the
  compatibility wrapper, `mate-volume-control-classic` kept; panel applet and layouts
  unchanged; `docs/matepanel.md` note for the applet menu item.
- `docs/notes/spaced-sound-manager-11264.md` records the decision (new app, not a
  restyle) and the #427 fix flow; DESIGN.md's string table is the source for the docs.
- Release notes: "Spaced Sound Manager ships in 11.26.4" (rhY 2026-11-21), not 11.26.3.
- Everything in TODAY.md §1–§11 still reachable, §9 state untouched by a second writer.

## 11. Open items after approval

- Per-stream **move** (Applications page) needs `move-sink-input` confirmed against
  PipeWire's pulse server on bigboy before it is offered.
- Bluetooth device names (DESIGN.md §4) come from bluez, not from the sound server; the
  source is decided in the backend task.
- Above-100 % volume: keep today's `volume-overamplifiable` semantics; confirm the UI
  never shows 150 % without the key on.
- A later "Sound troubleshooting" page could absorb `troubleshooting/` audio guides; not
  in 11.26.4.
