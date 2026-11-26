#!/bin/bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
if [ "${1:-}" != --inside ]; then
 base="$(realpath "$1")"
 interp=$(sed -n 's/^interpreter //p' /proc/sys/fs/binfmt_misc/qemu-aarch64)
 test -n "$interp"
 exec unshare --mount --pid --fork --mount-proc bash "$0" --inside "$base" "$interp"
fi
base=$2; interp=$3
t=$(mktemp -d /var/tmp/banana-ra-defaults.XXXXXX)
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
L="$repo/system/rootfs/usr/libexec/banana"
for f in emulator-defaults run-retroarch run-bananafront run-gw run-pico8; do install -m755 "$L/$f" "$r/usr/libexec/banana/$f"; done
mkdir -p "$r/data/banana" "$r/data/retroarch" "$r/run/banana" "$r/data/roms/"{gba,gbc,pico-8,gameandwatch}
touch "$r/data/roms/gba/test.gba" "$r/data/roms/gbc/test.gbc" "$r/data/roms/pico-8/test.p8" "$r/data/roms/gameandwatch/test.zip"
cp "$r/etc/banana/retroarch.cfg" "$r/data/retroarch/retroarch.cfg"
cat > "$r/data/banana/settings.conf" <<'EOF'
ra_frontend = retroarch
ra_shader = off
ra_border = off
ra_audio_latency = 64
ra_vsync = on
language = ko
EOF
cat > "$r/data/banana/emulator-defaults.conf" <<'EOF'
gba.ra_frontend = retroarch
gba.video_monitor_index = 1
gba.video_scale_integer = true
gba.savestate_auto_save = true
gba.ra_audio_latency = 128
gba.ra_vsync = off
gbc.ra_frontend = bananafront
gbc.ra_audio_latency = 32
gbc.ra_shader = lcd
gbc.video_scale_integer = true
gbc.savestate_auto_save = true
gbc.video_monitor_index = 2
pico-8.pico_engine = fake08
pico-8.ra_frontend = retroarch
gameandwatch.audio = off
gameandwatch.artwork = plain
EOF
# Stubs only at the final executable and hardware boundary. Exercise the real launchers.
cat > "$r/usr/libexec/banana/one-panel" <<'EOF'
one_panel_dark() { printf '%s\n' "$1" > /data/panel-test; }
one_panel_restore() { :; }
EOF
cat > "$r/usr/bin/retroarch" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > /data/ra-args
while [ "$#" -gt 0 ]; do
 if [ "$1" = --appendconfig ]; then
  shift
  oldIFS=$IFS; IFS='|'
  for f in $1; do [ ! -f "$f" ] || cat "$f"; done > /data/ra-append
  IFS=$oldIFS
 fi
 shift
done
# Emulate RetroArch saving runtime override values into its global cfg.
if [ -f /run/banana/retroarch-system.cfg ]; then
 cat /run/banana/retroarch-system.cfg >> /data/retroarch/retroarch.cfg
fi
EOF
cat > "$r/usr/bin/bananafront" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > /data/bf-args
EOF
cat > "$r/data/roms/pico-8/pico8_64" <<'EOF'
#!/bin/sh
echo official > /data/pico-official
EOF
cat > "$r/usr/bin/mame-gnw" <<'EOF'
#!/bin/sh
case " $* " in *" -listxml "*) echo '<display tag="screen" />' ;; *) printf '%s\n' "$@" > /data/gw-args ;; esac
EOF
printf '#!/bin/sh\nexit 0\n' > "$r/usr/libexec/banana/gw-hotkeys"
chmod 755 "$r/usr/bin/"{retroarch,bananafront,mame-gnw} "$r/data/roms/pico-8/pico8_64" "$r/usr/libexec/banana/gw-hotkeys"
CFG="$r/data/retroarch/retroarch.cfg"
# Set a known global baseline.
sed -i -E '/^(video_monitor_index|video_scale_integer|savestate_auto_save|savestate_auto_load) = /d' "$CFG"
printf 'video_monitor_index = "2"\nvideo_scale_integer = "false"\nsavestate_auto_save = "false"\nsavestate_auto_load = "false"\n' >> "$CFG"
BANANA_SYSTEM=gba chroot "$r" /usr/libexec/banana/run-retroarch gpsp /data/roms/gba/test.gba
grep -Fx 'video_monitor_index = "1"' "$r/data/ra-append"
grep -Fx 'video_scale_integer = "true"' "$r/data/ra-append"
grep -Fx 'savestate_auto_save = "true"' "$r/data/ra-append"
grep -Fx 'savestate_auto_load = "true"' "$r/data/ra-append"
grep -Fx 'bottom' "$r/data/panel-test"
grep -Fx 'video_monitor_index = "2"' "$CFG"
grep -Fx 'video_scale_integer = "false"' "$CFG"
grep -Fx 'savestate_auto_save = "false"' "$CFG"
grep -Fx 'savestate_auto_load = "false"' "$CFG"
! grep -q '^savestate_auto_save = "true"' "$CFG"
echo 'PASS actual RetroArch launcher scoped options and restoration'
BANANA_SYSTEM=gbc chroot "$r" /usr/libexec/banana/run-retroarch gambatte /data/roms/gbc/test.gbc
for v in --resume-save --resume-load --audio-latency 32 --scale integer --shader zfast-lcd; do grep -Fx -- "$v" "$r/data/bf-args"; done
grep -Fx 'top' "$r/data/panel-test"
echo 'PASS actual BananaFront launcher consumes per-system defaults'
BANANA_SYSTEM=pico-8 chroot "$r" /usr/libexec/banana/run-pico8 /data/roms/pico-8/test.p8
test ! -f "$r/data/pico-official"
grep -F fake08_libretro.so "$r/data/ra-args"
echo 'PASS PICO-8 forced Fake-08'
BANANA_SYSTEM=gameandwatch chroot "$r" /usr/libexec/banana/run-gw /data/roms/gameandwatch/test.zip
grep -A1 -Fx -- '-sound' "$r/data/gw-args" | grep -Fx none
grep -A1 -Fx -- '-view' "$r/data/gw-args" | grep -Fx auto
echo 'PASS Game & Watch audio/view defaults'
