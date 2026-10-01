#include "vision_overlay.h"
#include <stdio.h>

/* 5x7 column font, uppercase and digits; scaled 2x for 720p HDMI. */
static const unsigned char letters[26][5] = {
 {126,17,17,17,126},{127,73,73,73,54},{62,65,65,65,34},
 {127,65,65,34,28},{127,73,73,73,65},{127,9,9,9,1},
 {62,65,73,73,122},{127,8,8,8,127},{0,65,127,65,0},
 {32,64,65,63,1},{127,8,20,34,65},{127,64,64,64,64},
 {127,2,12,2,127},{127,4,8,16,127},{62,65,65,65,62},
 {127,9,9,9,6},{62,65,81,33,94},{127,9,25,41,70},
 {70,73,73,73,49},{1,1,127,1,1},{63,64,64,64,63},
 {31,32,64,32,31},{63,64,56,64,63},{99,20,8,20,99},
 {7,8,112,8,7},{97,81,73,69,67}
};
static const unsigned char digits[10][5] = {
 {62,81,73,69,62},{0,66,127,64,0},{66,97,81,73,70},
 {33,65,69,75,49},{24,20,18,127,16},{39,69,69,69,57},
 {60,74,73,73,48},{1,113,9,5,3},{54,73,73,73,54},
 {6,73,73,41,30}
};
static void pixel(uint8_t *f, unsigned w, unsigned h, unsigned stride,
                  int x, int y, unsigned rgb)
{
    uint8_t *p;
    if (x < 0 || y < 0 || (unsigned)x >= w || (unsigned)y >= h) return;
    p = f + (unsigned)y * stride + (unsigned)x * 3U;
    p[0] = (uint8_t)rgb; p[1] = (uint8_t)(rgb >> 8); p[2] = (uint8_t)(rgb >> 16);
}
static void text(uint8_t *f, unsigned w, unsigned h, unsigned stride,
                 int x, int y, const char *s)
{
    for (; *s; ++s, x += 12) {
        const unsigned char *glyph = 0;
        int col, row, dx, dy;
        if (*s >= 'A' && *s <= 'Z') glyph = letters[*s-'A'];
        if (*s >= '0' && *s <= '9') glyph = digits[*s-'0'];
        for (col = 0; col < 6; ++col)
            for (row = 0; row < 8; ++row) {
                int on = glyph && col < 5 && (glyph[col] & (1U << row));
                if (*s == '_' && row == 6 && col < 5) on = 1;
                for (dx = 0; dx < 2; ++dx)
                    for (dy = 0; dy < 2; ++dy)
                        pixel(f,w,h,stride,x+col*2+dx,y+row*2+dy,
                              on ? 0x00FF00U : 0);
            }
    }
}
void vision_overlay(uint8_t *f, unsigned w, unsigned h, unsigned stride,
                    const VisionDetection *items, int count, unsigned ms)
{
    int i, x, y, t;
    char label[80];
    if (!f || !w || !h || stride < w*3U || count < 0 || (count && !items)) return;
    for (i = 0; i < count; ++i) {
        const VisionDetection *d = &items[i];
        int left = d->bbox_x < 0 ? 0 : d->bbox_x;
        int top = d->bbox_y < 0 ? 0 : d->bbox_y;
        int right = d->bbox_x + d->bbox_w - 1;
        int bottom = d->bbox_y + d->bbox_h - 1;
        if (right >= (int)w) right = (int)w-1;
        if (bottom >= (int)h) bottom = (int)h-1;
        if (right < left || bottom < top) continue;
        for (t = 0; t < 2; ++t) {
            for (x = left; x <= right; ++x) {
                pixel(f,w,h,stride,x,top+t,0x00FF00U);
                pixel(f,w,h,stride,x,bottom-t,0x00FF00U);
            }
            for (y = top; y <= bottom; ++y) {
                pixel(f,w,h,stride,left+t,y,0x00FF00U);
                pixel(f,w,h,stride,right-t,y,0x00FF00U);
            }
        }
        for (t = -5; t <= 5; ++t) {
            pixel(f,w,h,stride,d->center_x+t,d->center_y,0xFF0000U);
            pixel(f,w,h,stride,d->center_x,d->center_y+t,0xFF0000U);
        }
        (void)snprintf(label,sizeof label,"%s CONF %d",vision_type_name(d->type),
                       d->confidence_percent);
        text(f,w,h,stride,left,top >= 18 ? top-18 : top+2,label);
    }
    (void)snprintf(label,sizeof label,"VISION V3 COUNT %d PROC %u MS",count,ms);
    text(f,w,h,stride,8,8,label);
}
