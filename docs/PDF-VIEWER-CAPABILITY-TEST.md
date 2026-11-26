# PDF viewer capability test (issue #304)

The 11.26.1 review refused to change the default PDF application in a stability
patch **without a current capability/package test**. This document is that test
in its offline form: one reviewed table of candidates, one script that gathers
evidence from the machine itself, and one gate that refuses to let a capability
be claimed before the evidence exists.

Two things stay open and are **not** answered here:

- the document/printer/log reproduction of the reported Atril printing failure,
  which needs a real printer;
- rhY's explicit default-app decision (`decision: pending` in the reviewed table).

## Inputs

| File | What it holds |
| --- | --- |
| `config/pdf-viewers.yaml` | One reviewed record per candidate: binary, `.desktop` file, apt package, the seven capability axes, `default_app: atril`, `decision: pending`. Every axis value is `unknown` until a source is printed for it. |
| `scripts/pdf-capability-matrix.py` | Stdlib only, no network. Reads `apt-cache policy`, the dpkg status database, installed `.desktop` files and the repository's own `config/` tables, then prints one row per candidate per axis. |
| `scripts/check.sh` | Asserts the shipped default is still `atril` in `config/packages.yaml` and that `config/pdf-viewers.yaml` agrees, naming issue #304. |
| `tests/test_pdf_capability_matrix.py` | Drives the script from fixture directories (policy files, `.desktop` files, a dpkg stanza) so the rules are checked on any host. |

Run it:

```
python3 scripts/pdf-capability-matrix.py            # print the matrix
python3 scripts/pdf-capability-matrix.py --check    # the gate
```

`--check` exits 0 only when every candidate resolves to a packaging state,
the recorded `default_app` is packaged **and** carries MIME evidence, and no
axis is claimed in the reviewed table without a source this run printed. It
exits non-zero with the offending row when the table names a default that is
not packaged, or asserts a capability the machine does not back.

## What each axis means

Each axis is the review's own list. Evidence means a machine-readable fact was
found and printed, **not** that the capability works.

