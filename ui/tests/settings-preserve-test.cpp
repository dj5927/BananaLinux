#include "settings_defaults.h"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
#include <sys/stat.h>
using namespace banana;
static std::string read(const std::string& p) {
 std::ifstream f(p,std::ios::binary);
 return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};
}
int main(int argc,char** argv) {
 assert(argc==2);
 std::string d=argv[1], p=d+"/settings.conf";
 assert(normalizeSettings(d));
 assert(readSettings(d).at("core.psx")=="duckstation_sa");
 assert(readSettings(d).at("face_layout")=="nintendo");
 assert(!normalizeSettings(d));
 const std::string old="# user text and CRLF\r\n  theme=light\r\nface_layout = xbox\r\nface_layout=individual\r\ncore.psx = swanstation\r\ncore.gba = \r\nra_vsync = invalid\r\nunknown = keep\r\n# no trailing newline";
 { std::ofstream f(p,std::ios::binary); f<<old; }
 struct stat before{},after{};
 assert(stat(p.c_str(),&before)==0);
 for(int i=0;i<3;++i){
  assert(!normalizeSettings(d));
  auto s=readSettings(d);
  assert(s.at("theme")=="light");
  assert(s.at("face_layout")=="individual");
  assert(s.at("core.psx")=="swanstation");
  assert(s.at("core.gba").empty());
  assert(s.at("ra_vsync")=="on");
  assert(s.at("unknown")=="keep");
  assert(s.at("nds_emulator")=="superdrastic");
  assert(read(p)==old);
 }
 assert(stat(p.c_str(),&after)==0);
 assert(before.st_ino==after.st_ino && before.st_mtime==after.st_mtime);
 assert(resetSettings(d,ResetScope::System));
 assert(read(p).find("face_layout = xbox\nface_layout=individual\n")!=std::string::npos);
 assert(readSettings(d).at("theme")=="dark");
 assert(resetSettings(d,ResetScope::Emulator));
 assert(readSettings(d).at("core.psx")=="duckstation_sa");
 assert(readSettings(d).at("face_layout")=="nintendo");
 assert(readSettings(d).at("unknown")=="keep");
 // Empty files are deliberate user files too, not fresh installs.
 {std::ofstream f(p,std::ios::binary);}
 assert(!normalizeSettings(d)); assert(read(p).empty());
 std::cout<<"SETTINGS_READ_ONLY_AND_EXPLICIT_RESET_PASS\n";
}
