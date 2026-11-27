#!/usr/bin/env python3
"""Apply v27 audio and Vulkan scanout changes to the v26 legacy source."""
from pathlib import Path
import sys
r=Path(sys.argv[1]); here=Path(__file__).resolve().parent
changes={}
def get(f):
    if f not in changes: changes[f]=(r/f).read_text()
    return changes[f]
def rep(f,a,b,n=1):
    s=get(f)
    assert s.count(a)==n,(f,a[:100],s.count(a))
    changes[f]=s.replace(a,b)
# SDL audio is compiled with the SDL input backend and uses the actual
# ring-buffer / time-stretch API of this legacy version.
rep("src/util/CMakeLists.txt","    sdl_input_source.cpp","    banana_sdl_audio.cpp\n    sdl_input_source.cpp")
rep("src/core/types.h","  Null,\n#ifdef WITH_CUBEB","  Null,\n#ifdef WITH_SDL2\n  SDL,\n#endif\n#ifdef WITH_CUBEB")
rep("src/core/settings.cpp",'  "Null",\n#ifdef WITH_CUBEB','  "Null",\n#ifdef WITH_SDL2\n  "SDL",\n#endif\n#ifdef WITH_CUBEB')
rep("src/core/settings.cpp",'  TRANSLATE_NOOP("AudioBackend", "Null (No Output)"),\n#ifdef WITH_CUBEB','  TRANSLATE_NOOP("AudioBackend", "Null (No Output)"),\n#ifdef WITH_SDL2\n  TRANSLATE_NOOP("AudioBackend", "SDL (ALSA)"),\n#endif\n#ifdef WITH_CUBEB')
rep("src/core/settings.h","  static constexpr AudioBackend DEFAULT_AUDIO_BACKEND = AudioBackend::Null;","#ifdef WITH_SDL2\n  static constexpr AudioBackend DEFAULT_AUDIO_BACKEND = AudioBackend::SDL;\n#else\n  static constexpr AudioBackend DEFAULT_AUDIO_BACKEND = AudioBackend::Null;\n#endif")
rep("src/util/audio_stream.h","  static std::unique_ptr<AudioStream> CreateNullStream(u32 sample_rate, u32 channels, u32 buffer_ms);","  static std::unique_ptr<AudioStream> CreateNullStream(u32 sample_rate, u32 channels, u32 buffer_ms);\n#ifdef WITH_SDL2\n  static std::unique_ptr<AudioStream> CreateSDLAudioStream(u32 rate,u32 channels,u32 ms,u32 latency,AudioStretchMode stretch);\n#endif")
rep("src/core/common_host.cpp","    case AudioBackend::Null:\n      return AudioStream::CreateNullStream","#ifdef WITH_SDL2\n    case AudioBackend::SDL:\n      return AudioStream::CreateSDLAudioStream(sample_rate, channels, buffer_ms, latency_ms, stretch);\n#endif\n    case AudioBackend::Null:\n      return AudioStream::CreateNullStream")
changes["src/util/banana_sdl_audio.cpp"]=(here/"banana_sdl_audio.cpp").read_text()
# Use the already verified v26 display lease selector. This does not
# change its OpenGL presentation behavior.
rep("src/common/drm_display.h","  int GetCardFD() const { return m_card_fd; }","  int GetCardFD() const { return m_card_fd; }\n  u32 GetCRTCID() const { return m_crtc_id; }\n  u32 GetConnectorID() const { return m_connector->connector_id; }\n  const drmModeModeInfo& GetMode() const { return *m_mode; }")
# Feature gated: other frontend/platform builds retain their standard WSI.
rep("src/common/CMakeLists.txt","  target_link_libraries(common PUBLIC Libdrm::Libdrm)","  target_link_libraries(common PUBLIC Libdrm::Libdrm)\n  if(ENABLE_VULKAN)\n    target_compile_definitions(common PUBLIC WITH_BANANA_DRM_VK=1)\n  endif()")
changes["src/common/vulkan/banana_scanout.h"]=(here/"banana_scanout.h").read_text()
f="src/common/vulkan/swap_chain.h"
rep(f,"namespace Vulkan {\n","namespace Vulkan {\n#ifdef WITH_BANANA_DRM_VK\nclass BananaScanout;\n#endif\n")
rep(f,"  VkResult AcquireNextImage();","""  VkResult AcquireNextImage();
#ifdef WITH_BANANA_DRM_VK
  bool IsBananaDrm() const { return bool(m_banana); }
  void BananaBarrier(VkCommandBuffer cb,bool acquire);
  bool BananaPresent(u32 index);
#endif""")
rep(f,"  u32 m_current_image = 0;","""#ifdef WITH_BANANA_DRM_VK
  std::unique_ptr<BananaScanout> m_banana;
#endif
  u32 m_current_image = 0;""")
