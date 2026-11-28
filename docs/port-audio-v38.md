# Correct outer-PCM recovery after pause/sleep (v0.5.3.6.38)

v37 still aborts on the real handheld at pcm_plugin.c:547, now after playback underrun recovery. Its synthetic RW-only/mmap_emul fixture did not cover a native MMAP slave. Adding a real MMAP-capable ioplug reproduces the exact failure with the actual target ALSA1.2.15.3 and the v37 private library still loaded.

ALSA forwards snd_pcm_poll_descriptors_revents through plugins by calling that public symbol recursively. The previous interposer recovered an inner slave first, cleared POLLERR, and left outer conversion positions stale. Diagnostic ALSA shows outer appl_ptr128 vs slave/status appl_ptr0, with no outer plugin initialization during recovery. Recovering only the outermost call fixes that path. A rate plugin adds another case: its state can remain RUNNING while inner layers report SUSPENDED or XRUN. Preserve the nested fault observation and perform recovery on the outer handle, without modifying any nested PCM while polling.

Thread-local depth/fault state is reset for each outer poll. Original errors, capture, disconnected and normal events stay unchanged. Successful recovery emits v38 plus the resolved ALSA backend path once per audio thread. Other hooks, opt-in scope, private ALSA and supervisor remain as v37.

Regression coverage now includes real MMAP and RW-only/mmap_emul backends, S32 and F32/lfloat, asym/plug/speaker EQ with44.1->48kHz conversion, both XRUN/SUSPENDED and poll/native recovery. Start playback before the fault; refill/restart it after recovery, and require RUNNING and backend frame transfer progress. Use PREVIOUS_AUDIO_SOURCE=v37 with the same private ALSA to reproduce the old underrun assertion. Existing state/error, signal, timestamp/TLS/capture tests remain coverage.

This is a host/ARM64-QEMU reproduction and fix, not proof of physical handheld sleep/audio. Device pause/power/lid recovery still requires user testing. OTA changes only the recovery helper and version/runtime metadata; v37 private ALSA, system ALSA, GPU/SDL/daemon/kernel, UI exit confirmation and v32 FBNeo rollback remain byte-identical.
