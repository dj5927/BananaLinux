// SPDX-License-Identifier: GPL-3.0-or-later
// Imported scanout buffers for Banana RG DS / Plus. No CPU pixel copying.
#pragma once
#include "../drm_display.h"
#include "context.h"
#include "../log.h"
#include <drm_fourcc.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <unistd.h>
#include <array>
#include <cerrno>
#include <chrono>
#include <cstdlib>
#include <cstdio>

namespace Vulkan {
class BananaScanout {
  DRMDisplay display{-1};
  struct Buffer { u32 handle=0,fb=0; VkImage image=VK_NULL_HANDLE; VkDeviceMemory memory=VK_NULL_HANDLE; bool used=false; };
  std::array<Buffer,3> buffers{};
  bool modeset=false, pending=false;
  std::chrono::steady_clock::time_point flip_deadline{};
  bool foreign=false;
  static void FlipDone(int,unsigned,unsigned,unsigned,void* p) { *static_cast<bool*>(p)=false; }
  bool WaitFlip() {
    if(!pending) return true;
    drmEventContext ec{};ec.version=2;ec.page_flip_handler=FlipDone;
    const auto until=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    while(pending && std::chrono::steady_clock::now()<until) {
      pollfd p{display.GetCardFD(),POLLIN,0};int r=poll(&p,1,100);
      if(r<0 && errno==EINTR) continue;
      if(r<0 || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) return false;
      if(r>0 && drmHandleEvent(display.GetCardFD(),&ec)!=0) return false;
    }
    return !pending;
  }
  static bool Check(VkResult r,const char* what) {
    if(r==VK_SUCCESS) return true;
    std::fprintf(stderr,"BANANA_DUCK_VK %s failed: %d\n",what,int(r));return false;
  }
public:
  ~BananaScanout() {
    // VulkanHostDisplay waits for GPU work and destroys the image views first.
    if(modeset) {
      WaitFlip();
      if(!std::getenv("BANANA_DRM_LEASE_FD")) display.RestoreBuffer();
      else drmModeSetCrtc(display.GetCardFD(),display.GetCRTCID(),0,0,0,nullptr,0,nullptr);
    }
    const auto device=g_vulkan_context->GetDevice();
    for(auto& b:buffers) {
      if(b.fb) drmModeRmFB(display.GetCardFD(),b.fb);
      if(b.image) vkDestroyImage(device,b.image,nullptr);
      if(b.memory) vkFreeMemory(device,b.memory,nullptr);
      if(b.handle) { drm_mode_destroy_dumb d{};d.handle=b.handle;ioctl(display.GetCardFD(),DRM_IOCTL_MODE_DESTROY_DUMB,&d); }
    }
  }
  bool Create(WindowInfo& wi) {
    if(!display.Initialize(0,0,0)) return false;
    const u32 w=display.GetWidth(),h=display.GetHeight();
    if(!((w==640 && h==480)||(w==1024 && h==768))) return false;
    wi.surface_width=w;wi.surface_height=h;
    auto device=g_vulkan_context->GetDevice();
    const auto getprops=reinterpret_cast<PFN_vkGetMemoryFdPropertiesKHR>(vkGetDeviceProcAddr(device,"vkGetMemoryFdPropertiesKHR"));
    if(!getprops) return false;
    u32 n=0;
    const auto phys=g_vulkan_context->GetPhysicalDevice();
    if(vkEnumerateDeviceExtensionProperties(phys,nullptr,&n,nullptr)!=VK_SUCCESS) return false;
    std::vector<VkExtensionProperties> exts(n);
    if(vkEnumerateDeviceExtensionProperties(phys,nullptr,&n,exts.data())!=VK_SUCCESS) return false;
    for(auto& e:exts) if(std::strcmp(e.extensionName,VK_EXT_QUEUE_FAMILY_FOREIGN_EXTENSION_NAME)==0) foreign=true;
    for(auto& b:buffers) {
      drm_mode_create_dumb bo{};bo.width=w;bo.height=h;bo.bpp=32;
      if(ioctl(display.GetCardFD(),DRM_IOCTL_MODE_CREATE_DUMB,&bo)!=0) return false;
      b.handle=bo.handle;
      VkSubresourceLayout layout{};layout.rowPitch=bo.pitch;
      VkImageDrmFormatModifierExplicitCreateInfoEXT mod{};
      mod.sType=VK_STRUCTURE_TYPE_IMAGE_DRM_FORMAT_MODIFIER_EXPLICIT_CREATE_INFO_EXT;
      mod.drmFormatModifier=0;mod.drmFormatModifierPlaneCount=1;mod.pPlaneLayouts=&layout;
      VkExternalMemoryImageCreateInfo ext{};ext.sType=VK_STRUCTURE_TYPE_EXTERNAL_MEMORY_IMAGE_CREATE_INFO;
      ext.pNext=&mod;ext.handleTypes=VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;
      VkImageCreateInfo ci{};ci.sType=VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO;ci.pNext=&ext;
      ci.imageType=VK_IMAGE_TYPE_2D;ci.format=VK_FORMAT_R8G8B8A8_UNORM;
      ci.extent={w,h,1};ci.mipLevels=1;ci.arrayLayers=1;ci.samples=VK_SAMPLE_COUNT_1_BIT;
      ci.tiling=VK_IMAGE_TILING_DRM_FORMAT_MODIFIER_EXT;
      ci.usage=VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT|VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_TRANSFER_DST_BIT;
      ci.sharingMode=VK_SHARING_MODE_EXCLUSIVE;
      if(!Check(vkCreateImage(device,&ci,nullptr,&b.image),"create scanout image")) return false;
      VkMemoryRequirements req{};vkGetImageMemoryRequirements(device,b.image,&req);
      int dma=-1;
      if(drmPrimeHandleToFD(display.GetCardFD(),b.handle,DRM_CLOEXEC|DRM_RDWR,&dma)!=0) return false;
      VkMemoryFdPropertiesKHR props{};props.sType=VK_STRUCTURE_TYPE_MEMORY_FD_PROPERTIES_KHR;
      auto res=getprops(device,VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT,dma,&props);
      if(res!=VK_SUCCESS) {close(dma);Check(res,"dma properties");return false;}
      u32 bits=req.memoryTypeBits&props.memoryTypeBits;
      if(!bits||req.size>bo.size) {close(dma);return false;}
      u32 type=0;while(!(bits&(1u<<type))) ++type;
      VkMemoryDedicatedAllocateInfo dedicated{};dedicated.sType=VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO;dedicated.image=b.image;
      VkImportMemoryFdInfoKHR import{};import.sType=VK_STRUCTURE_TYPE_IMPORT_MEMORY_FD_INFO_KHR;import.pNext=&dedicated;
      import.handleType=VK_EXTERNAL_MEMORY_HANDLE_TYPE_DMA_BUF_BIT_EXT;import.fd=dma;
      VkMemoryAllocateInfo ai{};ai.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO;ai.pNext=&import;
      ai.allocationSize=req.size;ai.memoryTypeIndex=type;
      res=vkAllocateMemory(device,&ai,nullptr,&b.memory);
      if(res!=VK_SUCCESS) {close(dma);Check(res,"import dma memory");return false;}
      if(!Check(vkBindImageMemory(device,b.image,b.memory,0),"bind dma memory")) return false;
      u32 handles[4]={b.handle},pitches[4]={bo.pitch},offsets[4]={0};
      uint64_t mods[4]={0};
      if(drmModeAddFB2WithModifiers(display.GetCardFD(),w,h,DRM_FORMAT_ABGR8888,handles,pitches,offsets,mods,&b.fb,DRM_MODE_FB_MODIFIERS)!=0) return false;
    }
    std::fprintf(stderr,"BANANA_DUCK_VK imported 3 scanout buffers %ux%u\n",w,h);
    return true;
  }
  std::vector<VkImage> Images() const {return {buffers[0].image,buffers[1].image,buffers[2].image};}
  bool Acquire() {return WaitFlip();}
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
  }
  void Barrier(VkCommandBuffer cb,u32 idx,bool acquire) {
    auto& b=buffers.at(idx);
    VkImageMemoryBarrier bi{};bi.sType=VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER;
    bi.image=b.image;bi.subresourceRange={VK_IMAGE_ASPECT_COLOR_BIT,0,1,0,1};
    bi.oldLayout=acquire?(b.used?VK_IMAGE_LAYOUT_GENERAL:VK_IMAGE_LAYOUT_UNDEFINED):VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
    bi.newLayout=acquire?VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL:VK_IMAGE_LAYOUT_GENERAL;
    const u32 q=g_vulkan_context->GetGraphicsQueueFamilyIndex();
    const u32 outside=foreign?VK_QUEUE_FAMILY_FOREIGN_EXT:VK_QUEUE_FAMILY_EXTERNAL;
    bi.srcQueueFamilyIndex=acquire?outside:q;bi.dstQueueFamilyIndex=acquire?q:outside;
    bi.srcAccessMask=acquire?0:VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT;
    bi.dstAccessMask=acquire?(VK_ACCESS_COLOR_ATTACHMENT_READ_BIT|VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT):0;
    vkCmdPipelineBarrier(cb,acquire?VK_PIPELINE_STAGE_TOP_OF_PIPE_BIT:VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT,
      acquire?VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT:VK_PIPELINE_STAGE_BOTTOM_OF_PIPE_BIT,0,0,nullptr,0,nullptr,1,&bi);
    b.used=true;
  }
  bool Present(u32 idx) {
    if(!WaitFlip()) return false;
    const u32 fb=buffers.at(idx).fb;
    if(!modeset) {
      u32 c=display.GetConnectorID();drmModeModeInfo mode=display.GetMode();
      if(drmModeSetCrtc(display.GetCardFD(),display.GetCRTCID(),fb,0,0,&c,1,&mode)!=0) return false;
      modeset=true;
    } else {
      if(drmModePageFlip(display.GetCardFD(),display.GetCRTCID(),fb,DRM_MODE_PAGE_FLIP_EVENT,&pending)!=0) return false;
      pending=true;
      flip_deadline=std::chrono::steady_clock::now()+std::chrono::seconds(2);
    }
    return true;
  }
};
}
