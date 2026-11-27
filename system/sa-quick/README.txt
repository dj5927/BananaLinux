BananaOS v0.5.3.6.30 native SA source
=====================================
The complete source is supplied as the two pinned, previously published
complete source archives listed in baseline.json plus this source overlay.
Download the exact archives from their listed URLs, verify SHA256, extract
both into one clean directory, and run:
  python3 apply-overlay.py /path/to/extracted
The script validates every original source file before applying the modified
files. This reconstructs the v30 native control and speed source. The base archives
include their engine source licenses and build recipes. The new build-native
script uses the same target SDK and prior CMake configurations; adjust the
workspace paths for another host. v24 font generation sources are unchanged
and remain at the v24 release. Includes the v29 presentation patches and v30 200% fast-forward/turbo cap. No Mali driver, audio, BIOS or font changes. Frontend and power-daemon sources (including sleep-tree.h) are in the matching BananaLinux source commit.
