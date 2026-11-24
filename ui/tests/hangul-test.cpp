#include "hangul.h"
#include <cassert>
#include <iostream>

using banana::HangulComposer;
static std::string type(const char32_t* text) {
    HangulComposer h;
    std::string s;
    for (; *text; ++text) assert(h.input(s, *text, 1024));
    return s;
}
int main() {
    assert(type(U"ㅎㅏㄴㄱㅡㄹ") == u8"한글");
    assert(type(U"ㄱㅏㄴㅏ") == u8"가나");
    assert(type(U"ㄱㅏㅂㅅㅇㅣ") == u8"값이");
    assert(type(U"ㄱㅏㅂㅅㅣ") == u8"갑시");
    assert(type(U"ㄱㅗㅏ") == u8"과");
    assert(type(U"ㅇㅜㅔ") == u8"웨");
    assert(type(U"ㄲㅏ") == u8"까");
    assert(type(U"ㅎㅏㄴ A") == u8"한 A");
    HangulComposer h;
    std::string s;
    for (char32_t c : std::u32string(U"ㄱㅏㅂㅅ")) assert(h.input(s,c,3));
    assert(s == u8"값");
    assert(!h.input(s,U'ㅣ',3) && s == u8"값");
    h.erase(s); assert(s == u8"갑");
    h.erase(s); assert(s == u8"가");
    h.erase(s); assert(s == u8"ㄱ");
    h.erase(s); assert(s.empty());
    for (char32_t c : std::u32string(U"ㄱㅗㅏ")) assert(h.input(s,c,3));
    h.erase(s); assert(s == u8"고");
    h.commit(); h.erase(s); assert(s.empty());
    std::cout << "hangul-test: all passed\n";
}
