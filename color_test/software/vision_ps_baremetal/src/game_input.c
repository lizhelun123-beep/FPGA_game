#include "game_input.h"

#include <string.h>

static const GameMenuAction none = {GAME_MENU_NONE, 0};

static int contains(GameMenuRect r, int x, int y)
{
    return x >= r.x && y >= r.y && x-r.x < r.width && y-r.y < r.height;
}

static int valid_rect(GameMenuRect r, int width, int height)
{
    return r.x >= 0 && r.y >= 0 && r.width > 0 && r.height > 0 &&
           r.width <= width && r.height <= height &&
           r.x <= width-r.width && r.y <= height-r.height;
}

static int overlap(GameMenuRect a, GameMenuRect b)
{
    return a.x < b.x+b.width && b.x < a.x+a.width &&
           a.y < b.y+b.height && b.y < a.y+a.height;
}

int game_menu_layout_valid(const GameMenuLayout *layout, const GameConfig *config)
{
    int i, j;
    if (!layout || !config || layout->version != GAME_MENU_VERSION ||
        layout->width <= 0 || layout->height <= 0 ||
        layout->level_count < 1 || layout->level_count > GAME_MAX_LEVELS ||
        layout->level_count != config->level_count ||
        !valid_rect(layout->start, layout->width, layout->height)) return 0;
    for (i = 0; i < layout->level_count; ++i) {
        const GameMenuButton *b = &layout->levels[i];
        if (b->level_id != config->levels[i].id ||
            !valid_rect(b->rect, layout->width, layout->height) ||
            overlap(b->rect, layout->start)) return 0;
        for (j = 0; j < i; ++j)
            if (overlap(b->rect, layout->levels[j].rect)) return 0;
    }
    return 1;
}

void game_menu_input_init(GameMenuInput *input)
{
    memset(input, 0, sizeof(*input));
    input->connected = 1;
}

GameMenuView game_menu_view(const GameMenuInput *input, const GameMenuLayout *layout,
                             const GameSnapshot *snapshot)
{
    GameMenuView view;
    int i;
    memset(&view, 0, sizeof(view));
    view.x = input->x; view.y = input->y;
    view.connected = input->connected; view.left_down = input->left_down;
    view.start_enabled = snapshot->state == GAME_PREPARING && snapshot->ready;
    if (!input->connected) return view;
    for (i = 0; i < layout->level_count; ++i)
        if (contains(layout->levels[i].rect, input->x, input->y)) {
            view.hover = (GameMenuAction){GAME_MENU_SELECT, layout->levels[i].level_id};
            return view;
        }
    if (view.start_enabled && contains(layout->start, input->x, input->y))
        view.hover = (GameMenuAction){GAME_MENU_START, 0};
    return view;
}

GameMenuAction game_menu_input(GameMenuInput *input, const GameMenuLayout *layout,
                                const GameSnapshot *snapshot, GameMouseEvent event)
{
    GameMenuAction action = none, hover;
    if (event.kind == GAME_MOUSE_DISCONNECT || event.kind == GAME_MOUSE_CONNECT) {
        input->connected = event.kind == GAME_MOUSE_CONNECT;
        input->require_release = 1;
        input->left_down = 0; input->pressed = none;
        return none;
    }
    if (!input->connected) return none;
    if (event.kind == GAME_MOUSE_MOVE) {
        input->x = event.x < 0 ? 0 : event.x >= layout->width ? layout->width-1 : event.x;
        input->y = event.y < 0 ? 0 : event.y >= layout->height ? layout->height-1 : event.y;
        return none;
    }
    hover = game_menu_view(input, layout, snapshot).hover;
    if (event.kind == GAME_MOUSE_LEFT_DOWN && !input->left_down) {
        input->left_down = 1;
        input->pressed = input->require_release ? none : hover;
        input->pressed_generation = snapshot->generation;
    } else if (event.kind == GAME_MOUSE_LEFT_UP) {
        if (input->left_down && !input->require_release &&
            input->pressed_generation == snapshot->generation &&
            input->pressed.kind == hover.kind && input->pressed.level_id == hover.level_id)
            action = hover;
        input->left_down = input->require_release = 0;
        input->pressed = none;
    }
    return action;
}
