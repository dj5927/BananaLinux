BananaOS v0.5.3.6.29 native SA source
=====================================
The complete source is supplied as the two pinned, previously published
complete source archives listed in baseline.json plus this source overlay.
Download the exact archives from their listed URLs, verify SHA256, extract
both into one clean directory, and run:
  python3 apply-overlay.py /path/to/extracted
The script validates every original source file before applying the modified
files. This reconstructs the v29 native control and speed source. The base archives
include their engine source licenses and build recipes. The new build-native
script uses the same target SDK and prior CMake configurations; adjust the
workspace paths for another host. v24 font generation sources are unchanged
and remain at the v24 release. Only presentation backpressure changes during fast-forward; no Mali driver, audio, BIOS or font changes.
