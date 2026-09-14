#!/bin/bash
# Prune old package revisions from a Spaced Linux APT repository checkout.
#
# The repository (crhy/spaced-apt, served via GitHub Pages) keeps every
# published revision forever unless pruned, because build-apt-repo.sh only
# adds files and regenerates the signed indexes. This script selects the
# superseded .deb and Marco source files for deletion.
#
# Usage: bash scripts/prune-apt-repo.sh [--keep N] [--apply] <repo-dir>
#
#   --keep N   Keep the newest N versions per package/arch (default 2).
#   --apply    Actually delete. Without it, this is a dry run that only
#              prints which files would be deleted and the bytes freed.
#
# Policy per suite (dists/<suite>/main/binary-amd64):
#   - Group .debs by package name and architecture, order versions with
#     `dpkg --compare-versions`, keep the newest N.
#   - Never delete a version pinned by an exact "(= X)" dependency of the
#     newest spaced-meta in that suite.
#   - In dists/<suite>/main/source, keep the Marco source set (dsc, orig
#     and debian tarballs) matching any kept marco/libmarco binary version.
#
# This script never regenerates or signs the indexes. Run
# scripts/build-apt-repo.sh afterwards to regenerate and re-sign them.
set -euo pipefail

KEEP=2
APPLY=0
REPO=""

usage() {
    echo "Usage: bash scripts/prune-apt-repo.sh [--keep N] [--apply] <repo-dir>" >&2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep)
            KEEP="${2:?Missing value for --keep}"
            shift 2
            ;;
        --keep=*)
            KEEP="${1#--keep=}"
            shift
            ;;
        --apply)
            APPLY=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            echo "Unknown option: $1" >&2
            usage
            exit 2
            ;;
        *)
            if [[ -n "$REPO" ]]; then
                echo "Too many arguments (expected one <repo-dir>)" >&2
                usage
                exit 2
            fi
            REPO="$1"
            shift
            ;;
    esac
done

if [[ -z "$REPO" ]]; then
    usage
    exit 2
fi
if ! [[ "$KEEP" =~ ^[0-9]+$ ]] || [[ "$KEEP" -lt 1 ]]; then
    echo "Error: --keep must be a positive integer (got '${KEEP}')" >&2
    exit 2
fi
if [[ ! -d "$REPO/dists" ]]; then
    echo "Error: $REPO/dists is missing; not a Spaced APT repository checkout" >&2
    exit 1
fi

# Refuse to prune a dirty checkout so a deleted file can always be traced
# back to a clean, committed repository state. Only the given directory
# itself counts: being nested inside some other repository (for example a
# developer worktree) must not trigger this refusal.
if [[ -e "$REPO/.git" ]]; then
    if [[ -n "$(git -C "$REPO" status --porcelain)" ]]; then
        echo "Error: $REPO has uncommitted git changes; commit or stash them first" >&2
        exit 1
    fi
fi

trim() {
    local value="$1"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    printf '%s' "$value"
}

# version_gt A B: true when Debian version A is strictly newer than B.
version_gt() {
    dpkg --compare-versions "$1" gt "$2"
}

version_eq() {
    dpkg --compare-versions "$1" eq "$2"
}

# is_pinned PKG VER PIN_ENTRY...: true when PKG=VER matches an exact pin.
# Each pin entry is stored as "package|version".
is_pinned() {
    local pkg="$1" ver="$2" entry pin_pkg pin_ver
    shift 2
    for entry in "$@"; do
        pin_pkg="${entry%%|*}"
        pin_ver="${entry#*|}"
        if [[ "$pkg" == "$pin_pkg" ]] && version_eq "$ver" "$pin_ver"; then
            return 0
        fi
    done
    return 1
}

DELETE_LIST=()
TOTAL_BYTES=0

