# 10.26.6 announcement materials

`announcement.md` is the GitHub Discussions announcement; `changes-since-10.26.1.md` is its detailed companion comment. Relative image links are replaced with immutable raw GitHub URLs when posted. The changelog excerpt preserves the published entries unchanged.

All PNGs are unretouched 1280×800 captures from the final ISO:

- ISO: `spaced-linux-10.26.6-amd64.iso`
- SHA-256: `bed3263b2d61f85e292eb86f34bb14969618215b77d667be60139e7436154617`
- `ubuntu.png`, `win7.png`, `win7-aero-dark.png`: final KVM BIOS theme-validation run; matching evidence is in the release validation archive.
- Other PNGs: a separate 2 GiB KVM live session booted from that same final ISO for this announcement. No packages were installed for the captures. GDebi opened the matching existing `spaced-meta` package; no install/remove action was taken.
- The theme chooser was allowed to finish generating its thumbnails before capture.
- The GPU image shows virtual hardware. The sharing-password image does not establish Windows-client compatibility. The updater image shows its initial Updates tab without a running transaction.

These images illustrate desktop features. Runtime checks, package hashes and hardware/client limitations are documented in [the release review](../../10.26.6-RELEASE-REVIEW.md).
