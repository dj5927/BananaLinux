# PortMaster per-game GPU selection (0.5.3.6.32)

In the port library, press X to open This game settings. Graphics driver offers Default (Panfrost), Panfrost and Mali. The saved choice applies on the next launch and is independent for each game. PortMaster itself always runs on Panfrost. Target: 64-bit ARM ports, no 32-bit compatibility runtime.

The UI stores UTF-8 game-key hex + `.gpu_driver` in `/data/banana/rpg-per-game.conf`. The supervisor reads the same game key, takes the existing GPU transaction lock, then uses the pinned EasyEmu Mali kernel/runtime transaction. Only EGL/GLES/GBM/Vulkan dependencies are exposed through a private `/run/banana/port-mali-*` directory. The dedicated ports SDL retains priority; EasyPSP SDL is not injected. The PortMaster OS hook reapplies this scoped path during common setup.

The supervisor is a child subreaper. Pause, restart, quit and termination scan PPid in proc stat (no CONFIG_PROC_CHILDREN dependency), use identity-checked pidfds, adopt detached helpers and finish cleanup before unloading Mali. Panfrost restoration is checked and retried. Cleanup refuses conflicting GPU module changes if a process remains active. Logs: `/data/banana/logs/ports/last-log-path.txt` points to the latest game log.

Validation: native Linux synthetic lifecycle tests, ARM64 target Python config/library/rollback tests, real headless X-button settings persistence for RG DS and Plus, package integrity and offline updater verification. The Mali module commands in these tests are simulated; individual port rendering must be tested on the device. Games with their own graphics library path overrides may need port-specific changes. Kernel, DTB, power daemon and native emulator binaries are copied unchanged from v31. Keep the v31 sleep behavior.