suites_found=0
for bindir in "$REPO"/dists/*/main/binary-amd64; do
    [[ -d "$bindir" ]] || continue
    suite="${bindir%/main/binary-amd64}"
    suite="${suite##*/dists/}"
    suites_found=$((suites_found + 1))

    # Group .debs by package name and architecture.
    declare -A group_entries=()
    declare -A group_pkg=()
    shopt -s nullglob
    deb_files=("$bindir"/*.deb)
    shopt -u nullglob
    for deb in "${deb_files[@]}"; do
        pkg="$(dpkg-deb -f "$deb" Package)"
        ver="$(dpkg-deb -f "$deb" Version)"
        arch="$(dpkg-deb -f "$deb" Architecture)"
        key="${pkg}__${arch}"
        group_pkg["$key"]="$pkg"
        group_entries["$key"]+="${ver}"$'\t'"${deb}"$'\n'
    done

    # Find the newest spaced-meta in this suite; its exact pins protect
    # older revisions that installed systems still resolve.
    newest_meta=""
    newest_meta_ver=""
    for key in "${!group_pkg[@]}"; do
        [[ "${group_pkg[$key]}" == "spaced-meta" ]] || continue
        while IFS=$'\t' read -r ver file; do
            [[ -n "${ver:-}" ]] || continue
            if [[ -z "$newest_meta_ver" ]] || version_gt "$ver" "$newest_meta_ver"; then
                newest_meta_ver="$ver"
                newest_meta="$file"
            fi
        done <<< "${group_entries[$key]}"
    done
    if [[ -z "$newest_meta" ]]; then
        echo "Error: suite '$suite' has no spaced-meta package; refusing to prune" >&2
        exit 1
    fi

    # Collect exact "(= X)" pins from the newest spaced-meta's Depends.
    pins=()
    depends="$(dpkg-deb -f "$newest_meta" Depends || true)"
    while IFS= read -r dep; do
        dep="$(trim "$dep")"
        [[ -n "$dep" ]] || continue
        if [[ "$dep" == *"("*")"* ]]; then
            inner="${dep#*(}"
            inner="${inner%%)*}"
            inner_trimmed="$(trim "$inner")"
            # An exact pin starts with "=" but not "==" (">="/"<=" start
            # with ">" or "<", so they never match this branch).
            if [[ "$inner_trimmed" == "="* && "$inner_trimmed" != "=="* ]]; then
                pin_ver="$(trim "${inner_trimmed#=}")"
                pin_pkg="$(trim "${dep%%(*}")"
                if [[ -n "$pin_pkg" && -n "$pin_ver" ]]; then
                    pins+=("${pin_pkg}|${pin_ver}")
                fi
            fi
        fi
    done <<< "$(tr ',' '\n' <<< "$depends")"

    # Keep the newest KEEP versions per group; pin-protected versions
    # survive even when they fall outside the newest N.
    declare -a kept_marco_versions=()
    for key in "${!group_pkg[@]}"; do
        pkg="${group_pkg[$key]}"
        # Sort this group's versions newest-first with dpkg ordering
        # (never sort -V; Debian revisions such as 9.26-1 vs 9.26.1-6
        # and 1.26.2-6+spaced9.26.1 need dpkg semantics).
        sorted_vers=()
        sorted_files=()
        while IFS=$'\t' read -r ver file; do
            [[ -n "${ver:-}" ]] || continue
            inserted=0
            for ((i = 0; i < ${#sorted_vers[@]}; i++)); do
                if version_gt "$ver" "${sorted_vers[$i]}"; then
                    sorted_vers=("${sorted_vers[@]:0:$i}" "$ver" "${sorted_vers[@]:$i}")
                    sorted_files=("${sorted_files[@]:0:$i}" "$file" "${sorted_files[@]:$i}")
                    inserted=1
                    break
                fi
            done
            if [[ "$inserted" -eq 0 ]]; then
                sorted_vers+=("$ver")
                sorted_files+=("$file")
            fi
        done <<< "${group_entries[$key]}"
        for ((i = 0; i < ${#sorted_vers[@]}; i++)); do
            if [[ "$i" -lt "$KEEP" ]]; then
                case "$pkg" in
                    marco*|libmarco*)
                        kept_marco_versions+=("${sorted_vers[$i]}")
                        ;;
                esac
                continue
            fi
            if is_pinned "$pkg" "${sorted_vers[$i]}" "${pins[@]}"; then
                case "$pkg" in
                    marco*|libmarco*)
                        kept_marco_versions+=("${sorted_vers[$i]}")
                        ;;
                esac
                continue
            fi
            DELETE_LIST+=("${sorted_files[$i]}")
        done
    done

    # Prune Marco sources that match no kept marco/libmarco binary version.
    # Only the source archives are candidates; the generated Sources index
    # files are left alone for build-apt-repo.sh to regenerate.
    srcdir="$REPO/dists/$suite/main/source"
    [[ -d "$srcdir" ]] || continue
    shopt -s nullglob
    source_files=("$srcdir"/marco_*.dsc "$srcdir"/marco_*.orig.tar.* "$srcdir"/marco_*.debian.tar.*)
    shopt -u nullglob
    for src in "${source_files[@]}"; do
        [[ -f "$src" ]] || continue
        base="${src##*/}"
        keep_src=0
        if [[ "$base" == marco_*.dsc ]]; then
            fver="${base#marco_}"
            fver="${fver%.dsc}"
            for kv in "${kept_marco_versions[@]}"; do
                if [[ "$fver" == "$kv" ]]; then
                    keep_src=1
                    break
                fi
            done
        elif [[ "$base" == marco_*.debian.tar.* ]]; then
            fver="${base#marco_}"
            fver="${fver%.debian.tar.*}"
            for kv in "${kept_marco_versions[@]}"; do
                if [[ "$fver" == "$kv" ]]; then
                    keep_src=1
                    break
                fi
            done
        elif [[ "$base" == marco_*.orig.tar.* ]]; then
            uver="${base#marco_}"
            uver="${uver%.orig.tar.*}"
            for kv in "${kept_marco_versions[@]}"; do
                case "$kv" in
                    "$uver"|"$uver"-*)
                        keep_src=1
                        break
                        ;;
                esac
            done
        else
            continue
        fi
        if [[ "$keep_src" -eq 0 ]]; then
            DELETE_LIST+=("$src")
        fi
    done
    unset group_entries group_pkg
