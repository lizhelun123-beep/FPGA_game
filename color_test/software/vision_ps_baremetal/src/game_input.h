#ifndef GAME_INPUT_H
#define GAME_INPUT_H

#include "game_session.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GAME_MENU_VERSION 1U
typedef struct { int x, y, width, height; } GameMenuRect;
typedef struct { unsigned int level_id; GameMenuRect rect; } GameMenuButton;
/* Display/menu pixels, independent of the uncalibrated camera/game space.
 * Generated from the same JSON as GameConfig; renderer uses these exact rects.
 * Rectangles are half-open: [x,x+width), [y,y+height). */
typedef struct {
    unsigned int version;
    int width, height, level_count;
    GameMenuButton levels[GAME_MAX_LEVELS];
    GameMenuRect start;
} GameMenuLayout;

typedef enum { GAME_MENU_NONE = 0, GAME_MENU_SELECT, GAME_MENU_START } GameMenuKind;
typedef struct { GameMenuKind kind; unsigned int level_id; } GameMenuAction;
typedef enum {
    GAME_MOUSE_MOVE = 0, GAME_MOUSE_LEFT_DOWN, GAME_MOUSE_LEFT_UP,
    GAME_MOUSE_DISCONNECT, GAME_MOUSE_CONNECT
} GameMouseKind;
/* Absolute menu pixels after platform normalization; x/y used only by MOVE. */
typedef struct { GameMouseKind kind; int x, y; } GameMouseEvent;
typedef struct {
    int x, y, connected, left_down, require_release;
    GameMenuAction pressed;
    uint64_t pressed_generation;
} GameMenuInput;
/* No independent game/menu state machine: derive this from the final snapshot. */
typedef struct {
    int x, y, connected, left_down, start_enabled;
    GameMenuAction hover;
} GameMenuView;

int game_menu_layout_valid(const GameMenuLayout *layout, const GameConfig *config);
void game_menu_input_init(GameMenuInput *input);
GameMenuView game_menu_view(const GameMenuInput *input, const GameMenuLayout *layout,
                             const GameSnapshot *snapshot);
/* One matching press/release emits one action. Repeat DOWN, dragging into a
 * button, generation changes mid-click and reconnect-held buttons emit none.
 * Reconnect requires a release before the next click. Mouse never edits poses. */
GameMenuAction game_menu_input(GameMenuInput *input, const GameMenuLayout *layout,
                                const GameSnapshot *snapshot, GameMouseEvent event);

#ifdef __cplusplus
}
#endif
#endif
