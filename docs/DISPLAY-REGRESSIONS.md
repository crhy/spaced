# Display and idle regressions: #189, #201, #204

## Source changes, not hardware closure

- [#189](https://github.com/crhy/spaced/issues/189): the checkout lacked
  [PR #197](https://github.com/crhy/spaced/pull/197)'s screensaver correction.
  Disabling X blanking/DPMS does not disable mate-screensaver's separate session
  idle activation. The display helper now saves and disables
  `org.mate.screensaver idle-activation-enabled` when the active display timeout
  is Never, and restores it when a finite timeout is selected. A previously
  disabled preference stays disabled. State survives logout; failed reads or
  saves cannot disable idle activation, and a failed restore remains retryable.
  Concurrent callbacks serialize preference updates with `flock`.
- **Security consequence:** Never now also suppresses automatic idle locking.
  Manual locking and `lock-enabled` are unchanged; `org.mate.session idle-delay`
  is not rewritten. Choose a finite display timeout to restore the saved idle
  preference. Changing Screensaver preferences while Never is active competes
  with this policy; select a finite display timeout before customizing them.
- [#201](https://github.com/crhy/spaced/issues/201): first-login repair inferred
  scaling from the X server's aggregate DPI and overwrote even explicitly
  selected scaling. That heuristic is removed. MATE alone owns scaling:
  [its settings daemon](https://github.com/mate-desktop/mate-settings-daemon/blob/master/plugins/xsettings/msd-xsettings-manager.c)
  uses primary-monitor geometry for automatic window scale and separately
  computes font DPI. Existing explicit settings are deliberately not reset,
  because a prior helper value cannot be distinguished from a user's choice.
  This removes a confirmed competing writer, **not proof that the reported
  boot-only underscaling is resolved**.
- [#204](https://github.com/crhy/spaced/issues/204): no driver, renderer, kernel
  error or Compiz backtrace establishes the cause of the physical-machine idle
  corruption. Do not force software rendering, replace the driver, restart
  Compiz on every unlock, or replay display geometry. The read-only graphics
  report now includes actual X DPI/resources, MATE scale/power/session/screensaver
  settings, window-manager identity, process state and saved idle preference.
  This issue remains hardware-blocked, not fixed by disabling screen locking.

## Focused automated checks

```sh
python3 -m unittest discover -s tests -p 'test_display_policy.py' -v
python3 -m unittest discover -s tests -p 'test_desktop_reliability.py' -v
bash -n overlays/usr/local/bin/spaced-display-repair
bash -n overlays/usr/local/bin/spaced-first-login-repair
bash -n overlays/usr/local/bin/spaced-graphics-report
```

Mocks cover preference round trips, pre-disabled idle activation, missing
schemas, malformed/failed reads, failed persistence/restoration, scale ownership
and read-only report commands. They do not emulate a GPU, DPMS or a real locker.

## Required hardware validation before closing issues

1. On the affected physical machine, run `spaced-graphics-report > before.txt`
   from the MATE terminal immediately after login, before opening Displays.
   Repeat into `after-scaling.txt` after selecting the working 100%/autodetect
   setting. Compare scale, font DPI, X resources and RandR transforms. Reboot
   without opening Displays; check both a new account and an upgraded account,
   including an explicitly selected 200% setting and mixed-DPI monitors.
2. Select Never in Power Management. Check `xset q` and
   `gsettings get org.mate.screensaver idle-activation-enabled`, then leave idle
   beyond both the session idle delay and the former DPMS timeout (at least
   25 minutes for #204). Check that the monitor stays on, manual locking still
   works, and moving windows does not smear. Repeat after logout/login.
3. Select a finite display timeout and verify the prior screensaver preference
   returns, timed blanking works and unlock redraws normally. Repeat with idle
   activation initially disabled. On laptops, test AC and battery separately;
   this helper currently reacts to login, preference changes and unlock, not
   power-source changes alone. Do not claim unplug/replug coverage from mocks.
4. If artifacts occur, capture `spaced-graphics-report > after-idle.txt` while
   they are visible, the exact GPU/driver/package versions, monitor arrangement,
   and kernel/Xorg errors around that timestamp. Compare finite timeout versus
   Never to separate idle rendering failure from DPMS wake failure. Review
   reports for identifying data before posting them publicly.

No release identity files or driver/compositor policy are changed by this work.
