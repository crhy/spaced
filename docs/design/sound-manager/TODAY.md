# TODAY.md — what "Sound Preferences" does today, function by function

Nothing in this list may be lost when Spaced Sound Manager replaces it (issue #429,
11.26.4). Source of truth, in this order:

- **the package Spaced actually installs**: `mate-media 1.26.2-1+b4` (`/usr/bin/mate-volume-control`,
  `/usr/bin/mate-volume-control-status-icon`, `/usr/libexec/mate-volume-control-applet`)
  with `libmatemixer0 1.28.0-1` (PulseAudio backend `libmatemixer-pulse.so`) and
  `pulseaudio 17.0+dfsg1-3` + `pulseaudio-module-bluetooth` (pinned in `scripts/check.sh`);
- upstream source of that package: `mate-media` `mate-volume-control/` (C, GTK3) and
  `libmatemixer` `backends/pulse/`;
- how Spaced reaches it: `overlays/usr/local/bin/spaced-hotkey-action`
  (`sound) exec mate-volume-control`), the Brisk menu, the panel applet
  (`config/desktop.yaml`, `docs/matepanel.md`, every `overlays/usr/share/mate-panel/layouts/*`),
  `overlays/etc/xdg/autostart/mate-volume-control-status-icon.desktop`, and
  `overlays/usr/local/bin/spaced-first-login-repair` (`volume-control-applet`).

The window itself is titled **Sound Preferences** and is a single `GtkDialog` with a
`GtkNotebook`: **Sound Effects · Hardware · Input · Output · Applications**. It is not
part of `mate-control-center` (that is `mate-settings-daemon`/`gnome-control-center`-style
capplets); it is a standalone app.

## 1. Entry points (all must keep working)

| Entry | Today |
|---|---|
| Brisk menu / main menu | `mate-volume-control.desktop` → "Sound Preferences" |
| Global hotkey (`spaced-hotkey-action sound`) | `exec mate-volume-control` |
| Panel applet menu item "_Sound Preferences" | `mate_volume_control` launched by `gvc-stream-status-icon.c` (`Failed to start Sound Preferences: %s` on failure) |
| Command line | `mate-volume-control` (dialog), `mate-volume-control-applet`, `mate-volume-control-status-icon` |
| Session | applet autostart (`…-status-icon.desktop`), panel object `volume-control-applet` |

## 2. Tab "Sound Effects" (`gvc-sound-theme-chooser.c`)

