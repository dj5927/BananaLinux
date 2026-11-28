#!/bin/bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/../.." && pwd)"
L="$repo/system/rootfs/usr/libexec/banana"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
export BANANA_FACE_SETTINGS="$t/settings.conf"
. "$L/emulator-defaults"
test "$(face_layout)" = nintendo
for mode in individual nintendo xbox; do
    printf 'nds_swap_ab = on\nface_layout = %s\n' "$mode" > "$BANANA_FACE_SETTINGS"
    test "$(face_layout)" = "$mode"
    want=on; [ "$mode" != nintendo ] || want=off
    test "$(NDS_BUTTONS_SETTINGS="$BANANA_FACE_SETTINGS" sh "$L/nds-buttons" swapab)" = "$want"
    unset SDL_GAMECONTROLLERCONFIG
    face_sdl_mapping "$mode"
    case "$mode" in
      individual) test -z "${SDL_GAMECONTROLLERCONFIG:-}" ;;
      nintendo) case "$SDL_GAMECONTROLLERCONFIG" in *a:b1,b:b0,x:b2,y:b3,*) ;; *) exit 1;; esac ;;
      xbox) case "$SDL_GAMECONTROLLERCONFIG" in *a:b0,b:b1,x:b3,y:b2,*) ;; *) exit 1;; esac ;;
    esac
done
export BANANA_RPG_DATA="$t/data" BANANA_RPG_RUNTIME="$t/runtime" SDL_VIDEODRIVER=dummy
mkdir -p "$t/data/banana" "$t/game" "$t/runtime/mkxp"
touch "$t/game/Game.ini"
export BANANA_GAME_KEY=mkxp/QA
cat > "$t/runtime/mkxp/mkxp-z" <<'EOF'
#!/bin/sh
printf 'LAYOUT=%s\n' "$BANANA_FACE_LAYOUT"
printf 'SDL=%s\n' "${SDL_GAMECONTROLLERCONFIG:-}"
cat "$MKXP_CONTROLLER_REMAP_FILE"
EOF
chmod +x "$t/runtime/mkxp/mkxp-z"
printf 'mkxp.ruby_runtime = ruby32\nmkxp.key_c = X\nmkxp.key_b = L3\nmkxp.key_r = B\nmkxp.key_l = R3\n' > "$t/data/banana/emulator-defaults.conf"
for mode in individual nintendo xbox; do
    unset SDL_GAMECONTROLLERCONFIG
    printf 'face_layout = %s\n' "$mode" > "$t/data/banana/settings.conf"
    sh "$L/run-rpg" mkxp "$t/game/Game.ini"
    log="$t/game/banana-mkxp.log"
    grep -Fx "LAYOUT=$mode" "$log"
    if [ "$mode" = individual ]; then
        grep -Fx 'A=X' "$log"; grep -Fx 'B=L3' "$log"; grep -Fx 'R1=B' "$log"
    else
        grep -Fx 'A=A' "$log"; grep -Fx 'B=B' "$log"; grep -Fx 'R1=R1' "$log"
    fi
    grep -Fx 'L1=R3' "$log"
done
echo 'PASS MKXP forced face actions override custom assignments; unrelated shoulder remap retained'
