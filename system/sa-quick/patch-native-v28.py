#!/usr/bin/env python3
"""Patch exact retained engine sources. Only native UI/state control changes."""
from pathlib import Path
import shutil
base=Path(__file__).resolve().parent
psp=Path("/var/tmp/banana-v20-sources/easypsp")
dc=Path("/var/tmp/banana-v20-sources/easycast")
duck=Path("/var/tmp/banana-v26-duck/duckstation")
changes={}
def read(root,file):
    p=root/file
    if p not in changes: changes[p]=p.read_text()
    return changes[p]
def rep(root,file,a,b,n=1):
    p=root/file;s=read(root,file)
    assert s.count(a)==n,(str(p),a[:90],s.count(a))
    changes[p]=s.replace(a,b)
def section(root,file,start,end,transform):
    p=root/file;s=read(root,file);i=s.index(start);j=s.index(end,i)
    changes[p]=s[:i]+transform(s[i:j])+s[j:]

# PPSSPP: UI-thread dispatch uses identical guard and native slot callbacks.
f="UI/EmuScreen.cpp"
rep(psp,f,"void EmuScreen::update() {",'''#include "banana_quick.h"

void EmuScreen::update() {
    if (IsOnTop() && PSP_IsInited() && !bootPending_ && coreState != CORE_RUNTIME_ERROR) {
        banana_quick::Request req;
        if (banana_quick::read(req)) {
            if (req.op == "fast") {
                if (NetworkWarnUserIfOnlineAndCantSpeed()) banana_quick::reply(req, "blocked");
                else {
                    PSP_CoreParameter().fastForward = !PSP_CoreParameter().fastForward;
                    banana_quick::reply(req, PSP_CoreParameter().fastForward ? "fast_on" : "fast_off");
                }
            } else if (Achievements::WarnUserIfHardcoreModeActive(req.op == "save") ||
                       NetworkWarnUserIfOnlineAndCantSavestate()) {
                banana_quick::reply(req, "blocked");
            } else {
                const auto prefix=SaveState::GetGamePrefix(g_paramSFO);
                const int slot=req.slot-1;
                g_Config.iCurrentStateSlot=slot;
                auto done=[req](SaveState::Status status,std::string_view message) {
                    AfterSaveStateAction(status,message);
                    banana_quick::reply(req,status==SaveState::Status::SUCCESS?"ok":
                        status==SaveState::Status::WARNING?"warning":"failed");
                };
                if (req.op=="save") SaveState::SaveSlot(prefix,slot,done);
                else if (SaveState::HasSaveInSlot(prefix,slot)) SaveState::LoadSlot(prefix,slot,done);
                else banana_quick::reply(req,"empty");
            }
        }
    }''')
# Flycast: preserve the original async writer and native screenshots, adding
# a completion callback to the existing save path. Load returns actual result.
f="core/nullDC.cpp"
rep(dc,f,"static void easycast_writeState(void *data, size_t size, std::vector<u8> png, std::string filename, bool async,\n\t\tstd::chrono::steady_clock::time_point t0, double serializeMs)",
'''static void easycast_writeState(void *data, size_t size, std::vector<u8> png, std::string filename, bool async,
        std::chrono::steady_clock::time_point t0, double serializeMs, std::function<void(bool)> done)''')
section(dc,f,"static void easycast_writeState(","void dc_savestate(",lambda s:s.replace("\t\tfree(data);\n\t\treturn;","\t\tfree(data);\n\t\tif (done) done(false);\n\t\treturn;").rstrip()[:-1]+"\tif (done) done(ok);\n}\n\n")
def save_impl(s):
    s=s.replace("void dc_savestate(int index, const u8 *pngData, u32 pngSize)","void dc_savestate_with_result(int index, const u8 *pngData, u32 pngSize, std::function<void(bool)> done)")
    s=s.replace("if (!dc_savestateAllowed())\n\t\treturn;","if (!dc_savestateAllowed()) { if (done) done(false); return; }")
    s=s.replace('os_notify(i18n::T("Save state failed - memory full"), 5000);','os_notify(i18n::T("Save state failed - memory full"), 5000);\n        if (done) done(false);')
    s=s.replace("easycastT0, serMs);","easycastT0, serMs, done);")
    s=s.replace('os_notify(i18n::T("Cannot open save file"), 5000);\n\t\tfree(data);','os_notify(i18n::T("Cannot open save file"), 5000);\n\t\tfree(data);\n        if (done) done(false);')
    s=s.replace('os_notify(i18n::T("State saved"), 2000);\n\treturn;','os_notify(i18n::T("State saved"), 2000);\n\tif (done) done(true);\n\treturn;')
    s=s.replace("\t// delete failed savestate?","\tif (done) done(false);\n\t// delete failed savestate?")
    return s+'''void dc_savestate(int index, const u8 *pngData, u32 pngSize)
{
    dc_savestate_with_result(index,pngData,pngSize,{});
}

'''
section(dc,f,"void dc_savestate(int index,","void dc_loadstate(int index)",save_impl)
def load_impl(s):
    s=s.replace("void dc_loadstate(int index)","bool dc_loadstate_with_result(int index)")
    s=s.replace("return;","return false;")
    s=s.replace('os_notify(i18n::T("Failed to load state"), 5000, e.what());','os_notify(i18n::T("Failed to load state"), 5000, e.what());\n        free(data);\n        return false;')
    assert s.endswith("\tfree(data);\n}\n\n")
    return s[:-len("\tfree(data);\n}\n\n")]+"\tfree(data);\n\treturn true;\n}\n\nvoid dc_loadstate(int index) { (void)dc_loadstate_with_result(index); }\n\n"
