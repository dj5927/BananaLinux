# eMMC installation (experimental)

Based on v0.5.3.6.40. RG DS and RG DS Plus only.

The compiled firmware DTBs enable the non-removable 8-bit eMMC controller.
The shipped Rockchip loader contains SD then eMMC SPL boot order and
`boot_targets=mmc1 mmc0 ...`. No loader/DTB changes are needed for this candidate.
Software tests do not prove physical eMMC startup or every controller timing.

## Use

1. Boot this version from a BananaOS SD card. Save anything needed from internal
   storage elsewhere before starting. Installation erases the existing internal
   operating system and all its files. Automatic recovery metadata is only a
   boot-area/GPT backup, not a full backup of the old internal contents.
2. Settings > System > Install to eMMC. Read the warning and confirm twice.
3. Wait for completion. Shut down. Remove the BananaOS boot SD, insert a FAT32 or
   exFAT data SD, and power on. Do not leave the BananaOS boot SD inserted when
   testing internal boot, because the loader tries that SD first.
4. Missing folders are created without formatting the SD. Place games in
   `roms/<system>` and BIOS files in `bios/`. BIOS files are not distributed.

Settings, accounts, emulator options and downloaded emulator runtimes stay on
eMMC. The selected SD supplies `roms`, `bios`, `saves`, `states`, `screenshots`
and `store`. Native DraStic, DuckStation, PSP and Dreamcast save paths are mapped
to these SD folders; their configuration files remain internal. Legacy native
data on the same SD is copied into the standard locations only where files are
missing. Existing destination files win. Per-game custom absolute paths in an
emulator's own configuration retain their existing meaning.

FAT/exFAT mounts grant root read/write/execute access and use UTF-8 names. exFAT
is needed for individual files larger than FAT32's 4 GiB limit. The RG DS Plus
uses the first detected non-system SD. Change cards with the handheld shut down.
Live insertion is detected and the game library is rescanned; removal during
gameplay cannot preserve files that were still being written.

The installer discovers one internal MMC device; the CLI accepts no target
path. It rejects mounted, read-only or busy internal storage, a non-SD source,
unavailable source mounts and unknown partition layouts. It backs up boot/GPT
metadata, creates fresh partition UUIDs, copies the loader and both system slots,
reads those bytes back for SHA-256 verification, copies internal settings, and
rewrites extlinux roots to the new UUIDs. The running root partition identifies
slot A/B even after switching from PARTLABEL to PARTUUID. OTA continues to write
the inactive slot on the system disk and preserves UUID arguments and settings.
eMMC hardware boot partitions and their enablement are not modified.

The copied inactive SD slot may hold older firmware that does not identify
PARTUUID roots correctly. Its boot kernel is invalidated on the eMMC copy;
the first subsequent OTA populates that slot safely. Previous version is
therefore unavailable immediately after installation. The original SD slots
and their kernels are retained unchanged.

## Validation boundaries

Tests use sparse loop disks rather than real hardware: GPT/bootloader/root
copy, readback, UUID uniqueness, extlinux A/B selection, settings preservation,
FAT32/exFAT folder creation and native save routing. The actual packaged ARM64
Python imports and boot configuration logic are also tested. Physical boot,
power interruption and the user's current eMMC boot-selection state still need
device verification. Until then this is a prerelease, and stable v40 remains
available.


## v42 consent screens

Installation now has two distinct modal warning screens. The first explains
full internal-storage erasure, installation/power-loss risks, backup and user
responsibility for all problems. The second repeats user responsibility,
including data loss, boot failure and recovery costs, and explicitly asks for
final installation consent. Both screens default to Cancel. Select Agree and
confirm separately on each screen; B cancels before installation begins.
A repeated from the first screen cannot accept the second screen's default.
The wording is a product warning; no legal-enforceability claim is made.
