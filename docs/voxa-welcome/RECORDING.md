# Voxa Welcome: scripts and recording steps (issue #283)

The Voxa Welcome has two kinds of Voxa speech:

1. **Three recorded clips**, played by Spaced Welcome *before* Voxa is installed.
   They ship on the ISO, because nothing can speak until Voxa and its model exist.
2. **Live speech** by the real Voxa on the fresh install: hardware setup, sound
   calibration, apps, and the brief tutorial. This is scripted text that Voxa
   speaks herself, so it never goes stale and adapts to the hardware.

## Part 1: the three recorded clips

| File | Plays when | Script | Length |
| --- | --- | --- | --- |
| `welcome.webm` | the chooser opens | `01-welcome.txt` | about 2 s |
| `install-offer.webm` | right after, under the two buttons | `02-install-offer.txt` | about 15 s |
| `setting-up.webm` | beside the progress ring, looped quietly | `03-setting-up.txt` | about 15 s |

### Making Voxa say the lines exactly

Voxa's `read-text-file` branch (in the next release after 0.1.6) reads a text file aloud, with the face moving,
through her normal reply path:

```
gapplication action io.github.crhy.voxa read-file "'/home/rhy/spaced-10.26/docs/voxa-welcome/01-welcome.txt'"
```

The same thing works by voice ("Voxa, read the file called 01 welcome") or by
selecting the file in Caja and saying "Voxa, read this text file". Line breaks
become short pauses. Use the terminal command for recordings so your own voice
is not on the take.

### Voxa settings for the takes

- Character: American female (Grace), face quality **Medium** (the default the
  Welcome promises), on **Active**.
- Window at a fixed size, centred, nothing else on screen behind it.
- Notifications off (MATE: right-click the clock area, or close mate-notification
  windows first); Strata and other GPU jobs stopped so the face runs smoothly.

### OBS

1. **Scene "Voxa clip"**, canvas and output 1920x1080, 30 fps.
2. **Source: Window Capture (Xcomposite)** of the Voxa window. Crop in the source's
   filter (**Crop/Pad**) to the face only, a square or 4:3 area.
3. **Audio:** add **Audio Output Capture (PulseAudio)** on the speakers' monitor
   (her voice) and **mute the microphone** source, so the room never leaks in.
4. **Settings > Output > Recording:** format **mkv** (safe if OBS stops), encoder
   NVENC or x264, CRF 18 / CQP 18, audio 48 kHz.
5. **Settings > Hotkeys:** a key for Start/Stop Recording, so the terminal can stay
   in front of you and off the captured window.
6. For each clip: start recording, wait one second, run the `read-file` command,
   wait until she finishes and the face settles for one second, stop. Record
   each clip two or three times and keep the best.

### Kdenlive

1. Import the mkv, trim to half a second before the first word and half a second
   after the last.
2. Crop or scale to **480x480** (square card in the chooser), fade audio in and
   out over 0.1 s, normalise audio to about -16 LUFS.
3. **Render:** WebM, VP9 video at about 600 kbit/s, Opus audio at 96 kbit/s,
   480x480, 30 fps. Expect roughly 1 to 1.5 MB per clip, about 4 MB for all three,
   which keeps the ISO comfortably under 2 GB.
4. Name the files `welcome.webm`, `install-offer.webm` and `setting-up.webm`.

### Into the ISO

Put the three files in Spaced Welcome's `data/voice/` (the folder its voice
helper already reads). Spaced Welcome currently plays audio clips only; showing
the video needs a small GStreamer player in the chooser and setup screens, which
is a Spaced Welcome task still to do.

## Part 2: live first-boot script (spoken by the real Voxa)

These lines are for the Voxa greeter mode (Voxa side of #283, not built yet).
Text in braces is filled in by Voxa at run time. Every step can be skipped, and
"Voxa, quit" always returns to the ordinary Spaced Welcome.

**1. First hello** (when the setup ring finishes and Voxa opens)
> Hello! I'm running on your computer now, and nothing you say to me leaves it.
> I checked your hardware: {graphics card}, {memory} of memory. I've picked the
> {model} model, which fits it well. You can change that any time in my settings.

**2. Sound calibration** (from #283)
> So I can be the best assistant possible, we need to do some sound calibration.
> Is that OK?

- Yes: the calibration walk-through (microphone at several levels, speaker volume
  choice, noise cancellation tuned to the user's voice). While it runs, Spaced
  Bazaar, LibreOffice, Audacious and VLC install in the background.
- No:
  > OK. I won't work quite as well, but you can come back any time and say,
  > "Voxa, let's calibrate sound."

  ("Let's calibrate sound" is a new command that comes with the greeter work.)

**3. Apps**
> Next, let's get your apps. I'm opening Spaced Welcome. You can install
> everything we suggest with one click, or pick only the apps you want. Tell me
> which, or click them yourself. I'll wait here.

After the installs (Voxa comes back to Active):
> All done. {count} apps are installed and ready in your menu.

**4. Browser** (from #283)
> You probably want a browser to surf the web. Can I install Brave for you, or do
> you prefer a different browser?

**5. Offer the brief tutorial**
> Would you like a quick tour of what I can do? It takes about three minutes.

## Part 3: brief tutorial (three to four minutes, live)

Each step: Voxa says the line, waits for the user to try it, and confirms.
Every command below was checked against Voxa's command router on 15 October
2026 (dictation is handled by the conversation layer).

1. > First, the most important one. Whenever I'm talking too much, just say
   > "Voxa, stop." Try it now. *(she starts reading; the user stops her)*
2. > I can open programs. Say "Voxa, open Pluma."
3. > Now say "Voxa, start dictation" and talk. I'll type what you say into Pluma.
   > Say "stop dictation" when you're done.
4. > Your desktop is a cube. Say "Voxa, spin the cube left." Now "spin the cube
   > right." You can do the same with Control, Alt and the arrow keys.
5. > To zoom in on anything, hold the Super key and scroll the mouse wheel.
6. > I can play music and radio. Try "Voxa, play some jazz radio."
   > *(then)* "Voxa, stop the music."
7. > I can read to you. Select some text and say "Voxa, read this," or ask me to
   > recite a poem by your favourite poet.
8. > And I keep Spaced Linux up to date. Say "Voxa, update Spaced Linux" any time.
9. > That's the quick tour. Would you like the longer one? It shows you email,
   > documents, video editing and more, and takes ten to thirty minutes.
   - No: > Enjoy Spaced Linux. I'm here whenever you need me. *(Voxa goes Active)*
   - Yes: the long tutorial (to be scripted separately, per #283).
