#!/bin/bash
# Run the actual ARM64 data-layout and UI against disposable data, never a physical SD.
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "${1:-}" != --inside ]; then
 base="$(realpath "$1")"
 interp=$(sed -n 's/^interpreter //p' /proc/sys/fs/binfmt_misc/qemu-aarch64)
 test -n "$interp"
 exec unshare --mount --pid --fork --mount-proc bash "$0" --inside "$base" "$interp"
fi
base=$2; interp=$3
t=$(mktemp -d /var/tmp/banana-bios-layout.XXXXXX)
r="$t/root"
mount --make-rprivate /
trap 'umount -R "$r" >/dev/null 2>&1 || :; rm -rf "$t"' EXIT
mkdir -p "$r" "$t/upper" "$t/work"
mount -t overlay overlay -o "lowerdir=$base,upperdir=$t/upper,workdir=$t/work" "$r"
mkdir -p "$r$(dirname "$interp")"
cp -L "$interp" "$r$interp"
while read -r lib; do mkdir -p "$r$(dirname "$lib")"; cp -L "$lib" "$r$lib"; done < <(ldd "$interp" | awk '/=> \//{print $3} /^[[:space:]]*\/.*ld-linux/{print $1}')
mount -t tmpfs tmpfs "$r/data"
mount -t tmpfs tmpfs "$r/run"
mount -t proc proc "$r/proc"
mount --rbind /dev "$r/dev"; mount --make-rslave "$r/dev"
mkdir -p "$r/run/banana"
check_folders() {
 for f in bios/psx bios/dc bios/dreamcast bios/fbneo bios/rtp/2000 bios/rtp/2003 bios/easyrpg-player/Font bios/easyrpg-player/Soundfont bios/mkxp/rtp/xp bios/mkxp/rtp/vx bios/mkxp/rtp/vxace bios/mkxp/rtp/fonts bios/mkxp/fonts bios/mkxp/soundfonts roms/psx roms/psp roms/dreamcast roms/fbneo roms/easyrpg roms/mkxp roms/ports; do
  test -d "$r/data/$f" || { echo "MISSING $f"; exit 1; }
 done
}
chroot "$r" /usr/libexec/banana/data-layout
check_folders
cmp "$r/etc/banana/settings.conf" "$r/data/banana/settings.conf"
grep -Fx 'core.psx = duckstation_sa' "$r/data/banana/settings.conf"
grep -Fx 'face_layout = nintendo' "$r/data/banana/settings.conf"
echo 'FRESH_BOOT_LAYOUT_PASS'
# Simulate an older card: noncanonical text, missing keys, unknown future key, duplicates,
# settings for networking and different emulators, games, saves, and BIOS.
printf '# keep whitespace and CRLF\r\n  theme=light\r\nface_layout = individual\r\ncore.psx = swanstation\r\nra_vsync = invalid\r\ncustom = keep\r\n' > "$r/data/banana/settings.conf"
for f in bananad.conf emulator-defaults.conf rpg-per-game.conf nds-per-game.conf wifi.conf accounts.conf swanstation.conf duckstation.conf; do printf 'test-fixture %s\r\n' "$f" > "$r/data/banana/$f"; done
printf '[psx]\nperf = balanced\n' > "$r/data/banana/systems.conf"
mkdir -p "$r/data/retroarch" "$r/data/banana/themes" "$r/data/banana/rpg/mkxp/test"
printf 'video_vsync = "false"\n' > "$r/data/retroarch/retroarch.cfg"
printf 'custom = 1\n' > "$r/data/banana/rpg/mkxp/test/options.conf"
printf 'fixture not a real BIOS\n' > "$r/data/bios/psx/test.bin"
printf 'fixture\n' > "$r/data/saves/test.sav"
printf 'fixture\n' > "$r/data/roms/psx/test.chd"
rmdir "$r/data/bios/dc" "$r/data/bios/dreamcast" "$r/data/bios/fbneo" "$r/data/bios/mkxp/rtp/fonts"
(cd "$r/data"; find banana -type f ! -name 'README.txt' ! -name 'systems.conf.default' ! -path '*/logs/*' -print0 | sort -z | xargs -0 sha256sum; sha256sum retroarch/retroarch.cfg bios/psx/test.bin saves/test.sav roms/psx/test.chd) > "$t/before"
chroot "$r" /usr/libexec/banana/data-layout
check_folders
chroot "$r" /usr/libexec/banana/data-layout
(cd "$r/data"; sha256sum -c "$t/before")
echo 'EXISTING_CARD_LAYOUT_PRESERVE_PASS'
# Actual UI startup, headless so it cannot access real panels or inputs.
mkdir -p "$r/tmp/qa"
chroot "$r" /usr/bin/banana-ui --headless /tmp/qa/ --size 640x480 --data /data/banana --roms /data/roms --systems /run/banana/systems.conf --script 'wait 1'
(cd "$r/data"; sha256sum -c "$t/before")
echo 'ACTUAL_UI_STARTUP_PRESERVE_PASS'
