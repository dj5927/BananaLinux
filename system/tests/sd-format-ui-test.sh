#!/bin/bash
set -euo pipefail
if [ "${1:-}" != --inside ]; then
 base=$(realpath "$1")
 interp=$(sed -n 's/^interpreter //p' /proc/sys/fs/binfmt_misc/qemu-aarch64)
 exec unshare --mount --pid --fork --mount-proc bash "$0" --inside "$base" "$interp"
fi
base=$2; interp=$3
t=$(mktemp -d /var/tmp/banana-sd-format-ui.XXXXXX)
r="$t/root"
mount --make-rprivate /
trap 'umount -R "$r" >/dev/null 2>&1 || :; rm -rf "$t"' EXIT
mkdir -p "$r" "$t/upper" "$t/work"
mount -t overlay overlay -o "lowerdir=$base,upperdir=$t/upper,workdir=$t/work" "$r"
mkdir -p "$r$(dirname "$interp")"
cp -L "$interp" "$r$interp"
while read -r lib; do mkdir -p "$r$(dirname "$lib")"; cp -L "$lib" "$r$lib"; done < <(ldd "$interp" | awk '/=> \//{print $3} /^[[:space:]]*\/.*ld-linux/{print $1}')
# QEMU loads the host unwinder lazily when a worker thread exits (not listed by ldd).
hostgcc=/lib/x86_64-linux-gnu/libgcc_s.so.1
mkdir -p "$r$(dirname "$hostgcc")"; cp -L "$hostgcc" "$r$hostgcc"
mount -t tmpfs tmpfs "$r/data"
mount -t tmpfs tmpfs "$r/run"
mount -t proc proc "$r/proc"
mount --rbind /dev "$r/dev"; mount --make-rslave "$r/dev"
mkdir -p "$r/run/banana" "$r/data/banana" "$r/tmp/sd-format-shots"
cp "$r/etc/banana/settings.conf" "$r/data/banana/settings.conf"
chroot "$r" /bin/sh -c 'for t in dd sfdisk partx mkfs.exfat mount umount mountpoint blockdev sync; do command -v "$t" || exit 1; done'
chroot "$r" /bin/sh -c 'mkdir -p /tmp/cp-a /tmp/cp-b; echo old > /tmp/cp-a/save; echo keep > /tmp/cp-b/save; cp -Rn /tmp/cp-a/. /tmp/cp-b/; test "$(cat /tmp/cp-b/save)" = keep'
cat > "$r/usr/libexec/banana/sd-format" <<'EOF'
#!/bin/sh
echo "$*" >> /run/banana/sd-format-commands
case "$1" in
probe)
 if [ -e /run/banana/fail-probe ]; then echo 'failed: Boot from internal eMMC without the boot SD, then insert the SD to format.' > /run/banana/sd-format-status
 else echo fixture-token > /run/banana/sd-format-token; echo 'ready /dev/mmcblk1 32.0 GiB' > /run/banana/sd-format-status; fi;;
format) echo "done $2" > /run/banana/sd-format-status;;
esac
EOF
chmod +x "$r/usr/libexec/banana/sd-format"
printf '#!/bin/sh\nexit 0\n' > "$r/usr/libexec/banana/sd2"
chmod +x "$r/usr/libexec/banana/sd2"
nav='home 0; press start; press r; press r; press r; press r; press r; press a; press up; press up; press a; sleep 700; upstate'
ui() {
 chroot "$r" /usr/bin/banana-ui --headless /tmp/sd-format-shots/ --size "$1" --data /data/banana --roms /data/roms --systems /etc/banana/systems.conf --script "$2" 2> "$t/ui.log" || { cat "$t/ui.log"; exit 1; }
}
if [ "${BANANA_UI_VISUAL_ONLY:-0}" = 1 ]; then
 ui 640x480 "$nav; shot filesystem-exfat-640x480; press a; shot warning-exfat-640x480; press right; press a; shot responsibility-exfat-640x480; press b"
 sleep 1
 out=/mnt/e/BananaOS-Korean-0.5.3.6.44/logs/sd-format-ui
 mkdir -p "$out"; cp "$r/tmp/sd-format-shots/"*.png "$out/"
 exit 0
fi
for size in 640x480 1024x768; do
 for flow in 'press b' 'press a; press a' 'press a; press right; press a; press a; press a' 'press a; press right; press b' 'press a; press right; press a; press b'; do
  : > "$r/run/banana/sd-format-commands"
  ui "$size" "$nav; $flow"
  test "$(grep -c '^format ' "$r/run/banana/sd-format-commands" || :)" = 0
 done
 for fs in exfat fat32; do
  key=right; [ "$fs" != fat32 ] || key=left
  : > "$r/run/banana/sd-format-commands"
  ui "$size" "$nav; press $key; shot filesystem-$fs-$size; press a; shot warning-$fs-$size; press right; press a; shot responsibility-$fs-$size; press right; press a; sleep 700; upstate; shot done-$fs-$size; press b"
  test "$(grep -c "^format $fs ERASE-ENTIRE-SD fixture-token$" "$r/run/banana/sd-format-commands")" = 1
  grep -q "status \"done $fs\"" "$t/ui.log"
 done
 : > "$r/run/banana/sd-format-commands"; touch "$r/run/banana/fail-probe"
 ui "$size" "$nav; shot blocked-$size; press right; press a; press a; press b"
 test "$(grep -c '^format ' "$r/run/banana/sd-format-commands" || :)" = 0
 rm "$r/run/banana/fail-probe"
 echo "SD_FORMAT_UI_BOTH_FILESYSTEMS_TWO_WARNINGS_DEFAULT_CANCEL_FAILURE_PASS $size"
done
# Let the UI's detached rescan worker finish before unmounting the fixture.
sleep 1
out=/mnt/e/BananaOS-Korean-0.5.3.6.44/logs/sd-format-ui
mkdir -p "$out"; cp "$r/tmp/sd-format-shots/"*.png "$out/"
