# Spaced Linux 11.26.1 is out

A patch release: the same desktop you know, with fewer sharp edges.

**Already on 11.26?** Open **Spaced Update** and install, or run `sudo apt
update && sudo apt full-upgrade`, then reboot. **Starting fresh?** Write the ISO
to a stick and check it with `sha256sum -c spaced-linux-11.26.1-amd64.iso.sha256`.

**What you will notice**

- Rebooting and powering off no longer crash the session manager.
- An install that reuses an existing home partition keeps that home.
- Updates stop before they can make things worse, and show the real error.
- The live USB doubles as a rescue stick (GParted, TestDisk, PhotoRec,
  ddrescue, `smartctl`) and says its own passwords; those tools never reach the
  installed system.
- Daily maintenance runs on machines that are off at night, desktop icons stay
  on screen, `xkill` has its cursor back, and right-clicking an image offers
  **Set as Wallpaper…**.

**Not tested:** all of it ran in virtual machines — no physical PC, real GPU,
multi-monitor setup or real USB stick. **Found a problem?** Open an issue at
<https://github.com/crhy/spaced/issues> with your Spaced version and the steps
to reproduce it. Thanks to the people who reported these issues and sent logs,
screenshots and the cursor artwork.
