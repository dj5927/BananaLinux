#include <alsa/asoundlib.h>
#include <errno.h>
#include <poll.h>
#include <time.h>
static int state, stream, result, recovery, resume_rc, prepare_rc, flags, calls;
static double last;
static int timed;
static double now(void) { struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9; }
void fixture(int s,int dir,int rc,int recover,int resume,int prepare,int ev) {
 state=s;stream=dir;result=rc;recovery=recover;resume_rc=resume;prepare_rc=prepare;flags=ev;calls=0;
}
int recovered_calls(void) { return calls; }
void timed_fixture(void) { timed=1;state=SND_PCM_STATE_RUNNING;stream=0;last=now(); }
int snd_pcm_poll_descriptors_revents(snd_pcm_t *p,struct pollfd *fds,unsigned n,unsigned short *ev) {
 (void)p;(void)fds;(void)n;
 if(timed) { double t=now();if(t-last>.15)state=SND_PCM_STATE_XRUN;last=t;flags=state==SND_PCM_STATE_XRUN?POLLERR:POLLOUT; }
 if(ev)*ev=flags;errno=EDOM;return result;
}
snd_pcm_stream_t snd_pcm_stream(snd_pcm_t *p) { (void)p;return stream; }
snd_pcm_state_t snd_pcm_state(snd_pcm_t *p) { (void)p;return state; }
int snd_pcm_recover(snd_pcm_t *p,int err,int silent) {
 (void)p;(void)silent;if(err!=-EPIPE)return -EINVAL;calls++;
 if(!recovery)state=SND_PCM_STATE_PREPARED;errno=EINVAL;return recovery;
}
int snd_pcm_resume(snd_pcm_t *p) { (void)p;calls++;if(!resume_rc)state=SND_PCM_STATE_RUNNING;return resume_rc; }
int snd_pcm_prepare(snd_pcm_t *p) { (void)p;calls++;if(!prepare_rc)state=SND_PCM_STATE_PREPARED;return prepare_rc; }

static snd_htimestamp_t fixture_now = { 2, 0 }, fixture_trigger = { 1, 0 };
void fixture_timestamps(long now_sec,long trigger_sec) { fixture_now.tv_sec=now_sec; fixture_trigger.tv_sec=trigger_sec; }
int snd_pcm_status(snd_pcm_t *pcm,snd_pcm_status_t *status) { (void)pcm;(void)status;return 0; }
void snd_pcm_status_get_htstamp(const snd_pcm_status_t *status,snd_htimestamp_t *stamp) { (void)status;*stamp=fixture_now;if(timed && state==SND_PCM_STATE_PREPARED)stamp->tv_sec=0; }
void snd_pcm_status_get_trigger_htstamp(const snd_pcm_status_t *status,snd_htimestamp_t *stamp) { (void)status;*stamp=fixture_trigger;if(timed && state==SND_PCM_STATE_PREPARED)stamp->tv_sec=100; }
