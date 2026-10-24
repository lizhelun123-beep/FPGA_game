#ifndef GAME_RENDER_H
#define GAME_RENDER_H
#include "game_loop.h"
#include "vision_overlay.h"

#ifdef __cplusplus
extern "C" {
#endif
#define GAME_RENDER_VERSION 1U
typedef struct { unsigned int version; GameMenuRect scene; } GameRenderConfig;
typedef enum {
    GAME_RENDER_OK=0, GAME_RENDER_FULL_RAY=1,
    GAME_RENDER_BAD_BUFFER, GAME_RENDER_BAD_LAYOUT, GAME_RENDER_BAD_SNAPSHOT,
    GAME_RENDER_IO_ERROR, GAME_RENDER_BAD_ASSET
} GameRenderStatus;
/* CPU-owned resident pack, zero-initialize before load, close exactly once.
 * Same rectangle/key compositor; these are NEVER display/DMA allocations.
 * +X is pose zero, clockwise image angles in 5-degree steps, center (56,56).
 * Geometry signature binds art to model sizes and the uniform preview mapping. */
typedef struct {
    uint8_t *storage;
    size_t bytes;
    uint32_t geometry_signature;
    unsigned loads;
    VisionCanvas background, poses[RAY_OBJECT_TYPE_COUNT][72];
} GameRenderAssets;
GameRenderStatus game_render_assets_load(GameRenderAssets *assets, const char *path,
                                         const GameConfig *config, const GameRenderConfig *render);
void game_render_assets_free(GameRenderAssets *assets);
GameRenderStatus game_render_cached(const GameLoopOutput *published, const GameConfig *config,
                                    const GameMenuLayout *layout, const GameRenderConfig *render,
                                    const GameRenderAssets *assets, const VisionCanvas *target);
/* Optional file-input label is drawn before the final cursor layer. */
GameRenderStatus game_render_cached_source(const GameLoopOutput *published, const GameConfig *config,
                                    const GameMenuLayout *layout, const GameRenderConfig *render,
                                    const GameRenderAssets *assets, const VisionCanvas *target,
                                    const char *source_label);
/* Small original UTF-8 label font plus shared ASCII, transparent and clipped. */
void game_render_text(const VisionCanvas *target, int x, int y, const char *text,
                      int scale, unsigned rgb);
/* Pure rendering of ONE publication. No time reads, ticking, tracing, game
 * mutation, retained scenes or camera pixels. config/layout are immutable.
 * Output dimensions must equal the menu canvas (currently 1280x800).
 * FULL_RAY means successful export of ALL solver segments with a visible
 * budget warning. Invalid arguments are rejected before any buffer write. */
GameRenderStatus game_render(const GameLoopOutput *published, const GameConfig *config,
                             const GameMenuLayout *layout, const GameRenderConfig *render,
                             const VisionCanvas *target);
/* Stage display only: fit the unchanged 1280x800 logical canvas into a
 * 1152x720 viewport at x=64 on a 1280x720 CPU canvas. Uniform 9/10 scale;
 * cursor and menu are rendered in the SAME logical coordinates before fit.
 * No geometry/game/input mutation; disjoint surfaces, padding untouched. */
GameRenderStatus game_render_fit_720p(const VisionCanvas *logical,
                                     const VisionCanvas *output);
/* P6 RGB on disk; source is BGR888 with arbitrary validated stride. Does not
 * close stream. Caller checks fclose too. No second framebuffer required. */
GameRenderStatus game_render_write_ppm(const VisionCanvas *source, FILE *stream);
/* PC-prepared top-down, tightly packed BGR888, exactly width*height*3 bytes.
 * No header/decoder, allocation, device or DMA access. Writes active bytes only.
 * On short/extra/error input the caller must discard the partially loaded asset.
 * Stream ownership stays with caller, who must also check fclose. */
GameRenderStatus game_render_read_bgr(FILE *stream, const VisionCanvas *asset);
/* Rectangle copy, optionally skipping RGB color_key. Disjoint CPU surfaces only;
 * clips signed coordinates without scaling/rotation/alpha. Writes active pixels
 * only. Caller owns an IDLE output, never a scanning or retained DMA buffer. */
GameRenderStatus game_render_blit(const VisionCanvas *asset, const VisionCanvas *target,
                                  int x, int y, int keyed, unsigned color_key);
#ifdef __cplusplus
}
#endif
#endif
