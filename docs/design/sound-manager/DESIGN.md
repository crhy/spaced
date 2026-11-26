# DESIGN.md — Spaced Sound Manager (issue #429, ships in 11.26.4)

Design only; rhY approves before any code. No shipped code is touched by this task.

Look and flow follow **`docs/design/gpu-manager/STYLE.md`** (written for #426, on
`origin/strata/s01-spaced-gpu-manager-design`): same header bar + centred stack switcher,
Spaced Monitor's cards and palette tokens that follow the live desktop theme, plain-word
copy, no vendor colours, one short status line instead of footer walls. The colour tokens
and the card geometry are **reused unchanged** — this design only adds the sound-specific
tokens (§6) and the icon set per device kind (§4). The standing rule
(`docs/notes/spaced-apps-follow-theme.md`) applies: colours come from the active desktop
theme, live.

## 1. Decision: a new small app, not a restyled mate-volume-control

**Decision: ship a new small app, "Spaced Sound Manager", and turn today's
`mate-volume-control` command into a compatibility launcher for it.** Reasons:

1. **The family look cannot be faked in CSS.** STYLE.md §2 requires Spaced Monitor's
   card system (`spaced_monitor/cards.py`, `theme.py`) — a Python widget set. Today's
   window is C/GTK3 (`mate-media` `gvc-mixer-dialog.c`) around a `GtkNotebook` whose tab
   labels and device rows are upstream's. Restyling means forking MATE's C app *and*
   libmatemixer forever, and the result would still be a notebook with stock rows.
