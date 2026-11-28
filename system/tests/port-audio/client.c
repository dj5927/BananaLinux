// Models the OUT/IN-only branch preceding CPAL9d269d8's EPIPE recovery.
#include <alsa/asoundlib.h>
#include <assert.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
void fixture(int,int,int,int,int,int,int);
int recovered_calls(void);
void timed_fixture(void);
static snd_pcm_t *pcm=(snd_pcm_t *)1;
static void test(int s,int dir,int rc,int recovery,int resume,int prepare,int events,int want,int calls) {
 fixture(s,dir,rc,recovery,resume,prepare,events);
 unsigned short e=0;assert(snd_pcm_poll_descriptors_revents(pcm,NULL,0,&e)==rc);
 assert(e==want);assert(recovered_calls()==calls);assert(errno==EDOM);
}
int main(int argc,char **argv) {
 if(argc>1 && argv[1][0]=='t') {
  timed_fixture();int frames=0;
  while(1) { unsigned short ev=0;snd_pcm_poll_descriptors_revents(pcm,NULL,0,&ev);
   if(ev==POLLOUT) { char tmp[4096];snprintf(tmp,sizeof tmp,"%s.new",argv[2]);FILE *f=fopen(tmp,"w");assert(f);assert(fprintf(f,"%d\n",++frames)>0);assert(fclose(f)==0);assert(rename(tmp,argv[2])==0); }
   usleep(10000);
  }
 }
 if(argc>1 && argv[1][0]=='b') {
  fixture(SND_PCM_STATE_XRUN,0,0,0,0,0,POLLERR);int progress=0;
  for(int i=0;i<100;i++) { unsigned short ev=0;snd_pcm_poll_descriptors_revents(pcm,NULL,0,&ev);if(ev==POLLOUT)progress++; }
  assert(progress==0 && recovered_calls()==0);puts("NEGATIVE_CONTROL_SILENCE_REPRODUCED");return 0;
 }
 test(SND_PCM_STATE_XRUN,0,0,0,0,0,POLLERR,POLLOUT,1);
 test(SND_PCM_STATE_XRUN,1,0,0,0,0,POLLERR,POLLERR,0);
 test(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLERR,POLLERR,0);
 test(SND_PCM_STATE_XRUN,0,0,-EIO,0,0,POLLERR,POLLERR,1);
 test(SND_PCM_STATE_DISCONNECTED,0,0,0,0,0,POLLERR,POLLERR,0);
 test(SND_PCM_STATE_XRUN,0,-EIO,0,0,0,POLLERR,POLLERR,0);
 test(SND_PCM_STATE_XRUN,0,0,0,0,0,0,0,0);
 test(SND_PCM_STATE_SUSPENDED,0,0,0,0,0,POLLERR,POLLOUT,1);
 test(SND_PCM_STATE_SUSPENDED,0,0,0,-ENOSYS,0,POLLERR,POLLOUT,2);
 test(SND_PCM_STATE_SUSPENDED,0,0,0,-EAGAIN,0,POLLERR,POLLERR,1);
 test(SND_PCM_STATE_SUSPENDED,0,0,0,-ENOSYS,-EIO,POLLERR,POLLERR,2);
 test(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLOUT,POLLOUT,0);
 puts("PORT_AUDIO_RECOVERY_12_CASES_PASS");return 0;
}
