# TODAY.md — what the current GPU driver app does, function by function

Nothing in this list may be lost when the GPU Manager replaces the app.
Source of truth: `overlays/usr/lib/spaced-linux/` on `main` at the time of writing
(spaced 11.26.2). Files: `spaced-nvidia-installer.py` (GTK UI),
`spaced-nvidia-helper` (privileged bash), `spaced_nvidia_state.py`,
`spaced-nvidia-postboot.py`, `spaced-nvidia-compat.py`, `spaced-nvidia-config.py`,
entry points `usr/local/bin/spaced-gpu-driver-manager` (+ `spaced-nvidia-installer`
compat shim), `.desktop`, autostart, polkit action, and
`scripts/spaced-nvidia-installer.sh` (maintainer install).

## 1. `spaced-nvidia-installer.py` — the GTK UI ("Spaced GPU Driver Manager")

| Function | What it must keep doing in the GPU Manager |
|---|---|
| `Installer.__init__` | window 800×600, heading + subtitle, "Detected hardware" frame, the long verification paragraph, pulsing progress bar, monospace log view, the six buttons, the three support links (Online Help, Discord, Telegram), and the four start-up progress states (awaiting reboot / verified after reboot / verification pending / no device) |
| `Installer.detect_gpu` (static) | `lspci -nn` filter for VGA/3D/display controllers; feeds the has_nvidia / has_amd sensitivity rules |
| `Installer.detect_working_nvidia` (static) | `nvidia-smi -L` exit status = "a working NVIDIA driver exists" → relabels the install button to *Replace Working NVIDIA Driver* |
| `Installer.on_delete` | refuses to close while a transaction runs |
| `Installer.append_log` | log lines + auto-scroll mark |
| `Installer.pulse` | pulse the progress bar while busy |
| `Installer.set_busy` | button sensitivity matrix while a transaction runs |
| `Installer.confirm_install` | replace-vs-install confirmation wording ("Keeping it is the safest choice…") |
| `Installer.confirm_rollback` | "Restore Graphics?" warning: removes packages from the last transaction, restores saved configuration, rebuilds boot image, offers reboot |
| `Installer.start_action` | resets log/progress, sets pulse timer, spawns the worker thread |
| `Installer.process_line` | parses `SPACED_STATUS/WARNING/ERROR/SUCCESS` protocol from the helper |
| `Installer.run_action` | `pkexec` + helper, `--desktop-user`, `--replace-working-driver`, audit runs unprivileged |
| `Installer.finish_action` | maps exit codes to progress text and dialogs (`126/127` = auth cancelled) |
| `Installer.show_error` | error dialog with the log path `/var/log/spaced-nvidia-installer.log` |
| `Installer.show_reboot_dialog` | "Reboot Now / Reboot Later" after success or restore |
| `Installer.request_reboot`, `run_reboot`, `reboot_failed` | `pkexec … --reboot --desktop-user` and its failure path |
| `Installer.copy_log` | copies the whole log to the clipboard (`Gtk.Clipboard.store()`) |
| `ERRORS` table (codes 3…52) | every message the helper can produce, incl. Secure Boot (10), amd64-only (11), no NVIDIA card (12), desktop user (13), disk space (14/15), headers (20), Devuan package (21), NVIDIA repo (22), Driver Assistant (23/24), working driver left alone (25), per-step recovery failures (30…47), no verified install awaiting reboot (50), nothing to roll back (51), recovery incomplete (52) |

## 2. `spaced-nvidia-helper` — privileged bash (modes `--audit --install --install-amd --reboot --rollback`)

Logging/protocol: `status`, `warning`, `fatal` (emits `SPACED_ERROR:<code>:`, runs
`rollback_transaction` when a transaction is active), `cleanup` (removes temp keyring),
`unexpected_failure` (ERR trap with line number).

Argument/env: `parse_args` (mode, `--desktop-user`, `--reboot-after`,
`--replace-working-driver`), `require_root`.

Desktop user: `resolve_desktop_user` (PKEXEC_UID → passwd scan; UID 1000–59999; fatal 13),
`run_as_desktop_user` (`runuser` with HOME/USER/LOGNAME/XDG_RUNTIME_DIR).

Detection: `detect_nvidia_gpu` (lspci vendor match), `working_nvidia_driver`
(nvidia-smi -L **and** `nvidia` in /proc/modules), `apt_candidate`,
`detect_debian_release` (Debian compatibility 11/12/13, CUDA keyring URL + pinned
SHA-256, fatal 24 for unsupported), `detect_nvidia_gpu`'s vendor list,
`installed_packages`, `installed_driver_versions` (the NVIDIA/CUDA package regex).

Preconditions: `check_secure_boot` (mokutil; fatal 10), `require_candidate` (fatal 21),
`check_disk_space` (2 GB root / 200 MB /boot; fatal 14/15).

