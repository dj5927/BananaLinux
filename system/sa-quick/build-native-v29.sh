#!/bin/bash
set -euo pipefail
o=/mnt/e/BananaOS-Korean-0.5.3.6.29
mkdir -p "$o/logs" "$o/binaries"
host=/home/banana-builder/banana/output/rgds/host/bin
case "$1" in
 psp) src=/var/tmp/banana-v20-sources/easypsp; b="$src/build-banana"; target=PPSSPPSDL; exe="$b/$target";;
 dc) src=/var/tmp/banana-v20-sources/easycast; b="$src/build-banana"; target=flycast; exe="$b/$target";;
 duck) src=/var/tmp/banana-v26-duck/duckstation; b=/var/tmp/banana-v26-duck/build; target=duckstation-nogui; exe="$b/bin/$target";;
 *) exit 2;;
esac
cmake --build "$b" --target "$target" -j5 > "$o/logs/build-$1.log" 2>&1
install -m755 "$exe" "$o/binaries/$target"
"$host/aarch64-linux-strip" --strip-unneeded "$o/binaries/$target"
readelf -h "$o/binaries/$target" | grep AArch64
if readelf -d "$o/binaries/$target" | grep -E 'RPATH|RUNPATH'; then exit 1; fi
strings "$o/binaries/$target" | grep -F 'BANANA_QUICK_REQUEST' > /dev/null
sha256sum "$o/binaries/$target"
echo "QUICK_ENGINE_BUILD_PASS $1"
