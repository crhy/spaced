---
name: spaced-no-prs-batch-into-release
description: Spaced fixes go on branches and ship together in the next release; never open PRs for them.
metadata:
  type: feedback
---
Don't open pull requests for Spaced Linux fixes. Commit each fix to its own branch, push it, track the bug as a crhy/spaced issue, and let everything land together in the next release. Pending fixes as of 2026-11-07: #408 on branch `fix-408-portal-db` (pushed), and #409 (elogind reboot-helper segfault; labelled priority:high, status:planned, must be fixed before the next release).

**Why:** rhY, 2026-11-07: "we'll fix everything in the next release. Let's not do PRs." Releases are cut as one batch (for example #405 for 11.26).
**How to apply:** after fixing a Spaced bug, push the branch and say which issue and branch it's on. Don't offer to open a PR. Related: [[notes-live-on-github]], [[spaced-linux-version-scheme]].
