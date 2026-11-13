# Updating an installed Spaced Linux

An installed system updates from the Devuan archives and from the signed Spaced
Linux APT repository. **Spaced Update** is the front end for both. This guide
is for an installed system.

## Update with Spaced Update

Open **Spaced Update** from the menu, press **Check for Updates**, select what
to install, and press **Install Selected**. System packages and Flatpak entries
are listed separately, and the progress page runs "Update system packages" and
"Update Flatpak applications" as separate steps. The **OS Release** tab shows
the installed version next to the latest published release, with **Check
Release** and **Update System**.

Let the run finish and read every message before you try again. Keep a separate
backup of your own files first; a Timeshift snapshot is not a backup of your
documents.

## The same thing in a terminal

```bash
sudo apt update && sudo apt full-upgrade
```

That is the APT part only. Spaced Update also refreshes Flatpak apps and
runtimes, and it checks the package state around the transaction.

## What Spaced Update checks

- It first completes packages left unpacked by an interrupted run
  (`dpkg --configure --pending`), then checks the package database with
  `apt-get check` and `dpkg --audit`. If the database is not healthy, it stops
  and says that no further update steps will run.
- It asks APT for a plan with `apt-get --simulate`. If APT cannot produce one,
  the solver's own output is shown in full and no package is installed.
- It refuses a plan that removes a core Spaced package or changes the init
  system.
- After the transaction it checks the package database again, then refreshes the
  boot files.

## The APT transaction guard

`/etc/apt/apt.conf.d/60spaced-transaction-guard` runs
`/usr/lib/spaced-linux/spaced-update-apt-guard` before `dpkg` unpacks anything,
for every APT transaction — including `apt` commands you run yourself as root.
The guard refuses a transaction that removes a core Spaced package, changes the
init system, or installs an X server known to stop the desktop starting on AMD
graphics. When it refuses, nothing has been unpacked yet, so the system is still
in the state it was in before the command.

## When an update stops

1. Read the message and keep the log. Spaced Update keeps the failed solver
   output instead of hiding it.
2. If it says the repositories may be between coordinated uploads, do not force
   the upgrade from a terminal: wait, refresh, and run Spaced Update again.
3. Run Spaced Update again. It completes pending configuration before planning
   the next transaction, and one automatic retry covers an installation pass
   that did not finish (issue #337).
4. Do not run a dependency repair, a forced package removal, or your own
   `dpkg --configure` loop. Spaced deliberately avoids those, and they can turn
   a stopped update into a half-configured system (issue #415).
5. Report a stop that repeats: the Spaced version, live or installed, the steps,
   and the log. See [../SECURITY.md](../SECURITY.md) first if the problem is a
   security problem.

The recovery behaviour and the reason for the guard are recorded in
[FIXES.md](FIXES.md) under "APT solver failure followed by a damaged
command-line upgrade (#415)".

## Flatpak applications

Flatpak apps and runtimes update separately inside Spaced Update: they appear as
their own rows in the list and are applied in their own step, after the system
packages. In a terminal:

```bash
flatpak update
```

## Restart after a kernel or driver update

A new kernel or graphics driver is not used until the machine restarts. Spaced
Update refreshes the boot files at the end of a run, but the running system
still uses the old kernel until you reboot. Save your work, then restart. An
update never removes old kernels; cleanup is a separate action, so the previous
kernel is still there if the new one fails. For a graphics driver that will not
start the desktop, see [NVIDIA-RECOVERY.md](NVIDIA-RECOVERY.md).

## Check which version is installed

```bash
cat /etc/os-release
```

`VERSION_ID` is the Spaced version, for example `11.26.1`, and
`VERSION_CODENAME` is the same number with the dots removed.

## A new version or a new package revision

Both routes are defined under "Release versioning" in
[../AGENTS.md](../AGENTS.md):

- A **patch release** is a new OS version, such as `11.26.1` after `11.26`. It
  changes `/etc/os-release` and comes with a new ISO.
- A **package revision** keeps the OS version and adds `-N` to the packages, as
  in `11.26.1-2`. It delivers fixes through the signed repository without a new
  ISO, so `cat /etc/os-release` still prints `11.26.1` afterwards. Check the
  package version instead:

  ```bash
  dpkg-query -W -f='${Version}\n' spaced-meta spaced-mate-default-settings
  ```
