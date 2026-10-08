# Spaced Linux + Voxa — feature video

Target length: about 6 minutes. Shot on a real Spaced Linux desktop with Voxa
0.1.6, one take per section, voice commands spoken live.

Lines in quotes are narration. Lines marked **SAY TO VOXA** are spoken to the
assistant on camera; leave a beat for her to answer. Every command below
worked in testing on 8 October unless it is listed under "Check before
filming" at the end.

## Before recording

- Voxa on **ACTIVE**, character Grace, echo setting **WebRTC**, Whisper **Base**
  (or Turbo if the graphics card is free).
- Close other browsers and anything that pops up notifications.
- Have Pluma closed, a song in mind, and the speakers at normal volume.
- Record the screen at 1080p and the room microphone separately so her voice
  and yours are both clean.

## Script and shot list

### 1. Cold open (0:00–0:25)

**[Black screen. Fade in on the desktop, music already playing quietly.]**

**SAY TO VOXA:** “Voxa, stop the music.” *(Music stops.)*

**SAY TO VOXA:** “Voxa, open Pluma.” *(Pluma opens.)*

“That was not a cloud service. Nothing I just said left this room. This is
Spaced Linux, and that is Voxa.”

**[Title card: Spaced Linux 10.26 · Voxa 0.1.6]**

### 2. What Spaced Linux is (0:25–1:10)

**[Slow pass over the desktop; open the menu, the file manager, Displays.]**

“Spaced Linux is a complete desktop built on Devuan, MATE and Compiz. It
starts with sysvinit. There is no systemd anywhere in it.”

**[Theme selector: click through four or five themes quickly.]**

“Eleven complete themes, from Windows 3.11 and XP to macOS, Android and our
own dark and light designs. Pick the desktop your hands already know.”

**[Spaced Bazaar, then Spaced Update.]**

“Apps come from Spaced Bazaar. Updates come from Spaced Update: one window for
the system and every app.”

### 3. Talk to your computer (1:10–2:20)

**[Voxa's window, Grace on screen.]**

“Most assistants are a chat box in a browser tab. Voxa is part of the desktop.”

**SAY TO VOXA:** “Voxa, open LibreOffice.”

**SAY TO VOXA:** “Voxa, minimize all apps.” then “Voxa, restore everything.”

**SAY TO VOXA:** “Voxa, play Dirty Old Town by the Pogues.” *(VLC opens, small.)*

**[While the song plays, without touching anything:]**

**SAY TO VOXA:** “Voxa, what time is it?”

“She heard that over the music, because she removes what her own speakers are
playing before she listens.”

**SAY TO VOXA:** “Voxa, stop music.”

### 4. Writing by voice (2:20–3:20)

**SAY TO VOXA:** “Voxa, open Pluma.” then “Voxa, start dictation.”

**[Dictate two sentences with a deliberate mistake or two.]**

**SAY TO VOXA:** “Stop dictation.” then “Voxa, clean up the text.”

**[Hold on the text being corrected.]**

**SAY TO VOXA:** “Voxa, save file.” — *she asks what to call it* — “Video demo.”

“Dictated, corrected and saved to Documents. I never touched the keyboard.”

### 5. Answers that come from somewhere (3:20–4:00)

**SAY TO VOXA:** “Voxa, what is the price of Bitcoin?”

**[Zoom on the Source line under the answer.]**

“When the question is about the real world, she looks it up and tells you
where the answer came from, instead of making something up.”

**SAY TO VOXA:** “Voxa, give me walking directions to the nearest library.”

### 6. Interrupting, like a person (4:00–4:30)

**SAY TO VOXA:** “Voxa, tell me a lot about Edgar Allan Poe.”

**[Let her speak for five seconds.]**

**SAY TO VOXA:** “Voxa, stop.” *(She stops.)*

“You can talk over her. And she does not mistake her own voice for yours.”

### 7. She runs the system too (4:30–5:10)

**SAY TO VOXA:** “Voxa, install GIMP.” *(Bazaar opens on GIMP and installs.)*

**SAY TO VOXA:** “Voxa, update Spaced Linux.” *(Spaced Update opens; type the
password when she asks.)*

“She presses the same buttons you would, in the real programs, and she asks
you to type passwords yourself. She never hears one.”

### 8. Why this is different (5:10–5:50)

**[Clean desktop. Text points appear one at a time as they are said.]**

“Here is what you get with Spaced Linux that the big operating systems do not
give you.”

- “A voice assistant that works with the network cable unplugged for
  everything on this computer, because the speech recognition and the AI model
  run on your own hardware.”
- “No account. No sign-in to use your own computer.”
- “No systemd, and no advertising built into the desktop.”
- “Your choice of AI model, and your choice of how the whole desktop looks.”
- “And all of it is free and open source. You can read every line.”

### 9. Close (5:50–6:05)

**[Website on screen: spacedlinux.com, then voxaai.me.]**

“Spaced Linux and Voxa. Download them at spacedlinux.com.”

**SAY TO VOXA:** “Voxa, pause.”

**[Cut to black.]**

## Check before filming

These depend on work that is not finished or not confirmed on a real desktop.
Try each one first; drop the line if it does not work on the day.

- **“Restore everything”, “VLC opens small”, walking directions and “clean up
  the text” on a long document** passed their automated tests but have not
  been watched working on a desktop.
- **“Nothing I just said left this room.”** True for commands, dictation and
  the local model. The spoken voice is fetched from an online service today,
  and web answers go to the internet. Either switch the voice to the offline
  one for the cold open, or change the line to “Nothing I just said was sent to
  an AI company.”
- **“Works with the network cable unplugged”** is true for opening apps,
  dictation, timers and system questions, with the offline voice. Web answers,
  music from the internet and the online voice need a connection. Say it only
  with that qualifier, as written above.
- **“No advertising built into the desktop”** is about Spaced itself. The
  Brave clean-up for 10.26.2 (issue #282) should be finished and checked with a
  packet capture before claiming the default browser is silent.
- **“The big operating systems do not give you”**: every point in section 8 is
  phrased as something Spaced does. If you name another system on camera, say
  only what you have checked yourself.
- **Installing GIMP and updating Spaced by voice** were built and tested in
  pieces; the full spoken flow has not been run end to end with a password.
