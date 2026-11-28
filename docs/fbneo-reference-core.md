# FBNeo reference-core A/B (v0.5.3.6.34)

Baseline: published v0.5.3.6.32. The user reported VF around10fps versus ROCKNIX around57fps. Selecting RetroArch instead of BananaFront did not improve it; the frontend-only hypothesis is not supported.

This test firmware installs the ARM64 binary from aleksei74/FBNeo Actions run46100403051, commit36a8fe5c865f6e1e89fcb0820035b872269b83cd. Upstream ran `make -C src/burner/libretro platform=unix REGEN_HEADERS=1` on Ubuntu22.04 ARM with GCC11.4. Our previous core was built with Buildroot GCC14.3. The binary is stripped only; allocated ELF sections are checked byte-for-byte. See `/usr/share/banana/fbneo/reference-core.json` for hashes and provenance.

The Buildroot source pin and source archive/license hashes track this commit. Rebuilding with the firmware toolchain does not reproduce the CI compiler; the packaged test binary is the exact CI artifact with symbols stripped. Its source archive is retained alongside the test build.

No CPU governor, frontend, core option, shader, save, kernel, daemon, GPU or sleep changes. Unpublished v33 PortMaster audio recovery is excluded so the A/B remains scoped to FBNeo.

Checks: compare old/new rootfs file trees allowing only FBNeo/provenance and firmware metadata changes, verify protected payloads, core ARM64 loader and API, OTA checksum and updater simulation on both boards. No ROM or physical-device FPS test was performed. Compare the same ROM, scene, frontend and settings; do not reset options during the core A/B. Source defaults are not evidence of the user's active options. If unchanged, collect actual core options (including Model1 Resolution), runtime CPU clocks and frame timings before another change.
