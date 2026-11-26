/* ARM64 libretro API smoke test; the caller supplies a legally acquired ROM.
 * Run with qemu-aarch64 -L <firmware-root> ./fbneo-smoke <core> <rom> <bios> <save>.
 * No ROM is part of this source or the distributed firmware.
 */
#include <dlfcn.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "libretro.h"

static const char *bios, *save;
static unsigned frames, audio, width, height;
static uint32_t pixels;
static enum retro_pixel_format format = RETRO_PIXEL_FORMAT_0RGB1555;
static struct { char *key, *value; } vars[512];
static size_t varcount;

static void logger(enum retro_log_level l, const char *fmt, ...) {
    if (l < RETRO_LOG_INFO) return;
    va_list ap; va_start(ap,fmt); vfprintf(stderr,fmt,ap); va_end(ap);
}
static bool environment(unsigned cmd, void *data) {
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY: *(const char **)data=bios; return true;
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data=save; return true;
    case RETRO_ENVIRONMENT_GET_CONTENT_DIRECTORY: *(const char **)data=bios; return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: ((struct retro_log_callback *)data)->log=logger; return true;
    case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool *)data=true; return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: format=*(enum retro_pixel_format *)data; return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data=0; return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data=false; return true;
    case RETRO_ENVIRONMENT_SET_VARIABLES: {
        struct retro_variable *v=data;
        for (;v && v->key && varcount<512;v++) {
            const char *p=v->value ? strchr(v->value,';') : NULL;
            if (!p) continue;
            p++; while (*p==' ') p++;
            size_t n=strcspn(p,"|");
            size_t i=0; for (;i<varcount;i++) if (!strcmp(v->key,vars[i].key)) break;
            if (i==varcount) {vars[i].key=strdup(v->key); varcount++;}
            free(vars[i].value); vars[i].value=strndup(p,n);
        }
        return true;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *v=data; v->value=NULL;
        for (size_t i=0;i<varcount;i++) if (!strcmp(v->key,vars[i].key)) {v->value=vars[i].value;return true;}
        return false;
    }
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_MINIMUM_AUDIO_LATENCY:
    case RETRO_ENVIRONMENT_SET_MESSAGE: return true;
    default: return false;
    }
}
static void video(const void *data,unsigned w,unsigned h,size_t pitch) {
    if (!data || data==RETRO_HW_FRAME_BUFFER_VALID) return;
    width=w; height=h; frames++;
    size_t bytes=format==RETRO_PIXEL_FORMAT_XRGB8888 ? 4:2;
    for (unsigned y=0;y<h;y+=8) {
        const unsigned char *p=(const unsigned char *)data+y*pitch;
        for (unsigned x=0;x<w*bytes;x+=4) pixels=(pixels*16777619u)^p[x];
    }
}
static void sample(int16_t l,int16_t r){(void)l;(void)r;audio++;}
static size_t samples(const int16_t *data,size_t n){(void)data;audio+=n;return n;}
static void poll(void){}
static int16_t input(unsigned p,unsigned dev,unsigned idx,unsigned id){
    (void)idx;
    if (p!=0 || dev!=RETRO_DEVICE_JOYPAD) return 0;
    return (id==RETRO_DEVICE_ID_JOYPAD_SELECT && frames>=5 && frames<8) ||
           (id==RETRO_DEVICE_ID_JOYPAD_START && frames>=30 && frames<33);
}
#define LOAD(name, type) type name = (type)dlsym(core,#name); if (!name) {fprintf(stderr,"Missing %s\n",#name);return 2;}
typedef void (*voidfn)(void);
typedef unsigned (*uintfn)(void);
typedef void (*infofn)(struct retro_system_info*);
typedef void (*avfn)(struct retro_system_av_info*);
typedef void (*envfn)(retro_environment_t);
typedef void (*videofn)(retro_video_refresh_t);
typedef void (*audiofn)(retro_audio_sample_t);
typedef void (*batchfn)(retro_audio_sample_batch_t);
typedef void (*pollfn)(retro_input_poll_t);
typedef void (*inputfn)(retro_input_state_t);
typedef bool (*loadfn)(const struct retro_game_info*);
typedef size_t (*sizefn)(void);
typedef bool (*serfn)(void*,size_t);
typedef bool (*unserfn)(const void*,size_t);
int main(int argc,char **argv){
    if (argc!=5) return 2;
    bios=argv[3];save=argv[4];
    void *core=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);
    if (!core){fprintf(stderr,"%s\n",dlerror());return 2;}
    LOAD(retro_api_version,uintfn)
    LOAD(retro_get_system_info,infofn)
    LOAD(retro_get_system_av_info,avfn)
    LOAD(retro_set_environment,envfn)
    LOAD(retro_set_video_refresh,videofn)
    LOAD(retro_set_audio_sample,audiofn)
    LOAD(retro_set_audio_sample_batch,batchfn)
    LOAD(retro_set_input_poll,pollfn)
    LOAD(retro_set_input_state,inputfn)
    LOAD(retro_init,voidfn)
    LOAD(retro_load_game,loadfn)
    LOAD(retro_run,voidfn)
    LOAD(retro_serialize_size,sizefn)
    LOAD(retro_serialize,serfn)
    LOAD(retro_unserialize,unserfn)
    LOAD(retro_unload_game,voidfn)
    LOAD(retro_deinit,voidfn)
    struct retro_system_info info={0};
    retro_get_system_info(&info);
    printf("Core: %s %s, extensions %s, API %u\n",info.library_name,info.library_version,info.valid_extensions,retro_api_version());
    if (retro_api_version()!=RETRO_API_VERSION || !strstr(info.valid_extensions,"zip")) return 3;
    retro_set_environment(environment);
    retro_set_video_refresh(video); retro_set_audio_sample(sample);
    retro_set_audio_sample_batch(samples);retro_set_input_poll(poll);retro_set_input_state(input);
    retro_init();
    struct retro_game_info game={0};game.path=argv[2];
    if (!retro_load_game(&game)){fprintf(stderr,"ROM load failed\n");return 4;}
    struct retro_system_av_info av={0};retro_get_system_av_info(&av);
    for (unsigned i=0;i<120;i++)retro_run();
    size_t state_size=retro_serialize_size();
    if (!state_size || state_size>100*1024*1024) return 5;
    void *state=malloc(state_size);if(!state || !retro_serialize(state,state_size))return 5;
    for (unsigned i=0;i<30;i++)retro_run();
    if(!retro_unserialize(state,state_size)) return 6;
    for(unsigned i=0;i<30;i++)retro_run();
    free(state);
    printf("Rendered frames=%u %ux%u audio_frames=%u fps=%.3f state=%zu video_hash=%08x\n",frames,width,height,audio,av.timing.fps,state_size,pixels);
    if(frames<150 || !width || !height || !audio || !pixels)return 7;
    retro_unload_game();retro_deinit();dlclose(core);
    puts("PASS ARM64 FBNeo ROM load, video, audio, input and save-state round trip");
    return 0;
}
