#!/usr/bin/env bash
# Integration test of a prepared ARM64 firmware root. Requires Linux root,
# qemu-user binfmt, iproute2, overlayfs, and python3-paramiko. Isolated network.
set -euo pipefail
if [ "${1:-}" != --inside ]; then
    [ "$#" = 1 ] || { echo "usage: $0 <unpacked-firmware-root>" >&2; exit 2; }
    base="$(realpath "$1")"
    [ -x "$base/usr/sbin/dropbear" ] && [ -x "$base/usr/libexec/sftp-server" ]
    interp=$(sed -n 's/^interpreter //p' /proc/sys/fs/binfmt_misc/qemu-aarch64)
    test -n "$interp"
    exec unshare --mount --net --pid --fork --mount-proc bash "$0" --inside "$base" "$interp"
fi
base="$2"
interp="$3"
testdir=$(mktemp -d /var/tmp/banana-ssh-test.XXXXXX)
root="$testdir/root"
mount --make-rprivate /
cleanup() {
    chroot "$root" /usr/libexec/banana/ssh down >/dev/null 2>&1 || true
    umount -R "$root" >/dev/null 2>&1 || true
    rm -rf "$testdir"
}
trap cleanup EXIT
mkdir -p "$root" "$testdir/upper" "$testdir/work"
mount -t overlay overlay -o "lowerdir=$base,upperdir=$testdir/upper,workdir=$testdir/work" "$root"
# Ubuntu's non-pinned dynamic binfmt interpreter must be visible inside chroot.
# All test-only files live in the temporary overlay, never the release root.
mkdir -p "$root$(dirname "$interp")"
cp -L "$interp" "$root$interp"
while IFS= read -r lib; do
    mkdir -p "$root$(dirname "$lib")"
    cp -L "$lib" "$root$lib"
done < <(ldd "$interp" | awk '/=> \//{print $3} /^[[:space:]]*\/.*ld-linux/{print $1}')
mount -t tmpfs -o mode=0755 tmpfs "$root/run"
mount -t tmpfs -o mode=0755 tmpfs "$root/data"
mount -t tmpfs -o mode=1777 tmpfs "$root/tmp"
mount -t proc proc "$root/proc"
mount --rbind /dev "$root/dev"
mount --make-rslave "$root/dev"
mkdir -p "$root/run/banana" "$root/data/banana/ssh"
# Reproduce the shipped read-only root; only data and /run remain writable.
mount -o remount,ro "$root"
ip link set lo up
chroot "$root" /bin/busybox true
python3 "$(dirname "$0")/ssh-sftp-test.py" "$root" "$testdir"
