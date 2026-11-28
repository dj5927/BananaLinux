// SPDX-License-Identifier: MIT
// CPAL 9d269d8 ignores POLLERR before reaching its underrun recovery.
// Recover in the owning audio thread, only for opted-in playback clients.
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <dlfcn.h>
#include <errno.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static pthread_once_t once = PTHREAD_ONCE_INIT;
static int enabled;
static int (*next_revents)(snd_pcm_t *, struct pollfd *, unsigned, unsigned short *);
static snd_pcm_stream_t (*next_stream)(snd_pcm_t *);
static snd_pcm_state_t (*next_state)(snd_pcm_t *);
static int (*next_recover)(snd_pcm_t *, int, int);
static int (*next_resume)(snd_pcm_t *);
static int (*next_prepare)(snd_pcm_t *);

static void init(void)
{
    const char *v = getenv("BANANA_PORT_AUDIO_RECOVERY");
    enabled = v && !strcmp(v, "1");
    next_revents = dlsym(RTLD_NEXT, "snd_pcm_poll_descriptors_revents");
    next_stream = dlsym(RTLD_NEXT, "snd_pcm_stream");
    next_state = dlsym(RTLD_NEXT, "snd_pcm_state");
    next_recover = dlsym(RTLD_NEXT, "snd_pcm_recover");
    next_resume = dlsym(RTLD_NEXT, "snd_pcm_resume");
    next_prepare = dlsym(RTLD_NEXT, "snd_pcm_prepare");
}

int snd_pcm_poll_descriptors_revents(snd_pcm_t *pcm, struct pollfd *pfds,
                                     unsigned count, unsigned short *events)
{
    pthread_once(&once, init);
    if (!next_revents) return -ENOSYS;
    int rc = next_revents(pcm, pfds, count, events);
    int saved_errno = errno;
    if (!enabled || rc || !events || !(*events & POLLERR) ||
        !next_stream || !next_state || !next_recover || !next_resume || !next_prepare ||
        next_stream(pcm) != SND_PCM_STREAM_PLAYBACK) return rc;
    snd_pcm_state_t state = next_state(pcm);
    int recovered = -1;
    if (state == SND_PCM_STATE_XRUN) {
        recovered = next_recover(pcm, -EPIPE, 1);
    } else if (state == SND_PCM_STATE_SUSPENDED) {
        // One bounded attempt; do not block the audio thread in a resume retry loop.
        recovered = next_resume(pcm);
        if (recovered < 0 && recovered != -EAGAIN) recovered = next_prepare(pcm);
    }
    if (recovered == 0) {
        snd_pcm_state_t after = next_state(pcm);
        if (after == SND_PCM_STATE_PREPARED || after == SND_PCM_STATE_RUNNING) {
            *events = POLLOUT;
            fprintf(stderr, "[banana-port-audio] recovered playback %s\n",
                    state == SND_PCM_STATE_XRUN ? "underrun" : "suspend");
        }
    }
    errno = saved_errno;
    return rc;
}