| Axis | Accepted evidence | Never accepted |
| --- | --- | --- |
| `printing` | A print action in the `.desktop` file (`Exec`, `Actions`, `X-…Print…`) **and** a print-pipeline dependency (a `cups`/`lp`/`lpr`/`printer`/`foomatic`/`ghostscript` name in the package's dpkg stanza, or in `config/packages.yaml`). | A description that says it can print. |
| `forms` | A `form`/`forms` token in `Keywords`, `Exec`, `TryExec`, `Categories`, `Actions`, an `X-…` key, or a dependency name. | Marketing prose. |
| `accessibility` | An `accessib`/`a11y`/`high-contrast`/`screen-reader`/`blind` token in the same structured fields. | Assumed GTK accessibility. |
| `search` | A `search`/`pdftotext`/`text-extract` token in the same structured fields. | "Searchable PDFs" in a description. |
| `encrypted-files` | A `gpg`/`gnupg`/`openssl`/`crypto*`/`secret`/`nss` dependency or keyword token. | Trusting the upstream bug tracker. |
| `sandbox-update-provenance` | The candidate's repository origin from `apt-cache policy` **and** a delivery record: the package listed in `config/packages.yaml`, or pinned in `config/external-artifacts.conf`. | A GitHub release link. |
| `mime-integration` | `MimeType=application/pdf` in the installed `.desktop` file, or an `application/pdf=` line in `overlays/usr/share/applications/mimeapps.list` naming that file. | The package merely being installed. |

`NOT-PACKAGED` means the configured sources offer no candidate at all, so no
axis can be evaluated for that candidate.

## Generated table

Output of `python3 scripts/pdf-capability-matrix.py --check` on the review
machine (Devuan Ceres, `apt-cache policy` from
`http://mirror.hootsoftware.com/devuan/merged ceres main contrib non-free
non-free-firmware` plus the signed third-party origins), 2026-11-17:

```
PDF viewer capability matrix (issue #304)
default_app: atril
decision: pending
PACKAGING
atril     INSTALLED       1.28.4-1            apt-cache policy atril: Installed: 1.28.4-1; dpkg status atril: Version 1.28.4-1
mupdf     CANDIDATE       1.28.2+ds1-3        apt-cache policy mupdf: Candidate: 1.28.2+ds1-3
okular    CANDIDATE       4:26.08.2-1         apt-cache policy okular: Candidate: 4:26.08.2-1
xpdf      CANDIDATE       3.04+git20260802-1  apt-cache policy xpdf: Candidate: 3.04+git20260802-1
zathura   CANDIDATE       2026.10.23-1        apt-cache policy zathura: Candidate: 2026.10.23-1
pdfcraft  NOT-PACKAGED    -                   apt-cache policy pdfcraft: no output (no candidate in the configured sources)

CAPABILITY
atril     printing                    NO-EVIDENCE   -
atril     forms                       NO-EVIDENCE   -
atril     accessibility               NO-EVIDENCE   -
atril     search                      NO-EVIDENCE   -
atril     encrypted-files             NO-EVIDENCE   -
atril     sandbox-update-provenance   EVIDENCE      apt-cache policy atril: http://mirror.hootsoftware.com/devuan/merged; config/packages.yaml: - atril
atril     mime-integration            EVIDENCE      /usr/share/applications/atril.desktop:MimeType=application/pdf
mupdf     printing                    NO-EVIDENCE   -
mupdf     forms                       NO-EVIDENCE   -
mupdf     accessibility               NO-EVIDENCE   -
mupdf     search                      NO-EVIDENCE   -
mupdf     encrypted-files             NO-EVIDENCE   -
mupdf     sandbox-update-provenance   NO-EVIDENCE   -
mupdf     mime-integration            NO-EVIDENCE   -
okular    printing                    NO-EVIDENCE   -
okular    forms                       NO-EVIDENCE   -
okular    accessibility               NO-EVIDENCE   -
okular    search                      NO-EVIDENCE   -
okular    encrypted-files             NO-EVIDENCE   -
okular    sandbox-update-provenance   NO-EVIDENCE   -
okular    mime-integration            NO-EVIDENCE   -
xpdf      printing                    NO-EVIDENCE   -
xpdf      forms                       NO-EVIDENCE   -
xpdf      accessibility               NO-EVIDENCE   -
xpdf      search                      NO-EVIDENCE   -
xpdf      encrypted-files             NO-EVIDENCE   -
xpdf      sandbox-update-provenance   NO-EVIDENCE   -
xpdf      mime-integration            NO-EVIDENCE   -
zathura   printing                    NO-EVIDENCE   -
zathura   forms                       NO-EVIDENCE   -
zathura   accessibility               NO-EVIDENCE   -
zathura   search                      NO-EVIDENCE   -
zathura   encrypted-files             NO-EVIDENCE   -
zathura   sandbox-update-provenance   NO-EVIDENCE   -
zathura   mime-integration            NO-EVIDENCE   -
pdfcraft  printing                    NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  forms                       NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  accessibility               NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  search                      NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  encrypted-files             NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  sandbox-update-provenance   NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
pdfcraft  mime-integration            NOT-PACKAGED  apt-cache policy pdfcraft: no output (no candidate in the configured sources)
check: atril is packaged and MIME-backed; no axis is claimed without a printed source
```

## What the table already settles

- **`pdfcraft` cannot be the default today.** `apt-cache policy pdfcraft` prints
  no `Candidate:` line in the configured sources, so every axis is
  `NOT-PACKAGED` and `--check` refuses it as `default_app`. The upstream release
  page named in issue #304 is not an installable input for Spaced Linux; a
  Flatpak or a pinned entry in `config/external-artifacts.conf` would have to
  land first.
- **The current default is only MIME-backed.** Atril's association comes from
  `MimeType=application/pdf;…` inside `/usr/share/applications/atril.desktop`;
  there is no `application/pdf=` line in
  `overlays/usr/share/applications/mimeapps.list` or in
  `overlays/etc/skel/.config/mimeapps.list`. Atril's installed `.desktop` file
  carries no print action, which is the gap rhY reports, and its dpkg stanza
  names no print-pipeline dependency even though the image ships `cups`,
  `cups-client`, `cups-filters` and `cups-ipp-utils`.
- **Nothing else is settled.** The four other candidates are packaged but
  uninstalled, so their dependency evidence is unavailable offline; installing
  them in a scratch chroot and re-running the script is the next step, not a
  claim made here.

## Still owed

1. **Atril printing reproduction.** A document, printer and log pair that shows
   the reported failure end to end, so a replacement is not just moving the bug.
   Needs real print hardware; `lp`/`cups` are installed here, the printer is not.
2. **The default-app decision.** `decision: pending` in `config/pdf-viewers.yaml`
   stays `pending` until rhY names a default. Flipping `default_app` without
   updating this table fails `scripts/check.sh` (issue #304) and
   `scripts/pdf-capability-matrix.py --check`.
