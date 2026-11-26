#include "rpg_projects.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <unistd.h>
using namespace banana::rpg;
int main() {
    char tmp[]="/tmp/banana-rpg-scan-XXXXXX";
    auto* d=mkdtemp(tmp); assert(d);
    fs::path root(d);
    auto put=[&](const std::string& p) {
        auto file=root/p;
        fs::create_directories(file.parent_path());
        std::ofstream(file)<<"fixture";
    };
    put("mkxp/한글 제목 (v1.0)/Game.ini");
    put("mkxp/한글 제목 (v1.0)/DATA/Scripts.rxdata");
    put("mkxp/한글 제목 (v1.0)/Graphics/Other/Game.ini");
    put("mkxp/한글 제목 (v1.0)/Graphics/Other/Game.rgss3a");
    put("mkxp/VX/Game.ini");put("mkxp/VX/Data/Scripts.rvdata");
    put("mkxp/VXAce/Game.INI");put("mkxp/VXAce/Game.rgss3a");
    put("mkxp/Grouped/Another/XP/Game.rxproj");put("mkxp/Grouped/Another/XP/Data/System.rxdata");
    put("mkxp/Incomplete/Game.ini");
    put("mkxp/Conflicting/Game.ini");put("mkxp/Conflicting/Game.rgssad");put("mkxp/Conflicting/Game.rgss3a");
    put("mkxp/NoEntry/Data/Scripts.rxdata");
    put("mkxp/media/Fake/Game.ini");put("mkxp/media/Fake/Data/Scripts.rxdata");
    put("easyrpg/2000/RPG_RT.ldb");put("easyrpg/2000/RPG_RT.lmt");
    put("easyrpg/2003/RPG_RT.LDB");put("easyrpg/2003/RPG_RT.LMT");
    put("easyrpg/Incomplete/RPG_RT.ldb");
    put("easyrpg/XP/Game.ini");put("easyrpg/XP/Game.rgssad");
    fs::create_directory_symlink(root/"mkxp"/"VX",root/"mkxp"/"Link");
    std::vector<Project> m,e;scan(root/"mkxp","mkxp",m);scan(root/"easyrpg","easyrpg",e);
    assert(m.size()==4);assert(e.size()==2);
    std::map<std::string,std::string> expect={
      {"한글 제목 (v1.0)","RPG Maker XP"},{"VX","RPG Maker VX"},{"VXAce","RPG Maker VX Ace"},{"Grouped/Another/XP","RPG Maker XP"}};
    for(const auto& p:m){ assert(expect.at(p.rel)==p.engine);assert(fs::is_regular_file(root/"mkxp"/p.entry)); }
    for(const auto& p:e)assert(p.engine=="RPG Maker 2000/2003");
    assert(key("mkxp/게임 1")!=key("mkxp/게임 2"));
    assert(key("mkxp/@sd2/게임 1")!=key("mkxp/게임 1"));
    fs::remove_all(root);
    std::cout<<"PASS XP/VX/VX Ace/2000/2003 project scan, encrypted archives, case-insensitive markers, Korean folders, grouping and deduplication\n";
}
