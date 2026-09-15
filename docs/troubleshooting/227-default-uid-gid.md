# Default user and group UID/GID — research for issue #227

Research-only note (no code or configuration changed). Question from the
issue: someone on Reddit suggested the default user and group should be
UID/GID 1000 "for compatibility with other distros". This note traces what
UID/GID the live user and the first installed user actually get, what (if
anything) is hardcoded to a UID, the upsides/downsides of guaranteeing
1000:1000, and what the minimal change would be.

## TL;DR

- Live-session user `user` **is 1000:1000** (created first in a fresh
  chroot with plain `useradd`, and `user` is also live-config's Debian
  default name).
- First **installed** user is **probably 1001:1001, not 1000:1000**,
  even though every default in the chain "wants" 1000. The baked-in live
  `user` (UID 1000) is copied into the install target by unpackfs and is
  still present when Calamares creates the new account, so `useradd`
  skips to the next free ID. This needs a 5-minute verification on a real
  install (commands in §5); if confirmed, the fix is small (two options
  in §4).
- Nothing in this repository hardcodes UID 1000, so honoring the request
  would not break any overlay, script, or test found here.

## 1. What UID/GID does the first installed user get today?

Short version: nothing in this repository pins it; the value falls out of
Calamares plus Debian `useradd` defaults, with one Spaced-specific twist
(the baked-in live user) that likely pushes the first installed user to
1001.

### 1a. Calamares users module: no UID/GID knobs

`overlays/etc/calamares/modules/users.conf:1-23` sets only group
membership and password policy:

- `userGroup: users`, `defaultGroups:` (cdrom, sudo, audio, …),
  `autologinGroup: autologin`, `sudoersGroup: sudo`
  (`overlays/etc/calamares/modules/users.conf:2-16`)
- `setRootPassword: false` and `passwordRequirements: minLength: 1`
  (`overlays/etc/calamares/modules/users.conf:17-23`)

There is no UID/GID option in this file, and none of the shellprocess
modules create users either: postinstall only fixes permissions, enables
chrony and refreshes grub/initramfs
(`overlays/etc/calamares/modules/shellprocess@spaced-postinstall.conf:1-10`),
machineid only generates the D-Bus machine ID
(`overlays/etc/calamares/modules/shellprocess@spaced-machineid.conf:1-16`),
and time-sync only syncs the clock. Upstream Calamares' users job creates
the account with `useradd -m -U … <login>` — notably **without `-u` or
`-g`** — then adds supplementary groups with `usermod -aG`, then
`chown -R <login>:<login> /home/<login>` (all name-based, so safe under
any numeric ID). These flags are from current upstream Calamares
`CreateUserJob.cpp`; Devuan Ceres tracks upstream closely, but the exact
installed build should be re-confirmed when the §5 check runs. With no
`-u`, `useradd` assigns the smallest free UID
≥ `UID_MIN`, and `-U` creates a matching user-private primary group.
Debian's defaults are `UID_MIN`/`GID_MIN` 1000 (`/etc/login.defs` on any
Debian/Devuan host) and `FIRST_UID=1000` (`/etc/adduser.conf`, shown as
the compiled-in default). So on a pristine target the first user would be
1000:1000 (primary group `<login>`, plus supplementary `users` — GID 100
on Debian — sudo, etc.).

### 1b. The twist: the live `user` already occupies UID 1000 in the target

The install target is a copy of the live squashfs (unpackfs runs before
the users job in the exec sequence,
`overlays/etc/calamares/settings.conf:36-60` — `unpackfs` at line 40,
`users` at line 48, cleanup last at line 56). That squashfs contains a
baked-in `user` account because the live-build hook creates one at image
build time:

```sh
id -u user >/dev/null 2>&1 || useradd -m -s /bin/bash user
```

(`scripts/iso/01-configure.chroot:53-54`, installed as a live hook by
`Makefile:120-122`). Plain `useradd` in a fresh debootstrap chroot yields
UID/GID 1000 — the first non-system account. So when the `users` job runs
`useradd -m -U <newlogin>` inside the target, UID 1000 (and the `user`
name) are already taken and the new account most likely lands on
**UID 1001 with primary group GID 1001**. Only afterwards does
`spaced-cleanup` remove the live account:

```sh
if [ 'USER' != 'user' ] && id user >/dev/null 2>&1; then userdel -r user; fi
```

(`overlays/etc/calamares/modules/shellprocess@spaced-cleanup.conf:21`;
context in lines 9-11). No `unpackfs.conf` is shipped in this repository
to exclude the live account from the copy, so whatever
`calamares-settings-debian` provides by default applies — and the default
is a full copy (the cleanup job itself assumes live files such as
`/home/*/Desktop/install-spaced-linux.desktop` exist in the target,
lines 13-17).

### 1c. No shipped adduser.conf / login.defs overrides

