#pragma once
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace banana {
struct SwanOption {
    std::string key, def, label, help;
    std::vector<std::string> values, names;
};
inline std::vector<std::string> swanSplit(const std::string& line, char delim) {
    std::vector<std::string> out;
    std::istringstream in(line);
    std::string v;
    while(std::getline(in,v,delim)) out.push_back(v);
    return out;
}
inline const std::vector<SwanOption>& swanOptions() {
    static const auto options=[] {
        std::vector<SwanOption> out;
        const char* fixture=std::getenv("BANANA_SWAN_OPTIONS");
        std::ifstream f(fixture?fixture:"/usr/share/banana/swanstation-options.tsv");
        std::string line;
        while(std::getline(f,line)) {
            if(!line.empty() && line.back()=='\r') line.pop_back();
            auto p=swanSplit(line,'\t');
            if(p.size()!=6) continue;
            auto v=swanSplit(p[4],'|'),n=swanSplit(p[5],'|');
            if(v.empty() || v.size()!=n.size()) continue;
            out.push_back({p[0],p[1],p[2],p[3],v,n});
        }
        return out;
    }();
    return options;
}
// RetroArch exposes GET_STATUS and PAUSE_TOGGLE, not a stdin "PAUSE".
// Query before toggling, remember a pre-existing pause, and verify the
// resulting state rather than assuming every command was delivered.
struct SwanMenuPause {
    bool active=false, desired=false, known=false, original=false, waiting=false;
    double next=0;
    void request(bool open) {
        if(open==desired) return;
        desired=open;
        if(open && !active) { active=true; known=false; waiting=false; next=0; }
        if(!waiting) next=0;
    }
    template<class Send> void tick(double t, Send send) {
        if(!active || t<next) return;
        if(send("GET_STATUS\n")) { waiting=true; next=t+1000; }
        else next=t+200;
    }
    template<class Send> void status(bool paused, double t, Send send) {
        if(!active || !waiting) return;
        waiting=false;
        if(!known) { known=true; original=paused; }
        bool target=desired || original;
        if(paused!=target) { send("PAUSE_TOGGLE\n"); next=t+250; }
        else if(!desired) { active=false; known=false; next=0; }
        else next=t+500;
    }
};
}
