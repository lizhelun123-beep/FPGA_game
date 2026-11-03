#include "game_linux_capture.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void image_copy_checks(void)
{
    const size_t row_bytes=3840U,source_span=3840U*720U,target_stride=3856U;
    const size_t target_span=3856U*720U;
    uint8_t *source=malloc(source_span+2U),*target=malloc(target_span+2U);
    GameCaptureImageView image,bad;
    VisionCanvas canvas,invalid;
    unsigned row;
    size_t column;
    assert(source && target);
    memset(source,0xa7,source_span+2U);memset(target,0xcd,target_span+2U);
    for (row=0;row<720U;++row) for (column=0;column<row_bytes;++column)
        source[1U+(size_t)row*row_bytes+column]=(uint8_t)(row+3U*column);
    image=(GameCaptureImageView){source+1U,1280U,720U,row_bytes,source_span,{7U,91U,1234U}};
    canvas=(VisionCanvas){target+1U,1280,720,target_stride,target_span};
    assert(game_capture_image_copy(&image,&canvas)==0);
    for (row=0;row<720U;++row) {
        assert(memcmp(source+1U+(size_t)row*row_bytes,target+1U+(size_t)row*target_stride,row_bytes)==0);
        for (column=row_bytes;column<target_stride;++column)
            assert(target[1U+(size_t)row*target_stride+column]==0xcd);
    }
    assert(source[0]==0xa7 && source[source_span+1U]==0xa7);
    assert(target[0]==0xcd && target[target_span+1U]==0xcd);
    assert(image.stamp.generation==7U && image.stamp.sequence==91U && image.stamp.captured_ms==1234U);
    assert(game_capture_image_copy(NULL,&canvas)==-1);
    assert(game_capture_image_copy(&image,NULL)==-1);
    bad=image;bad.data=NULL;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;bad.width=1279;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;bad.height=719;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;bad.stride=5760;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;--bad.capacity;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;bad.stamp.generation=0;assert(game_capture_image_copy(&bad,&canvas)==-1);
    bad=image;bad.stamp.sequence=0;assert(game_capture_image_copy(&bad,&canvas)==-1);
    invalid=canvas;invalid.width=1279;assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid=canvas;invalid.height=719;assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid=canvas;invalid.stride=row_bytes-1U;assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid=canvas;invalid.capacity=719U*target_stride+row_bytes-1U;
    assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid=(VisionCanvas){source+1U,1280,720,row_bytes,source_span};
    assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid.data=source+2U;assert(game_capture_image_copy(&image,&invalid)==-1);
    bad=image;bad.data=(const uint8_t *)(uintptr_t)(UINTPTR_MAX-100U);
    assert(game_capture_image_copy(&bad,&canvas)==-1);
    invalid=canvas;invalid.data=(uint8_t *)(uintptr_t)(UINTPTR_MAX-100U);
    assert(game_capture_image_copy(&image,&invalid)==-1);
    invalid=canvas;invalid.capacity=SIZE_MAX;
    assert(game_capture_image_copy(&image,&invalid)==-1);
    assert(source[0]==0xa7 && source[source_span+1U]==0xa7);
    assert(target[0]==0xcd && target[target_span+1U]==0xcd);
    free(source);free(target);
}

#if !defined(__linux__)
static int image_callback(void *context,const GameDetectionFrame *frame,
                          const GameCaptureImageView *image)
{
    (void)frame;(void)image;++*(unsigned *)context;return 0;
}
static void no_owner_checks(void)
{
    unsigned calls=0;
    uint32_t copied=123U,detected=456U;
    assert(game_capture_owner_can_exit());
    assert(game_capture_owner_dispatch_image_parked(0,1,7,91,1234,
        image_callback,&calls,&copied,&detected)==-1);
    assert(!calls && copied==123U && detected==456U && game_capture_owner_can_exit());
}
#endif

int main(void)
{
    GameCaptureDmaState good={0x11001,0,0x01000100,720,3840,5760,{0,0,0}},bad;
    const uint64_t base=UINT64_C(0x38000000);
    unsigned i,slot,writer;
    for (i=0;i<3U;++i) good.addresses[i]=(uint32_t)(base+(uint64_t)i*GAME_CAPTURE_FRAME_SPAN);
    for (slot=0;slot<3U;++slot) for (writer=0;writer<3U;++writer) {
        good.park=(writer<<24)|(writer<<8);
        assert(game_capture_parked_slot_valid(&good,base,slot,writer)==(slot!=writer));
    }
    good.park=0x01000100;
    for (i=0;i<32U;++i) {
        if ((UINT32_C(1)<<i)&0x00ff101fU) {
            bad=good;bad.control^=UINT32_C(1)<<i;
            assert(!game_capture_parked_slot_valid(&bad,base,0,1));
        }
        if ((UINT32_C(1)<<i)&0x89f1U) {
            bad=good;bad.status|=UINT32_C(1)<<i;
            assert(!game_capture_parked_slot_valid(&bad,base,0,1));
        }
    }
    bad=good;bad.park=0x00000100; /* request readback without actual acknowledgement */
    assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    bad=good;bad.park=0x01000000;
    assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    for (i=0;i<3U;++i) {
        bad=good;bad.addresses[i]+=64;
        assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    }
    bad=good;bad.vsize=719;assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    bad=good;bad.hsize=3839;assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    bad=good;bad.stride=3840;assert(!game_capture_parked_slot_valid(&bad,base,0,1));
    assert(!game_capture_parked_slot_valid(&good,base+1,0,1));
    assert(!game_capture_parked_slot_valid(&good,UINT64_C(0x3ffff000),0,1));
    assert(!game_capture_parked_slot_valid(&good,base,3,1));
    assert(!game_capture_parked_slot_valid(&good,base,0,3));
    image_copy_checks();
#if !defined(__linux__)
    no_owner_checks();
#endif
    puts("capture parked-store checks + CPU image copy stride/span/overlap/sentinels PASS (host only; no live owner)");
    return 0;
}
