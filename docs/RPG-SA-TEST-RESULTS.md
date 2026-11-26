# RPG SA integration - 0.5.3.6.6 local test candidate

Date: 2026-11-27. Base production firmware: 0.5.3.6.5 (10e70a2).
Branch: feature/rpg-native. Both RPG engines are standalone; prior experimental Libretro changes were removed. No public GitHub release or OTA feed change.

## Changes
- MKXP native mkxp-z 2.4.2 (Ruby 3.2.3) and EasyRPG Player 0.8.1.1 SDL2, independent process and bottom menu. Separate private SDL2 DRM lease and FluidSynth runtime. Existing global SDL, BananaFront, RetroArch, FBNeo, SSH and updater left unchanged.
- Native RGSS pause keeps GL context on its own thread; detach GL and AL on RGSS thread before cleanup. This resolved observed QEMU shutdown crashes after pause/reset.
- EasyRPG supports game-specific font1/font2 sizes, SoundFont, encoding and scaling; MKXP supports RGSS override, scale and SoundFont. Changes apply on next launch. Shared default TimGM6mb SF2, private libraries and Ruby extensions included. In-game saves remain in game folders. No proprietary RTP or game assets included.
- Abort native launch if the required DRM lease/control FIFO is unavailable rather than taking both displays. Existing RetroArch companions bypassed for standalone systems.

## Verified
- RGSS synthetic XP, VX, VX Ace archives: actual Ruby script + graphics frames, paused frame counter, resume, reset, clean quit (3/3 after lifecycle fix; QEMU with Ubuntu ARM64 Mesa offscreen, not device GPU).
- Both real existing firmware roots isolated with static QEMU: exact private runtime loader dependencies resolved. EasyRPG official 2000/2003 test projects loaded and acknowledged pause, resume, reset, quit (4/4; SDL dummy video/audio).
- Both firmware roots: actual FluidSynth SF2 synthesis nonzero, FreeType font rasterization passed.
- Both screen resolutions: native UI screenshot/tap test, isolated per-game option persistence, pause/reset/quit actions, Korean translation check and folder scanner. Launcher argument test passed including paths with spaces.
- Both 0.5.3.6.6 development update tar archives: base and new inner hashes, exact installed ELF/launcher, outer hashes and updater list recognition passed. Rootfs sizes: RG DS 208588800 bytes; Plus 208699392 bytes, each below 268435456-byte slot. Existing global SDL, frontends, FBNeo, activity, store, SSH, update and launch scripts compared byte-for-byte with 0.5.3.6.5. Test executables and test games excluded.
- RG DS update tar: 219136000 bytes, SHA256 ac9711be41186421bc0fde372a78d7a989438920b00f636e05e67132120dd0c1.
- Plus update tar: 219238400 bytes, SHA256 60b36e261fae28d493cf71c97326688fb64116b462748b74569a73a5db93916c.

## Delivery and blockers
Local development candidate only: D:/BananaOS-Korean-0.5.3.6.6-test/ota-artifacts. Copy only the matching board update.tar to banana/updates/ on the data card and select it in Settings > System > Updates. Do not use a mismatched board. Retain previous A/B slot.
Physical RK3568/Mali DRM lease, display, controller, touch, audio and sleep/wake tests have not been performed; no actual device IP/session available. Do not label stable or 100% device-verified. Legacy Ruby 1.8/1.9 and arbitrary commercial/third-party game compatibility remain unverified; current MKXP binary is Ruby 3.2.3, RGSS versions 1-3. Standard game folders with Game.ini and valid scripts are the verified path. The test package is not published to the public update feed.
Exact source archive, library versions, build recipes and hashes saved under D:/BananaOS-Korean-0.5.3.6.6-test/source-provenance. Work logs and screenshots under D:/BananaOS-RPG-Work. Preserve all patches and complete corresponding-source obligations before publishing binaries publicly.