2. **The naming layer does not exist anywhere.** Friendly names ("LG monitor (HDMI on
   RTX 4070 Ti SUPER)") need ALSA card + EDID monitor + sysfs GPU mapping (§4). That code
   already exists in Python for the GPU Manager (#426: `/sys/class/drm`, PCI identity) and
   in `spaced-audio-restore` (`pactl`). Writing it in the same Python stack reuses both.
3. **The app family is Python GTK3** (Spaced Update, Bazaar, Spaced RGB, GPU Manager,
   Spaced Monitor). A new small app joins the family; the fork would fight upstream every
   MATE release.
4. **Nothing is lost, and nothing new is installed.** The C app stays on the system as
   `mate-volume-control-classic` fallback; the `mate-volume-control` name keeps working
   (hotkey, applet menu item, muscle memory) by launching the new app. The data plane is
   `pactl` / the PulseAudio native protocol, already shipped and already used by
   `spaced-audio-restore` and `spaced-hotkey-action`.
5. **Scope stays honest.** The panel applet (`volume-control-applet`) is *not* replaced in
   11.26.4: it follows the theme icons already and is pinned by `scripts/check.sh` and
   every panel layout. The applet's "_Sound Preferences" item lands in the new app through
   the compatibility launcher, so no MATE panel fork is needed.

Rejected alternative (restyle upstream): rejected for the four reasons above; it also
cannot show the #427 broken-server state, which is the whole point of the issue.

## 2. Name, icon, one-line purpose

- **App name**: "Spaced Sound Manager". Menu label **"Sound Manager"** (replaces
  "Sound Preferences" in the Brisk menu); the old menu entry is removed, the old binary
  stays as `mate-volume-control-classic`.
- **Comment** (.desktop): "Choose your speakers and microphones, set levels, and fix
  sound that stopped working."
- **Window icon**: stock `multimedia-volume-control` — already the shipped icon for the
  applet and the old entry, so no new artwork and no broken theme.
- **Subtitle, always specific to this machine**:
  "4 outputs · 2 microphones · sound is working" /
  "Speakers: Realtek onboard · your microphone is the Blue Yeti".
- Hotkey, applet menu item, `spaced-hotkey-action sound`: unchanged commands, new window.

## 3. Shape of the app

HeaderBar (title + subtitle + Refresh + About) and one page bar, exactly like Spaced
Update (STYLE.md §1): **Output · Input · Applications · Effects · Advanced**.
Default 900 × 680, minimum 720 × 540 (same numbers as the GPU Manager, so both sit the
same way on the 30 px-panel desktop). Bottom row of the three community links, as always.

```
┌ Spaced Sound Manager ─────────────────────────────────────────────────┐
│ 4 outputs · 2 microphones · sound is working          ⟳ refresh  ⓘ   │
│ [Output] [Input] [Applications] [Effects] [Advanced]                  │
│  ┌ selected device card ────────────────────────────────────────────┐ │
│  │ ⏵ name · kind · connector      ▁▂▃▅ level meter      [Test sound]│ │
│  │ volume ─────────────●──── 60%   [muted]                          │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│  ┌ other outputs ──── one row each: icon · name · connector · ▁▂ ──┐  │
│  └──────────────────────────────────────────────────────────────────┘ │
│ one short status line                                                  │
└───────────────────────────────────────────────────────────────────────┘
```

## 4. The naming layer — friendly names and icons per kind

Raw server strings never appear on a card face. Names are built from, in this order, and
fall back to the raw name (muted, with a tooltip giving the raw string) when a layer is
missing:

| Kind | Name built from | Example |
|---|---|---|
| Built-in analog output, speakers | ALSA card + port ("Speakers") | "Speakers (onboard audio)" |
| Headphone jack, when plugged | port availability from the server | "Headphones (onboard audio, green jack)" |
| USB microphone | udev/USB product name | "Blue Yeti microphone (USB)" |
| Webcam microphone | udev/USB product name + "microphone" | "Galyimage webcam microphone" |
| Monitor HDMI/DisplayPort audio | EDID monitor name + the GPU it belongs to (sysfs: the audio function `01:00.1` sits next to the GPU `01:00.0`) | "LG monitor (HDMI on RTX 4070 Ti SUPER)" |
| Second monitor | same | "TCL TV (HDMI on RTX 4070 Ti SUPER)" |
| S/PDIF / optical | port name | "Digital output (optical)" |
| Bluetooth device | device name + "Bluetooth" | "WH-1000XM4 (Bluetooth)" |
| Dummy / auto_null | never named like hardware | "No sound hardware found" |

Connectors are spelled out (`HDMI`, `DisplayPort`, `USB`, `3.5 mm jack`, `Optical`), never
`HDMI1-1` / `output:2`; the sysfs/server names live only in the tooltip and the log
(STYLE.md §6 — plain words, no jargon on the surface).

**Icons per kind** (symbolic, so the desktop theme tints them; no vendor colours):

| Kind | Icon name (fallback in brackets) |
|---|---|
| Speakers | `audio-speakers-symbolic` (`speaker-symbolic`) |
| Headphones | `audio-headphones-symbolic` |
| USB / webcam microphone | `audio-input-microphone-symbolic` (webcam also gets a small `camera-web-symbolic` badge) |
| Monitor speakers | `video-display-symbolic` |
| Optical | `audio-optical-symbolic` (`audio-volume-high-symbolic`) |
| Bluetooth | `bluetooth-symbolic` |
| Dummy / unknown | `audio-x-generic-symbolic` |
| App rows | the app's own icon, else `application-x-executable-symbolic` |

A missing icon falls back to `audio-x-generic-symbolic`; nothing renders as a PCI card,
which is #429's complaint.

## 5. The Output page

The page opens on. One **selected device card** (Monitor's card box), then a row per other
output. Every string is written out; bigboy's fake data is used in the mockups.

Selected card, in this order:

1. **Name** (13 px bold) — "LG monitor (HDMI on RTX 4070 Ti SUPER)".
2. **Kind line** (muted) — "HDMI · stereo · plugged into the RTX 4070 Ti SUPER".
3. **Connector picker** (only when the device has several ports):
   "Connector: [HDMI ▾]"; choices "HDMI 1", "DisplayPort" — with "(nothing plugged in)"
   on the ones that report no presence.
4. **Level meter** — segmented, live, peak-hold dot, in the sound tokens (§6): green up to
   −12 dB, amber to 0 dB, red at clipping. "No level" (em dash) when the server does not
   report one.
5. **Volume** — one slider, 0–100 % by default with the number; above 100 % only after the
   Effects page "Allow volume above 100 %" is on (TODAY.md §5's checkbox, same
   `org.mate.sound volume-overamplifiable` key). "60 %" text, and a mute button that says
   "Muted" while muted.
6. **Test sound button** — one click, one short stereo clip, never at startup
   (§5.1). While it plays the button becomes "Stop".
7. **Make this the one apps use** (radio/segmented per device; the default sink). Disabled
   with a tooltip when it cannot happen: "This output is off — Spaced will turn it on."

Rows for the other outputs: icon · friendly name · connector kind (muted) · small live
meter · "Use" button. Clicking a row selects it into the card.

Under the cards, **one** short line (never a wall): "Sound goes to the LG monitor. To
listen on the speakers instead, pick them above."

bigboy example (fake data, same facts the roadmap records):

```
[LG monitor (HDMI on RTX 4070 Ti SUPER)]  HDMI · stereo · plugged into the RTX 4070 Ti SUPER   (in use)
  Connector: HDMI 1        ▁▁▂▃▅▇ 0 dB peak      Volume ─────●─── 60 %  [Test sound]
[TCL TV (HDMI on RTX 4070 Ti SUPER)]      HDMI · stereo · nothing plugged in        [Use]
[Speakers (onboard audio)]                3.5 mm jack · green socket              [Use]
[Headphones (onboard audio, green jack)]  3.5 mm jack · plugged in                [Use]
```

### 5.1 Test sound (issue #429: "a test-sound button")

- The button is **never pressed by the app itself**: no sound at startup, no loop, nothing
  when the page is merely open. Only a click plays.
- One shipped clip: `/usr/share/sounds/spaced/sound-test.wav` — left channel, right
  channel, then both, ~2 s, at the device's current volume. It is a shipped file, not
  generated at runtime, so it works with no network.
- If the device is muted or at 0 %, the button reads **"Unmute and test sound"** and the
  click restores 50 % first, then plays (the change is undone when the window closes,
  matching `spaced-audio-restore`'s saved state).
- While playing, the clip appears in Applications as "Spaced Sound Manager" so the
  meter is honest, and the button turns into "Stop".
- The prototype/mockups never play sound and never open a microphone (issue text and
  `docs/notes/spaced-strata-roadmap.md`); the mockups contain a static meter picture only.

## 6. Sound tokens (added to STYLE.md's set, same source style)

```
level_start   green  (#22c55e)      quiet signal
level_mid     amber  (#f59e0b)      approaching 0 dB
level_peak    red    (#ef4444)      clipping / muted meter
meter_track   #1e2a44 dark / #e5e7eb light
```

Same palette class as Monitor's `DARK`/`LIGHT`, resolved live with the desktop theme.
Red stays reserved: clipping, and the one dangerous thing (the "restart the sound server"
action while apps are playing). No vendor colours anywhere.

## 7. The Input page

Same shape as Output, microphones only: Blue Yeti, webcam, any other.

- Selected card: "Blue Yeti microphone (USB)" · "USB · mono · plugged in" · live input
  level meter (green→amber, red = clipping) · gain/volume slider · mute.
- **"Show my microphone level"** button, off by default: the app only opens a monitor of a
  microphone when this is pressed, and while it runs a red-tinted line appears under the
  meter: "Spaced is listening to your microphone right now — you can stop it." (Stop is
  always next to it.) Without the button, the page only shows levels of streams apps have
  already opened — no hidden microphone use. (This is a deliberate improvement on today's
  always-on "Input level:" bar.)
- "Make this the one apps record from" for the default source.
- One short line: "Your microphone is the Blue Yeti. If an app records silence, check the
  app's own microphone setting."

## 8. The Applications page (per-app volumes, TODAY §6)

One row per stream, grouped: **Playing** then **Recording**. Each row: app icon · app name
· "→ LG monitor (HDMI on RTX 4070 Ti SUPER)" in muted text · live meter · per-app slider
(0–100 %, above-100 only when allowed) · mute. Empty state exactly today's, in plain
words: "Nothing is playing or recording sound right now."

Extra control that today's UI lacks: **Move to…** on each row, listing the outputs from §5.
Disabled with a tooltip while the server is unreachable.

One short line: "An app too quiet? Set its own slider here; it never changes your other
sounds."

## 9. The Effects page (today's Sound Effects tab, same keys)

- "Play sounds when things happen" (`event-sounds`), "Play sounds for typing and clicks"
  (`input-feedback-sounds`).
- Sound theme picker: theme names, "No sounds", "Custom" (`theme-name`).
- Alert sound chooser (Name / Type as today, stored the same way in the XDG sound theme)
  with a "Test" that plays only on click.
- "Alert volume" slider.
- "Allow volume above 100 %" (`volume-overamplifiable`).
- One short line: "Event sounds are played by your desktop, not by this app."

## 10. The Advanced page (today's Hardware tab, nothing lost)

For people who want the raw view, once, plainly:

- Card list with the **raw** server name in muted text under the friendly name
  ("alsa_card.pci-0000_0a_00.1 · HDA NVidia") — the only screen where those strings show.
- Profile picker per card ("Analog Stereo duplex", "Digital Stereo (HDMI) Output", "Off")
  with a warning before a change: "Changing this turns the sound off for a second and
  moves sounds that are playing onto the new setup."
- Connector list per card.
- "Test speakers" (today's per-channel test, kept: "Speaker testing — press each speaker's
  button as you hear it").
- "Open the old Sound Preferences" button (`mate-volume-control-classic`) so no feature is
  unreachable if the new app is wrong about something.

## 11. "Sound server not reachable" — the #427 state, with one-click fix

Detected by asking the server itself (`pactl info`), not by guessing. When it answers
nothing, the whole window switches to one card, controls greyed, nothing silently stale:

```
⚠  Sound is not working
   Spaced can't reach the sound server, so apps have no sound.
   What Spaced found: your login folder (/run/user/1001) was removed while the desktop
   was running, and the sound server's socket went with it. Apps started after that
   moment lost their sound.

   [ Fix it for me ]     [ Show details ]     [ Quit ]

Details (expander, plain words + the raw strings): sound server version, socket path,
whether the process is running, XDG_RUNTIME_DIR, whether autospawn is on, the last 10
server log lines if readable.
```

"Fix it for me" runs the steps in ARCHITECTURE.md §5, stating each before it runs:
1. "Put your login folder back" (root, once, through Spaced's own helper),
2. "Restart the sound server" (your session's, never a system service — sysvinit only),
3. "Check the sounds you had before came back" (compares the sinks and the state
   `spaced-audio-restore` saved: default sink, volume, mute, per-card profiles).

Then: "Sound is back. 4 outputs and 2 microphones found. Apps you started before the
problem may need to be restarted once." The last sentence is honest: apps that started
during the outage keep their broken connection, and the app lists them ("These apps may
need to be restarted: Firefox, VLC").

States the flow must handle, with strings written out:

| What is wrong | Shown |
|---|---|
| login folder gone, socket gone (the #427 case) | "Your login folder (/run/user/1001) was removed while the desktop was running." + Fix |
| server not running at all | "No sound server is running. Start it." + Fix |
| socket alive but the server hung | "The sound server stopped answering. Restart it." + Fix (with a warning that sound stops for a second) |
| only the dummy output | "No sound hardware found. Is your sound card plugged in / switched on in the BIOS?" |
| PipeWire instead of PulseAudio | no error at all — the same names and controls work; the detail line says "Sound server: PipeWire (PulseAudio-compatible)" |
| Bluetooth module missing | "Bluetooth audio is not available in this session." |

## 12. What this version says it does not do

- cannot make an app that ignores your settings obey them (only the app's own choice can);
- does not touch `~/.asoundrc` / ALSA directly — the sound server is the only thing it
  talks to (no systemd units anywhere; sysvinit only, `docs/notes/spaced-no-systemd.md`);
- does not install or switch sound stacks (PulseAudio stays the Spaced default);
- does not run EasyEffects or other EQ layers, which the release refuses anyway (issue
  #397), and says so once, in Advanced, not in a footer;
- never plays a sound or listens to a microphone without a click (§5.1, §7).

## 13. Screens in this design

`screens/output-spaced-dark.png`, `output-light.png`, `input-spaced-dark.png`,
`input-light.png`, `applications-spaced-dark.png`, `applications-light.png`,
`effects-spaced-dark.png`, `effects-light.png`, `advanced-spaced-dark.png`,
`advanced-light.png` — built by `prototype/sound_manager_prototype.py` from **fake**
bigboy data (Blue Microphones USB mic, Galyimage webcam, onboard HD-Audio analog, two
NVIDIA HDMI outputs on the RTX 4070 Ti SUPER), rendered under Xvfb in the real
`Spaced-Dark` engine and the `Spaced-Linux-Light` theme. No real audio device is opened,
no sound is played, no microphone is touched.