| Function | Control / store |
|---|---|
| Event sounds on/off | `org.mate.sound event-sounds` (played by `mate-settings-daemon`'s media-keys + libcanberra) |
| Input feedback sounds (keyboard/button) | `org.mate.sound input-feedback-sounds` |
| Sound theme picker | `org.mate.sound theme-name`; list shows theme name + "No sounds", "Built-in", "Custom"; previews the theme's `.theme`/`index.theme` events |
| Alert sound chooser | tree view, columns **Name** / **Type**, "Default" and "From theme", check-marked per alert (`window bell` etc.); selection is written into the XDG sound theme (`index.theme` `Alert=`), with a custom theme created when needed |
| Testing an event/alert | libcanberra event `Testing event sound`, application id `org.mate.VolumeControl` |
| Alert volume | `_Alert volume:` channel bar |
| GTK widget sounds | "Enable _window and button sounds" (`libcanberra-gtk3-module`) |

## 3. Tab "Hardware" (`gvc-mixer-dialog.c`, device list)

| Function | Control |
|---|---|
| Pick a **sound card/device** to configure | frame "C_hoose a device to configure:" with a device list (name + icon **straight from the server**: "Build-in Audio Analog Stereo", "HD-Audio Generic", "HDA NVidia" — issue #429's complaint) |
| Card **profile** | combo "_Profile:" (PulseAudio card profiles: "Analog Stereo duplex", "Digital Stereo (HDMI) Output", "Off" …) |
| Port / connector switching when a device has several ports | combo "Co_nnector:" (sinks/sources' `ports`: "Speakers", "Headphones (plugged in)", "HDMI / DisplayPort") |
| **Test Speakers** button | `gvc-speaker-test.c`: starts the device's test stream (`find_device_test_stream`), window "Speaker Testing for %s", per-channel forward; button hidden when the device has no test stream (`update_device_test_visibility`) |
| Level / mute of the selected device | channel bars + level bar (`gvc-level-bar.c`, shown "only if supported by the control") |
| Live device add/remove | `device-added` / `device-removed` signals from libmatemixer |

## 4. Tab "Input"

| Function | Control |
|---|---|
| Choose the recording device | frame "C_hoose a device for sound input:" (combo of sources, raw server names) |
| Set it as the default input | libmatemixer `mate_mixer_context_set_default_input_stream` |
| Input volume | `_Input volume:` channel bar (base/max volume honoured) |
| **Live input level** | "Input level:" + `gvc-level-bar.c` fed by `mate_mixer_stream_get_level` (libmatemixer `pulse-monitor.c`: a record stream on the device's monitor, peaks at 20 Hz) |
| Port switching per input, mute | same combos/bars as §3 |
| Profile change for that card | "Changing device profile" |

## 5. Tab "Output"

| Function | Control |
|---|---|
| Choose the playback device | frame "C_hoose a device for sound output:" (sinks) |
| Set it as the default output | `mate_mixer_context_set_default_output_stream` |
| Output volume | `_Output volume:` channel bar |
| Above-100% volume | check "Allow volume to e_xceed 100%" (`org.mate.sound volume-overamplifiable`) |
| **Balance / fade / LFE** | `gvc-balance-bar.c`: left-right, front-rear, sub-woofer bars, only when the control has those channels ("Balance type", "LFE") |
| Port switching ("Connector:"), profile | as §3, frame "Settings for the selected device:" |
| Live output level | level bar on the sink's monitor |
| Dummy sink visible | when no real sink exists libmatemixer exposes `auto_null`, shown "Disabled" |

## 6. Tab "Applications"

| Function | Control |
|---|---|
| One row per **playing/recording stream** | `mate_mixer_context_list_streams` / `mate_mixer_device_list_streams`: app name (`mate_mixer_app_info_get_name`), icon, stream volume (`…_control_set_volume`, normal/base/max), mute |
| Per-stream routing | stream → device (`mate_mixer_stream_get_device`); move is not offered in the UI today, only shown |
| Event-sound streams | appear as rows too (`mate_mixer_context_set_app_id`/`set_app_name`) |
| Empty state | "No application is currently playing or recording audio." |

## 7. Backend (`libmatemixer` pulse backend) — the data the UI shows

Sinks, sources, sink-inputs, source-outputs, cards, profiles, ports; default sink/source;
subscription events (`device-added`, `stored-control-added`, `notify::default-*-stream`,
"Updating output settings" / "Updating input settings"); per-stream peak levels via monitor
record streams (`backends/pulse/pulse-monitor.c`, `pa_stream_connect_record` on the monitor
source). Names, icons and port labels are the **server's own strings** — that is the origin
of "HD-Audio Generic" ×2 and "HDA NVidia" ×2 in #429. PipeWire's pulse server answers the
same protocol, so the same UI works on either sound stack.

## 8. Panel applet (not the window, but the same project — must not regress)

`gvc-stream-status-icon.c`: icon follows level (`audio-volume-low/medium/high`,
`audio-input-microphone-*`), tooltip with volume ("Muted at"), menu with **Output Device** /
**Input Device** submenus, Mute/Unmute, "Show _media player controls", "_Sound Preferences";
MPRIS player entries ("Media Players", "Launch Player"), middle-click action and
`org.mate.volume-control` keys (`tooltip-show-volume`, `middle-click-action`, …). The
Spaced panel layouts and `scripts/check.sh` pin the applet object, so any replacement must
leave it installed and pointed at a working window.

## 9. State Spaced itself owns (must not be fought)

`overlays/usr/local/bin/spaced-audio-restore` (autostart) already keeps, through **`pactl`
only**: `~/.config/spaced/audio-state` (default sink + volume + mute) and
`~/.config/spaced/audio-card-profiles` (per-card profile), with a settle-then-save watcher on
`pactl subscribe`. New code must read the same files/protocol or the two will fight.
`overlays/usr/bin/…`/`overlays/etc/bazaar/blocklist.yaml` refuses EasyEffects on the
PulseAudio release (issue #397), so nothing may assume PipeWire-only tools.

## 10. Known-broken state the design must surface (issue #427)

A `11.26.1-1 → 11.26.2` update wiped `/run/user/<uid>` on bigboy; PulseAudio's socket
(`$XDG_RUNTIME_DIR/pulse/native`) went away and **apps started after that moment had no
sound at all**, while Sound Preferences kept showing the old device list. It was fixed live
at 21:47 by restarting `pulseaudio` (roadmap note `docs/notes/spaced-strata-roadmap.md`
items 12–13). Today's window has no "sound server not reachable" state at all:
libmatemixer simply stops emitting signals. This is the state DESIGN.md §7 must design,
including the one-click fix.

## 11. What the Spaced menus/labels say today

- Menu entry: "Sound Preferences" (upstream name), icon `multimedia-volume-control`.
- Applet: "Volume Control" / "Show desktop volume control".
- Device rows: raw ALSA/server strings, generic PCI-style icons ("generic PCI icons" in
  #429), no level meter on Output, no test sound on the Output page (only in Hardware),
  no per-app routing control, no error state.
