# Release checklist

One pass from a clean tree to a deployed website. The order is the one recorded
under "Required resume order" in `docs/11.26.1-PAUSE-HANDOFF.md`; it exists to
prevent issue #209 (an OS tag whose APT packages are not published yet) and a
website that links an absent or wrongly checksummed image. Replace
`<version>` with the value in `VERSION`.

1. **Start from a clean tree.**
   `git status --porcelain` must print nothing. Read
   `docs/<version>-RELEASE-REVIEW.md`, and after a pause the handoff's
   "Required resume order".
   Nothing is published yet and no tag exists.

2. **Preflight the release inputs.**
   `make release-preflight`
   Passed: `make check` succeeds (`scripts/check.sh`, the unit tests, the GTK
   desktop test) and it prints `Release inputs are pinned for Spaced Linux
   <version>`. `scripts/release-preflight.sh` rejects an `UNRELEASED` tag,
   digest or fingerprint.
   Not before it: no ISO build.

3. **Build the ISO and its checksum.**
   `make release`
   Passed: `build/iso/spaced-linux-<version>-amd64.iso` and its `.sha256`
   exist, and `sha256sum -c` passes in that directory.
   Not before it: no website publish, no tag, no APT publication.

4. **Smoke-test the built image.**
   `make iso-smoke`, then `make vbox-smoke` and `make vbox-smoke-default`
   Passed: SSH and the complete MATE desktop (session, panel, Caja, Compiz) are
   reached in KVM BIOS/EFI and VirtualBox BIOS/EFI; the live installer is
   launched and closed without installing; screenshots land under
   `build/test-artifacts/`. `vbox-smoke-default` exits 3 with a `NO WINDOW
   MANAGER` diagnosis when Compiz cannot start on VirtualBox's own controller
   (#218): record that, do not hide it.
   Not before it: no installed-system claim and no website publish.

5. **Install it in a disposable VM and run the installed gates.**
   `make vm-create`, `make vm-install`, `make vm-start`
   Passed, and recorded in the release review: repeated menu reboots with clean
   elogind logs; a separate or reused `/home` reaching the installed
   `/etc/fstab` (#413); a real upgrade from the previous release, including the
   path where an update stops and is retried.
   Not before it: no issue may be called fixed on source evidence alone.

6. **Put the tested image state into the website source and the records.**
   `scripts/website-release.sh publish` once the ISO is tested;
   `scripts/website-release.sh preview` while it is not.
   Passed: the checksum in `website/index.html` is the one in the `.sha256`
   file, and `make check` rejects a preview page that links an ISO or prints a
   checksum. Record only the evidence actually obtained in `CHANGELOG.md` and
   the release review.
   Not before it: never type a checksum by hand, and never link an untested
   image.

7. **Re-run the gates, review the diff, merge the release batch to `main`.**
   `make check`, review the whole diff, then merge and push under the project's
   no-PR release procedure
   (`docs/notes/spaced-no-prs-batch-into-release.md`).
   Passed: the source-checks workflow is green on `main`.
   Not before it: keep the download block in preview until step 9 exists —
   pushing to `main` deploys the site (`CLOUDFLARE-PAGES.md`).

8. **Publish the APT repository.**
   `make apt-repo` to build and test it locally, then
   `make apt-repo-publish UPGRADE_STATUS_FILES=<paths>`
   Passed: publication refuses to start without an installed-system dpkg status
   fixture (collect one with `scripts/tests/collect-upgrade-status.sh` on the
   previous ISO); the historical upgrade, payload and trust tests pass; the new
   packages resolve from the public signed archive.
   `scripts/build-apt-repo.sh` refuses to republish different bytes under an
   already published version, so any content change needs a new package
   revision. To publish one already-built package without a full build, use
   `scripts/publish-apt-package.sh`.
   The signed `Release` expires 180 days after its `Date`, so republish the
   repository at least every 180 days even with no package change
   (`make apt-repo-publish`, or `scripts/publish-apt-package.sh` to re-sign);
   otherwise `apt update` reports an expired Release file on every system.
   Not before it: **no OS tag and no GitHub release.** A tag without APT
   packages makes every system loop on the upgrade (#209).

9. **Create the OS release and attach the tested image.**
   Create the `v<version>` GitHub release, upload the ISO and its `.sha256`.
   Passed: both files download, and the downloaded hash matches the uploaded
   checksum.
   Not before it: step 8 must already be public.

10. **Close only the fixed issues.**
    Comment each fixed issue with the released version and its evidence, then
    close it. Decision and evidence issues stay open.
    Not before it: an issue is closed only after its fix is merged to `main`
    and, for a component repository, released (`AGENTS.md`).

11. **Deploy the website and verify it live.**
    Push the publish-mode website source to `main`; Cloudflare Pages runs
    `bash scripts/build-site.sh` and publishes `dist` from `main`.
    Passed: the live page's download link and displayed checksum match the
    published asset, and a download taken from the live site verifies against
    that checksum.
    Not before it: no published download block on `main` before step 9.

12. **Leave the records honest.**
    Never edit a published release's `CHANGELOG.md` entry or its issue-status
    evidence; a later fix goes under a new revision section, saying whether it
    ships as an APT package revision, a Welcome release, or a Bazaar Flatpak
    (`AGENTS.md`, "Maintenance rules learned from releases").