f="src/common/vulkan/swap_chain.cpp"
rep(f,'#include "util.h"','#include "util.h"\n#ifdef WITH_BANANA_DRM_VK\n#include "banana_scanout.h"\n#endif')
rep(f,"  if (!swap_chain->CreateSwapChain() || !swap_chain->SetupSwapChainImages() || !swap_chain->CreateSemaphores())","""#ifdef WITH_BANANA_DRM_VK
  if(surface == VK_NULL_HANDLE && std::getenv("BANANA_DUCK_VK_DRM")) {
    swap_chain->m_banana=std::make_unique<BananaScanout>();
    if(!swap_chain->m_banana->Create(swap_chain->m_window_info)) return nullptr;
    swap_chain->m_surface_format={VK_FORMAT_R8G8B8A8_UNORM,VK_COLOR_SPACE_SRGB_NONLINEAR_KHR};
    if(!swap_chain->SetupSwapChainImages()) return nullptr;
    return swap_chain;
  }
#endif
  if (!swap_chain->CreateSwapChain() || !swap_chain->SetupSwapChainImages() || !swap_chain->CreateSemaphores())""")
a=get(f).index("  u32 image_count;\n",get(f).index("bool SwapChain::SetupSwapChainImages()"))
b=get(f).index("  m_load_render_pass",a)
changes[f]=get(f)[:a]+"""  std::vector<VkImage> images;
#ifdef WITH_BANANA_DRM_VK
  if(m_banana) images=m_banana->Images();
  else
#endif
  {
    u32 image_count=0;
    VkResult res=vkGetSwapchainImagesKHR(g_vulkan_context->GetDevice(),m_swap_chain,&image_count,nullptr);
    if(res!=VK_SUCCESS || image_count==0) return false;
    images.resize(image_count);
    res=vkGetSwapchainImagesKHR(g_vulkan_context->GetDevice(),m_swap_chain,&image_count,images.data());
    if(res!=VK_SUCCESS) return false;
  }
  const u32 image_count=static_cast<u32>(images.size());

"""+get(f)[b:]
# Avoid deferred destruction of views on imported images, and cleanup partial
# initialization if creating a framebuffer fails.
rep(f,"    if (image.framebuffer == VK_NULL_HANDLE)\n      return false;","    if (image.framebuffer == VK_NULL_HANDLE) {\n      image.texture.Destroy(false);\n      return false;\n    }")
rep(f,"    vkDestroyFramebuffer(g_vulkan_context->GetDevice(), it.framebuffer, nullptr);","    vkDestroyFramebuffer(g_vulkan_context->GetDevice(), it.framebuffer, nullptr);\n#ifdef WITH_BANANA_DRM_VK\n    if(m_banana) it.texture.Destroy(false);\n#endif")
rep(f,"void SwapChain::DestroySwapChain()\n{","void SwapChain::DestroySwapChain()\n{\n#ifdef WITH_BANANA_DRM_VK\n  if(m_banana) {m_banana.reset();return;}\n#endif")
rep(f,"VkResult SwapChain::AcquireNextImage()\n{","""#ifdef WITH_BANANA_DRM_VK
void SwapChain::BananaBarrier(VkCommandBuffer cb,bool acquire) {
  m_banana->Barrier(cb,m_current_image,acquire);
  GetCurrentTexture().OverrideImageLayout(acquire?VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL:VK_IMAGE_LAYOUT_GENERAL);
}
bool SwapChain::BananaPresent(u32 index) {return m_banana->Present(index);}
#endif
VkResult SwapChain::AcquireNextImage()
{
#ifdef WITH_BANANA_DRM_VK
  if(m_banana) {
    if(!m_banana->Acquire()) {Log_ErrorPrint("Banana Vulkan scanout timed out");std::abort();}
    m_current_image=(m_current_image+1)%GetImageCount();
    return VK_SUCCESS;
  }
#endif""")
rep(f,"bool SwapChain::ResizeSwapChain(u32 new_width /* = 0 */, u32 new_height /* = 0 */)\n{","bool SwapChain::ResizeSwapChain(u32 new_width /* = 0 */, u32 new_height /* = 0 */)\n{\n#ifdef WITH_BANANA_DRM_VK\n  if(m_banana) return true; // physical DSI mode is fixed\n#endif")
rep(f,"bool SwapChain::RecreateSwapChain()\n{","bool SwapChain::RecreateSwapChain()\n{\n#ifdef WITH_BANANA_DRM_VK\n  if(m_banana) return true;\n#endif")
rep(f,"bool SwapChain::RecreateSurface(const WindowInfo& new_wi)\n{","bool SwapChain::RecreateSurface(const WindowInfo& new_wi)\n{\n#ifdef WITH_BANANA_DRM_VK\n  if(m_banana) return new_wi.type==WindowInfo::Type::Display;\n#endif")
rep(f,"  if (wi.type == WindowInfo::Type::Display)\n    return GetDisplayModes(instance, physical_device, wi);","""#ifdef WITH_BANANA_DRM_VK
  if(std::getenv("BANANA_DUCK_VK_DRM")) return {};
#endif
  if (wi.type == WindowInfo::Type::Display)
    return GetDisplayModes(instance, physical_device, wi);""")