Transaction journal: `new_run` (`/var/lib/spaced-nvidia-installer/runs/<id>`),
`backup_configuration` (config snapshot + package list + driver versions +
`current-run` file), `record_configuration_changes`, `restore_configuration`
(fatal 52 without a per-file backup), `record_new_nvidia_packages`
(before/after `comm` + NVIDIA regex), `remove_recorded_nvidia_packages`
(simulated purge plan; refuses to remove packages the transaction did not add → 52).

Rollback machinery: `rollback_step` (per-step warnings), `rollback_transaction`
(resume an interrupted install from `current-run`; `dpkg --configure -a`, `apt -f
install`, downgrade to recorded versions, restore config, `apt update`, reinstall
Nouveau/Mesa, `update-glx --auto glx`, `dconf update`, `update-initramfs -u -k all`,
`update-grub`, clear the verified marker, write `recovery-reboot-required`,
`SPACED_ERROR:52` if any step failed, optional `--reboot-after`).

Install: `install_prerequisites` (headers, build-essential, dkms, …),
`install_official_repository` (CUDA/NVIDIA repo with pinned keyring),
`disable_official_repository_for_legacy`, `select_driver_package` (legacy vs current,
`spaced-nvidia-compat.py`), `install_driver_packages`,
`neutralize_nvidia_blacklists`, `write_nvidia_policy` (modprobe policy),
`sanitize_grub` (embedded python3: strips `nomodeset` / `*modeset=` / NVIDIA names out
of `module_blacklist=`, `modprobe.blacklist=`, `rd.driver.blacklist=` in
`/etc/default/grub`; `clean_token`), `remove_stale_xorg_configs`,
`install_compiz_launcher`, `verify_modules_on_disk`, `verify_modprobe_policy`,
`verify_initramfs`, `verify_userspace_and_grub`, `write_pending_marker`
(`reboot-required` with boot id).

Modes: `audit_system`, `install_amd`, `install_system`, `reboot_system`,
`rollback_system`, `main` (flock on `transaction.lock`, fatal 17 when busy).

## 3. `spaced_nvidia_state.py` (shared by the GTK tools)

`marker_id` (sha256 of the pending file), `ack_path`
(`~/.cache/spaced-nvidia-installer/verified-<id>`), `installation_verified`,
`awaiting_reboot` (boot id match; old markers without a boot id keep verify-on-login).

## 4. `spaced-nvidia-postboot.py` (verify the driver after reboot)

`load_gtk`, `run` (timeout-guarded), `check_opengl`, `collect_checks` (PCI binding,
`nvidia-smi`, NVIDIA OpenGL, Compiz, MATE panel, Caja), `wait_for_session`,
`show_success`, `show_failure`, `recovery_message`, `run_recovery` (calls the helper's
`--rollback`), `show_recovery_error`, `main`. Autostart:
`etc/xdg/autostart/spaced-nvidia-postboot.desktop`.

## 5. `spaced-nvidia-compat.py` (driver choice)

`check_hardware` (PCI ids vs a database, `allowed_legacy`), `recommended_package`,
`debian_version_key`, `legacy_version` (madison output, max major), `main`.

## 6. `spaced-nvidia-config.py` (per-file configuration backup)

`snapshot`, `write_manifest`, `backup`, `load_manifest`, `capture`, `pending`,
`restore`, `main` (subcommands `backup|capture|pending|restore`).

## 7. Entry points, policy, packaging

- `usr/local/bin/spaced-gpu-driver-manager` → runs the GTK UI;
  `usr/local/bin/spaced-nvidia-installer` is the compatibility shim kept for existing
  shortcuts and docs.
- `usr/share/applications/spaced-gpu-driver-manager.desktop`: name "Spaced GPU Driver
  Manager", comment "Inspect GPUs, assign the desktop and repair graphics drivers",
  `Icon=video-display`, `Categories=Settings;HardwareSettings;`.
- `usr/share/polkit-1/actions/com.spacedlinux.nvidia.policy`: the helper's action,
  `allow_active=auth_admin`, exec-path annotation.
- `usr/local/bin/spaced-graphics-report`: read-only text report used by support docs.
- `scripts/spaced-nvidia-installer.sh`: maintainer source install — the file list above,
  `/root/spaced-nvidia-installer-backup-<stamp>` backups, refuses to replace files
  during a driver transaction.
- Tests on `main` that pin today's behaviour: `tests/test_nvidia_*.py` (installer,
  helper, postboot, compat, config, polkit, graphics report). They keep running; the
  redesign adds tests, it does not delete coverage.

## 8. What today's app does NOT do (and the GPU Manager must now add)

No multi-GPU inventory (it greps one NVIDIA/AMD line), no roles, no desktop-GPU
selection, no monitor/port awareness, no render-offload or CUDA selection, no
automatic rollback of an X layout. Those are this design's job, and the candidate
backend on `gpu-manager/11.26.4` (see ARCHITECTURE.md) already proves most of them.
