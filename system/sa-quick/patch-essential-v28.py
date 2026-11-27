#!/usr/bin/env python3
from pathlib import Path
p=Path("/var/tmp/banana-v20-sources/easypsp/Core/Config.cpp")
s=p.read_text()
a='\tif (getenv("BANANA_DRM_LEASE_FD")) {\n\t\tiEasypspScreen = 0;'
assert s.count(a)==1
p.write_text(s.replace(a,'''    if (const char* v=getenv("BANANA_EASY_VSYNC")) {
        if (std::string(v)=="on") bVSync=true;
        else if (std::string(v)=="off") bVSync=false;
    }
    if (const char* v=getenv("BANANA_EASY_FILTER")) {
        if (std::string(v)=="nearest") iTexFiltering=2;
        else if (std::string(v)=="linear") iTexFiltering=3;
    }
    if (const char* v=getenv("BANANA_EASY_SOUND")) {
        if (std::string(v)=="on") bEnableSound=true;
        else if (std::string(v)=="off") bEnableSound=false;
    }
'''+a))
p=Path("/var/tmp/banana-v20-sources/easycast/core/emulator.cpp")
s=p.read_text()
a="\tconfig::Settings::instance().load(true);\n\n\tif (config::GGPOEnable"
assert s.count(a)==1
p.write_text(s.replace(a,'''    config::Settings::instance().load(true);
    if(const char* v=std::getenv("BANANA_EASY_VSYNC")) {
        if(std::string(v)=="on") config::VSync.override(true);
        else if(std::string(v)=="off") config::VSync.override(false);
    }
    if(const char* v=std::getenv("BANANA_EASY_FILTER")) {
        if(std::string(v)=="nearest") config::TextureFiltering.override(1);
        else if(std::string(v)=="linear") config::TextureFiltering.override(2);
    }
    if(const char* v=std::getenv("BANANA_EASY_FPS")) {
        if(std::string(v)=="on") config::ShowFPS.override(true);
        else if(std::string(v)=="off") config::ShowFPS.override(false);
    }

    if (config::GGPOEnable'''))
print("ESSENTIAL_OPTIONS_PATCH_PASS")