# Device creation and extension checks. The proprietary Mali runtime is
# Vulkan 1.1; no VK_KHR_display or window-system swapchain is needed.
f="src/common/vulkan/context.cpp"
rep(f,'#include "swap_chain.h"','#include "swap_chain.h"\n#include <cstdlib>')
rep(f,"  // Common extensions\n","""#ifdef WITH_BANANA_DRM_VK
  if(wi && wi->type==WindowInfo::Type::Display && std::getenv("BANANA_DUCK_VK_DRM")) wi=nullptr;
#endif
  // Common extensions
""")
rep(f,"  const bool enable_surface = (wi && wi->type != WindowInfo::Type::Surfaceless);","""  const bool banana_display =
#ifdef WITH_BANANA_DRM_VK
    wi && wi->type==WindowInfo::Type::Display && std::getenv("BANANA_DUCK_VK_DRM");
#else
    false;
#endif
  const bool enable_surface = (wi && wi->type != WindowInfo::Type::Surfaceless && !banana_display);""")
rep(f,"(enable_surface && (*out_swap_chain = SwapChain::Create(wi_copy, surface, vsync)) == nullptr)","((enable_surface || banana_display) && (*out_swap_chain = SwapChain::Create(wi_copy, surface, vsync)) == nullptr)")
rep(f,"  m_optional_extensions.vk_ext_memory_budget =","""#ifdef WITH_BANANA_DRM_VK
  if(std::getenv("BANANA_DUCK_VK_DRM")) {
    if(!SupportsExtension(VK_KHR_EXTERNAL_MEMORY_FD_EXTENSION_NAME,true) ||
       !SupportsExtension(VK_EXT_EXTERNAL_MEMORY_DMA_BUF_EXTENSION_NAME,true) ||
       !SupportsExtension(VK_EXT_IMAGE_DRM_FORMAT_MODIFIER_EXTENSION_NAME,true)) return false;
    SupportsExtension(VK_EXT_QUEUE_FAMILY_FOREIGN_EXTENSION_NAME,false);
    SupportsExtension(VK_KHR_IMAGE_FORMAT_LIST_EXTENSION_NAME,false);
  }
#endif
  m_optional_extensions.vk_ext_memory_budget =""")
