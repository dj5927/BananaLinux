#pragma once
// Folder projects: one entry per RPG Maker game, without generating launch
// files or modifying the user's project. Shared by library and its unit tests.
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <map>
#include <set>
#include <string>
#include <vector>

namespace banana::rpg {
namespace fs = std::filesystem;
struct Project { std::string rel, entry, engine; };
inline bool isSystem(const std::string& id) { return id=="mkxp" || id=="easyrpg"; }
inline std::string lower(std::string s) {
    for (auto& c:s) c=static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}
inline bool usable(const std::string& s) {
    return !s.empty() && s[0]!='.' && s.find_first_of("\r\n\t")==std::string::npos;
}
inline bool ignored(const std::string& name) {
    auto n=lower(name);
    return !usable(name) || n=="media" || n=="images" || n=="videos" || n=="manuals" ||
        n=="downloaded_images" || n=="rtp" || n=="fonts" || n=="_compat";
}
inline std::vector<fs::directory_entry> entries(const fs::path& dir) {
    std::vector<fs::directory_entry> result;
    std::error_code ec;
    for (fs::directory_iterator it(dir,fs::directory_options::skip_permission_denied,ec), end;
         !ec && it!=end; it.increment(ec)) {
        std::error_code st;
        if (it->is_symlink(st) || st || !usable(it->path().filename().string())) continue;
        result.push_back(*it);
    }
    std::sort(result.begin(),result.end(),[](const auto& a,const auto& b){return a.path().filename().string()<b.path().filename().string();});
    return result;
}
inline bool regular(const fs::directory_entry& e) {
    std::error_code ec;
    return e.is_regular_file(ec) && !ec;
}
inline bool directory(const fs::directory_entry& e) {
    std::error_code ec;
    return e.is_directory(ec) && !ec;
}
inline int kind(const std::string& ext) {
    if(ext==".rxdata" || ext==".rgssad" || ext==".rxproj") return 1;
    if(ext==".rvdata" || ext==".rgss2a" || ext==".rvproj") return 2;
    if(ext==".rvdata2" || ext==".rgss3a" || ext==".rvproj2") return 3;
    return 0;
}
inline Project inspect(const fs::path& dir,const std::string& id) {
    Project p;
    std::string ini,json,ldb,lmt,project;
    std::set<int> types;
    int explicitType=0;
    for(const auto& e:entries(dir)) {
        const auto n=e.path().filename().string(), l=lower(n);
        if(directory(e) && l=="data" && id=="mkxp") {
            for(const auto& d:entries(e.path())) {
                if(!regular(d)) continue;
                const auto stem=lower(d.path().stem().string());
                if(stem!="scripts" && stem!="system") continue;
                const int v=kind(lower(d.path().extension().string()));
                if(v) types.insert(v);
            }
        }
        if(!regular(e)) continue;
        if(l=="rpg_rt.ldb") ldb=n;
        else if(l=="rpg_rt.lmt") lmt=n;
        else if(l=="game.ini") ini=n;
        else if(l=="mkxp.json") json=n;
        const auto ext=lower(e.path().extension().string());
        int v=kind(ext);
        if(ext==".rgssad" || ext==".rgss2a" || ext==".rgss3a") types.insert(v);
        if(ext==".rxproj" || ext==".rvproj" || ext==".rvproj2") {
            // Two different project types in one directory are ambiguous.
            if(explicitType && explicitType!=v) return {};
            explicitType=v;
            if(project.empty()) project=n;
        }
    }
    if(id=="easyrpg") {
        if(!ldb.empty() && !lmt.empty()) { p.entry=ldb; p.engine="RPG Maker 2000/2003"; }
        return p;
    }
    if(id!="mkxp") return {};
    if(types.empty() || types.size()!=1 || (explicitType && !types.count(explicitType))) return {};
    int v=*types.begin();
    // A project entry is necessary for the Libretro core. Never manufacture
    // Game.ini or a project marker in the user's folder.
    p.entry=!project.empty()?project:!ini.empty()?ini:json;
    if(p.entry.empty()) return {};
    p.engine=v==1?"RPG Maker XP":v==2?"RPG Maker VX":"RPG Maker VX Ace";
    return p;
}
inline void scan(const fs::path& root,const std::string& id,std::vector<Project>& result,
                 const std::string& rel="",int depth=0) {
    if(depth>=3) return; // one game folder, with up to two grouping directories
    for(const auto& e:entries(rel.empty()?root:root/fs::path(rel))) {
        const auto n=e.path().filename().string();
        if(!directory(e) || ignored(n)) continue;
        const auto next=rel.empty()?n:rel+"/"+n;
        auto p=inspect(e.path(),id);
        if(!p.entry.empty()) {
            p.rel=next;
            p.entry=next+"/"+p.entry;
            result.push_back(std::move(p));
        } else {
            // Don't descend into an invalid project/asset folder and mistake
            // embedded test data for a separate game.
            auto l=lower(n);
            if(l!="data" && l!="graphics" && l!="audio") scan(root,id,result,next,depth+1);
        }
    }
}
inline std::string key(const std::string& s) {
    const char* hex="0123456789abcdef";
    std::string out;
    out.reserve(s.size()*2);
    for(unsigned char c:s) { out+=hex[c>>4];out+=hex[c&15]; }
    return out;
}
}
