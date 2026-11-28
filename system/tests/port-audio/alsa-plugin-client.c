// Exercise real ALSA conversion/mmap plugins, not mocked PCM status calls.
#define _GNU_SOURCE
#include <alsa/asoundlib.h>
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void ok(int rc,const char *what){if(rc<0){fprintf(stderr,"%s: %s\n",what,snd_strerror(rc));exit(2);}}
int main(int argc,char **argv){
 if(argc<3)return 2;
 snd_pcm_t *pcm;ok(snd_pcm_open(&pcm,"repro",SND_PCM_STREAM_PLAYBACK,0),"open");
 printf("REAL_ALSA_VERSION %s\n",snd_asoundlib_version());fflush(stdout);
 void *lib=dlopen(argv[1],RTLD_NOW|RTLD_NOLOAD);assert(lib);
 void (*fault)(void)=dlsym(lib,"banana_fault_once");void (*suspend)(void)=dlsym(lib,"banana_fault_suspend");void (*xrun)(void)=dlsym(lib,"banana_fault_xrun");snd_pcm_uframes_t (*position)(void)=dlsym(lib,"banana_fault_position");assert(fault&&suspend&&xrun&&position);
 ok(snd_pcm_set_params(pcm,(argc>4&&!strcmp(argv[4],"f32")?SND_PCM_FORMAT_FLOAT_LE:SND_PCM_FORMAT_S32_LE),SND_PCM_ACCESS_RW_INTERLEAVED,2,(argc>3?atoi(argv[3]):48000),1,30000),"params");
 int32_t samples[2048]={0};snd_pcm_status_t *status;snd_pcm_status_alloca(&status);
 for(int cycle=0;cycle<3;cycle++){
  long initial=snd_pcm_writei(pcm,samples,512);assert(initial==512);ok(snd_pcm_start(pcm),"start");
  ok(snd_pcm_status(pcm,status),"running initial status");
  fault();long n=snd_pcm_writei(pcm,samples,512);assert(n<=512&&(n>=0||n==-EPIPE));
  if(strstr(argv[2],"xrun"))xrun();else suspend();
  if(strstr(argv[2],"recover")){ok(snd_pcm_recover(pcm,strstr(argv[2],"xrun")?-EPIPE:-ESTRPIPE,1),"recover");}
  else{
   int count=snd_pcm_poll_descriptors_count(pcm);assert(count>0&&count<16);struct pollfd fds[16];ok(snd_pcm_poll_descriptors(pcm,fds,count),"descriptors");
   for(int i=0;i<count;i++)fds[i].revents=POLLERR;
   unsigned short ev=0;ok(snd_pcm_poll_descriptors_revents(pcm,fds,count,&ev),"events");
   assert(ev==POLLOUT);
  }

  ok(snd_pcm_status(pcm,status),"status");
  n=snd_pcm_writei(pcm,samples,512);assert(n==512);ok(snd_pcm_status(pcm,status),"postwrite status");
  ok(snd_pcm_start(pcm),"restart playback");ok(snd_pcm_status(pcm,status),"restarted status");
  assert(snd_pcm_state(pcm)==SND_PCM_STATE_RUNNING);assert(position()>0);
  printf("REAL_ALSA_PLUGIN_WRITE_STATUS_PASS %s cycle=%d\n",argv[2],cycle+1);fflush(stdout);
  ok(snd_pcm_prepare(pcm),"next cycle prepare");
 }
 snd_pcm_close(pcm);return 0;
}