done

if [[ "$suites_found" -eq 0 ]]; then
    echo "No suite directories (dists/*/main/binary-amd64) found under $REPO; nothing to prune."
    echo "Reminder: run scripts/build-apt-repo.sh afterwards to regenerate and re-sign the indexes."
    exit 0
fi

if [[ "${#DELETE_LIST[@]}" -eq 0 ]]; then
    echo "Nothing to prune: newest $KEEP per package already satisfy the retention policy."
    echo "Reminder: run scripts/build-apt-repo.sh afterwards to regenerate and re-sign the indexes."
    exit 0
fi

# Sort the deletion list for stable, reviewable output.
mapfile -t DELETE_LIST < <(printf '%s\n' "${DELETE_LIST[@]}" | LC_ALL=C sort -u)

for file in "${DELETE_LIST[@]}"; do
    size="$(stat -c '%s' -- "$file")"
    TOTAL_BYTES=$((TOTAL_BYTES + size))
    if [[ "$APPLY" -eq 1 ]]; then
        echo "Deleting: $file (${size} bytes)"
    else
        echo "Would delete: $file (${size} bytes)"
    fi
done

if [[ "$APPLY" -eq 1 ]]; then
    for file in "${DELETE_LIST[@]}"; do
        rm -f -- "$file"
    done
    echo "Deleted ${#DELETE_LIST[@]} file(s), freed $TOTAL_BYTES bytes."
else
    echo "Dry run: ${#DELETE_LIST[@]} file(s) would be deleted, freeing $TOTAL_BYTES bytes."
fi

echo "Reminder: run scripts/build-apt-repo.sh afterwards to regenerate and re-sign the indexes."
