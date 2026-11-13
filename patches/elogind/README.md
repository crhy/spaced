# elogind power-action backport

Spaced rebuilds Devuan Ceres `elogind` 257.13-1 with the upstream fix for
elogind issue 341. Immediate poweroff and reboot actions clear
`Manager.delayed_action` before the helper exits, so the old completion log
dereferenced a null pointer after the machine action had already begun.

The runtime patch is upstream v257-stable commit
`f5d1d8413df17a9548b205a80f715174ded00762` and should be removed once Ceres
ships 257.14 or newer. Do not replace the system power commands or suppress
core dumps to conceal this failure; validate both poweroff and reboot in the
release KVM image.

The source release also needs the functional part of upstream commit
`5b6579284f92770af5999bbcbb9169ca96f78643` so its documentation index can be
generated with current lxml. That build-only patch enables resolution of the
external entities already used by elogind's XML sources; unrelated IDE changes
from the upstream commit are not carried.
