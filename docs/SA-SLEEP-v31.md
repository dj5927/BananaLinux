# BananaOS Korean v0.5.3.6.31 - Standalone sleep kernel compatibility fix (test prerelease)

- Fix the v30 regression where MKXP, PPSSPP, DuckStation and Flycast can keep game/audio running after both displays go dark.
- The RG DS kernel configuration disables CONFIG_PROC_CHILDREN. v30 relied on optional /proc/PID/task/TID/children files and silently skipped descendants when missing. v31 discovers children through each process's PPid in /proc/PID/stat, which does not require that optional feature.
- Wait for every game/audio/render thread to stop, including engines in independent sessions and children forked from a non-main thread. Preserve existing paused tasks and resume only tasks stopped by sleep. Log stopped PIDs and states in banana/logs/sleep.log.
- Existing lid/power system-suspend and wake behavior, charger handling and suspend-error fallback are retained. No kernel replacement or emulator binary changes.
- PortMaster GPU-selection work is paused as requested. UI, all four native engines, driver/runtime libraries and v30 DuckStation 2x speed cap remain unchanged.

Validation: reproduce the old failure with optional children files unavailable, verify corrected game/audio/render counters stop and resume in four launcher layouts, and run the complete power/SA regressions with those files forced absent. All 165 power regressions and 17 SA regressions passed with children files unavailable. These are process-control simulations; actual handheld deep suspend and GPU/audio wake still need on-device acceptance.