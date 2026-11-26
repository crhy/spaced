# DESIGN.md — Spaced GPU Manager (issue #426, ships in 11.26.4)

Design only. No shipped code changes. The look and flow here must be approved before
the backend work continues on `gpu-manager/11.26.4`.

Base: the working candidate on branch `gpu-manager/11.26.4` (docs/GPU-MANAGER.md,
`spaced_gpu.py`, `spaced-gpu-manager.py`, `spaced-gpu-helper`,
`etc/init.d/spaced-gpu-guard`, polkit action, 41 passing tests). Its safety backend is
kept unchanged (journaled Xorg edits, boot guard, confirmation deadline, rollback,
refusing custom Xorg, PCI identity, UUID-based CUDA selection). This document changes
the **words, the look and the flow** on top of it, per rhY/Claude's review findings.

## 1. Name and icon

- **Name: "Spaced GPU Manager"** (the candidate already renamed it). Menu title
  "GPU Manager", window title "Spaced GPU Manager". The old names
  `spaced-gpu-driver-manager` and `spaced-nvidia-installer` stay as compatibility
  commands (TODAY.md §7) — never in user-visible text.
- One sentence under the title, always specific to this machine:
  "Three graphics cards · your screen is on the GeForce RTX 4070 Ti SUPER".
- **Icon**: stock `video-display` for the window and menu (no new artwork needed for
  11.26.4); inside the app a symbolic board-with-fan badge per card, and a
  board-inside-a-CPU badge for the integrated GPU. No vendor colours (STYLE.md §4).
- Comment for the .desktop: "See your graphics cards, choose what each one does, and
  move your screen between them."

## 2. Shape of the app

HeaderBar (title + subtitle + Refresh + Drivers + About) and one page bar, exactly like
Spaced Update (STYLE.md §1): **Overview · Roles · Move monitor · Drivers**.
Minimum 720×540, default 900×680. Trial banners appear once, at the top, never as
wall-of-footer text (review finding 3).

```
┌ Spaced GPU Manager ────────────────────────────────────────────────┐
│ Three graphics cards · your screen is on the GeForce RTX 4070 Ti   │
│ [Overview] [Roles] [Move monitor] [Drivers]      ⟳ refresh  ⚠ banner│
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ card 1  card 2  card 3      (one card per graphics card)      │ │
│  └───────────────────────────────────────────────────────────────┘ │
│ one short status line                                              │
└────────────────────────────────────────────────────────────────────┘
```

## 3. Words: engineer → human (review finding 1)

The candidate says things a user cannot act on. The redesign keeps every fact but says
it plainly. Left = today's candidate string, right = shipped string.

| Candidate (engineer wording) | Shipped (plain words) |
|---|---|
| `Active display output` | "Your screen is on this card" |
| `Monitor connected (scanout unverified)` | "Your screen is plugged into this card, but Spaced is not using it for the desktop yet" |
| `No connected monitor reported` | "Nothing is plugged into this card" |
| `Firmware primary: Yes (not necessarily desktop renderer)` | "Shows the boot screens first" (tooltip: "Your PC's start-up picture comes from this card. That is not the same as Spaced drawing your desktop on it.") |
| `Ports: DP-2: disconnected (disabled)` and friends | "Two sockets: DisplayPort, HDMI. One of them has your screen — open *Move monitor* to find which." (full connector list only in the *Move monitor* page, where a picture and a port name are meaningful) |
| `PCIe link 2.5 GT/s × 16` | "PCIe 4.0 · 16 lanes" (see §4; live speed never on the card face) |
| `VRAM usage unavailable (shared memory or driver does not expose it)` | "Shared memory — Spaced cannot measure it" (tooltip carries the technical reason) |
| `Not bound` | "No driver is handling this card yet" |
| `Driver: nvidia 570.172.08` | "Driver: NVIDIA 570.172.08 (installed by Spaced)" |
| `Desktop trial` | "Trying a new setup" everywhere; the word *trial* only in the countdown line |
| `Render offload`, `xorg.conf.d`, `BusID`, `X provider`, `modprobe` | never shown; they live in ARCHITECTURE.md and the log |

Honesty rules that must not be lost with the rewording: a connected plug is not proof
that the card draws the desktop; a boot-order card is not proof that it renders; the
app never claims a memory saving it has not measured.

## 4. The Overview page

One card per graphics card, biggest/most-used first (the card drawing the desktop,
then the others), like Spaced Monitor's cards (STYLE.md §2).

Card fields, in this order, all strings written out:

1. **Name** — "GeForce RTX 4070 Ti SUPER" (13 px bold). No PCI address on the face.
2. **Badge line** — what it is and what it's for: "NVIDIA · 16 GB · drives your screen" /
   "AMD · built into your CPU · can take over the desktop" / "NVIDIA · 8 GB · AI & compute".
