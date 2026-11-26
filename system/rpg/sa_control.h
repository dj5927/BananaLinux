#pragma once
// Standalone engine control channel, shared by the two native adapters.
// A command is a fixed ASCII token on the private FIFO created by banana-ui.
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
namespace banana_sa {
// Re-execute the launcher after clean engine shutdown. The process ID and
// inherited display lease stay unchanged; the launcher reads new options.
inline bool& restartRequested() { static bool requested=false; return requested; }
inline bool requestRestart() {
    const char *launcher=std::getenv("BANANA_SA_LAUNCHER");
    const char *entry=std::getenv("BANANA_SA_ENTRY");
    const char *sys=std::getenv("BANANA_SYSTEM");
    if (!launcher || launcher[0]!='/' || !entry || entry[0]!='/' || !sys ||
        (std::strcmp(sys,"mkxp") && std::strcmp(sys,"easyrpg"))) return false;
    restartRequested()=true;
    return true;
}
inline int finish(int status) {
    if (status || !restartRequested()) return status;
    setenv("BANANA_SA_RESTARTING","1",1);
    const char *launcher=std::getenv("BANANA_SA_LAUNCHER");
    const char *entry=std::getenv("BANANA_SA_ENTRY");
    const char *sys=std::getenv("BANANA_SYSTEM");
    char *const args[]={const_cast<char*>(launcher),const_cast<char*>(sys),const_cast<char*>(entry),nullptr};
    execv(launcher,args);
    return 125;
}
enum Command { None, TogglePause, Reset, Quit };
class Channel {
    int fd_ = -1;
    char line_[32]{};
    unsigned used_ = 0;
    bool overflow_ = false;
public:
    Channel() {
        const char* path = std::getenv("BANANA_SA_CMD");
        if (!path || !*path) return;
        fd_ = open(path,O_RDONLY|O_NONBLOCK|O_CLOEXEC|O_NOFOLLOW);
        struct stat st{};
        if (fd_ >= 0 && (fstat(fd_,&st) != 0 || !S_ISFIFO(st.st_mode))) { close(fd_); fd_=-1; }
    }
    ~Channel() { if (fd_>=0) close(fd_); }
    Channel(const Channel&) = delete;
    Channel& operator=(const Channel&) = delete;
    bool enabled() const { return fd_>=0; }
    Command next() {
        if (fd_<0) return None;
        for (unsigned n=0;n<128;n++) {
            char ch;
            if (read(fd_,&ch,1)!=1) return None;
            if (ch=='\n') {
                line_[used_]=0;
                Command c=None;
                if (!overflow_) {
                    if (!std::strcmp(line_,"MENU_TOGGLE")) c=TogglePause;
                    else if (!std::strcmp(line_,"RESET")) c=Reset;
                    else if (!std::strcmp(line_,"QUIT")) c=Quit;
                }
                used_=0; overflow_=false;
                if (c!=None) return c;
            } else if (used_<sizeof(line_)-1) line_[used_++]=ch;
            else overflow_=true;
        }
        return None;
    }
};
}
