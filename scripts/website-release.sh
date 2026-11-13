#!/usr/bin/env bash
# Keep the download card in website/index.html honest about the release state of
# the ISO named by VERSION. The checksum on the page is never typed by hand: it
# is copied from the .sha256 file that `make release` produces for the ISO.
#
#   scripts/website-release.sh preview
#   scripts/website-release.sh publish [SHA256_FILE]
#
# preview  - the state while the ISO of VERSION is still unvalidated: no download
#            link, no ISO file name and no checksum for VERSION.
# publish  - only once the ISO is built and tested; the checksum comes from
#            build/iso/spaced-linux-<version>-amd64.iso.sha256 (or the file given).
#
# Both commands are idempotent and rewrite index.html atomically.
set -euo pipefail

ROOT=${SPACED_WEBSITE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
VERSION=$(<"$ROOT/VERSION")
VERSION=${VERSION//[[:space:]]/}
ISO_NAME="spaced-linux-${VERSION}-amd64.iso"

usage() {
    cat >&2 <<EOF
Usage: scripts/website-release.sh preview
       scripts/website-release.sh publish [SHA256_FILE]

Rewrites the marked download block in $ROOT/website/index.html
for Spaced Linux ${VERSION}.

  preview   show the "being validated" block; no ISO link, no checksum
  publish   show the ISO link and the SHA-256 read from SHA256_FILE
            (default: build/iso/${ISO_NAME}.sha256)
EOF
}

if [[ ! "$VERSION" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then
    echo "website-release: $ROOT/VERSION is not a release version: '${VERSION}'" >&2
    exit 1
fi

mode=""
sha256_file=""
case "${1:-}" in
    preview)
        if [[ $# -ne 1 ]]; then usage; exit 2; fi
        mode=preview
        ;;
    publish)
        shift
        if [[ $# -gt 1 ]]; then usage; exit 2; fi
        mode=publish
        sha256_file=${1:-"$ROOT/build/iso/${ISO_NAME}.sha256"}
        ;;
    *)
        usage
        exit 2
        ;;
esac

digest=""
if [[ "$mode" == publish ]]; then
    if [[ ! -f "$sha256_file" ]]; then
        echo "website-release: no checksum file for ${VERSION}: $sha256_file" >&2
        echo "Build and test the ISO first (make release), or pass its .sha256 file." >&2
        exit 1
    fi
    digest=$(SPACED_SHA256_FILE="$sha256_file" SPACED_ISO_NAME="$ISO_NAME" python3 - <<'PY'
import os
import re
import sys

path = os.environ["SPACED_SHA256_FILE"]
iso = os.environ["SPACED_ISO_NAME"]
try:
    text = open(path, encoding="utf-8").read()
except OSError as exc:
    print(f"website-release: cannot read {path}: {exc.strerror}", file=sys.stderr)
    raise SystemExit(1)
match = re.fullmatch(r"([0-9a-f]{64})  " + re.escape(iso) + r"\r?\n?", text)
if not match:
    print(
        f"website-release: {path} must hold exactly one line "
        f"'<64 hex digits>  {iso}'",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(match.group(1))
PY
)
    # When the ISO itself is next to the checksum file, the checksum must match it.
    iso_dir=$(dirname -- "$sha256_file")
    if [[ -f "$iso_dir/$ISO_NAME" ]]; then
        if ! (cd "$iso_dir" && sha256sum -c -- "$(basename -- "$sha256_file")" >/dev/null); then
            echo "website-release: sha256sum -c failed for $iso_dir/$ISO_NAME" >&2
            exit 1
        fi
    fi
fi

SPACED_MODE="$mode" SPACED_VERSION="$VERSION" SPACED_SHA256="$digest" python3 - \
    "$ROOT/website/index.html" <<'PY'
import os
import re
import sys
import tempfile

path = sys.argv[1]
mode = os.environ["SPACED_MODE"]
version = os.environ["SPACED_VERSION"]
digest = os.environ.get("SPACED_SHA256", "")

START = "<!-- release-download:start -->"
END = "<!-- release-download:end -->"

try:
    text = open(path, encoding="utf-8").read()
except OSError as exc:
    print(f"website-release: cannot read {path}: {exc.strerror}", file=sys.stderr)
    raise SystemExit(1)

block = re.compile(
    r"(?m)^([ \t]*)%s\n.*?\n[ \t]*%s([^\n]*)$" % (re.escape(START), re.escape(END)),
    re.DOTALL,
)
matches = list(block.finditer(text))
if len(matches) != 1:
    print(
        f"website-release: {path} needs exactly one '{START}' ... '{END}' block "
        f"(found {len(matches)})",
        file=sys.stderr,
    )
    raise SystemExit(1)

indent = matches[0].group(1)
if mode == "preview":
    lines = [
        f"<p>Spaced Linux {version} is being validated. "
        "Until it is published, use the current release.</p>",
        '<p><a class="button primary" '
        'href="https://github.com/crhy/spaced/releases/latest">Get the current release</a></p>',
    ]
    kicker = f"SPACED LINUX \u00b7 {version} PREVIEW"
else:
    lines = [
        '<p><a class="button primary" '
        f'href="https://github.com/crhy/spaced/releases/download/v{version}/'
        f'spaced-linux-{version}-amd64.iso">Download the ISO</a></p>',
        f'<p class="checksum">SHA-256 <code>{digest}</code></p>',
        '<p class="checksum">Check your download: '
        f'<code>sha256sum spaced-linux-{version}-amd64.iso</code> '
        "must print this value.</p>",
        f'<p><a href="https://github.com/crhy/spaced/releases/tag/v{version}">'
        "All files and release notes \u2192</a></p>",
    ]
    kicker = f"SPACED LINUX \u00b7 {version}"

replacement = "\n".join(
    [f"{indent}{START}"] + [f"{indent}{line}" for line in lines] + [f"{indent}{END}"]
) + matches[0].group(2)
text = text[: matches[0].start()] + replacement + text[matches[0].end() :]

hero = re.compile(r'(<p class="kicker">)SPACED LINUX · [^<]*(</p>)')
if not hero.search(text):
    print(f"website-release: {path} has no hero kicker to update", file=sys.stderr)
    raise SystemExit(1)
text = hero.sub(lambda match: match.group(1) + kicker + match.group(2), text, count=1)

directory = os.path.dirname(path) or "."
handle, temporary = tempfile.mkstemp(dir=directory, prefix=".index.html.", suffix=".tmp")
try:
    with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
    os.chmod(temporary, os.stat(path).st_mode & 0o777)
    os.replace(temporary, path)
except BaseException:
    if os.path.exists(temporary):
        os.unlink(temporary)
    raise

print(f"website-release: {path} set to {mode} for Spaced Linux {version}")
PY
