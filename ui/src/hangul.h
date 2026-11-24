#pragma once
// Small two-set Hangul IME for Banana's file/title/search fields (UTF-8 NFC).
// Account names, passwords, network addresses and firmware nickname retain their original keyboard.
#include <string>
#include <cstddef>
#include <utility>

namespace banana {
struct HangulComposer {
    int l=-1,v=-1,t=0;
    static constexpr char32_t leading[] = U"ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ";
    static constexpr char32_t vowels[] = U"ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ";
    static constexpr char32_t trailing[] = U" ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ";
    static int index(const char32_t* a, char32_t c) {
        for(int i=0; a[i]; ++i) if(a[i]==c) return i;
        return -1;
    }
    static std::string utf8(char32_t c) {
        if(c<0x80) return std::string(1,char(c));
        if(c<0x800) return {char(0xc0|(c>>6)),char(0x80|(c&63))};
        return {char(0xe0|(c>>12)),char(0x80|((c>>6)&63)),char(0x80|(c&63))};
    }
    static void pop(std::string& s) {
        while(!s.empty() && (static_cast<unsigned char>(s.back())&0xc0)==0x80) s.pop_back();
        if(!s.empty()) s.pop_back();
    }
    bool active() const { return l>=0 || v>=0; }
    void commit(){l=v=-1;t=0;}
    char32_t glyph() const {
        if(l>=0 && v>=0) return 0xac00+(l*21+v)*28+t;
        return l>=0 ? leading[l] : v>=0 ? vowels[v] : 0;
    }
    static int combineV(int a,int b) {
        if(a==8){if(b==0)return 9;if(b==1)return 10;if(b==20)return 11;}
        if(a==13){if(b==4)return 14;if(b==5)return 15;if(b==20)return 16;}
        if(a==18&&b==20)return 19;
        return -1;
    }
    static int firstV(int a) {if(a>=9&&a<=11)return 8;if(a>=14&&a<=16)return 13;if(a==19)return 18;return -1;}
    static int combineT(int a,int b) {
        if(a==1&&b==19)return 3;
        if(a==4){if(b==22)return 5;if(b==27)return 6;}
        if(a==8){if(b==1)return 9;if(b==16)return 10;if(b==17)return 11;if(b==19)return 12;if(b==25)return 13;if(b==26)return 14;if(b==27)return 15;}
        if(a==17&&b==19)return 18;
        return -1;
    }
    static void splitT(int a,int& first,int& second){
        first=0;second=a;
        switch(a){
        case 3:first=1;second=19;break;case 5:first=4;second=22;break;case 6:first=4;second=27;break;
        case 9:first=8;second=1;break;case 10:first=8;second=16;break;case 11:first=8;second=17;break;
        case 12:first=8;second=19;break;case 13:first=8;second=25;break;case 14:first=8;second=26;break;
        case 15:first=8;second=27;break;case 18:first=17;second=19;break;}
    }
    bool input(std::string& s,char32_t c,std::size_t maxBytes) {
        HangulComposer old=*this; std::string out=s;
        if(active()) pop(out);
        auto flush=[&](){if(active())out+=utf8(glyph());commit();};
        int cv=index(vowels,c),cl=index(leading,c),ct=index(trailing,c);
        if(cv>=0){
            if(l>=0&&v<0)v=cv;
            else if(l>=0&&v>=0&&t){
                int first,second;splitT(t,first,second);t=first;out+=utf8(glyph());
                l=index(leading,trailing[second]);v=cv;t=0;
            }else if(v>=0){int n=combineV(v,cv);if(n>=0)v=n;else{flush();v=cv;}}
            else v=cv;
        }else if(cl>=0){
            if(l>=0&&v>=0&&ct>0){
                if(!t)t=ct;
                else {int n=combineT(t,ct);if(n>=0)t=n;else{flush();l=cl;}}
            }else{flush();l=cl;}
        }else{flush();out+=utf8(c);}
        if(active())out+=utf8(glyph());
        if(out.size()>maxBytes){*this=old;return false;}
        s=std::move(out);return true;
    }
    void erase(std::string& s) {
        if(!active()){pop(s);return;}
        pop(s);
        if(t){int first,second;splitT(t,first,second);t=first;}
        else if(v>=0){v=firstV(v);}
        else l=-1;
        if(active())s+=utf8(glyph());
    }
};
}