This repository ships neither `overlays/etc/adduser.conf` nor
`overlays/etc/login.defs` (no matches for those names or for
`FIRST_UID`/`UID_MIN` under `overlays/`, `config/`, `scripts/`, `tests/`),
so the installed system inherits stock Debian/Devuan ID policy: first
free human UID/GID is 1000. Nothing here *prevents* 1000:1000 — the only
occupant is the live user described above.

## 2. Live-session user and hardcoded UIDs

- The live user is `user` (`config/iso.yaml:22`, `live_user: user`, with
  live/root passwords on lines 23-24) and resolves to **UID/GID 1000**:
  it is the first account created in the image chroot
  (`scripts/iso/01-configure.chroot:54`), and `user` is also live-config's
  own Debian default, so the boot-time live-config path
  (`live-config`, `live-config-sysvinit` in `config/packages.yaml:158-162`)
  agrees rather than conflicting. LightDM autologs in as `user` by name
  (`scripts/iso/01-configure.chroot:17`), and the hook seeds and
  name-chowns its home (`scripts/iso/01-configure.chroot:79-81`).
- Grep over `overlays scripts config tests` for `1000|1001|useradd|
  adduser|live-config|FIRST_UID` finds **no file that assumes or pins UID
  1000**: the only `1000` hits besides this chain are a Compiz fractional
  setting (`0.100000`, noise) and the NVIDIA helper's *generic*
  desktop-user range check `$3 >= 1000 && $3 < 60000`
  (`overlays/usr/lib/spaced-linux/spaced-nvidia-helper:98-104`), which
  works for any human UID and resolves the account by name/`PKEXEC_UID`.
  All `chown` invocations found are name-based (`user:user`,
  `login:login`, `0:0` for build staging in `Makefile:141`).
- Post-install, `live-config`/`live-boot` are removed from the target
  (`overlays/etc/calamares/modules/packages.conf:6-14`, enforced by
  `scripts/check.sh:591` and `scripts/tests/test-release-package-payload.sh:26`),
  and the live autologin lines are stripped from LightDM by
  `packages/spaced-mate-default-settings/DEBIAN/postinst:6-14` (enforced
  by `scripts/tests/test-release-package-payload.sh:45`). The installed
  LightDM defaults contain no autologin and no UID references
  (`overlays/etc/lightdm/lightdm.conf`,
  `overlays/etc/lightdm/lightdm.conf.d/60-spaced-installed.conf`).

Edge case worth knowing (not changed, just observed): if the person
installing chooses the login name `user`, the `useradd` in the target
collides with the baked-in live account (username already in use), and
the cleanup job's guard compares the literal string `'USER'` to `'user'`,
so it always deletes a `user` account when one exists. A follow-up check
of that quoting is advisable but out of scope here.

## 3. Upsides and downsides of guaranteeing 1000:1000

Upsides (why the Reddit suggestion has merit — all of these key off the
numeric ID stored on disk, not the name):

- **External drives / shared data partitions:** ext4 (and other
  POSIX filesystems on USB drives, SD cards, dual-boot data partitions)
  store the numeric UID/GID. Today Ubuntu, Fedora, Debian, Mint, Arch and
  Devuan all give the first user 1000:1000, so a drive written on any of
  them is read/write on the others without `chown`. If Spaced's first
  user is 1001, files the user creates on external drives show up as
  owned by "some other user" (or inaccessible) on every other distro.
- **Dual-boot / shared `/home`:** sharing one home partition between
  Spaced and another distro only works permission-clean if both sides'
  users share the UID/GID.
- **Flatpak / containers / Docker bind mounts:** Flatpak itself is
  UID-agnostic, but anything bind-mounting host paths into a container
  (Docker `-v ~:/data`, distrobox, systemd-nspawn directory binds) maps
  by number; mismatched UIDs produce root-owned-looking or inaccessible
  files across the boundary.
- **Backups and restores (Timeshift, rsync `-a`):** archives preserve
  numeric ownership. Restoring a Timeshift snapshot or an rsync backup
  taken on a 1000-based distro onto a 1001 account (or vice versa)
  leaves the user's own files owned by the wrong ID until manually
  `chown`ed — exactly the kind of papercut a "first user is always 1000"
  convention exists to avoid.
- **NFS:** classic NFS (`auth_sys`) authorizes purely by numeric
  UID/GID, so cross-distro NFS home dirs / shares expect 1000.

Downsides and limits (why "guarantee" is a strong word):

- **Only the first account can be 1000.** The second user is 1001+ on
  every distro; the convention helps exactly one account per machine.
- **It cannot be forced unconditionally.** If *any* account already
  holds 1000 in the target (today: the live `user`), `useradd` moves on
  to 1001 unless forced with `-o` (duplicate UIDs — never acceptable) or
  the occupant is removed first. A "guarantee" is therefore really
  "ensure UID 1000 is free at account-creation time", which is fragile
  across Calamares upgrades since the users module offers no `-u` option.
