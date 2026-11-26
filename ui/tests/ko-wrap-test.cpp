#include "RndsRaster.h"
#include <cassert>
#include <cstdio>

int main(int argc, char** argv)
{
    assert(argc == 2);
    rnds::TextStyle style;
    style.font = rnds::Font::load(argv[1]);
    assert(style.font);
    style.size = 20;
    const auto first = U"마이크를";
    const auto second = U"사용합니다.";
    int width = int(rnds::layoutLine(second, style).width + 1);
    auto lines = rnds::layoutWrap(U"마이크를 사용합니다.", style, width);
    assert(lines.size() == 2);
    assert(lines[0].text == first && lines[1].text == second);
    lines = rnds::layoutWrap(U"종류 1[[br]]종류 2", style, 500);
    assert(lines.size() == 2 && lines[0].text == U"종류 1" && lines[1].text == U"종류 2");
    lines = rnds::layoutWrap(U"정수배율정수배율정수배율정수배율", style, width);
    assert(lines.size() > 1);
    std::u32string joined;
    for (const auto& line : lines) {
        assert(line.width <= width + 0.01f);
        joined += line.text;
    }
    assert(joined == U"정수배율정수배율정수배율정수배율");
    std::puts("ko-wrap-test: PASS");
}
