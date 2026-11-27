#!/usr/bin/env python3
"""GPL legacy DuckStation: Banana DRM lease and native control bridge."""
from pathlib import Path
import subprocess
import sys
r=Path(sys.argv[1])
assert subprocess.check_output(["git","-C",str(r),"rev-parse","HEAD"],text=True).strip()=="bfa792ddbff11c102521124f235ccb310cac6e6a"
def rep(f,a,b,n=1):
    p=r/f;s=p.read_text();assert s.count(a)==n,(f,a[:100],s.count(a));p.write_text(s.replace(a,b))
f="src/duckstation-nogui/CMakeLists.txt"
rep(f,"if(USE_DRMKMS AND USE_EVDEV)","if(USE_DRMKMS)")
rep(f,"  target_include_directories(duckstation-nogui PRIVATE $"+ "{LIBEVDEV_INCLUDE_DIRS})\n  target_link_libraries(duckstation-nogui PRIVATE $"+ "{LIBEVDEV_LIBRARIES})\n","")
f="src/duckstation-nogui/vty_nogui_platform.h"
rep(f,"#include <libevdev/libevdev.h>\n","")
rep(f,"    struct libevdev* obj;\n","")
f="src/duckstation-nogui/vty_nogui_platform.cpp"
rep(f,"#include <linux/input-event-codes.h>","#include <linux/input.h>\n#include <sys/ioctl.h>")
rep(f,"  // not implemented\n}\n\nbool VTYNoGUIPlatform::ConfirmMessage","  Log_ErrorPrintf(\"%.*s: %.*s\", int(title.size()), title.data(), int(message.size()), message.data());\n}\n\nbool VTYNoGUIPlatform::ConfirmMessage")
p=r/f;s=p.read_text();a=s.index("void VTYNoGUIPlatform::OpenEVDevFDs()");b=s.index("std::optional<u32> VTYNoGUIPlatform::ConvertHostKeyboardStringToCode",a)
p.write_text(s[:a]+'''void VTYNoGUIPlatform::OpenEVDevFDs()
{
  for (int i = 0; i < 128; i++)
  {
    TinyString path;
    path.Format("/dev/input/event%d", i);
    int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) continue;
    unsigned char keys[(KEY_MAX + 8) / 8] = {};
    if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) < 0 ||
        !(keys[KEY_SPACE / 8] & (1u << (KEY_SPACE % 8))))
    { close(fd); continue; }
    m_evdev_keyboards.push_back({fd});
  }
}
void VTYNoGUIPlatform::CloseEVDevFDs()
{
  for (const EvDevKeyboard& kb : m_evdev_keyboards) close(kb.fd);
  m_evdev_keyboards.clear();
}
void VTYNoGUIPlatform::PollEvDevKeyboards()
{
  for (const EvDevKeyboard& kb : m_evdev_keyboards)
  {
    struct input_event ev;
    while (read(kb.fd, &ev, sizeof(ev)) == sizeof(ev))
      if (ev.type == EV_KEY && ev.value != 2)
        NoGUIHost::ProcessPlatformKeyEvent(static_cast<s32>(ev.code), ev.value == 1);
  }
}

'''+s[b:])
f="src/common/drm_display.cpp"
rep(f,"#include <cmath>","#include <cmath>\n#include <cstdlib>\n#include <cerrno>\n#include <climits>")
rep(f,"Log_SetChannel(DRMDisplay);",'''Log_SetChannel(DRMDisplay);
static bool HasBananaLease()
{
  const char* p = std::getenv("BANANA_DRM_LEASE_FD");
  return p && *p;
}
static int BananaDisplayFD()
{
  if (!HasBananaLease()) return -2;
  const char* value = std::getenv("BANANA_DRM_LEASE_FD");
  char* end = nullptr;
  errno = 0;
  const long fd = std::strtol(value, &end, 10);
  if (errno || *end || fd < 3 || fd > INT_MAX) return -1;
  return fcntl(static_cast<int>(fd), F_DUPFD_CLOEXEC, 3);
}
''')
rep(f,"  if (m_card_id < 0)\n  {","  if (HasBananaLease()) return TryOpeningCard(-1, 0, 0, 0.0f);\n  if (m_card_id < 0)\n  {")
rep(f,'  if (m_card_fd >= 0)\n    close(m_card_fd);\n\n  m_card_fd = open(TinyString::FromFormat("/dev/dri/card%d", card), O_RDWR);','''  if (m_card_fd >= 0) close(m_card_fd);
  if (m_connector) drmModeFreeConnector(m_connector);
  m_connector = nullptr;
  m_mode = nullptr;
  m_crtc_id = 0;
  m_card_fd = BananaDisplayFD();
  if (m_card_fd == -2)
    m_card_fd = open(TinyString::FromFormat("/dev/dri/card%d", card), O_RDWR | O_CLOEXEC);''')
