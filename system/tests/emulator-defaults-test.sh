#!/bin/bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
L="$repo/system/rootfs/usr/libexec/banana"
t=$(mktemp -d /var/tmp/banana-v9-test.XXXXXX)
trap 'rm -rf "$t"' EXIT
for f in emulator-defaults run-rpg run-retroarch run-bananafront run-gw run-pico8; do sh -n "$L/$f"; done
export BANANA_RPG_DATA="$t/data" BANANA_RPG_RUNTIME="$t/runtime" SDL_VIDEODRIVER=dummy
mkdir -p "$t/data/banana" "$t/data/roms/mkxp/Game" "$t/data/roms/easyrpg/Game" "$t/runtime/mkxp" "$t/runtime/easyrpg"
touch "$t/data/roms/mkxp/Game/Game.ini" "$t/data/roms/easyrpg/Game/RPG_RT.ldb"
cat > "$t/runtime/mkxp/mkxp-z" <<'EOF'
#!/bin/sh
printf 'ENGINE scale=%s font=%s render=%s encoding=%s\n' "$BANANA_RPG_SCALE" "$BANANA_RPG_FONT_SCALE" "$BANANA_RPG_RENDER" "$BANANA_RPG_FILENAME_ENCODING"
EOF
cat > "$t/runtime/easyrpg/easyrpg-player" <<'EOF'
#!/bin/sh
printf 'ENGINE filename-encoding=%s\n' "$BANANA_RPG_FILENAME_ENCODING"
printf 'ARG %s\n' "$@"
EOF
chmod +x "$t/runtime/"*/*
f="$t/data/banana/emulator-defaults.conf"
cat > "$f" <<'EOF'
mkxp.scale = integer
mkxp.font_scale = 110
mkxp.render = compat
mkxp.filename_encoding = 949
easyrpg.encoding = 949
easyrpg.scale = smooth
gba.ra_frontend = retroarch
gbc.ra_frontend = bananafront
gba.video_monitor_index = 1
gba.ra_audio_latency = 128
gbc.ra_audio_latency = inherit
EOF
m="$t/data/roms/mkxp/Game"
e="$t/data/roms/easyrpg/Game"
export BANANA_GAME_KEY=mkxp/Game
sh "$L/run-rpg" mkxp "$m/Game.ini"
grep -Fx 'ENGINE scale=integer font=110 render=compat encoding=949' "$m/banana-mkxp.log"
grep -Fx "$m/banana-mkxp.log" "$t/data/banana/logs/rpg-last-log-path.txt"
hex=$(printf '%s' "$BANANA_GAME_KEY" | od -An -tx1 | tr -d ' \n')
printf '%s\n' "$hex.scale = smooth" "$hex.font_scale = auto" "$hex.filename_encoding = auto" > "$t/data/banana/rpg-per-game.conf"
sh "$L/run-rpg" mkxp "$m/Game.ini"
grep -Fx 'ENGINE scale=smooth font= render=compat encoding=' "$m/banana-mkxp.log"
grep -Fx 'ENGINE scale=integer font=110 render=compat encoding=949' "$m/banana-mkxp.previous.log"
BANANA_SA_RESTARTING=1 sh "$L/run-rpg" mkxp "$m/Game.ini"
test "$(grep -c '^ENGINE ' "$m/banana-mkxp.log")" = 2
echo 'PASS MKXP inherited defaults, individual overrides, explicit auto, local log rotation and restart append'
export BANANA_GAME_KEY=easyrpg/Game BANANA_RPG_LOG=0
sh "$L/run-rpg" easyrpg "$e/RPG_RT.ldb" > "$t/easy"
grep -Fx 'ENGINE filename-encoding=949' "$t/easy"
grep -A1 -Fx 'ARG --encoding' "$t/easy" | grep -Fx 'ARG 949'
grep -A1 -Fx 'ARG --scaling' "$t/easy" | grep -Fx 'ARG bilinear'
hex=$(printf '%s' "$BANANA_GAME_KEY" | od -An -tx1 | tr -d ' \n')
printf '%s\n' "$hex.encoding = 932" "$hex.scale = integer" "$hex.filename_encoding = auto" >> "$t/data/banana/rpg-per-game.conf"
sh "$L/run-rpg" easyrpg "$e/RPG_RT.ldb" > "$t/easy"
grep -Fx 'ENGINE filename-encoding=' "$t/easy"
grep -A1 -Fx 'ARG --encoding' "$t/easy" | grep -Fx 'ARG 932'
grep -A1 -Fx 'ARG --scaling' "$t/easy" | grep -Fx 'ARG integer'
echo 'PASS EasyRPG default CP949, per-game CP932, independent filename auto'
export BANANA_DEFAULTS_FILE="$f"
. "$L/emulator-defaults"
export BANANA_SYSTEM=gba
test "$(emu_override ra_frontend)" = retroarch
test "$(emu_override video_monitor_index)" = 1
test "$(emu_override ra_audio_latency)" = 128
export BANANA_SYSTEM=gbc
test "$(emu_override ra_frontend)" = bananafront
test -z "$(emu_override ra_audio_latency)"
test -z "$(emu_override video_monitor_index)"
echo 'PASS system-specific RA values and global fallback'
