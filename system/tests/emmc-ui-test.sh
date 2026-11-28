#!/bin/bash
set -euo pipefail
if [ "${1:-}" != --inside ]; then
 base=$(realpath "$1")
 interp=$(sed -n 's/^interpreter //p' /proc/sys/fs/binfmt_misc/qemu-aarch64)
 exec unshare --mount --pid --fork --mount-proc bash "$0" --inside "$base" "$interp"
fi
base=$2; interp=$3
t=$(mktemp -d /var/tmp/banana-emmc-ui.XXXXXX)
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
mkdir -p "$r/run/banana" "$r/data/banana" "$r/tmp/emmc-shots"
cp "$r/etc/banana/settings.conf" "$r/data/banana/settings.conf"
chroot "$r" /bin/sh -c 'for t in dd sfdisk partx mkfs.exfat mount umount mountpoint blockdev sync; do command -v "$t" || exit 1; done'
chroot "$r" /bin/sh -c 'mkdir -p /tmp/cp-a /tmp/cp-b; echo old > /tmp/cp-a/save; echo keep > /tmp/cp-b/save; cp -Rn /tmp/cp-a/. /tmp/cp-b/; test "$(cat /tmp/cp-b/save)" = keep'
cat > "$r/usr/libexec/banana/emmc-install" <<'EOF'
#!/bin/sh
echo "$*" >> /run/banana/emmc-commands
case "$1" in
probe) echo 'ready /dev/mmcblk0 32 GiB' > /run/banana/emmc-status;;
install) echo 'done eMMC' > /run/banana/emmc-status;;
esac
EOF
chmod +x "$r/usr/libexec/banana/emmc-install"
nav='home 0; press start; press r; press r; press r; press r; press r; press a; press up; press a; sleep 700; upstate'
ui() {
 chroot "$r" /usr/bin/banana-ui --headless /tmp/emmc-shots/ --size "$1" --data /data/banana --roms /data/roms --systems /etc/banana/systems.conf --script "$2" 2> "$t/ui.log" || { cat "$t/ui.log"; exit 1; }
}
for size in 640x480 1024x768; do
 # Default Cancel on screen one: A must never start installation.
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; shot warning-$size; press a"
 test "$(cat "$r/run/banana/emmc-commands")" = probe
 # B on either screen cancels.
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; press right; press b"
 test "$(cat "$r/run/banana/emmc-commands")" = probe
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; press right; press a; upstate; shot responsibility-$size; press b"
 test "$(cat "$r/run/banana/emmc-commands")" = probe
 # Screen two defaults to Cancel again; repeated A cannot inherit consent.
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; press right; press a; press a; press a; sleep 700; press a"
 test "$(grep -c '^install ' "$r/run/banana/emmc-commands" || :)" = 0
 # Explicit left/Cancel on screen two also prevents installation.
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; press right; press a; press right; press left; press a"
 test "$(cat "$r/run/banana/emmc-commands")" = probe
 # Only selecting Agree and confirming on each distinct screen installs once.
 : > "$r/run/banana/emmc-commands"
 ui "$size" "$nav; press right; press a; press right; shot final-agree-$size; press a; sleep 700; upstate; shot done-$size; press b"
 test "$(grep -c '^install ERASE-INTERNAL-EMMC$' "$r/run/banana/emmc-commands")" = 1
 grep -q 'status "done eMMC"' "$t/ui.log"
 echo "EMMC_UI_TWO_WARNINGS_DEFAULT_CANCEL_BOTH_STAGES_REPEATED_A_AND_EXPLICIT_CONSENT_PASS $size"
done
out=/mnt/e/BananaOS-Korean-0.5.3.6.44/logs/emmc-ui
mkdir -p "$out"
cp "$r/tmp/emmc-shots/"*.png "$out/"