rep(f,"if (next_connector->connection == DRM_MODE_CONNECTED)","if (next_connector && next_connector->connection == DRM_MODE_CONNECTED && next_connector->count_modes > 0)")
rep(f,"if (next_encoder->encoder_id == m_connector->encoder_id)","if (next_encoder && next_encoder->encoder_id == m_connector->encoder_id)")
rep(f,"      if (crtc_id != 0)","      if (crtc_id != 0 && crtc_id != static_cast<u32>(-1))")
rep(f,"  drmModeFreeResources(resources);\n\n  m_card_id = card;\n  m_prev_crtc = drmModeGetCrtc(m_card_fd, m_crtc_id);",'''  bool allowed = false;
  for (int i = 0; i < resources->count_crtcs; i++) allowed |= resources->crtcs[i] == m_crtc_id;
  if (!allowed)
  {
    m_crtc_id = find_crtc_for_connector(m_card_fd, resources, m_connector);
    for (int i = 0; i < resources->count_crtcs; i++) allowed |= resources->crtcs[i] == m_crtc_id;
  }
  drmModeFreeResources(resources);
  if (!allowed) return false;
  m_card_id = card;
  m_prev_crtc = HasBananaLease() ? nullptr : drmModeGetCrtc(m_card_fd, m_crtc_id);
  Log_InfoPrintf("Banana display: lease=%d connector=%u crtc=%u %ux%u",
                 HasBananaLease(), m_connector->connector_id, m_crtc_id, GetWidth(), GetHeight());''')
rep(f,"  int card_fd = -1;\n  if (card < 0)","  int card_fd = BananaDisplayFD();\n  if (HasBananaLease() && card_fd < 0) return false;\n  if (!HasBananaLease() && card < 0)")
rep(f,'  else\n  {\n    card_fd = open(TinyString::FromFormat("/dev/dri/card%d", card), O_RDWR);\n  }','  else if (!HasBananaLease())\n  {\n    card_fd = open(TinyString::FromFormat("/dev/dri/card%d", card), O_RDWR);\n  }')
rep(f,"      if (connector_ptr->connection == DRM_MODE_CONNECTED)\n        break;\n\n      drmModeFreeConnector(connector_ptr);","      if (connector_ptr && connector_ptr->connection == DRM_MODE_CONNECTED)\n        break;\n      drmModeFreeConnector(connector_ptr);\n      connector_ptr = nullptr;")
rep(f,"    int res = select(m_card_fd + 1, &fds, nullptr, nullptr, nullptr);","    timeval timeout{2, 0};\n    int res = select(m_card_fd + 1, &fds, nullptr, nullptr, &timeout);")
rep(f,'      Log_ErrorPrintf("select() failed: %d", errno);\n      break;','      if (errno == EINTR) continue;\n      Log_ErrorPrintf("select() failed: %d", errno);\n      std::abort();')
rep(f,"    else if (res == 0)\n    {\n      continue;\n    }",'    else if (res == 0)\n    {\n      Log_ErrorPrintf("Banana display flip timed out");\n      std::abort();\n    }')
f="src/common/gl/context_egl_gbm.cpp"
rep(f,"  struct gbm_bo* bo = gbm_surface_lock_front_buffer(m_fb_surface);\n","  struct gbm_bo* bo = gbm_surface_lock_front_buffer(m_fb_surface);\n  if (!bo) return nullptr;\n")
rep(f,"    Assert(m_num_buffers < MAX_BUFFERS);","    if (m_num_buffers >= MAX_BUFFERS) { gbm_surface_release_buffer(m_fb_surface, bo); return nullptr; }")
rep(f,"    if (!fb_id.has_value())\n      return nullptr;","    if (!fb_id.has_value()) { gbm_surface_release_buffer(m_fb_surface, bo); return nullptr; }")
rep(f,"    m_present_cv.wait(lock);","    m_present_cv.wait(lock, [this]() { return m_present_pending.load() || m_present_thread_shutdown.load(); });\n    if (m_present_thread_shutdown.load()) break;")
rep(f,"    const bool wait_for_vsync = m_vsync && m_current_present_buffer;","    if (!next_buffer) { m_present_pending.store(false); m_present_done_cv.notify_one(); continue; }\n    const bool wait_for_vsync = m_vsync && m_current_present_buffer;")
f="src/duckstation-nogui/nogui_host.cpp"
rep(f,"#include <thread>","#include <thread>\n#include <fstream>\n#include <cstdlib>\n#ifndef _WIN32\n#include <unistd.h>\n#endif")
rep(f,"static bool s_batch_mode = false;","static bool s_batch_mode = false;\nstatic bool s_banana_failure = false;\nstatic bool s_banana_paused = false;")
rep(f,"  Host::RunOnCPUThread([params = std::move(params)]() { System::BootSystem(std::move(params)); });",'''  Host::RunOnCPUThread([params = std::move(params)]() {
    if (!System::BootSystem(std::move(params)) && std::getenv("BANANA_DUCK_READY_FILE"))
    {
      s_banana_failure = true;
      s_running.store(false, std::memory_order_release);
    }
  });''')
