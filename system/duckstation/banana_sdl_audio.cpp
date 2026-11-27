// SPDX-License-Identifier: GPL-3.0-or-later
// SDL2 ALSA output for Banana's legacy DuckStation build.
#include "audio_stream.h"
#include "common/log.h"
#include <SDL.h>
#include <algorithm>
#include <cstring>
Log_SetChannel(BananaSDLAudio);
namespace {
class SDLAudio final : public AudioStream {
  SDL_AudioDeviceID device = 0;
  bool initialized = false;
  std::atomic<u32> volume{100};
  static void Callback(void* userdata, Uint8* bytes, int len) {
    auto& self = *static_cast<SDLAudio*>(userdata);
    const u32 frame_bytes = self.m_channels * sizeof(s16);
    const u32 frames = static_cast<u32>(len) / frame_bytes;
    auto* samples = reinterpret_cast<s16*>(bytes);
    self.ReadFrames(samples, frames);
    const u32 vol = self.volume.load(std::memory_order_relaxed);
    if (vol != 100) {
      for (u32 i=0; i<frames*self.m_channels; i++)
        samples[i]=static_cast<s16>(std::clamp<int>(static_cast<int>(samples[i])*static_cast<int>(vol)/100,-32768,32767));
    }
    std::memset(bytes+frames*frame_bytes,0,len-frames*frame_bytes);
  }
public:
  SDLAudio(u32 rate,u32 channels,u32 ms,AudioStretchMode stretch)
    : AudioStream(rate,channels,ms,stretch) {}
  ~SDLAudio() override {
    if (device) SDL_CloseAudioDevice(device);
    if (initialized) SDL_QuitSubSystem(SDL_INIT_AUDIO);
  }
  bool Initialize(u32 latency) {
    if (SDL_InitSubSystem(SDL_INIT_AUDIO)!=0) {
      Log_ErrorPrintf("SDL audio init failed: %s",SDL_GetError()); return false;
    }
    initialized=true;
    SDL_AudioSpec want{},got{};
    want.freq=static_cast<int>(m_sample_rate);
    want.format=AUDIO_S16SYS;
    want.channels=static_cast<Uint8>(m_channels);
    u32 frames=std::clamp<u32>((latency?latency:25)*m_sample_rate/1000,256,4096);
    u32 samples=256; while(samples<frames && samples<4096) samples*=2;
    want.samples=static_cast<Uint16>(samples);
    want.callback=Callback;
    want.userdata=this;
    device=SDL_OpenAudioDevice(nullptr,0,&want,&got,SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    if (!device) { Log_ErrorPrintf("SDL audio open failed: %s",SDL_GetError()); return false; }
    if(got.format!=want.format || got.freq!=want.freq || got.channels!=want.channels) {
      Log_ErrorPrintf("SDL audio format mismatch"); return false;
    }
    BaseInitialize();
    m_volume=100;
    m_paused=true;
    Log_InfoPrintf("BANANA SDL audio active: driver=%s rate=%d channels=%u samples=%u",
      SDL_GetCurrentAudioDriver(),got.freq,got.channels,got.samples);
    return true;
  }
  void SetPaused(bool paused) override {
    if (!device || paused==m_paused) return;
    SDL_PauseAudioDevice(device,paused?1:0);
    m_paused=paused;
  }
  void SetOutputVolume(u32 v) override {
    volume.store(std::min(v,100u),std::memory_order_relaxed);
    m_volume=std::min(v,100u);
  }
};
}
std::unique_ptr<AudioStream> AudioStream::CreateSDLAudioStream(u32 rate,u32 channels,u32 ms,u32 latency,AudioStretchMode stretch) {
  auto stream=std::make_unique<SDLAudio>(rate,channels,ms,stretch);
  if(!stream->Initialize(latency)) return {};
  return stream;
}
