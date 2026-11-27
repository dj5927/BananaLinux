/* SPDX-License-Identifier: GPL-2.0-or-later
 * Freeze the launcher's descendants even when an SA engine called setsid().
 * pidfds prevent a reused PID receiving SIGCONT. Already-paused processes stay paused.
 */
#ifndef BANANA_SLEEP_TREE_H
#define BANANA_SLEEP_TREE_H
#include <sys/syscall.h>
#define SLEEP_TREE_MAX 512
struct sleep_process { pid_t pid; int fd, resume; };
struct sleep_tree { struct sleep_process p[SLEEP_TREE_MAX]; int count; };
static char sleep_process_state(pid_t pid)
{
    char path[64], buf[4096];
    snprintf(path, sizeof path, "/proc/%d/stat", pid);
    FILE *f=fopen(path,"r");
    if(!f) return 0;
    char *got=fgets(buf,sizeof buf,f); fclose(f);
    char *end=got?strrchr(buf,')'):NULL;
    return end && end[1]==' '?end[2]:0;
}
static int sleep_pid_signal(int fd,int sig)
{
    return syscall(SYS_pidfd_send_signal,fd,sig,NULL,0);
}
static void sleep_tree_resume(struct sleep_tree *tree)
{
    /* Children first, then their supervisor. Never wake an already-paused engine. */
    for(int i=tree->count-1;i>=0;i--) {
        if(tree->p[i].resume) sleep_pid_signal(tree->p[i].fd,SIGCONT);
        close(tree->p[i].fd);
    }
    tree->count=0;
}
static int sleep_tree_stop(struct sleep_tree *tree,pid_t pid,int depth)
{
    if(pid<=1 || pid==getpid()) return -1;
    for(int i=0;i<tree->count;i++) if(tree->p[i].pid==pid) return 0;
    if(tree->count==SLEEP_TREE_MAX || depth>64) return -1;
    int fd=syscall(SYS_pidfd_open,pid,0);
    if(fd<0) return errno==ESRCH?0:-1;
    char state=sleep_process_state(pid);
    if(!state || state=='Z' || state=='X') {close(fd);return 0;}
    struct sleep_process *p=&tree->p[tree->count++];
    *p=(struct sleep_process){pid,fd,state!='T' && state!='t'};
    if(p->resume && sleep_pid_signal(fd,SIGSTOP)<0) {
        p->resume=0;
        return errno==ESRCH?0:-1;
    }
    int stopped=0;
    for(int n=0;n<250;n++) {
        state=sleep_process_state(pid);
        if(!state || state=='Z' || state=='X') return 0;
        if(state=='T' || state=='t') {stopped=1;break;}
        usleep(1000);
    }
    if(!stopped) return -1;
    /* All threads are stopped before collecting their children: no new fork races. */
    char path[96]; snprintf(path,sizeof path,"/proc/%d/task",pid);
    DIR *tasks=opendir(path);
    if(!tasks) return errno==ENOENT?0:-1;
    struct dirent *ent;
    int result=0;
    while(!result && (ent=readdir(tasks))) {
        if(!isdigit((unsigned char)ent->d_name[0])) continue;
        char children[384];
        snprintf(children,sizeof children,"/proc/%d/task/%s/children",pid,ent->d_name);
        FILE *f=fopen(children,"r");
        if(!f) continue;
        int child;
        while(fscanf(f,"%d",&child)==1) if(sleep_tree_stop(tree,child,depth+1)) {result=-1;break;}
        fclose(f);
    }
    closedir(tasks);
    return result;
}
#endif