section(dc,f,"void dc_loadstate(int index)","time_t dc_getStateCreationDate",load_impl)
f="core/ui/gui.cpp"
rep(dc,f,"static void savestate()\n{",'''#include "banana_quick.h"
void dc_savestate_with_result(int index,const u8* pngData,u32 pngSize,std::function<void(bool)> done);
bool dc_loadstate_with_result(int index);

static void savestate(const std::function<void(bool)>& done={})
{''')
rep(dc,f,"dc_savestate(config::SavestateSlot, pngData.empty() ? nullptr : &pngData[0], pngData.size());","dc_savestate_with_result(config::SavestateSlot, pngData.empty() ? nullptr : &pngData[0], pngData.size(),done);")
rep(dc,f,"void gui_cycleSaveStateSlot(int step)\n{",'''void gui_bananaQuick()
{
    banana_quick::Request req;
    if (!banana_quick::read(req)) return;
    const LockGuard lock(guiMutex);
    if (gui_state!=GuiState::Closed || !emu.running()) { banana_quick::reply(req,"blocked"); return; }
    if (req.op=="fast") {
        if(settings.network.online || settings.naomi.multiboard) banana_quick::reply(req,"blocked");
        else {
            settings.input.fastForwardMode=!settings.input.fastForwardMode;
            banana_quick::reply(req,settings.input.fastForwardMode?"fast_on":"fast_off");
        }
        return;
    }
    if (!dc_savestateAllowed() || (req.op=="load" && settings.raHardcoreMode)) {
        banana_quick::reply(req,"blocked"); return;
    }
    const int slot=req.slot-1;
    config::SavestateSlot=slot;
    if(req.op=="load" && dc_getStateCreationDate(slot)==0) {
        banana_quick::reply(req,"empty"); return;
    }
    try {
        emu.stop();
        if(req.op=="save") savestate([req](bool ok) { banana_quick::reply(req,ok?"ok":"failed"); });
        else banana_quick::reply(req,dc_loadstate_with_result(slot)?"ok":"failed");
        emu.start();
    } catch(const FlycastException& e) {
        banana_quick::reply(req,"failed");
        gui_stop_game(e.what());
    }
}

void gui_cycleSaveStateSlot(int step)
{''')
f="core/sdl/sdl.cpp"
rep(dc,f,"void input_sdl_handle()\n{\n\tbananaMenuEvent();","void gui_bananaQuick();\nvoid input_sdl_handle()\n{\n\tbananaMenuEvent();\n\tgui_bananaQuick();")
# DuckStation: emulation-thread native save/load/fast-forward; no GPU changes.
f="src/duckstation-nogui/nogui_host.cpp"
rep(duck,f,"static void BananaControls()\n{",'''#include "banana_quick.h"
static void BananaControls()
{''')
rep(duck,f,'  if (BananaMarker("BANANA_DUCK_RESET_FILE", true)) System::ResetSystem();','''  if (BananaMarker("BANANA_DUCK_RESET_FILE", true)) System::ResetSystem();
  banana_quick::Request req;
  if (banana_quick::read(req)) {
    if (!System::IsRunning() || FullscreenUI::HasActiveWindow()) banana_quick::reply(req,"blocked");
    else if (req.op=="fast") {
      System::SetFastForwardEnabled(!System::IsFastForwardEnabled());
      banana_quick::reply(req,System::IsFastForwardEnabled()?"fast_on":"fast_off");
    } else if (System::GetGameSerial().empty()) banana_quick::reply(req,"blocked");
    else {
      auto file=System::GetGameSaveStateFileName(System::GetGameSerial(),req.slot);
      if(req.op=="save") banana_quick::reply(req,System::SaveState(file.c_str(),true)?"ok":"failed");
      else if(!System::GetSaveStateInfo(System::GetGameSerial().c_str(),req.slot)) banana_quick::reply(req,"empty");
      else banana_quick::reply(req,System::LoadState(file.c_str())?"ok":"failed");
    }
  }''')
# Validate every anchor before modifying any retained engine tree.
for p,s in changes.items():
    p.write_text(s)
for root,dest in [(psp,"UI/banana_quick.h"),(dc,"core/ui/banana_quick.h"),(duck,"src/duckstation-nogui/banana_quick.h")]:
    shutil.copyfile(base/"banana_quick.h",root/dest)
print("NATIVE_QUICK_PATCH_PASS",len(changes),flush=True)
