#include <alsa/asoundlib.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include <assert.h>
#include <errno.h>
void fixture(int,int,int,int,int,int,int);
void fixture_timestamps(long,long);
void timed_fixture(void);
static snd_pcm_t *pcm=(snd_pcm_t *)1;
static snd_pcm_status_t *status=(snd_pcm_status_t *)7;
static long stamp(snd_pcm_t *p) {
 snd_htimestamp_t now,trigger;
 assert(snd_pcm_status(p,status)==0);
 snd_pcm_status_get_htstamp(status,&now);snd_pcm_status_get_trigger_htstamp(status,&trigger);
 return now.tv_sec-trigger.tv_sec;
}
static void *other_thread(void *ignored) {(void)ignored;assert(stamp(pcm)==-100);return NULL;}
int main(int argc,char **argv) {
 unsigned short ev=0;
 if(argc>1) {
  timed_fixture();int frames=0;
  while(1) {
   snd_pcm_poll_descriptors_revents(pcm,NULL,0,&ev);
   if(ev==POLLOUT) {
    if(stamp(pcm)<0) {fputs("CPAL_STYLE_TIMESTAMP_ABORT\n",stderr);return 42;}
    fixture(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLOUT);
    char tmp[4096];snprintf(tmp,sizeof tmp,"%s.new",argv[1]);FILE *f=fopen(tmp,"w");assert(f);fprintf(f,"%d\n",++frames);fclose(f);assert(rename(tmp,argv[1])==0);
   }
   usleep(10000);
  }
 }
 fixture(SND_PCM_STATE_XRUN,0,0,0,0,0,POLLERR);
 snd_pcm_poll_descriptors_revents(pcm,NULL,0,&ev);assert(ev==POLLOUT);
 fixture_timestamps(0,100);
 if(stamp(pcm)<0) {fputs("CPAL_STYLE_TIMESTAMP_ABORT\n",stderr);return 42;}
 assert(stamp((snd_pcm_t *)2)==-100);
 assert(stamp(pcm)==0);
 pthread_t t;assert(pthread_create(&t,NULL,other_thread,NULL)==0);assert(pthread_join(t,NULL)==0);
 fixture(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLOUT);fixture_timestamps(200,100);
 assert(stamp(pcm)==100);
 fixture_timestamps(0,100);assert(stamp(pcm)==-100);
 fixture(SND_PCM_STATE_XRUN,0,0,0,0,0,POLLERR);
 assert(snd_pcm_recover(pcm,-EPIPE,1)==0);assert(stamp(pcm)==0);
 fixture(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLOUT);fixture_timestamps(200,100);assert(stamp(pcm)==100);
 fixture_timestamps(0,100);assert(snd_pcm_prepare(pcm)==0);assert(stamp(pcm)==0);
 fixture(SND_PCM_STATE_RUNNING,0,0,0,0,0,POLLOUT);fixture_timestamps(200,100);assert(stamp(pcm)==100);
 fixture(SND_PCM_STATE_XRUN,1,0,0,0,0,POLLERR);fixture_timestamps(0,100);
 assert(snd_pcm_prepare(pcm)==0);assert(stamp(pcm)==-100);
 puts("TIMESTAMP_NATIVE_CPAL_RECOVER_PREPARE_CAPTURE_PASS");
 puts("TIMESTAMP_SCOPE_TLS_NORMAL_RUNNING_PASS");return 0;
}