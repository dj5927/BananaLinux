#!/usr/bin/env python3
"""Remove display-vblank backpressure only during accelerated gameplay."""
from pathlib import Path
dc=Path("/var/tmp/banana-v20-sources/easycast")
du=Path("/var/tmp/banana-v26-duck/duckstation")
changes={}
def rep(root,f,a,b):
    p=root/f
    s=changes.get(p,p.read_text())
    assert s.count(a)==1,(str(p),a[:80],s.count(a))
    changes[p]=s.replace(a,b)
# Flycast: only the producer submits images; worker can only free them.
# Do not recycle an image before the actual flip event/GPU fence.
rep(dc,"core/rend/vulkan/async_present.h",
    "\t// render thread: before reusing an image for a new frame",
    """    // Fast-forward may drop only presentation, never reuse a busy scanout.
    bool canSubmit(unsigned index)
    {
        std::lock_guard<std::mutex> lk(m);
        // Let the normal Present() error recovery run if the worker failed.
        return failed || !inUse[index % MAX];
    }

\t// render thread: before reusing an image for a new frame""")
rep(dc,"core/rend/vulkan/vulkan_context.cpp",
    "\tlastFrameAR = aspectRatio;\n\n\tif (imageView && IsValid())",
    """\tlastFrameAR = aspectRatio;

    // A 60 Hz panel cannot display every frame of a fast-forwarded game.
    // Skip the scanout pass if the next image is still queued/on screen.
    // Normal speed, menus, fences, buffer ownership and renderer stay unchanged.
    if (easycastDrm && EasycastAsyncPresent::enabled() && !gui_is_open()
        && settings.input.fastForwardMode && IsValid() && GetSwapChainSize()>0
        && !easycastAsync.canSubmit((currentImage+1)%GetSwapChainSize()))
        return;

\tif (imageView && IsValid())""")
# Independent emulated vblank counter (not a made-up display FPS).
rep(dc,"core/emulator.cpp",
    "void Emulator::vblank()\n{\n\tEventManager::event(Event::VBlank);",
    """std::atomic<uint64_t> bananaVblankCount{0};
void Emulator::vblank()
{
    bananaVblankCount.fetch_add(1,std::memory_order_relaxed);
\tEventManager::event(Event::VBlank);""")
rep(dc,"core/ui/gui.cpp",
    "static float fps = -1;",
    """static float fps = -1;
extern std::atomic<uint64_t> bananaVblankCount;
static uint64_t bananaLastVblank=0;
static float bananaVps=-1;
static bool bananaWasFast=false;""")
rep(dc,"core/ui/gui.cpp",
    """\t\tif (now - LastFPSTime >= 1000) {
\t\t\tfps = ((float)MainFrameCount - lastFrameCount) * 1000.f / (now - LastFPSTime);
\t\t\tLastFPSTime = now;
\t\t\tlastFrameCount = MainFrameCount;
\t\t}""",
    """        const uint64_t vb=bananaVblankCount.load(std::memory_order_relaxed);
        const bool fast=settings.input.fastForwardMode;
        if (!LastFPSTime || bananaWasFast!=fast) {
            LastFPSTime=now;lastFrameCount=MainFrameCount;bananaLastVblank=vb;
            fps=bananaVps=-1;bananaWasFast=fast;
        } else if (now - LastFPSTime >= 1000) {
            fps = ((float)MainFrameCount - lastFrameCount) * 1000.f / (now - LastFPSTime);
            bananaVps = float(vb-bananaLastVblank)*1000.f/(now-LastFPSTime);
            LastFPSTime = now;lastFrameCount = MainFrameCount;bananaLastVblank=vb;
        }""")
rep(dc,"core/ui/gui.cpp",
    """\t\t\tchar text[32];
\t\t\tsnprintf(text, sizeof(text), "F:%4.1f%s", fps, settings.input.fastForwardMode ? " >>" : "");""",
    """            char text[64];
            if(settings.input.fastForwardMode && bananaVps>=0)
                snprintf(text,sizeof(text),"F:%4.1f V:%4.1f >>",fps,bananaVps);
            else snprintf(text,sizeof(text),"F:%4.1f",fps);""")
