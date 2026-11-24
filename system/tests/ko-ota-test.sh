#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
export BANANA_DATA="$tmp/data" BANANA_RUN="$tmp/run" BANANA_BOARD=rgds BANANA_VERSION=0.5.3.6.1 BANANA_UPDATE_FREE_KB=1000000
unset BANANA_UPDATE_FEED BANANA_UPDATE_BETA_FEED
mkdir -p "$BANANA_DATA/updates" "$BANANA_RUN"
update="$root/system/rootfs/usr/libexec/banana/update"
# Even an old saved beta password cannot reactivate the upstream channel.
echo old > "$BANANA_DATA/updates/.beta"
if sh "$update" beta-on; then exit 1; else test "$?" -eq 4; fi
cat > "$BANANA_DATA/updates/.check-ko" <<'EOF'
state=newer
board=rgds
channel=github
file=banana-rgds-0.5.3.7.update.tar
url=https://github.com/JorreFog/BananaLinux/releases/download/v0.5.3.7/banana-rgds-0.5.3.7.update.tar
sums=https://github.com/JorreFog/BananaLinux/releases/download/v0.5.3.7/SHA256SUMS-rgds.txt
size=1024
EOF
if sh "$update" download > "$tmp/log" 2>&1; then
    echo "FAIL: accepted upstream OTA"; exit 1
fi
grep -q 'not from the Korean edition' "$tmp/log"
echo "ko-ota-test: upstream assets and beta channel rejected"
