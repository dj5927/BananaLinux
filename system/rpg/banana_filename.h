#pragma once
// Keep filenames in UTF-8 for lookup without renaming original files.
// ICU is already used by EasyRPG; MKXP uses the same library on BananaOS.
#include <unicode/ucnv.h>
#include <unicode/ucnv_err.h>
#include <unicode/unistr.h>
#include <unicode/normalizer2.h>
#include <unicode/utf8.h>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace banana_name {
inline bool validUtf8(const std::string& s) {
    const auto* p=reinterpret_cast<const uint8_t*>(s.data());
    int32_t i=0, n=static_cast<int32_t>(s.size());
    while(i<n) { UChar32 cp; U8_NEXT(p,i,n,cp); if(cp<0) return false; }
    return true;
}
inline const char* codepage(const char* name) {
    if (!name || !*name) return nullptr;
    if (!std::strcmp(name,"949")) return "windows-949";
    if (!std::strcmp(name,"932")) return "windows-932";
    if (!std::strcmp(name,"1252")) return "windows-1252";
    if (!std::strcmp(name,"65001")) return "UTF-8";
    return name;
}
inline const char* preferred() {
    return codepage(std::getenv("BANANA_RPG_FILENAME_ENCODING"));
}
// Strict conversion: a wrong encoding must not silently substitute U+FFFD.
inline bool decode(const std::string& s,const char* enc,std::string& out) {
    if (!enc || !*enc) return false;
    UErrorCode ec=U_ZERO_ERROR;
    UConverter* cv=ucnv_open(codepage(enc),&ec);
    if (U_FAILURE(ec) || !cv) return false;
    ucnv_setToUCallBack(cv,UCNV_TO_U_CALLBACK_STOP,nullptr,nullptr,nullptr,&ec);
    if (U_FAILURE(ec)) { ucnv_close(cv); return false; }
    const int32_t cap=static_cast<int32_t>(s.size()*2+2);
    std::vector<UChar> buf(cap);
    const int32_t len=ucnv_toUChars(cv,buf.data(),cap,s.data(),static_cast<int32_t>(s.size()),&ec);
    ucnv_close(cv);
    if (U_FAILURE(ec)) return false;
    out.clear();
    icu::UnicodeString(buf.data(),len).toUTF8String(out);
    return true;
}
inline std::string utf8(const std::string& s,const char* detected=nullptr) {
    if (validUtf8(s)) return s;
    std::string converted;
    const char* p=preferred();
    if (p && decode(s,p,converted)) return converted;
    if (detected && decode(s,detected,converted)) return converted;
    return s;
}
// Canonical composition and Unicode case folding, including decomposed Hangul.
// Never use the folded spelling for physical I/O; use the stored original path.
inline std::string key(const std::string& raw,const char* detected=nullptr) {
    auto s=utf8(raw,detected);
    if (!validUtf8(s)) {
        for (auto& c:s) if (c>='A' && c<='Z') c=static_cast<char>(c+32);
        return s;
    }
    UErrorCode ec=U_ZERO_ERROR;
    auto u=icu::UnicodeString::fromUTF8(s);
    u.foldCase();
    const auto* n=icu::Normalizer2::getNFCInstance(ec);
    if (U_SUCCESS(ec)) {
        icu::UnicodeString normalized;
        n->normalize(u,normalized,ec);
        if (U_SUCCESS(ec)) u=normalized;
    }
    std::string result;
    u.toUTF8String(result);
    return result;
}
}
