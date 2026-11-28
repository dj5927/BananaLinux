#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <alsa/pcm_external.h>
#include <alsa/pcm_ioplug.h>
#include <errno.h>
#include <poll.h>
#include <stdlib.h>
#include <sys/eventfd.h>
#include <unistd.h>
typedef struct {snd_pcm_ioplug_t io;snd_pcm_uframes_t position;int fail;} Fault;
static Fault *active;
static int start(snd_pcm_ioplug_t *io){(void)io;return 0;}
static int stop(snd_pcm_ioplug_t *io){(void)io;return 0;}
static snd_pcm_sframes_t pointer(snd_pcm_ioplug_t *io){Fault *f=io->private_data;return f->position%io->buffer_size;}
static snd_pcm_sframes_t transfer(snd_pcm_ioplug_t *io,const snd_pcm_channel_area_t *a,snd_pcm_uframes_t off,snd_pcm_uframes_t size){
 (void)a;(void)off;Fault *f=io->private_data;
 if(f->fail){f->fail=0;snd_pcm_ioplug_set_state(io,SND_PCM_STATE_XRUN);return -EPIPE;}
 f->position+=size;return size;
}
static int prepare(snd_pcm_ioplug_t *io){Fault *f=io->private_data;f->position=0;return 0;}
static int resume(snd_pcm_ioplug_t *io){snd_pcm_ioplug_set_state(io,SND_PCM_STATE_PREPARED);return 0;}
static int events(snd_pcm_ioplug_t *io,struct pollfd *p,unsigned n,unsigned short *ev){(void)n;*ev=(io->state==SND_PCM_STATE_SUSPENDED||io->state==SND_PCM_STATE_XRUN)?POLLERR:p[0].revents;return 0;}
static int finish(snd_pcm_ioplug_t *io){Fault *f=io->private_data;close(io->poll_fd);active=NULL;free(f);return 0;}
static const snd_pcm_ioplug_callback_t callbacks={.start=start,.stop=stop,.pointer=pointer,.transfer=transfer,.prepare=prepare,.resume=resume,.poll_revents=events,.close=finish};
void banana_fault_once(void){active->fail=1;}
void banana_fault_suspend(void){snd_pcm_ioplug_set_state(&active->io,SND_PCM_STATE_SUSPENDED);}
SND_PCM_PLUGIN_DEFINE_FUNC(banana_fault){
 (void)root;(void)conf;Fault *f=calloc(1,sizeof(*f));if(!f)return -ENOMEM;
 f->io.version=SND_PCM_IOPLUG_VERSION;f->io.name="Banana RW fault fixture";f->io.callback=&callbacks;f->io.private_data=f;
 f->io.poll_fd=eventfd(0,EFD_CLOEXEC|EFD_NONBLOCK);f->io.poll_events=POLLOUT;
 int err=snd_pcm_ioplug_create(&f->io,name,stream,mode);if(err<0){close(f->io.poll_fd);free(f);return err;}
 unsigned access[]={SND_PCM_ACCESS_RW_INTERLEAVED};unsigned format[]={SND_PCM_FORMAT_S16_LE};
 if((err=snd_pcm_ioplug_set_param_list(&f->io,SND_PCM_IOPLUG_HW_ACCESS,1,access))<0||
    (err=snd_pcm_ioplug_set_param_list(&f->io,SND_PCM_IOPLUG_HW_FORMAT,1,format))<0||
    (err=snd_pcm_ioplug_set_param_minmax(&f->io,SND_PCM_IOPLUG_HW_CHANNELS,2,2))<0||
    (err=snd_pcm_ioplug_set_param_minmax(&f->io,SND_PCM_IOPLUG_HW_RATE,48000,48000))<0||
    (err=snd_pcm_ioplug_set_param_minmax(&f->io,SND_PCM_IOPLUG_HW_PERIOD_BYTES,64,4096))<0||
    (err=snd_pcm_ioplug_set_param_minmax(&f->io,SND_PCM_IOPLUG_HW_BUFFER_BYTES,128,16384))<0||
    (err=snd_pcm_ioplug_set_param_minmax(&f->io,SND_PCM_IOPLUG_HW_PERIODS,2,8))<0){snd_pcm_ioplug_delete(&f->io);return err;}
 active=f;*pcmp=f->io.pcm;return 0;
}
SND_PCM_PLUGIN_SYMBOL(banana_fault);