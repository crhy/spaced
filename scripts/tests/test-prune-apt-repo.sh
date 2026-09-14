#!/bin/bash
# Test scripts/prune-apt-repo.sh against a fake repository.
# Only fixture .debs built with dpkg-deb and dummy source files are used;
# the real ./spaced-apt checkout and scripts/build-apt-repo.sh are untouched.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
PRUNE="$ROOT/scripts/prune-apt-repo.sh"
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT

REPO="$WORK/repo"
BIN="$REPO/dists/spaced/main/binary-amd64"
SRC="$REPO/dists/spaced/main/source"
TBIN="$REPO/dists/spaced-testing/main/binary-amd64"
mkdir -p "$BIN" "$SRC" "$TBIN"

make_deb() {
    local pkg=$1 ver=$2 arch=$3 depends=$4 dest=$5
    local stage="$WORK/stage/${pkg}_${ver}"
    rm -rf -- "$stage"
    mkdir -p "$stage/DEBIAN"
    {
        echo "Package: $pkg"
        echo "Version: $ver"
        echo "Architecture: $arch"
        echo "Maintainer: Spaced Linux Test <test@spaced>"
        if [[ -n "$depends" ]]; then
            echo "Depends: $depends"
        fi
        echo "Description: prune test fixture"
    } > "$stage/DEBIAN/control"
    dpkg-deb --build "$stage" "$dest/${pkg}_${ver}_${arch}.deb" >/dev/null 2>&1
}

# Tricky Debian orderings must resolve via dpkg, newest last:
#   8.26.9 < 9.26-1 < 9.26.1-6 < 9.26.2-2
#   1.26.1-1 < 1.26.2-6 < 1.26.2-6+spaced9.26.1
for spec in \
    "9.26-1 lt 9.26.1-6" \
    "9.26.1-6 lt 9.26.2-2" \
    "8.26.9 lt 9.26-1" \
    "1.26.1-1 lt 1.26.2-6" \
    "1.26.2-6 lt 1.26.2-6+spaced9.26.1"; do
    set -- $spec
    dpkg --compare-versions "$1" "$2" "$3" || {
        echo "FAIL: expected dpkg ordering $spec" >&2
        exit 1
    }
done
echo "PASS: tricky version orderings resolve through dpkg"

# Newest spaced-meta pins an OLDER settings revision exactly; the ">="
# mention of old marco must NOT protect it.
make_deb spaced-meta 9.26-1 all "" "$BIN"
make_deb spaced-meta 9.26.1-6 all "" "$BIN"
make_deb spaced-meta 9.26.2-2 all \
    "spaced-mate-default-settings (= 9.26-1), marco (>= 1.26.1-1)" "$BIN"
make_deb spaced-mate-default-settings 8.26.9 all "" "$BIN"
make_deb spaced-mate-default-settings 9.26-1 all "" "$BIN"
make_deb spaced-mate-default-settings 9.26.1-6 all "" "$BIN"
make_deb spaced-mate-default-settings 9.26.2-2 all "" "$BIN"
make_deb marco 1.26.1-1 amd64 "" "$BIN"
make_deb marco 1.26.2-6 amd64 "" "$BIN"
make_deb marco 1.26.2-6+spaced9.26.1 amd64 "" "$BIN"
# Second suite: already at retention depth, nothing to prune there.
make_deb spaced-meta 9.26.2-2 all "" "$TBIN"
make_deb spaced-mate-default-settings 9.26.2-2 all "" "$TBIN"

# Marco sources: an old set (all three files pruned) and the newest kept
# set, plus generated index sentinels the pruner must never touch.
echo "old dsc" > "$SRC/marco_1.26.1-1.dsc"
echo "old orig" > "$SRC/marco_1.26.1.orig.tar.xz"
echo "old debian" > "$SRC/marco_1.26.1-1.debian.tar.xz"
echo "new dsc" > "$SRC/marco_1.26.2-6+spaced9.26.1.dsc"
echo "new orig" > "$SRC/marco_1.26.2.orig.tar.xz"
echo "new debian" > "$SRC/marco_1.26.2-6+spaced9.26.1.debian.tar.xz"
echo "sentinel packages" > "$BIN/Packages"
echo "sentinel sources" > "$SRC/Sources"

must_exist() {
    [[ -e "$1" ]] || { echo "FAIL: expected to exist: $1" >&2; exit 1; }
}
must_gone() {
    [[ ! -e "$1" ]] || { echo "FAIL: expected deletion: $1" >&2; exit 1; }
}

debs_before=$(find "$REPO" -name '*.deb' | wc -l)

