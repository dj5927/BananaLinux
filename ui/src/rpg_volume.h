#pragma once
// The existing BananaOS level card is also used over native RPG games.
// Geometry, font, icon and palette come from Settings::level, matching
// the BananaFront libretro-game pill; 160ms slide and 1500ms timeout.
#include "settings.h"
#include "soft.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <ctime>
#include <fstream>
#include <memory>
#include <string>
#include <sys/stat.h>
#include <vector>

namespace banana {
class RpgVolume {
    struct stat seen_{};
    int value_=0, builtValue_=-1;
    double from_=0, until_=0, nextCheck_=0;
    std::string path_;
    std::unique_ptr<SoftBackend> scratch_;
    std::vector<uint32_t> card_;
    static uint32_t over(uint32_t d,uint32_t s) {
        unsigned a=s>>24, inv=255-a;
        unsigned b=(s&255)+((d&255)*inv+127)/255;
        unsigned g=((s>>8)&255)+(((d>>8)&255)*inv+127)/255;
        unsigned r=((s>>16)&255)+(((d>>16)&255)*inv+127)/255;
        return 0xff000000u|(std::min(255u,r)<<16)|(std::min(255u,g)<<8)|std::min(255u,b);
    }
public:
    int width=0,height=0;
    std::vector<uint32_t> pixels; // premultiplied ARGB8888
    explicit RpgVolume(const std::string& path="/run/banana/osd"):path_(path) {
        stat(path_.c_str(),&seen_); // do not replay a pre-launch event
    }
    bool check(double now) {
        if(now<nextCheck_) return false;
        nextCheck_=now+100;
        struct stat st{};
        if(stat(path_.c_str(),&st)) return false;
        if(st.st_ino==seen_.st_ino && st.st_mtim.tv_sec==seen_.st_mtim.tv_sec &&
           st.st_mtim.tv_nsec==seen_.st_mtim.tv_nsec) return false;
        seen_=st;
        const auto age=std::time(nullptr)-st.st_mtime;
        if(age<0||age>2) return false;
        std::ifstream f(path_); std::string what; int v;
        if(!(f>>what>>v)||what!="volume"||v<0||v>100) return false;
        show(v,now); return true;
    }
    void show(int percent,double now) {
        if(!active(now)) from_=now;
        value_=std::clamp(percent,0,100); until_=now+1500;
    }
    bool active(double now) const {return now<until_;}
    bool animating(double now) const {return active(now)&&(now-from_<160||until_-now<160);}
    int value() const {return value_;}
    void render(Settings& settings,int w,int h,double now) {
        const int strip=std::min(h,int(std::lround(46.0*w/640.0)));
        if(!scratch_||width!=w||height!=strip) {
            width=w; height=strip;
            scratch_=std::make_unique<SoftBackend>(width,height);
            builtValue_=-1;
        }
        if(builtValue_!=value_) {
            // Recover premultiplied color/coverage from the existing card
            // drawn on black and white, without duplicating any visual art.
            for(int i=0;i<2;i++) {
                scratch_->beginScreen(i);
                scratch_->fill(0,0,width,height,rnds::Color::hex(i?0xffffff:0));
                settings.levelOn(scratch_.get(),"Volume",value_);
                scratch_->endScreen();
            }
            const uint32_t* black=scratch_->pixels(0);
            const uint32_t* white=scratch_->pixels(1);
            card_.resize(size_t(width)*height);
            for(size_t i=0;i<card_.size();i++) {
                int a=std::clamp(255-(int((white[i]>>8)&255)-int((black[i]>>8)&255)),0,255);
                unsigned r=std::min(unsigned(a),(black[i]>>16)&255);
                unsigned g=std::min(unsigned(a),(black[i]>>8)&255);
                unsigned b=std::min(unsigned(a),black[i]&255);
                card_[i]=(unsigned(a)<<24)|(r<<16)|(g<<8)|b;
            }
            builtValue_=value_;
        }
        double phase=std::clamp(std::min(now-from_,until_-now)/160.0,0.0,1.0);
        int offset=int(std::lround((1-phase)*(1-phase)*height));
        pixels.assign(card_.size(),0);
        if(offset<height)
            std::copy(card_.begin()+size_t(offset)*width,card_.end(),pixels.begin());
    }
    void composite(uint32_t* dst,int stride) const {
        for(int y=0;y<height;y++) for(int x=0;x<width;x++)
            if(pixels[size_t(y)*width+x]>>24)
                dst[size_t(y)*stride+x]=over(dst[size_t(y)*stride+x],pixels[size_t(y)*width+x]);
    }
};
}
