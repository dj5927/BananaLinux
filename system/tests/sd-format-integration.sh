#!/bin/bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../..";pwd)
root=$(realpath "$1")
python3 -B "$repo/system/tests/sd-format-probe-test.py"
qemu-aarch64 -L "$root" -E PYTHONHOME="$root/usr" -E LD_LIBRARY_PATH="$root/usr/lib:$root/lib" "$root/usr/bin/python3.14" -B "$repo/system/tests/sd-format-probe-test.py" "$root/usr/libexec/banana/sd-format.py"
if [ "${BANANA_SKIP_LOOP:-0}" != 1 ]; then python3 -B "$repo/system/tests/sd-format-loop-test.py" "$root" "$repo"; fi
