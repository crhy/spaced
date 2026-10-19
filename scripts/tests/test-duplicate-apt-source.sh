#!/bin/bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
HELPER=$ROOT/overlays/usr/lib/spaced-linux/spaced-clean-duplicate-apt-source
WORK=$(mktemp -d)
trap 'rm -rf -- "$WORK"' EXIT

make_fixture() {
    rm -rf -- "$WORK/sources"
    mkdir -p "$WORK/sources"
    cat > "$WORK/sources/spaced-apt.list" <<'EOF'
# Spaced Linux signed package repository
deb [signed-by=/usr/share/keyrings/spaced-archive-keyring.gpg] https://crhy.github.io/spaced-apt spaced main
EOF
}

make_fixture
cat > "$WORK/sources/spaced-apt.sources" <<'EOF'
Types: deb
URIs: https://crhy.github.io/spaced-apt/
Suites: spaced
Components: main
Signed-By: /usr/share/keyrings/spaced-archive-keyring.gpg
EOF
"$HELPER" --sources-dir "$WORK/sources"
[[ ! -e "$WORK/sources/spaced-apt.sources" ]]

for customization in \
    'Suites: spaced-testing' \
    'Components: main experimental' \
    'Architectures: amd64' \
    'Signed-By: /etc/apt/keyrings/local.gpg'
do
    make_fixture
    cat > "$WORK/sources/spaced-apt.sources" <<EOF
Types: deb
URIs: https://crhy.github.io/spaced-apt
Suites: spaced
Components: main
Signed-By: /usr/share/keyrings/spaced-archive-keyring.gpg
$customization
EOF
    "$HELPER" --sources-dir "$WORK/sources"
    [[ -f "$WORK/sources/spaced-apt.sources" ]]
done

make_fixture
sed -i 's|crhy.github.io/spaced-apt|mirror.example/spaced|' "$WORK/sources/spaced-apt.list"
cat > "$WORK/sources/spaced-apt.sources" <<'EOF'
Types: deb
URIs: https://crhy.github.io/spaced-apt
Suites: spaced
Components: main
Signed-By: /usr/share/keyrings/spaced-archive-keyring.gpg
EOF
"$HELPER" --sources-dir "$WORK/sources"
[[ -f "$WORK/sources/spaced-apt.sources" ]]

echo "Duplicate Spaced APT source cleanup tests passed."
