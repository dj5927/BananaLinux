#!/bin/bash
# Reproduce the static ARM64 FAT32 formatter used by the incremental firmware.
set -euo pipefail
out=$(realpath "${1:?output directory required}")
mkdir -p "$out"
t=$(mktemp -d);trap 'rm -rf "$t"' EXIT
cd "$t"
curl -fL --retry 2 https://github.com/dosfstools/dosfstools/releases/download/v4.2/dosfstools-4.2.tar.gz -o dosfstools-4.2.tar.gz
echo '64926eebf90092dca21b14259a5301b7b98e7b1943e8a201c7d726084809b527  dosfstools-4.2.tar.gz' | sha256sum -c -
tar -xzf dosfstools-4.2.tar.gz
cd dosfstools-4.2
./configure --host=aarch64-linux-gnu --without-udev --disable-dependency-tracking CFLAGS='-O2 -static' LDFLAGS=-static
make -j4
aarch64-linux-gnu-strip src/mkfs.fat
install -m755 src/mkfs.fat "$out/mkfs.fat"
