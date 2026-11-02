---
name: spaced-linux-dev-machine
description: "rhY's own workstation runs Spaced Linux, so Spaced changes can be verified here directly — on a private Xvfb display, never rhY's session."
metadata: 
  node_type: memory
  pinned: false
  originSessionId: 1e5c0034-f47b-4761-9ca0-96fc40a509fb
  modified: 2026-09-10T09:19:32.628Z
---

# rhY develops Spaced Linux on a machine running Spaced Linux

When asked to work on Spaced Linux, do not report desktop-level verification
as impossible. rhY's workstation is itself an upgraded Spaced Linux install
(`/etc/os-release` reports `ID=spaced`), with the Spaced themes in
`/usr/share/themes/Spaced-*`, the first-party Flatpaks installed, and the
`spaced-github` remote configured. When I said screenshot and GUI work could
not be done from source, rhY's answer was: "Do all of it. You're on an
upgraded spaced linux build right now."

That makes running applications, capturing screenshots, and reproducing
reported GUI bugs part of the job rather than something to hand back.

## How to do it without touching rhY's desktop

The standing rule against automating rhY's desktop still applies — rhY is
working at that machine. The way to satisfy both is a private X display that
rhY's pointer and windows never touch:

1. Start `Xvfb :91 -screen 0 1600x1000x24 -nolisten tcp`, and verify the
   server is the one just started. Stale servers from earlier sessions can
   already own a display number, and connecting to one of those, or falling
   back to `:0`, would capture rhY's real screen.
2. Run `marco --replace --sm-disable` on that display for real Spaced window
   decorations.
3. Start a private session bus with `dbus-launch`; do not borrow rhY's.
4. Launch Flatpaks with `flatpak run --env=DISPLAY=:91
   --env=GTK_THEME=Spaced-Linux-Dark <app-id>`. Pass the theme per run rather
   than using `flatpak override`, which would change rhY's live desktop.
5. Capture with a small GdkPixbuf script; `xdotool` against `:91` is fine
   because that display is not shared with a person.

To run a locally built Flatpak, `flatpak-builder --run` is not enough — it
ignores the manifest's `finish-args`, so an application needing Flatpak or
network access never gets far enough to show a window. Export the build and
install it into an isolated installation instead by setting
`FLATPAK_USER_DIR` to a scratch directory, which also avoids replacing the
copy rhY has installed.

Tear the display, window manager, and bus down when finished.

## This box is the primary Spaced Linux test machine — report what you find

rhY treats this workstation as the primary testing machine for Spaced Linux
and SpacedUpdate: "This is the primary testing machine, so if there's any
issues in spaced linux or in spacedupdate, we need to know."

So when something on this machine misbehaves — a desktop component that does
not come back, a migration that lands in the wrong order, drift between what
an in-place upgrade produces and what a fresh ISO install would produce — the
job is not finished by repairing rhY's running session. Trace it back to the
Spaced Linux or SpacedUpdate code that caused it and report the defect, even
when it was incidental to whatever was actually being asked.

Note also that this install has been upgraded in place since an early release
rather than reinstalled, which makes it exactly the machine where upgrade-path
bugs show up first. Treat "it works on a fresh install" as an unproven claim
until the upgrade path is checked too.

**10.26.2 work in progress (2026-10-08):** branch `fix/10.26.2` in `~/spaced-10.26` (plan in `docs/10.26.2-ISSUE-PLAN.md`; nothing pushed). Two headline fixes found by measuring on a virtual screen: (1) #279 — Compiz's `gtk-window-decorator` displaced each title-bar button's click area 10 px left/down; patch in `patches/compiz/`, built by `make marco` in the chroot (needs rhY's password, NOT yet compiled or tested); themes also got 32x27 button boxes; `scripts/tests/titlebar-hit-test.sh` measures under Compiz+decorator in Xvfb. (2) #275 — `.caja-desktop-window * {background:none}` in `Spaced-Dark/gtk-3.0/spaced-overrides.css` erased desktop selection; fixed there (Caja uses :selected when focused, :active when not, labels always white). Local-model tasks ran through `~/spaced-strata-queue*.sh` with task files in each repo's `.strata/` (excluded from git); their runner does `git add -A`, so hand edits made while a task runs get swept into its commit — wait for the repo to be free. Spaced Update work: branch `cleanup-277`; Welcome: `issues-285-287`; Bazaar: `issues-291-292` (cannot be compiled on this machine). rhY wants an overlay VM (10.26.1 ISO in KVM + 10.26.2 changes copied in) for testing once Strata is stopped; a real ISO needs `make iso-build` with rhY's password.
