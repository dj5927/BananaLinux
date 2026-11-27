// SPDX-License-Identifier: GPL-2.0-or-later
// Per-launch, single-flight command bridge. No game/GPU state is shared with UI.
#pragma once
#include <cstdlib>
#include <cstdio>
#include <fstream>
#include <string>
#include <cstdint>

namespace banana_quick {
struct Request { uint64_t id=0; std::string op; int slot=0; };
inline bool read(Request& r) {
    const char* path=std::getenv("BANANA_QUICK_REQUEST");
    if(!path) return false;
    std::ifstream f(path);
    if(!f) return false;
    const bool valid=bool(f>>r.id>>r.op>>r.slot);
    f.close();
    if(std::remove(path)!=0) return false;
    return valid && r.id && r.slot>=1 && r.slot<=5 &&
           (r.op=="save" || r.op=="load" || r.op=="fast");
}
inline void reply(const Request& r,const char* result) {
    const char* path=std::getenv("BANANA_QUICK_RESULT");
    if(!path) return;
    std::string tmp=std::string(path)+".tmp";
    { std::ofstream f(tmp,std::ios::trunc); f<<r.id<<" "<<result<<"\n"; if(!f) return; }
    std::rename(tmp.c_str(),path);
}
}
