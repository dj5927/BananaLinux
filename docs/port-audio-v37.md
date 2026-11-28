# Doukutsu-rs pause/resume audio crash (v0.5.3.6.37)

The supplied hardware log identifies SIGABRT at ALSA 1.2.15.3 pcm_plugin.c:547, after playback suspend recovery. The v36 timestamp guard runs after real snd_pcm_status and cannot prevent this internal assertion. The earlier timestamp model was insufficient evidence for the hardware crash.

A real linear -> mmap_emul -> RW-only ioplug chain reproduces the same assertion, including the exact target library and source line under ARM64 QEMU. A one-shot failed slave write leaves plugin application positions inconsistent. Whole-PCM prepare alone passes host ALSA1.2.11 but does not eliminate the target-library reproducer. Do not weaken or remove the assertion.

Ship a private ALSA1.2.15.3 with upstream PR541 (head665b61baa76055e999046df51e59b0fe2da34826) correcting mmap_emul playback status to report its own application position, delay and available frames. The system library stays unchanged. Only official Doukutsu-rs.sh with BANANA_PORT_AUDIO_RECOVERY=1 receives absolute LD_PRELOAD entries: recovery helper, private ALSA, then existing preloads. This survives a port replacing LD_LIBRARY_PATH and preserves Mali/gl4es selection. Explicit0 and other ports are unchanged.

Suspended playback now prepares the outer PCM (including native recover(-ESTRPIPE)) rather than only resuming its slave. Timestamp protection, XRUN/error/capture behavior remain scoped to opted-in playback. No audio calls occur in signal handlers. Preparing drops stale queued samples and lets the game refill audio.

Validation: port-audio-real-alsa-test.py uses real ALSA status/plugin operations, three recovery/write/status cycles per poll/native recovery path. PREVIOUS_AUDIO_SOURCE reproduces the old SIGABRT; ALSA_PRELOAD selects the private implementation for positive tests. Existing state/error, thread/PCM/capture/timestamp and signal fixtures remain regression coverage, not hardware tests. Both speaker EQ and conversion paths must be tested on the target ABI. Device sleep/lid/audio still require the user's physical update test.

Source: buildroot/package/banana-port-alsa (version/hash/patch/build recipe); release source archive includes the pristine upstream tarball, patch and build instructions. Private library LGPL2.1+, license installed under /usr/share/licenses/banana-port-alsa. UI exit confirmation and v32 FBNeo rollback are unchanged.
