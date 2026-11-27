// Run the exact ARM64 SDL backend against SDL's dummy audio device.
#include "util/audio_stream.h"
#include <SDL.h>
#include <cassert>
#include <cstdio>
#include <algorithm>
int main() {
  SDL_setenv("SDL_AUDIODRIVER","dummy",1);
  auto stream=AudioStream::CreateSDLAudioStream(44100,2,64,15,AudioStretchMode::Off);
  if(!stream || !stream->IsPaused()) return 1;
  stream->SetOutputVolume(100);
  for(unsigned n=0;n<24;n++) {
    u32 count=64;s16* ptr=nullptr;
    stream->BeginWrite(&ptr,&count);
    std::fill_n(ptr,count*2,400);
    stream->EndWrite(count);
  }
  const auto before=stream->GetBufferedFramesRelaxed();
  if(before==0) return 2;
  stream->SetPaused(false);
  SDL_Delay(160);
  const auto after=stream->GetBufferedFramesRelaxed();
  stream->SetPaused(true);
  if(after>=before || !stream->IsPaused()) return 3;
  stream->SetOutputVolume(25);
  if(stream->GetOutputVolume()!=25) return 4;
  stream.reset();
  std::printf("SDL_AUDIO_CALLBACK_PASS before=%u after=%u\n",before,after);
}
