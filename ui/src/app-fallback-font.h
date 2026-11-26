// Shared Unicode fallback for Activity and the Store. The existing Fusion Pixel
// font is installed by banana-ui, so no second font or atlas is distributed.
#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <ft2build.h>
#include FT_FREETYPE_H

static FT_Library banana_af_lib;
static FT_Face banana_af_face;
static int banana_af_tried;
static int banana_af_size;

static FT_GlyphSlot banana_af_glyph(uint32_t cp, int px)
{
    if (!banana_af_tried) {
        banana_af_tried = 1;
        const char *path = getenv("BANANA_APP_FONT");
        if (!path || !*path)
            path = "/usr/share/banana/rnds/fonts/fusion-pixel-12px-proportional-zh_hans.ttf";
        if (FT_Init_FreeType(&banana_af_lib) ||
            FT_New_Face(banana_af_lib, path, 0, &banana_af_face))
            banana_af_face = 0;
        if (banana_af_face) FT_Select_Charmap(banana_af_face, FT_ENCODING_UNICODE);
    }
    if (!banana_af_face || px < 1 || !FT_Get_Char_Index(banana_af_face, cp)) return 0;
    if (banana_af_size != px) {
        if (FT_Set_Pixel_Sizes(banana_af_face, 0, (unsigned)px)) return 0;
        banana_af_size = px;
    }
    if (FT_Load_Char(banana_af_face, cp, FT_LOAD_RENDER | FT_LOAD_TARGET_NORMAL)) return 0;
    return banana_af_face->glyph;
}

static int banana_af_advance(FT_GlyphSlot g)
{
    int a = (int)((g->advance.x + 32) >> 6);
    return a > 0 ? a : (int)g->bitmap.width;
}

static unsigned banana_af_alpha(const FT_Bitmap *b, unsigned x, unsigned y)
{
    const unsigned char *row = b->pitch >= 0 ? b->buffer + y * b->pitch :
        b->buffer + (b->rows - 1 - y) * (unsigned)(-b->pitch);
    if (b->pixel_mode == FT_PIXEL_MODE_MONO) return row[x / 8] & (0x80 >> (x % 8)) ? 255 : 0;
    if (b->pixel_mode == FT_PIXEL_MODE_GRAY) return b->num_grays > 1 ?
        (unsigned)row[x] * 255 / (b->num_grays - 1) : 0;
    return 0;
}