# Reuse the original context present thread. It already serializes work and
# protects the frame resource fence from reuse while a present is queued.
f="src/common/vulkan/context.h"
rep(f,"uint32_t present_image_index = 0xFFFFFFFF, bool submit_on_thread = false);","uint32_t present_image_index = 0xFFFFFFFF, bool submit_on_thread = false, SwapChain* banana_chain=nullptr);")
rep(f,"  void DoPresent(VkSemaphore wait_semaphore, VkSwapchainKHR present_swap_chain, uint32_t present_image_index);","  void DoPresent(VkSemaphore wait_semaphore, VkSwapchainKHR present_swap_chain, uint32_t present_image_index);\n  void DoBananaPresent(SwapChain* chain,u32 frame,u32 image);")
rep(f,"    u32 present_image_index;\n  };","    u32 present_image_index;\n    SwapChain* banana_chain;\n  };")
f="src/common/vulkan/context.cpp"
rep(f,"bool submit_on_thread /* = false */)","bool submit_on_thread /* = false */, SwapChain* banana_chain)")
rep(f,"    if (present_swap_chain != VK_NULL_HANDLE)\n      DoPresent(signal_semaphore, present_swap_chain, present_image_index);","    if(banana_chain) DoBananaPresent(banana_chain,m_current_frame,present_image_index);\n    else if (present_swap_chain != VK_NULL_HANDLE)\n      DoPresent(signal_semaphore, present_swap_chain, present_image_index);")
rep(f,"  m_queued_present.command_buffer_index = m_current_frame;","  m_queued_present.command_buffer_index = m_current_frame;\n  m_queued_present.banana_chain=banana_chain;")
rep(f,"void Vulkan::Context::DoPresent(VkSemaphore wait_semaphore, VkSwapchainKHR present_swap_chain,","""void Vulkan::Context::DoBananaPresent(SwapChain* chain,u32 frame,u32 image)
{
#ifdef WITH_BANANA_DRM_VK
  const VkFence fence=m_frame_resources[frame].fence;
  if(vkWaitForFences(m_device,1,&fence,VK_TRUE,2000000000ULL)!=VK_SUCCESS || !chain->BananaPresent(image)) {
    Log_ErrorPrint("Banana Vulkan scanout failed");
    std::abort(); // supervisor restores the display and GPU driver
  }
#endif
}
void Vulkan::Context::DoPresent(VkSemaphore wait_semaphore, VkSwapchainKHR present_swap_chain,""")
rep(f,"    DoPresent(m_queued_present.signal_semaphore, m_queued_present.present_swap_chain,\n              m_queued_present.present_image_index);","""    if(m_queued_present.banana_chain)
      DoBananaPresent(m_queued_present.banana_chain,m_queued_present.command_buffer_index,m_queued_present.present_image_index);
    else if(m_queued_present.present_swap_chain!=VK_NULL_HANDLE)
      DoPresent(m_queued_present.signal_semaphore, m_queued_present.present_swap_chain,
                m_queued_present.present_image_index);""")
f="src/util/vulkan_host_display.cpp"
rep(f,"    swap_chain_texture.OverrideImageLayout(VK_IMAGE_LAYOUT_UNDEFINED);\n    swap_chain_texture.TransitionToLayout(cmdbuffer, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);","""#ifdef WITH_BANANA_DRM_VK
    if(m_swap_chain->IsBananaDrm()) m_swap_chain->BananaBarrier(cmdbuffer,true);
    else
#endif
    {
      swap_chain_texture.OverrideImageLayout(VK_IMAGE_LAYOUT_UNDEFINED);
      swap_chain_texture.TransitionToLayout(cmdbuffer, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL);
    }""")
rep(f,"    swap_chain_texture.TransitionToLayout(cmdbuffer, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR);","""#ifdef WITH_BANANA_DRM_VK
    if(m_swap_chain->IsBananaDrm()) m_swap_chain->BananaBarrier(cmdbuffer,false);
    else
#endif
      swap_chain_texture.TransitionToLayout(cmdbuffer, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR);""")
rep(f,"  g_vulkan_context->SubmitCommandBuffer(m_swap_chain->GetImageAvailableSemaphore(),","""#ifdef WITH_BANANA_DRM_VK
  if(m_swap_chain->IsBananaDrm())
    g_vulkan_context->SubmitCommandBuffer(VK_NULL_HANDLE,VK_NULL_HANDLE,VK_NULL_HANDLE,
        m_swap_chain->GetCurrentImageIndex(),g_settings.gpu_threaded_presentation,m_swap_chain.get());
  else
#endif
  g_vulkan_context->SubmitCommandBuffer(m_swap_chain->GetImageAvailableSemaphore(),""")
# Prevent live GPU API switches across the mutually exclusive kernel driver
# sessions. Native settings are still persisted for the next launch.
f="src/core/settings.cpp"
rep(f,"#include \"settings.h\"","#include \"settings.h\"\n#include <cstdlib>")
rep(f,"  gpu_adapter = si.GetStringValue(\"GPU\", \"Adapter\", \"\");","""#ifdef WITH_BANANA_DRM_VK
  if(const char* backend=std::getenv("BANANA_DUCK_RENDERER"))
    gpu_renderer=ParseRendererName(backend).value_or(gpu_renderer);
#endif
  gpu_adapter = si.GetStringValue("GPU", "Adapter", "");""")
# All preconditions have passed before editing a source file.
for f,s in changes.items():
    (r/f).write_text(s)
print("V27_NATIVE_PATCH_PASS",len(changes),flush=True)
