Spaced NVIDIA Driver Installer hardening test bundle

This installs a test version of:
- the graphical NVIDIA installer
- the privileged transactional helper
- the renderer-aware Compiz launcher (during driver installation)
- a one-shot post-reboot NVIDIA/GLX/Compiz verifier
- automatic rollback to Nouveau on any pre-reboot verification failure
- a user-triggered post-reboot rollback path

Install:
  cd spaced-nvidia-hardening
  sudo ./install.sh

Then launch:
  spaced-nvidia-installer

The driver is not installed by install.sh. The graphical app performs the
actual package installation only after confirmation.
