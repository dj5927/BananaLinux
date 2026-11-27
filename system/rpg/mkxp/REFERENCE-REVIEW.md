# 053615 MKXP reference review (2026-11-27)

Reviewed immutable GitHub tree revisions:
- https://github.com/Orochimarufan/Kawariki/tree/bb5ea9a79d5ca358c6f6bb8b3c31524beb29c7b4/mkxp
- https://github.com/bakustarver/rpgmakermlinux-cicpoffs/tree/5af2721de47ce874073e8fa719dba6c1acd88bed/Kawariki-patches

Inspected Kawariki README, runtime.py, preload.rb, patches.rb, Win32API.rb, ruby18.rb, XP_TilemapOverrideLib.rb, CRDJ_Input.rb; cicpoffs README, patches.rb, AppImage/mkxpz/AppRun, editscripts.sh. cicpoffs extends Kawariki's patch catalogue; these are not independent engine optimizations.

Adopted narrow in-memory MOG visible boolean, Galv font shadow boolean, CAO frozen string copy, independently adapted with literal signature/line checks, diagnostics, and opt-out. Opt-in font effects reduction uses native Font setters; no performance claim without physical benchmark. Existing four Ruby runtimes, filesystem and Win32 layer remain. Native MKXP controller remapper is present in all four builds (keybindings.cpp); per-action mappings exposed as global and per-game choices, launch passes a per-game text file. Supported physical controls are A/B/X/Y/L1/R1/L3/R3; directional keys, keyboard, F shortcuts retained. Shared assignments allowed; no full keyboard/trigger remapper. Existing engine-specific native saved bindings can affect remap results. No direct game file edits. Raw Win32 key handling (e.g. Senia) remains separate.

Not adopted wholesale: Zeus fullscreen ports (KMS lease must stay owned by BananaOS), CRDJ/Glitchfinder/custom mouse scripts (plugin signatures, physical controller semantics, license and individual game verification needed), XP large tileset workaround (explicitly incurs extra work, only older Pokemon Essentials custom tilemaps; validate GL limits), broad Ruby method-list wrappers (actual legacy runtimes already present; modern wrappers may change behavior), INI read/write emulation (needs byte semantics and save path tests), wide script removal, Steam or subscription bypass, Windows native DLL stubs, PC AppImage/X11/NW.js tools. Further candidate-specific testing rather than generic blanket patches.

Do not infer FPS gains from PC-side tests. Actual handheld input and performance need device verification.
