# Whole-card SD formatting (v44 experimental)

Boot BananaOS from internal eMMC with the boot SD removed, then insert the SD
to reset. Settings > System > Format SD card offers FAT32 and exFAT. exFAT is
the default and permits individual files larger than 4 GiB. Each of two warning
screens defaults to Cancel and requires separate explicit agreement.

This removes EVERY existing SD partition, including an old OS, and resets MBR,
primary/backup GPT and the Rockchip loader area. A single MBR data partition uses
the entire usable card (starting at 1 MiB); formatting creates ROM, BIOS, save,
state, screenshot and store folders and reconnects internal native-emulator
paths to SD data. This is a quick format, not a secure overwrite of every sector.

The helper accepts no caller-supplied disk path. It checks that both running
root and settings belong to the internal MMC, identifies exactly one removable
SD, records CID/device/diskseq/capacity of both disks, and rechecks before writes.
Multiple SDs, system SD boot, read-only cards, external mounts, holders, active
swap and enabled file sharing block formatting. Removal/replacement after the
preview and expired confirmation tokens also block it. Normal unmount must
succeed; no lazy/forced unmount is used. SD scanning and OTA/eMMC writes are
serialized with formatting. Failed preparation can leave media detached until
the menu is closed and the scanner reattaches it.

Tests use disposable loop disks with four old GPT partitions, check one new
full-capacity partition, erased loader/GPT markers, both actual ARM64 formatters,
folder creation, UTF-8 filenames, sync and remount readback. Preflight fixtures
run natively and in the packaged ARM64 Python. Headless ARM64 UI fixtures cover
filesystem selection, both default-cancel warnings, repeated A, cancellation,
blocked probes and one execution per completed consent sequence at both sizes.
Physical cards, power interruption and physical eMMC boot remain unverified.
NTFS formatting/support is not included.
