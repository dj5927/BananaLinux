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
static _Thread_local unsigned poll_depth;
static _Thread_local int poll_fault;
static _Thread_local int recovery_noted;
static int (*next_revents)(snd_pcm_t *, struct pollfd *, unsigned, unsigned short *);
static snd_pcm_stream_t (*next_stream)(snd_pcm_t *);
static snd_pcm_state_t (*next_state)(snd_pcm_t *);
static int (*next_recover)(snd_pcm_t *, int, int);
static int (*next_prepare)(snd_pcm_t *);

static int (*next_status)(snd_pcm_t *, snd_pcm_status_t *);
static void (*next_htstamp)(const snd_pcm_status_t *, snd_htimestamp_t *);
static void (*next_trigger)(const snd_pcm_status_t *, snd_htimestamp_t *);
static _Thread_local snd_pcm_t *recovered_pcm;
static _Thread_local const snd_pcm_status_t *guard_status;
static _Thread_local int timestamp_noted;

static int before(snd_htimestamp_t a, snd_htimestamp_t b)
{
    return a.tv_sec < b.tv_sec || (a.tv_sec == b.tv_sec && a.tv_nsec < b.tv_nsec);
}

static void init(void)
{
    const char *v = getenv("BANANA_PORT_AUDIO_RECOVERY");
    enabled = v && !strcmp(v, "1");
    next_revents = dlsym(RTLD_NEXT, "snd_pcm_poll_descriptors_revents");
    next_stream = dlsym(RTLD_NEXT, "snd_pcm_stream");
    next_state = dlsym(RTLD_NEXT, "snd_pcm_state");
    next_recover = dlsym(RTLD_NEXT, "snd_pcm_recover");
    next_prepare = dlsym(RTLD_NEXT, "snd_pcm_prepare");
    next_status = dlsym(RTLD_NEXT, "snd_pcm_status");
    next_htstamp = dlsym(RTLD_NEXT, "snd_pcm_status_get_htstamp");
    next_trigger = dlsym(RTLD_NEXT, "snd_pcm_status_get_trigger_htstamp");
}

int snd_pcm_poll_descriptors_revents(snd_pcm_t *pcm, struct pollfd *pfds,
                                     unsigned count, unsigned short *events)
{
    pthread_once(&once, init);
    if (!next_revents) return -ENOSYS;
    // ALSA calls this symbol again while forwarding through conversion plugins.
    // Observe nested errors, but prepare only the outer handle. A rate plugin can
    // still report RUNNING while its slave is already XRUN or SUSPENDED.
    if (!poll_depth) poll_fault = -1;
    ++poll_depth;
    int rc = next_revents(pcm, pfds, count, events);
    --poll_depth;
    int saved_errno = errno;
    if (!enabled || rc || !events || !next_stream || !next_state ||
        !next_recover || !next_prepare || !next_status || !next_htstamp ||
        !next_trigger || next_stream(pcm) != SND_PCM_STREAM_PLAYBACK) {
        errno = saved_errno;
        return rc;
    }
    if (*events & POLLERR) {
        snd_pcm_state_t observed = next_state(pcm);
        if (observed == SND_PCM_STATE_XRUN || observed == SND_PCM_STATE_SUSPENDED)
            poll_fault = observed;
    }
    if (poll_depth || (!(*events & POLLERR) && poll_fault < 0)) {
        errno = saved_errno;
        return rc;
    }
    snd_pcm_state_t state = next_state(pcm);
    if (state != SND_PCM_STATE_XRUN && state != SND_PCM_STATE_SUSPENDED &&
        state != SND_PCM_STATE_DISCONNECTED && poll_fault >= 0)
        state = (snd_pcm_state_t)poll_fault;
    int recovered = -1;
    if (state == SND_PCM_STATE_XRUN) {
        recovered = next_recover(pcm, -EPIPE, 1);
    } else if (state == SND_PCM_STATE_SUSPENDED) {
        // Prepare the outer conversion chain, rather than resuming just a slave.
        recovered = next_prepare(pcm);
    }
    if (recovered == 0) {
        snd_pcm_state_t after = next_state(pcm);
        if (after == SND_PCM_STATE_PREPARED || after == SND_PCM_STATE_RUNNING) {
            recovered_pcm = pcm;
            timestamp_noted = 0;
            *events = POLLOUT;
            if (!recovery_noted) {
                Dl_info backend = {0};
                recovery_noted = 1;
                dladdr((void *)next_status, &backend);
                fprintf(stderr, "[banana-port-audio] outer PCM recovery v38; ALSA=%s\n",
                        backend.dli_fname ? backend.dli_fname : "unknown");
            }
            fprintf(stderr, "[banana-port-audio] recovered playback %s\n",
                    state == SND_PCM_STATE_XRUN ? "underrun" : "suspend");
        }
    }
    errno = saved_errno;
    return rc;
}

