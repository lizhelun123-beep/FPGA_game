#include "game_loop.h"

#include <string.h>

GameStatus game_loop_init(GameLoop *loop, const GameConfig *config,
                          const GameSceneMapping *mapping, const GameMenuLayout *layout)
{
    GameStatus status;
    if (!loop) return GAME_BAD_ARGUMENT;
    memset(loop, 0, sizeof(*loop));
    if (!game_menu_layout_valid(layout, config)) return GAME_BAD_CONFIG;
    status = game_app_init(&loop->app, config, mapping);
    if (status != GAME_OK) return status;
    loop->layout = layout;
    game_menu_input_init(&loop->input);
    return GAME_OK;
}

static GameStatus apply(GameApp *app, GameMenuAction action, uint64_t now)
{
    switch (action.kind) {
    case GAME_MENU_NONE: return GAME_OK;
    case GAME_MENU_SELECT: return game_app_select(app, action.level_id, now);
    case GAME_MENU_START: return game_app_start(app, now);
    default: return GAME_BAD_ARGUMENT;
    }
}

GameStatus game_loop_step(GameLoop *loop, uint64_t now_ms,
                          const GameLoopEvent *event, GameLoopOutput *output)
{
    GameSnapshot before;
    GameStatus status;
    if (!loop || !loop->layout || !output) return GAME_BAD_ARGUMENT;
    memset(output, 0, sizeof(*output));
    status = game_app_tick(&loop->app, now_ms);
    if (status == GAME_OK && event) {
        switch (event->kind) {
        case GAME_LOOP_MOUSE:
            if (event->data.mouse.kind < GAME_MOUSE_MOVE ||
                event->data.mouse.kind > GAME_MOUSE_CONNECT) {
                status = GAME_BAD_ARGUMENT;
                break;
            }
            game_app_snapshot(&loop->app, &before);
            output->action = game_menu_input(&loop->input, loop->layout, &before,
                                              event->data.mouse);
            status = apply(&loop->app, output->action, now_ms);
            break;
        case GAME_LOOP_MENU:
            output->action = event->data.menu;
            status = apply(&loop->app, output->action, now_ms);
            break;
        case GAME_LOOP_DETECTION:
            status = game_app_submit(&loop->app, &event->data.detection, now_ms);
            break;
        case GAME_LOOP_DISPATCH:
            status = game_app_capture_stamp(&loop->app, event->data.dispatch.sequence,
                                            event->data.dispatch.captured_ms, &output->stamp);
            output->has_stamp = status == GAME_OK;
            break;
        default: status = GAME_BAD_ARGUMENT; break;
        }
    }
    game_app_snapshot(&loop->app, &output->game);
    output->menu = game_menu_view(&loop->input, loop->layout, &output->game);
    output->status = status;
    return status;
}
