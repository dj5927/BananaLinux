# Standalone RPG integration checkpoint (2026-11-27)

Feature branch: feature/rpg-native, based on production 10e70a2 (v0.5.3.6.5).
Decision: both MKXP and EasyRPG must be standalone (SA). Existing BananaFront and RetroArch stay as they are. The previous experimental RPG-only Libretro patches are removed from this branch, not from the earlier history.

Implemented:
- Folder-based XP/VX/VX Ace and EasyRPG project scan; native run-rpg launcher; separate per-game configuration directories. Original game files and native in-game saves remain in their own game folders.
- EasyRPG SA: Player 0.8.1.1 source 409a0bff37f0049f93286ee2019d851301eb7506, liblcf 0.8.1 016847fb32496c167eba6b2494e7f7867c87b339, SDL2, FreeType, HarfBuzz, FluidSynth. ARM64 cross build and patched rebuild succeeded.
- MKXP SA: existing D:/GPT/MKXP/_dev/mkxp-z-upstream HEAD b47047e10211821634a6a61ec4ff298c9a480a8b plus its local compatibility changes; mkxp-z 2.4.2, Ruby 3.2, GLES. ARM64 cross build and patched rebuild succeeded. Fix SDL2_ttf struct-tag detection in local build (resume-mkxp-sa.sh).
- Game-specific font1/font2, pixel sizes, encoding, scaling, SoundFont for EasyRPG; RGSS version, scaling, SoundFont and portable RTP/Ruby paths for MKXP. File choices scan shared BIOS folders. Configuration changes in the lower panel apply on next launch, not live reload.
- Dedicated lower panel with per-engine options, pause/resume, restart/quit confirmation, no unsupported Libretro state slots or RA display. Native engine command FIFO reader and engine-specific adapters. ARM64 banana-ui rebuilt successfully.
- Private SDL2 2.32.10 inherited DRM lease patch (system/rpg/patches/sdl2-native-drm-lease.patch), built with KMSDRM and GLES2. Do not install as global SDL replacement; private standalone runtime only.

Verified:
- Both ARM64 SA engine executables compiled, loader dependency lists resolved against Ubuntu ARM64 cross environment. Not yet an exact firmware-runtime dependency test.
- ARM64 UI build and prior five-project scanner test passed; translation check passed (2888 records).
- Launcher argument test: isolated keys, font/SoundFont paths containing spaces, encoding/size/scaling and MKXP RGSS override.
- EasyRPG 2000 and 2003 official test projects launched in QEMU ARM64 with SDL dummy video/audio and accepted FIFO quit. Pause/resume/reset commands were sent; frame-level pause and actual MIDI/font rendering quality have not been independently validated.
- MKXP XP synthetic project: GLES Mesa initialization, path cache succeeded. First failure: Ruby load path cleared by binding, zlib LoadError; addressed with existing MKXP_PORTABLE_RUBY_LOADPATH hook. Retest no zlib error, but script heartbeat still timed out. Do not mark XP/VX/VX Ace execution passed.
- SDL lease compilation and KMSDRM/GLES2 generated macros confirmed. No physical DRM lease/dual-panel test yet.

Remaining release blockers:
- Diagnose MKXP script startup; test synthetic and real XP/VX/VX Ace projects, legacy Ruby 1.8/1.9 compatibility, controller remapping, native pause/quit/reset and actual MIDI/font output.
- Test native bottom panel rendering and commands end-to-end on both board firmware roots and physical devices, touch routing, game display lease, audio and suspend/resume. If lease is unavailable, prevent unsafe/unsupported dual-panel launch.
- Complete private runtime packaging with target-compatible dependencies, Ruby stdlib/extensions, license/source and build recipes; fit partition or use verified data partition installer. Verify all existing games/OTA regressions. No OTA published.
- Work files: D:/BananaOS-RPG-Work/build, logs, sources, test, sdk, work. Standalone binaries and SDL library are development artifacts, not installable release.