# Default run is a dry run: it must report but delete nothing.
dry_output=$(bash "$PRUNE" "$REPO")
debs_after=$(find "$REPO" -name '*.deb' | wc -l)
[[ "$debs_before" == "$debs_after" ]] || {
    echo "FAIL: dry run deleted files" >&2
    exit 1
}
for victim in \
    "spaced-meta_9.26-1_all.deb" \
    "spaced-mate-default-settings_8.26.9_all.deb" \
    "marco_1.26.1-1_amd64.deb" \
    "marco_1.26.1-1.dsc" \
    "marco_1.26.1.orig.tar.xz" \
    "marco_1.26.1-1.debian.tar.xz"; do
    grep -qF "$victim" <<< "$dry_output" || {
        echo "FAIL: dry run did not list $victim" >&2
        exit 1
    }
done
grep -q "scripts/build-apt-repo.sh" <<< "$dry_output" || {
    echo "FAIL: dry run omits the build-apt-repo.sh reminder" >&2
    exit 1
}
echo "PASS: dry run deletes nothing and lists every expected file"

# The pinned older settings revision must be listed as kept, not deleted.
if grep -q "spaced-mate-default-settings_9.26-1_all.deb" <<< "$dry_output"; then
    echo "FAIL: pinned 9.26-1 settings revision selected for deletion" >&2
    exit 1
fi
echo "PASS: exact (= ...) pin on older revision is honoured"

bash "$PRUNE" --apply "$REPO" > "$WORK/apply.log"
grep -q "scripts/build-apt-repo.sh" "$WORK/apply.log" || {
    echo "FAIL: apply run omits the build-apt-repo.sh reminder" >&2
    exit 1
}

must_gone "$BIN/spaced-meta_9.26-1_all.deb"
must_gone "$BIN/spaced-mate-default-settings_8.26.9_all.deb"
must_gone "$BIN/marco_1.26.1-1_amd64.deb"
must_gone "$SRC/marco_1.26.1-1.dsc"
must_gone "$SRC/marco_1.26.1.orig.tar.xz"
must_gone "$SRC/marco_1.26.1-1.debian.tar.xz"
for kept in \
    "$BIN/spaced-meta_9.26.1-6_all.deb" \
    "$BIN/spaced-meta_9.26.2-2_all.deb" \
    "$BIN/spaced-mate-default-settings_9.26-1_all.deb" \
    "$BIN/spaced-mate-default-settings_9.26.1-6_all.deb" \
    "$BIN/spaced-mate-default-settings_9.26.2-2_all.deb" \
    "$BIN/marco_1.26.2-6_amd64.deb" \
    "$BIN/marco_1.26.2-6+spaced9.26.1_amd64.deb" \
    "$SRC/marco_1.26.2-6+spaced9.26.1.dsc" \
    "$SRC/marco_1.26.2.orig.tar.xz" \
    "$SRC/marco_1.26.2-6+spaced9.26.1.debian.tar.xz" \
    "$TBIN/spaced-meta_9.26.2-2_all.deb" \
    "$TBIN/spaced-mate-default-settings_9.26.2-2_all.deb"; do
    must_exist "$kept"
done
# Generated indexes are byte-identical: pruning never regenerates them.
[[ "$(cat "$BIN/Packages")" == "sentinel packages" ]] || {
    echo "FAIL: pruner touched the Packages index" >&2
    exit 1
}
[[ "$(cat "$SRC/Sources")" == "sentinel sources" ]] || {
    echo "FAIL: pruner touched the Sources index" >&2
    exit 1
}
echo "PASS: --apply deletes exactly the expected files and keeps the pin"

# Pruning is idempotent: a second run finds nothing left to delete.
second_output=$(bash "$PRUNE" --apply "$REPO")
grep -q "Nothing to prune" <<< "$second_output" || {
    echo "FAIL: second run is not idempotent" >&2
    exit 1
}
echo "PASS: second run reports nothing to prune"

# Refusals: missing dists, a suite without spaced-meta, dirty git checkout.
if bash "$PRUNE" "$WORK/no-such-repo" 2>/dev/null; then
    echo "FAIL: missing dists was accepted" >&2
    exit 1
fi
mkdir -p "$WORK/nometa/dists/spaced/main/binary-amd64"
make_deb spaced-mate-default-settings 9.26.2-2 all "" "$WORK/nometa/dists/spaced/main/binary-amd64"
if bash "$PRUNE" "$WORK/nometa" 2>/dev/null; then
    echo "FAIL: suite without spaced-meta was accepted" >&2
    exit 1
fi
git init -q "$WORK/gitrick"
mkdir -p "$WORK/gitrick/dists/spaced/main/binary-amd64"
make_deb spaced-meta 9.26.2-2 all "" "$WORK/gitrick/dists/spaced/main/binary-amd64"
git -C "$WORK/gitrick" add -A
git -C "$WORK/gitrick" -c user.name=t -c user.email=t@t commit -qm init
echo untracked > "$WORK/gitrick/dists/spaced/main/binary-amd64/untracked.deb"
if bash "$PRUNE" "$WORK/gitrick" 2>/dev/null; then
    echo "FAIL: dirty git checkout was accepted" >&2
    exit 1
fi
echo "PASS: missing dists, missing spaced-meta, and dirty git are refused"

echo "APT repository prune tests passed."
