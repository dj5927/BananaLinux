#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include <pthread.h>
#include "sleep-tree.h"
static int denied;
FILE *__real_fopen(const char *,const char *);
FILE *__wrap_fopen(const char *path,const char *mode)
{
    size_t n=strlen(path);
    if(n>=9 && !strcmp(path+n-9,"/children")) {denied++;errno=ENOENT;return NULL;}
    return __real_fopen(path,mode);
}
struct shared {volatile pid_t engine,renderer,paused;volatile unsigned long game,audio,render;} *s;
static void *audio(void *unused)
{
    (void)unused;
    pid_t p=fork();
    if(!p) {setsid();prctl(PR_SET_NAME,"render ) (test");for(;;){s->render++;usleep(1000);}}
    s->renderer=p;
    for(;;){s->audio++;usleep(1000);}
    return NULL;
}
static int one(const char *name,int own_session,int old)
{
    memset(s,0,sizeof *s);denied=0;
    pid_t launcher=fork();
    if(!launcher) {
        setsid();prctl(PR_SET_NAME,"SA launcher");
        pid_t p=fork();
        if(!p){
            if(own_session) setsid();
            prctl(PR_SET_NAME,name);
            pthread_t t;pthread_create(&t,NULL,audio,NULL);
            for(;;){s->game++;usleep(1000);}
        }
        s->engine=p;
        p=fork();
        if(!p){setsid();raise(SIGSTOP);for(;;)pause();}
        s->paused=p;
        for(;;)pause();
    }
    int bad=0;
    for(int n=0;n<1000 && (!s->engine || !s->renderer || !s->paused || !s->audio || !s->render);n++)usleep(1000);
    if(!s->engine || !s->renderer || !s->paused || !s->audio || !s->render) bad=1;
    for(int cycle=0;cycle<(old?1:3) && !bad;cycle++) {
        struct sleep_tree tree={0};
        if(sleep_tree_stop(&tree,launcher,0)) bad=1;
        unsigned long a=s->game,b=s->audio,c=s->render;usleep(60000);
        if(old) {
            if(tree.count!=1 || denied<1 || s->game==a || s->audio==b || s->render==c)bad=1;
        } else {
            if(tree.count!=4 || denied || s->game!=a || s->audio!=b || s->render!=c ||
               sleep_process_state(s->engine)!='T' || sleep_process_state(s->renderer)!='T')bad=1;
        }
        sleep_tree_resume(&tree);usleep(30000);
        if(!old && (s->game==a || s->audio==b || s->render==c || sleep_process_state(s->paused)!='T'))bad=1;
    }
    if(s->engine>1)kill(s->engine,SIGKILL);
    if(s->renderer>1)kill(s->renderer,SIGKILL);
    if(s->paused>1)kill(s->paused,SIGKILL);
    kill(launcher,SIGKILL);waitpid(launcher,NULL,0);
    usleep(5000);while(waitpid(-1,NULL,WNOHANG)>0){}
    printf("%s %s no-PROC_CHILDREN game/audio/render %s\n",old?"V30_REPRODUCED_FAILURE":"V31_FIXED",name,bad?"FAIL":"PASS");fflush(stdout);
    return bad;
}
int main(int argc,char **argv)
{
    int old=argc>1 && !strcmp(argv[1],"old");
    prctl(PR_SET_CHILD_SUBREAPER,1);
    s=mmap(NULL,sizeof *s,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
    if(s==MAP_FAILED)return 2;
    int bad=0;
    bad+=one("mkxp ) (",0,old);bad+=one("PPSSPPSDL",1,old);
    bad+=one("duckstation",1,old);bad+=one("flycast",1,old);
    return bad?1:0;
}