# RPG SA fixes - 0.5.3.6.7

Base: 0.5.3.6.6, feature/rpg-native. Both engines remain standalone.

## Changes
- EasyRPG library detects ZIP and .easyrpg files (case insensitive) as individual games. Native archive filesystem is used, no extraction. Handles root projects and a unique nested project; saves in a separate archive-name.save folder. Save folders excluded from library scan.
- MKXP automatic aspect-preserving filtered fit, true integer mode without fractional last mile, safe fit fallback for oversized games, guard zero/invalid dimensions and initialize scale framebuffer to 1x. Retains original RGSS game resolution.
- MKXP default hinted font, optional original RGSS hinting, fallback font chosen from bios/mkxp/fonts, size adjustment. Existing game fonts not replaced. Invalid fallback file falls back to bundled font. Safer shader-based blits and sub-image compatibility by default, native blitting optional.
- Changed options persist; Apply / restart gracefully re-executes run-rpg in the same process and rereads settings. No Libretro. Both engines retain native reset when launched without the Banana launcher.
- Per-game last-run.log and previous-run.log, /data/banana/logs/rpg-last-log-path.txt identifies most recent session. Resolved MKXP config logged; RGSS errors logged and nonzero exit in native mode instead of attempting an unavailable desktop error box.

## Software QA
- EasyRPG official 2000/2003 projects in uppercase ZIP and nested .easyrpg archives tested on both isolated 0.5.3.6.6 firmware roots; launch, pause/resume/quit and unchanged ZIP checksums passed 4/4.
- Both ARM64 UI sizes: ZIP list/launch, MKXP option touch persistence and restart action passed. Korean dictionary format check (2899 entries) passed. Launcher archive/save paths and log path test passed.
- MKXP synthetic RGSS 1/2/3 menu tests: window and bitmap creation, font metrics and draw_text, alpha stretch/blit, freeze/transition, supported snapshots, repeated disposal, pause/resume/reset/quit. XP and Ace passed together; VX first run reached menu 30 then software renderer test timeout; VX single retest passed all five cycles and controls. Host Ubuntu ARM64 QEMU Mesa offscreen, not physical RK3568.
- Real same-PID re-exec through the launcher: EasyRPG passed, MKXP second-launch resolved config log changed from smooth, font-scale 0.9 to integer, font-scale 1.2. Final second-launch frame/exit check recorded separately.
- Both OTA packages built from verified 0.5.3.6.6 tar/rootfs, target ELF loader checks and checksums passed. Existing global SDL, BananaFront, RetroArch, FBNeo, SSH, Activity, Store and updater compared byte-for-byte. RG DS 219146240 bytes SHA256 3c76fd232d6257dd625091808dc9bd7b1c0e40244085d332bb1c2147faabcda8; Plus 219248640 bytes SHA256 7b82a70ed7833fd8f42da22f40e2850701601a9b318af5d0335211d2714b5573.

## Limitations
Actual reported MKXP game, script, physical GPU/display and font appearance unavailable. The menu crash has not been reproduced with that exact game; compatibility improvements and regression tests do not establish that every game crash is fixed. Ruby 3.2.3 remains; legacy Ruby and Windows-only scripts still may fail. Options take effect when applying/restarting (unsaved progress lost), not live. No commercial games/RTP in release. If crash remains, collect the most recent run log and game name/engine. Work records under D:/BananaOS-RPG-Work; release under D:/BananaOS-Korean-0.5.3.6.7.
