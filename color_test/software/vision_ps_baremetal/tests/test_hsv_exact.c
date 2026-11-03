/* Exhaust every8-bit RGB color against the unchanged division/rounding path. */
#include "vision_ps.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
    unsigned b,g,r;
    unsigned char reference[256][3];
    for(b=0;b<256;++b) for(g=0;g<256;++g) {
        assert(!vision_set_real_scene_profile(VISION_PROFILE_LEGACY));
        for(r=0;r<256;++r)
            vision_bgr_to_hsv_pixel((uint8_t)b,(uint8_t)g,(uint8_t)r,
                &reference[r][0],&reference[r][1],&reference[r][2]);
        assert(!vision_set_real_scene_profile(VISION_PROFILE_RESTORED));
        for(r=0;r<256;++r) {
            uint8_t h,s,v;
            vision_bgr_to_hsv_pixel((uint8_t)b,(uint8_t)g,(uint8_t)r,&h,&s,&v);
            if(h!=reference[r][0] || s!=reference[r][1] || v!=reference[r][2]) {
                fprintf(stderr,"RGB parity failed b%u g%u r%u\n",b,g,r);return 1;
            }
        }
    }
    puts("PASS exact HSV: all16777216 RGB colors equal the legacy integer division path");
    return 0;
}
