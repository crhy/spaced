# Only a text login after updating (AMD graphics)

Applies to Spaced Linux 10.26.1 and 10.26.2 computers with AMD graphics
that updated their X server before 10.26.3 was available. The commands
below are typed at the text login prompt, after signing in with your user
name and password. This system uses sysvinit: there is no `systemctl` here.

## 1. What you see

After updating, AMD graphics computers start to a text login instead of
the desktop. Cause: X server `2:21.1.25-1devuan1` changed an internal
structure the amdgpu driver relies on; the driver crashed X at startup.

Spaced Update and apt refuse the broken version
(`/etc/apt/preferences.d/spaced-xorg-abi`), so an ordinary update will
not install it.

## 2. Fix

Sign in at the text login, then run:

```
sudo apt-mark unhold xserver-common xserver-xorg-core xvfb
```

This line is only needed if you held those packages. Then:

```
sudo apt update && sudo apt full-upgrade
```

and reboot:

```
sudo reboot
```

The fixed server is `2:21.1.25-1devuan1+spaced10.26.3`. Check what you
have:

```
dpkg-query -W xserver-xorg-core
```

If it prints `2:21.1.25-1devuan1+spaced10.26.3`, the fixed X server is
in place and the desktop should start after the reboot.

## 3. If you added a workaround file

If you added a workaround file that sets `Driver "modesetting"` under
`/etc/X11/xorg.conf.d/`, delete it after upgrading and run:

```
sudo apt install --reinstall spaced-mate-default-settings
```

so Spaced's TearFree setting
(`/etc/X11/xorg.conf.d/20-spaced-amdgpu.conf`) returns. `modesetting`
has no TearFree, which causes the pixelation some users saw.

## 4. Diagnose

To see the crash in the X server log:

```
grep -E "\(EE\)|Segmentation|amdgpu" /var/log/Xorg.0.log | tail -20
```

The matching lines show the X errors and the amdgpu crash at startup.

## 5. Reporting

When reporting at https://github.com/crhy/spaced/issues, include the
`spaced-graphics-report` output and `/var/log/Xorg.0.log`.