- **Collision/ordering risk:** any future build-time system account in
  the 1000+ range, or a target with a reused/preserved `/home`, would
  silently push the new user off 1000 again. The fix must be re-verified
  per release (a 30-second `id` check, see §5).
- **Scope of benefit:** single-user desktops with no shared media see no
  difference; the payoff is entirely in multi-distro / multi-machine
  file sharing.

## 4. Conclusion and minimal change

> **Verified on a real install (2026-09-14):** a Spaced Linux 9.26.2 system
> installed with Calamares has its first user at **UID 1001, GID 1002**, and
> no account at UID 1000. The `scanner` group holds GID 1001, so two separate
> problems push the IDs up: the live `user` occupying 1000 during account
> creation, and a package-created `scanner` group taking the first free
> GID ≥ 1000. Any fix must handle both and needs a full-install VM test,
> so it is planned after 9.26.3.

- **Live user:** already 1000:1000. Nothing to do.
- **First installed user:** almost certainly **1001:1001 today**, an
  accident of install ordering (live `user` occupies 1000 when the new
  account is created), not of policy. So the issue should **not** be
  closed as "already the case" — but it also needs no new ID-management
  machinery, because stock Debian policy already yields 1000 the moment
  the slot is free.
- **Minimal change (after verifying §5 confirms 1001):** pick one —
  - **Option A (recommended): stop baking the live user into the
    squashfs.** Drop the account-creation block
    (`scripts/iso/01-configure.chroot:53-59`) and the baked-home
    seeding (`scripts/iso/01-configure.chroot:79-81`), and let
    `live-config`
    (already shipped, `config/packages.yaml:161-162`) create `user`
    (UID 1000) at boot, as stock Debian live does. unpackfs copies the
    squashfs (which then has no UID-1000 occupant), so the installed
    account becomes 1000:1000. Needs care: the hook's `cp -a
    /etc/skel/. /home/user`, Desktop pruning, and `chown` lines assume a
    baked-in home and must become conditional, and LightDM autologin plus
    the Calamares desktop icon must be re-tested on the live session.
  - **Option B: delete the live user from the target *before* the users
    job.** Add a `shellprocess` instance ordered ahead of `users` in
    `overlays/etc/calamares/settings.conf:36-60` that runs
    `userdel -r user` inside the target (same chrooted mechanism the
    existing cleanup job uses). Smaller diff, but it leaves a baked-in
    account in every live boot and depends on job ordering surviving
    future `calamares-settings-debian` updates.
  - Either way, add a release-time assertion: install in a VM and check
    `id <newuser>` is `uid=1000 gid=1000` (§5). Do **not** patch a
    numeric `-u 1000` anywhere — Calamares offers no such option, and a
    hardcoded flag would fail loudly the day 1000 is legitimately taken.

## 5. How to verify (maintainer / tester, ~5 minutes)

On the live ISO, before installing (confirms the premise):

```sh
id user                  # expect uid=1000(user) gid=1000(user)
grep -E 'user|1000' /etc/passwd
```

After a default install, on the installed system:

```sh
id <your-login>          # 1000:1000 if fixed, 1001:1001 if issue reproduces
ls -ln /home             # numeric owner of the new home dir
getent passwd 1000 1001  # who holds which slot
```

To confirm the mechanism during an install (optional): open a terminal
while Calamares is at the user-creation step and inspect
`/tmp/calamares-root-*/etc/passwd` (actual mount path varies) — the
baked-in `user` entry at UID 1000 should be visible before the new
account is created.

## 6. Draft reply for issue #227

> Thanks for raising this — good news: we don't need any new ID
> machinery, and nothing in the system is hardcoded to a particular UID.
>
> What we found: the live-session user `user` is already UID/GID 1000
> (stock Debian `useradd`/`live-config` defaults). But the *first
> installed* user most likely lands on **1001:1001** today, by accident:
> the live image carries a baked-in `user` account (UID 1000) into the
> install target, and Calamares creates the new account while that
> occupant is still there, so `useradd` hands out the next free ID. The
> live account is only deleted afterwards.
>
> Since every other mainstream distro gives its first user 1000:1000,
> matching that is worth doing: it keeps external ext4 drives, shared
> `/home` partitions, Timeshift/rsync restores, Docker bind mounts and
> NFS shares working by numeric ownership across distros with no manual
> `chown`. The only real caveat is that the convention can cover just the
> first account, and it holds only while UID 1000 is free at install
> time — which is exactly what we'll ensure.
>
> Next step: we'll confirm `id` shows 1001 on a test install, then make
> the minimal fix (create the live user at boot via live-config instead
> of baking it into the image, or remove it from the target before user
> creation) and add an install-time UID check to release testing. Leaving
> this open until the verification lands.
