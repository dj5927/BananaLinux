# RPG Maker native integration checkpoint

Branch: feature/rpg-native (based on localization/ko v0.5.3.6.5, 10e70a2eb3ec6ffe04509fb05c642ca218956fef). No OTA published from this branch.

Implemented folder-based library entries for roms/mkxp and roms/easyrpg, project marker detection (XP/VX/VX Ace/2000/2003), per-project ID and options, native BananaFront launch only, project-scoped frontend saves/states/screenshots, RPG assets directories, Korean UI labels. BananaFront patch 0002 adds independent A/B and X/Y swaps, per-project core options, scaling override and EasyRPG native-save hints. Patch 0003 adds an experimental MKXP-only GLES2 offscreen framebuffer/readback bridge; not yet validated with a real MKXP core or device GPU.

Verified:
- ARM64 UI build and scanner unit test.
- RG DS and Plus headless UI tests: both shelves, folder titles, X options, persisted config, correct project entry launch event.
- EasyRPG Player 0.8.1.1 (409a0bff37f0049f93286ee2019d851301eb7506), liblcf 0.8.1 (016847fb32496c167eba6b2494e7f7867c87b339), ARM64 source build, both BananaFront ARM64 variants built. TestGame 2000/2003 on both board firmware roots: 4/4 native launch, frames, Korean pause menu, resume, exit. Test-only additional shared libraries; final packaging and complete audio/font/RTP validation pending.
- Host Mesa GLES2 synthetic test: framebuffer, context callbacks, XRGB readback passed. Not an MKXP game test.
- Plus old extracted QA tree was damaged; fresh extraction from existing OTA verified all internal hashes and normal ELF loader, used for successful retests. Existing OTA unchanged.

MKXP libretro white-axe commit 650cb0888a07d0b5044e131160ddfa53feaf595b; SDK WASI 30 and Binaryen 123 installed under D work dir. Stage 1 compiled dependencies and entered Ruby configure, then stopped at checkpoint (not a completed core). Stage 2 not run. No background task left intentionally. Resume stage 1 after checking generated build state; actual core integration tests, graphics performance, game-specific settings and legacy Ruby compatibility, lower panel save capability/UI titles and runtime packaging remain. Do not release until real XP, VX and VX Ace tests and both firmware images pass.

Host working data: D:\BananaOS-RPG-Work\ (sources, sdk, build, logs, screenshots). Existing .ko-work build/test scripts copied to work directory. Existing production version and releases unchanged.
