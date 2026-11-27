#!/bin/bash
set -euo pipefail
o=/mnt/e/BananaOS-Korean-0.5.3.6.27
w=/var/tmp/banana-v26-duck
host=/home/banana-builder/banana/output/rgds/host
r=/var/tmp/banana-rpg-v20-rgds/root
test -f "$r/usr/lib/libSDL2.so" || r=/var/tmp/banana-rpg-v19-rgds/root
cd "$w/build"
"$host/bin/aarch64-linux-g++" -std=c++17 -O2 -DWITH_SDL2=1 -I"$w/duckstation/src" -I"$w/deps/include" -I"$w/deps/include/SDL2" -c "$o/qa-sdl-audio.cpp" -o "$w/qa-sdl-audio.o"
# Reuse the exact successful link line, replacing the frontend objects
# with our standalone regression fixture. Static libraries remain identical.
python3 - "$w" <<'PY'
import shlex,subprocess,sys
from pathlib import Path
w=Path(sys.argv[1])
cmd=subprocess.check_output(["ninja","-t","commands","duckstation-nogui"],text=True)
line=next(l for l in reversed(cmd.splitlines()) if " -o bin/duckstation-nogui " in l)
args=shlex.split(line)
# CMake/Ninja prints a shell command with ': && ... && :'.
if args[:2]==[":","&&"]:args=args[2:]
if "&&" in args:args=args[:args.index("&&")]
args=[a for a in args if not ("/duckstation-nogui.dir/" in a and a.endswith(".o"))]
args.insert(1,str(w/"qa-sdl-audio.o"))
i=args.index("-o");args[i+1]=str(w/"qa-sdl-audio")
subprocess.run(args,check=True)
PY
for b in rgds rgds-plus; do
  r=/var/tmp/banana-rpg-v20-$b/root
  test -e "$r/usr/lib/libSDL2.so" || r=/var/tmp/banana-rpg-v19-$b/root
  qemu-aarch64 -L "$r" -E LD_LIBRARY_PATH="$r/usr/lib:$r/lib" "$w/qa-sdl-audio"
  echo ARM64_AUDIO_QA_PASS "$b"
done
