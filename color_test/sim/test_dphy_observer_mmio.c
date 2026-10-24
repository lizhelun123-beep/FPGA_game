/* Native host RAM fixtures, same canonical access implementation, no device I/O. */
#include <stdio.h>
#include <string.h>
#include "../tools/dphy_observer_mmio.c"

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { \
    fprintf(stderr, "FAIL line%d check%u\n", __LINE__, checks); return 1; } } while (0)

int main(void)
{
    uint32_t words[8], value = 0xdeadbeefu;
    const uint32_t patterns[] = {0,1,0x80000000u,0xffffffffu,0x91a2b3c4u};
    unsigned char before[sizeof(words)];
    CHECK(dphy_mmio_abi() == 1);
    for (unsigned offset=0; offset<sizeof(words); offset+=4) {
        for (unsigned i=0; i<sizeof(patterns)/sizeof(patterns[0]); ++i) {
            memset(words,0xa5,sizeof(words));memcpy(before,words,sizeof(words));
            CHECK(dphy_mmio_write32(words,sizeof(words),offset,patterns[i]) == 0);
            CHECK(dphy_mmio_read32(words,sizeof(words),offset,&value) == 0);
            CHECK(value == patterns[i]);
            CHECK(memcmp(words,before,offset) == 0);
            CHECK(memcmp((char *)words+offset+4,before+offset+4,sizeof(words)-offset-4) == 0);
        }
    }
    memcpy(before,words,sizeof(words));value=0xdeadbeefu;
    const uint32_t bad_offsets[] = {1,2,3,29,32,0xfffffffcu};
    for (unsigned i=0; i<sizeof(bad_offsets)/sizeof(bad_offsets[0]); ++i) {
        CHECK(dphy_mmio_write32(words,sizeof(words),bad_offsets[i],0) == -1);
        CHECK(dphy_mmio_read32(words,sizeof(words),bad_offsets[i],&value) == -1);
        CHECK(value == 0xdeadbeefu && memcmp(words,before,sizeof(words)) == 0);
    }
    CHECK(dphy_mmio_write32(NULL,32,0,0) == -1);
    CHECK(dphy_mmio_read32(NULL,32,0,&value) == -1);
    CHECK(dphy_mmio_write32((char *)words+1,32,0,0) == -1);
    CHECK(dphy_mmio_read32((char *)words+1,32,0,&value) == -1);
    CHECK(dphy_mmio_write32(words,0,0,0) == -1);
    CHECK(dphy_mmio_write32(words,3,0,0) == -1);
    CHECK(dphy_mmio_read32(words,31,0,&value) == -1);
    CHECK(dphy_mmio_read32(words,32,0,NULL) == -1);
    CHECK(memcmp(words,before,sizeof(words)) == 0);
    printf("MMIO_NATIVE_RAM_PASS checks=%u\n",checks);
    return 0;
}