rep(f,'    g_nogui_window->ReportError("Error", "Failed to open host display.");','    s_banana_failure = true;\n    g_nogui_window->ReportError("Error", "Failed to open host display.");')
rep(f,'  Log_VerbosePrintf("Host::OnSystemStarted()");','  Log_VerbosePrintf("Host::OnSystemStarted()");\n  if (const char* path = std::getenv("BANANA_DUCK_READY_FILE")) std::ofstream(path) << "ready\\n";')
rep(f,"void Host::PumpMessagesOnCPUThread()\n{",'''#ifndef _WIN32
static bool BananaMarker(const char* name, bool consume)
{
  const char* path = std::getenv(name);
  if (!path || access(path, F_OK) != 0) return false;
  return !consume || unlink(path) == 0;
}
static void BananaControls()
{
  static auto last = std::chrono::steady_clock::time_point{};
  const auto now = std::chrono::steady_clock::now();
  if (now - last < std::chrono::milliseconds(20)) return;
  last = now;
  if (BananaMarker("BANANA_SA_QUIT_FILE", true)) { Host::RequestExit(false); return; }
  if (!System::IsValid()) return;
  const bool want = BananaMarker("BANANA_SA_PAUSE_FILE", false);
  if (!want && s_banana_paused)
  {
    s_banana_paused = false;
    if (System::IsPaused() && !FullscreenUI::HasActiveWindow()) System::PauseSystem(false);
  }
  if (BananaMarker("BANANA_SA_MENU_FILE", true))
  {
    if (s_banana_paused)
    {
      s_banana_paused = false;
      if (System::IsPaused()) System::PauseSystem(false);
    }
    FullscreenUI::OpenPauseMenu();
  }
  if (BananaMarker("BANANA_DUCK_RESET_FILE", true)) System::ResetSystem();
  if (want && !s_banana_paused && System::IsRunning() && !FullscreenUI::HasActiveWindow())
  {
    s_banana_paused = true;
    System::PauseSystem(true);
  }
}
#endif
void Host::PumpMessagesOnCPUThread()
{
#ifndef _WIN32
  if (std::getenv("BANANA_DUCK_READY_FILE")) BananaControls();
#endif''')
rep(f,"  s_base_settings_interface.reset();\n  g_nogui_window.reset();\n  return EXIT_SUCCESS;","  s_base_settings_interface.reset();\n  g_nogui_window.reset();\n  return s_banana_failure ? EXIT_FAILURE : EXIT_SUCCESS;")
print("BANANA_DUCK_SOURCE_PATCH_PASS")