// CPAL 9d269d8 panics when current htstamp precedes the old trigger after prepare.
// Scope the guard to this thread's recovered playback PCM and its status snapshot.
// Keep normal status timestamps and every other stream unchanged.
int snd_pcm_status(snd_pcm_t *pcm, snd_pcm_status_t *status)
{
    pthread_once(&once, init);
    if (!next_status) return -ENOSYS;
    int rc = next_status(pcm, status);
    int saved_errno = errno;
    guard_status = NULL;
    if (enabled && !rc && status && pcm == recovered_pcm && next_htstamp && next_trigger) {
        snd_htimestamp_t current, trigger;
        next_htstamp(status, &current);
        next_trigger(status, &trigger);
        if (before(current, trigger)) {
            guard_status = status;
            if (!timestamp_noted++) fprintf(stderr, "[banana-port-audio] guarded recovery timestamp\n");
        } else if (next_state && next_state(pcm) == SND_PCM_STATE_RUNNING) {
            recovered_pcm = NULL;
        }
    }
    errno = saved_errno;
    return rc;
}

void snd_pcm_status_get_trigger_htstamp(const snd_pcm_status_t *status, snd_htimestamp_t *stamp)
{
    pthread_once(&once, init);
    if (!next_trigger || !stamp) return;
    next_trigger(status, stamp);
    int saved_errno = errno;
    if (enabled && status == guard_status && next_htstamp) {
        snd_htimestamp_t current;
        next_htstamp(status, &current);
        if (before(current, *stamp)) *stamp = current;
    }
    errno = saved_errno;
}

// CPAL can also recover an underrun from avail()/writei(), bypassing poll recovery.
int snd_pcm_recover(snd_pcm_t *pcm, int error, int silent)
{
    pthread_once(&once, init);
    if (!next_recover) return -ENOSYS;
    int restart = enabled && error == -ESTRPIPE && next_prepare &&
        next_stream && next_stream(pcm) == SND_PCM_STREAM_PLAYBACK;
    int rc = restart ? next_prepare(pcm) : next_recover(pcm, error, silent);
    int saved_errno = errno;
    if (enabled && !rc && (error == -EPIPE || error == -ESTRPIPE) &&
        next_stream && next_stream(pcm) == SND_PCM_STREAM_PLAYBACK) {
        recovered_pcm = pcm;
        timestamp_noted = 0;
    }
    errno = saved_errno;
    return rc;
}

int snd_pcm_prepare(snd_pcm_t *pcm)
{
    pthread_once(&once, init);
    if (!next_prepare) return -ENOSYS;
    int rc = next_prepare(pcm);
    int saved_errno = errno;
    if (enabled && !rc && next_stream && next_stream(pcm) == SND_PCM_STREAM_PLAYBACK) {
        recovered_pcm = pcm;
        timestamp_noted = 0;
    }
    errno = saved_errno;
    return rc;
}