3. **Role chip** — Desktop / AI & compute / Games / Off (page 2 sets it).
4. **VRAM gauge + pair** — "12.6 GB of 16 GB used" (violet, Monitor's GPU MEMORY colour).
   For the iGPU: "Shared with your PC · about 2 GB available to graphics".
5. **PCIe line (review finding 2)** — the card's own capability in big text:
   "PCIe 4.0 · 16 lanes". Detail, in muted text under it, only when it differs:
   "· running at 4 lanes because of the slot it's in". Never a bare
   "2.5 GT/s" idle-link number.
6. **Monitor line** — "Your screen: HDMI 2 on this card, 1920 × 1080" /
   "Nothing plugged in".
7. **Two buttons**: "Set up…" (opens the role picker for this card) and
   "Move my screen here…" (disabled with a tooltip when it cannot happen yet:
   "Plug your screen into this card first, then press ⟳ refresh").

Under the cards, one line only (the candidate's advice block restyled as a sentence,
never a paragraph): "Your desktop is using 310 MB of the RTX 4070 Ti SUPER. Moving the
desktop to the CPU's graphics frees it for games and AI — *Roles* explains the trade."

Machine example (bigboy):

```
[GeForce RTX 4070 Ti SUPER]  NVIDIA · 16 GB · drives your screen   [Desktop]
  VRAM 0.3 / 16 GB          PCIe 4.0 · 16 lanes
  Your screen: HDMI 2 · 1920 × 1080            [Set up…]  [Move my screen here…]
[GeForce RTX 3050]           NVIDIA · 8 GB · AI & compute          [AI & compute]
  VRAM 0 / 8 GB             PCIe 4.0 · 16 lanes · running at 4 lanes (its slot)
  Nothing plugged in                          [Set up…]  [Move my screen here…]
[Radeon 610M]                AMD · built into your CPU             [Off]
  Shared memory · about 2 GB for graphics     PCIe (in the CPU)
  Ports free: DisplayPort, HDMI               [Set up…]  [Move my screen here…]
```

## 5. The Roles page (review finding 4: a real picker)

Today's candidate only offers buttons that print an environment prefix. The redesign
turns that into the page rhY asked for: for each card, one role out of four, chosen in
a dialog, applied on OK, with the costs stated before the button is pressable.

Roles, with the exact wording:

- **Desktop** — "Draws your screen. Everything you see runs on this card."
  Note: only one card can have it; taking it away is the *Move monitor* flow.
- **AI & compute** — "Saves this card for your AI work. Spaced gives your AI programs
  this card by its real name, so they can't end up on the wrong one."
- **Games** — "Saves this card for games. Steam, Lutris and Wine games start on this
  card automatically; your screen stays on the other one."
- **Off** — "Leave it alone. Nothing starts here unless you say so. The card can still
  be used for your screen." (This version does not power a card down — one sentence,
  not a footer: "Spaced 11.26.4 cannot switch a graphics card off to save power.")

The picker (one dialog per card, radio buttons, not a raw prefix):

```
What should this card do?
GeForce RTX 3050 · 8 GB

● AI & compute     Your AI programs get this card. Spaced picks it by name.
○ Desktop          Draw your screen. You must move your screen's cable first.
○ Games            Games start here. Desktop apps stay on the other card.
○ Off              Nothing starts here.

What it changes: your AI programs must be started with Spaced's launcher
("Run on the RTX 3050…"). Nothing else about your PC changes. Nothing is
downloaded or installed.
                                          [Cancel]  [Set this role]
```

The iGPU suggestion appears once, where it is true, as a highlighted card:

> "Your CPU has its own graphics (Radeon 610M). If you plug your screen into the
> motherboard's socket, your desktop moves onto it and the whole 16 GB of the
> RTX 4070 Ti SUPER is free for AI and games." → *Move my screen to the CPU's graphics*

Per-role honesty lines (shown before applying, never buried):

- Desktop: "Your screen must be plugged into this card first."
- Games: "Games run a few percent slower when a different card draws the screen, and
  the picture is copied between cards, which adds a little lag. Some NVIDIA
  features (G-Sync) don't work across cards."
- AI & compute: "Two AI programs can't both own one card exclusively; your program
  decides. Flatpak/container programs must allow GPU access themselves."
- Off: "Spaced 11.26.4 cannot switch a card off to save power."

Rollback of a role: "Undo" restores the previous role; nothing persists until the
trial is confirmed (ARCHITECTURE.md).

## 6. The Move-monitor page: the guided cable move (review finding 4)