# DuckStation: keep actual DRM page flips synchronized, but do not block
# emulation on a queued presentation or pending flip in FF/turbo.
rep(du,"src/common/vulkan/context.h","  void WaitForPresentComplete();",
    """  void WaitForPresentComplete();
  bool IsPresentComplete() const { return m_present_done.load(); }""")
rep(du,"src/common/vulkan/banana_scanout.h",
    "  bool modeset=false, pending=false;",
    """  bool modeset=false, pending=false;
  std::chrono::steady_clock::time_point flip_deadline{};""")
rep(du,"src/common/vulkan/banana_scanout.h",
    "  bool Acquire() {return WaitFlip();}",
    """  bool Acquire() {return WaitFlip();}
  // Called by the CPU thread only after the present worker signals completion.
  // Do not spin/wait on the panel. A timed-out/error flip falls back to the
  // existing bounded blocking acquire/error path instead of hiding a failure.
  bool ReadyWithoutWait() {
    if(!pending) return true;
    if(std::chrono::steady_clock::now()>=flip_deadline) return true;
    pollfd p{display.GetCardFD(),POLLIN,0};
    const int r=poll(&p,1,0);
    if(r<0 && errno==EINTR) return false;
    if(r<0 || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) return true;
    if(!(p.revents&POLLIN)) return false;
    drmEventContext ec{};ec.version=2;ec.page_flip_handler=FlipDone;
    if(drmHandleEvent(display.GetCardFD(),&ec)!=0) return true;
    return !pending;
  }""")
rep(du,"src/common/vulkan/banana_scanout.h",
    "      pending=true;",
    """      pending=true;
      flip_deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);""")
rep(du,"src/common/vulkan/swap_chain.h",
    "  bool BananaPresent(u32 index);",
    """  bool BananaPresent(u32 index);
  bool BananaReadyWithoutWait();""")
rep(du,"src/common/vulkan/swap_chain.cpp",
    "bool SwapChain::BananaPresent(u32 index) {return m_banana->Present(index);}",
    """bool SwapChain::BananaPresent(u32 index) {return m_banana->Present(index);}
bool SwapChain::BananaReadyWithoutWait() {return m_banana->ReadyWithoutWait();}""")
rep(du,"src/util/vulkan_host_display.cpp",
    '#include "core/common_host.h"',
    '#include "core/common_host.h"\n#include "core/system.h"\n#include "core/fullscreen_ui.h"')
rep(du,"src/util/vulkan_host_display.cpp",
    "bool VulkanHostDisplay::Render(bool skip_present)\n{\n  if (skip_present || !m_swap_chain)",
    """bool VulkanHostDisplay::Render(bool skip_present)
{
#ifdef WITH_BANANA_DRM_VK
  if (!skip_present && m_swap_chain && m_swap_chain->IsBananaDrm() &&
      System::IsRunning() && (System::IsFastForwardEnabled() || System::IsTurboEnabled()) &&
      !FullscreenUI::HasActiveWindow())
    skip_present = !g_vulkan_context->IsPresentComplete() || !m_swap_chain->BananaReadyWithoutWait();
#endif
  if (skip_present || !m_swap_chain)""")
# Non-Vulkan fallback: use the existing frame-skip/pacing API when accelerated,
# since the DRM EGL swap path can still synchronize to physical refresh.
rep(du,"src/core/system.cpp","#include <cctype>","#include <cctype>\n#include <cstdlib>\n#include <algorithm>")
rep(du,"src/core/system.cpp",
    "  const float max_display_fps = (s_throttler_enabled || s_syncing_to_host) ? 0.0f : g_settings.display_max_fps;",
    """  float max_display_fps = (s_throttler_enabled || s_syncing_to_host) ? 0.0f : g_settings.display_max_fps;
  if (std::getenv("BANANA_DUCK_RENDERER") && (s_fast_forward_enabled || s_turbo_enabled) &&
      (s_target_speed==0.0f || s_target_speed>1.05f) &&
      g_host_display->GetRenderAPI()!=RenderAPI::Vulkan)
  {
    float refresh=60.0f;
    if (!g_host_display->GetHostRefreshRate(&refresh) || refresh<30.0f || refresh>240.0f) refresh=60.0f;
    max_display_fps=max_display_fps>0.0f?std::min(max_display_fps,refresh):refresh;
  }""")
for p,s in changes.items():
    p.write_text(s)
print("SPEED_PATCH_PASS",len(changes))
