---
name: notes-live-on-github
description: rhY's rule (2026-11-01): all Spaced/theme data and every memory note must be on GitHub; upload each note to its repo's docs/notes/ right after writing it.
metadata:
  type: feedback
---
Every memory note is also published to its project's GitHub repo under `docs/notes/<name>.md` (with `docs/notes/README.md` as the index): Spaced -> crhy/spaced (Spaced Monitor also crhy/spacedmonitor), Strata/workflow -> crhy/Strata, Voxa -> crhy/voxa, rhYciv -> crhy/rhYciv, Cards With Cats -> crhy/CardsWithCats, Dr. Mario Wii -> crhy/drmario64wii. Upload script: `gh api PUT repos/<repo>/contents/docs/notes/...` (no local checkout touched). Bugs and plans for Spaced also get a crhy/spaced issue (e.g. #398 theme monitor).

**Why:** rhY: "ALL data about spaced and spaced themes and any and all documentation should be on the github" (2026-11-01). A note that exists only in ~/.claude is invisible to them and to other tools.
**How to apply:** whenever a memory note is written or changed, upload it to the matching repo in the same turn and update that repo's docs/notes/README.md; scan for secrets first (repos are public). Related: [[voxa-spec-lives-in-github-issues]], [[spaced-theme-monitor-dies]].