The part the candidate is missing entirely. Purpose, in the user's words:
"Your screen is plugged into the wrong card for the setup you chose."
Three steps, each shown as a card, with a port table taken from
`/sys/class/drm` (which is the only honest source of "which socket belongs to which
card"), and nothing is applied until rhY has physically moved the cable and pressed
"I've moved it".

```
Move your screen onto the CPU's graphics
Why: your desktop uses 310 MB of the RTX 4070 Ti SUPER. Moving the desktop onto your
CPU's own graphics frees all 16 GB for AI and games.
Cost, honestly: games on the 4070 run a few percent slower and a little laggier, some
NVIDIA features (G-Sync) don't work across cards, and your motherboard's socket may
support fewer screens than the 4070's. Spaced measures nothing until it is done and
will show you what changed.

1 · Find the right socket
   Your CPU's graphics has these sockets, on the back of the PC near the USB ports:
   • DisplayPort 1        (nothing plugged in)
   • HDMI 1               (nothing plugged in)
   Your screen is in: HDMI 2 — on the GeForce RTX 4070 Ti SUPER.
   (Sockets are grouped by card on the back of every PC; the motherboard's group is
   next to the USB and audio jacks.)

2 · Move the cable
   Turn the PC down but leave it on, or do it after a reboot — Spaced will tell you
   which socket it wants before it changes anything.

3 · Tell Spaced
   [ ⟳ I've moved the cable ]  → Spaced checks the socket is live, then
   [ Use it for the desktop ]  → the countdown starts

Then: your screen goes blank for a few seconds while Spaced restarts the desktop.
Log in within 3 minutes and press "Keep this". If you do nothing, Spaced puts
everything back on its own.
```

Strings for the states the guide must handle:

- "This card has no sockets: nothing to plug in." (driver not exposing connectors)
- "Two sockets, neither plugged in yet."
- "Your screen is already here." → the card is greyed with "Nothing to move".
- "That socket is not reporting a screen yet." → "Check the cable is in firmly, then
  press ⟳ I've moved the cable."
- "Another setup is waiting to be confirmed — finish it first." (one pending trial)

Cost strings are stated in step 1's *Cost* card **and** in the confirmation dialog. The
physical port names are always shown as `<kind> <number>` ("HDMI 2"), never as
`HDMI-A-1`, and the sysfs names appear only in the log.

## 7. The Drivers page (today's NVIDIA install/recovery, restyled)

Everything TODAY.md §1 promises, on one page in Monitor's card style:

- A **status card**: "NVIDIA driver: NVIDIA 570.172.08 · working" / "no driver
  installed" / "installed, waiting for a reboot" / "startup check found a problem".
- Buttons: **Check graphics** (the audit, unprivileged), **Install NVIDIA driver** /
  **Replace working NVIDIA driver** (same warning wording as today: "Keeping it is the
  safest choice"), **Install / repair AMD drivers**, **Restore graphics** (rollback),
  **Copy log**, plus the three support links.
- The verification paragraph from today becomes a bullet list of what is checked before
  reboot (kernel headers, Secure Boot, packages, module building, module policy, boot
  image contents, X libraries, GRUB arguments, Compiz launcher) and after reboot
  (card driver, `nvidia-smi`, 3D, Compiz, panel, file manager).
- The pulsing progress bar, the live log and the reboot prompt keep their exact
  behaviour; only their typography moves to the family look.
- Secure Boot, disk space, unsupported version and the other 20 error codes keep
  today's messages — they are already plain words.

## 8. First run

First launch after install (no role chosen yet, no managed Xorg file):

```
Spaced GPU Manager
See your graphics cards, choose what each one does, and move your screen between them.

• Nothing happens until you press a button. Spaced never changes your graphics setup on
  its own.
• Changing which card draws your screen switches your screen off for a few seconds and
  restarts your desktop. Spaced puts everything back if you don't confirm it.
• Save your work before you change anything.

            [ Look around ]      [ Choose my setup ]
```

"Look around" opens Overview read-only (the candidate's `--preview` mode: privileged
buttons disabled). "Choose my setup" opens Roles with the iGPU suggestion highlighted
when a second card exists and the monitor is on a discrete card.

A trial countdown window opens by itself in the new session (autostart
`spaced-gpu-trial.desktop`), showing:

```
New desktop setup is being tried — 2:47 left
Keep this desktop, or Spaced will put the old one back and end this session.
            [ Keep this desktop ]     [ Put it back ]
```

Strings for the guard, kept from the candidate (they are already plain):
"Save your work and reboot. Confirm within 3 minutes of start-up or everything goes
back." / "Spaced put the old desktop back." / recovery from a text console:
`sudo /usr/lib/spaced-linux/spaced-gpu-helper revert` then `sudo reboot`.

## 9. What this version says it does not do

One line each, on the relevant page — never a footer wall:

- cannot power a card off to save power;
- cannot promise a VRAM saving before the move is measured;
- cannot decide for Flatpak/container programs, MIG, or AMD/Intel compute tools;
- refuses to touch graphics settings that a person added by hand
  ("Your own graphics settings are in the way — Spaced will not overwrite them");
- on more than one NVIDIA card, it will not guess which one games should use
  ("Choose the card inside the game for now").

## 10. Screens in this design

`screens/overview-spaced-dark.png`, `overview-light.png`, `roles-spaced-dark.png`,
`roles-light.png`, `move-monitor-spaced-dark.png`, `move-monitor-light.png`,
`drivers-spaced-dark.png`, `drivers-light.png`, `first-run-spaced-dark.png`,
`first-run-light.png` — built by `prototype/gpu_manager_prototype.py` from fake
bigboy data (RTX 4070 Ti SUPER, RTX 3050 in a ×4 slot, Radeon 610M), rendered under
Xvfb with the real Spaced Linux Dark and Spaced Linux Light themes.
