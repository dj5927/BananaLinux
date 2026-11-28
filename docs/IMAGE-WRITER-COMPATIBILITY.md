# Image writer compatibility investigation

User report: Rufus-written cards fail to start while Raspberry Pi Imager 1.9.6
works. No failed card dump or Rufus log has yet been supplied; the exact failure
and a confirmed hardware fix are not established.

Inspected primary sources: pbatard/rufus src/format.c (WriteDrive and
FormatThread cleanup) and raspberrypi/rpi-imager v1.9.6 src/downloadthread.cpp.
Rufus writes a DD image sequentially then refreshes layout and explicitly
remounts the first supported non-ESP filesystem. Imager saves the first 4 KiB
until the end of writing/verification and ejects when enabled. Thus their
interaction with Windows automount differs even when the image payload agrees.

Previous Banana images marked the firmware FAT partition Microsoft Basic Data,
which makes it a candidate for Rufus's final remount. The v41 full-image
candidate instead marks it EFI System Partition and sets GPT no-automount (bit
63), retaining the legacy bootable attribute, all partition offsets, partition
UUIDs, Rockchip loader bytes and firmware contents. Genimage's source recipe and
the incremental image builder both produce this metadata. U-Boot loads extlinux
from the same FAT partition; this does not introduce a PC EFI boot requirement.

This is an image compatibility hardening, not proof that Windows automount was
the reported cause. Both new GPT copies and their CRCs are checked, and the
loader and filesystem payload are compared independently. Existing OTA cards
keep their original disk metadata; this change applies to newly written full
images. Physical Rufus and Imager A/B boot tests are still needed.

For diagnosis, keep the Rufus log and run tools/writer-card-check.ps1 immediately
after writing, before the card's first handheld boot. It reads only the selected
non-system removable disk and compares its MBR/GPT/loader and boot filesystem
against the chosen raw image. A result from a working Imager-written card with
the same image/card/reader is useful to distinguish actual changed bytes from
partition-table repairs or device/flush issues.
