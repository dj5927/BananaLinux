/* SPDX-License-Identifier: GPL-2.0-or-later
 * Freeze all game descendants, including engines that created their own sessions.
 * RG DS has CONFIG_PROC_CHILDREN=n: discover PPid via /proc/PID/stat instead.
 * pidfds prevent signals reaching reused PIDs; pre-paused tasks stay paused.
 */
#ifndef BANANA_SLEEP_TREE_H
#define BANANA_SLEEP_TREE_H
#include <sys/syscall.h>
#define SLEEP_TREE_MAX 512
struct sleep_process { pid_t pid; int fd, resume; };
struct sleep_tree { struct sleep_process p[SLEEP_TREE_MAX]; int count; };
static char sleep_process_info(pid_t pid,pid_t *parent)
{
    char path[64],buf[4096];
    snprintf(path,sizeof path,"/proc/%d/stat",pid);
    FILE *f=fopen(path,"r");
    if(!f) return 0;
    char *got=fgets(buf,sizeof buf,f); fclose(f);
    char *end=got?strrchr(buf,')'):NULL;
    char state=0; int ppid=0;
    if(!end || sscanf(end+1," %c %d",&state,&ppid)!=2) return 0;
    if(parent) *parent=ppid;
    return state;
}
static char sleep_process_state(pid_t pid) {return sleep_process_info(pid,NULL);}
static int sleep_pid_signal(int fd,int sig)
{
    return syscall(SYS_pidfd_send_signal,fd,sig,NULL,0);
}
static void sleep_tree_resume(struct sleep_tree *tree)
{
    for(int i=tree->count-1;i>=0;i--) {
        if(tree->p[i].resume) sleep_pid_signal(tree->p[i].fd,SIGCONT);
        close(tree->p[i].fd);
    }
    tree->count=0;
}
/* A stopped leader alone does not prove every emulator/audio/render thread stopped. */
static int sleep_all_threads_stopped(pid_t pid)
{
    char path[64];snprintf(path,sizeof path,"/proc/%d/task",pid);
    DIR *tasks=opendir(path);
    if(!tasks) return errno==ENOENT?1:-1;
    struct dirent *ent;int result=1;
    while((ent=readdir(tasks))) {
        if(!isdigit((unsigned char)ent->d_name[0])) continue;
        char state=sleep_process_state(atoi(ent->d_name));
        if(state && state!='T' && state!='t' && state!='Z' && state!='X') {result=0;break;}
    }
    closedir(tasks);return result;
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
        p->resume=0;return errno==ESRCH?0:-1;
    }
    int stopped=0;
    for(int n=0;n<250;n++) {
        int all=sleep_all_threads_stopped(pid);
        if(all<0) return -1;
        if(all) {stopped=1;break;}
        usleep(1000);
    }
    if(!stopped) return -1;
    /* Parent threads can no longer fork. PPid works without optional kernel features,
     * and is the parent's thread-group ID even for children forked by another thread. */
    DIR *proc=opendir("/proc");
    if(!proc) return -1;
    struct dirent *ent;int result=0;
    while(!result && (ent=readdir(proc))) {
        if(!isdigit((unsigned char)ent->d_name[0])) continue;
        pid_t child=atoi(ent->d_name),parent=0;
        if(child>1 && sleep_process_info(child,&parent) && parent==pid)
            result=sleep_tree_stop(tree,child,depth+1);
    }
    closedir(proc);return result;
}
#endif