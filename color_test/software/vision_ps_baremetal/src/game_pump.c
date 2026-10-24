#include "game_pump.h"

#include <string.h>

static GameStatus step(GamePump *pump, const GameLoopEvent *event)
{
    pump->now = pump->io.now_ms(pump->io.context);
    if (pump->now == GAME_PUMP_CLOCK_ERROR) return GAME_BAD_TIME;
    return game_loop_step(pump->loop, pump->now, event, &pump->latest);
}

static void mouse_batch(void *context, const GameMouseBatch *batch)
{
    GamePump *pump = context;
    size_t i;
    /* One report is atomic on the external time sampled before feeding bytes. */
    for (i = 0; i < batch->count; ++i) {
        GameLoopEvent event;
        event.kind = GAME_LOOP_MOUSE;
        event.data.mouse = batch->events[i];
        game_loop_step(pump->loop, pump->now, &event, &pump->latest);
    }
}

int game_pump_init(GamePump *pump, GameLoop *loop, const GamePumpConfig *config,
                   GameEvdevLayout layout, const GamePumpIO *io)
{
    if (!pump || !loop || !loop->layout || !config || !config->tick_ms || !io ||
        io->version != GAME_PUMP_IO_VERSION || !io->now_ms || !io->connection ||
        !io->read || !io->wait_until) return 0;
    memset(pump, 0, sizeof(*pump));
    pump->loop = loop; pump->config = *config; pump->io = *io;
    if (!game_evdev_stream_init(&pump->stream, layout, loop->layout->width, loop->layout->height))
        return 0;
    pump->stream.evdev.x = pump->stream.evdev.published_x = loop->input.x;
    pump->stream.evdev.y = pump->stream.evdev.published_y = loop->input.y;
    return step(pump, NULL) == GAME_OK;
}

GameStatus game_pump_event(GamePump *pump, const GameLoopEvent *event, GameLoopOutput *output)
{
    GameStatus status;
    if (!pump || !pump->loop || !output) return GAME_BAD_ARGUMENT;
    status = step(pump, event);
    *output = pump->latest;
    return status;
}

static void disconnect(GamePump *pump)
{
    pump->read_fault = 1;
    game_evdev_stream_connection(&pump->stream, 0, mouse_batch, pump);
}

static uint64_t add(uint64_t a, uint64_t b)
{
    return UINT64_MAX-a < b ? UINT64_MAX : a+b;
}

GamePumpStatus game_pump_once(GamePump *pump, GamePumpOutput *output)
{
    GamePumpConnection connection;
    unsigned int i;
    int result_error = 0;
    if (!pump || !pump->loop || !output) return GAME_PUMP_IO_ERROR;
    memset(output, 0, sizeof(*output));
    output->read_status = GAME_READ_AGAIN;
    if (step(pump, NULL) == GAME_BAD_TIME) return GAME_PUMP_BAD_CLOCK;
    connection = pump->io.connection(pump->io.context);
    if (!pump->have_connection || connection.epoch != pump->connection.epoch ||
        !!connection.connected != !!pump->connection.connected) {
        pump->connection = connection; pump->have_connection = 1; pump->read_fault = 0;
        game_evdev_stream_connection(&pump->stream, connection.connected, mouse_batch, pump);
    }
    if (connection.connected && !pump->read_fault &&
        game_evdev_stream_can_resync(&pump->stream) && pump->io.resync) {
        int resync = pump->io.resync(pump->io.context);
        if (step(pump, NULL) == GAME_BAD_TIME) return GAME_PUMP_BAD_CLOCK;
        if (resync > 0) game_evdev_stream_recover(&pump->stream, mouse_batch, pump);
        else if (resync < 0) disconnect(pump);
    }
    for (i = 0; connection.connected && !pump->read_fault && i < GAME_PUMP_READ_MAX; ++i) {
        unsigned char bytes[GAME_PUMP_READ_BYTES];
        GameReadResult read = pump->io.read(pump->io.context, bytes, sizeof(bytes));
        ++output->reads;
        if (step(pump, NULL) == GAME_BAD_TIME) return GAME_PUMP_BAD_CLOCK;
        if (read.status < GAME_READ_DATA || read.status > GAME_READ_ERROR ||
            (read.status == GAME_READ_DATA ? (!read.count || read.count > sizeof(bytes)) : read.count != 0))
            read = (GameReadResult){GAME_READ_ERROR, 0};
        output->read_status = read.status;
        if (read.status == GAME_READ_DATA) {
            output->bytes += read.count;
            game_evdev_stream_feed(&pump->stream, bytes, read.count, mouse_batch, pump);
        } else if (read.status == GAME_READ_AGAIN) break;
        else if (read.status != GAME_READ_INTERRUPTED) disconnect(pump);
    }
    for (i = 0; pump->io.result && i < GAME_PUMP_RESULT_MAX; ++i) {
        GameLoopEvent event;
        int ready;
        memset(&event, 0, sizeof(event));
        ready = pump->io.result(pump->io.context, &event.data.detection);
        event.kind = GAME_LOOP_DETECTION;
        if (ready < 0) { result_error = 1; break; }
        if (!ready) break;
        output->result_status = step(pump, &event);
        if (output->result_status == GAME_BAD_TIME) return GAME_PUMP_BAD_CLOCK;
        ++output->results;
    }
    if (step(pump, NULL) == GAME_BAD_TIME) return GAME_PUMP_BAD_CLOCK;
    output->view = pump->latest;
    output->deadline_ms = add(pump->now, pump->config.tick_ms);
    if (output->view.game.state == GAME_RUNNING &&
        output->view.game.remaining_ms < output->deadline_ms-pump->now)
        output->deadline_ms = add(pump->now, output->view.game.remaining_ms);
    output->idle = !output->bytes && !output->results && !result_error;
    if (pump->io.publish) pump->io.publish(pump->io.context, output);
    if (result_error) return GAME_PUMP_IO_ERROR;
    if (pump->io.stopping && pump->io.stopping(pump->io.context)) return GAME_PUMP_STOP;
    if (output->idle) {
        if (output->deadline_ms == pump->now) return GAME_PUMP_BAD_CLOCK;
        GameWaitStatus wait = pump->io.wait_until(pump->io.context, output->deadline_ms);
        if (wait == GAME_WAIT_STOP) return GAME_PUMP_STOP;
        if (wait != GAME_WAIT_READY && wait != GAME_WAIT_INTERRUPTED) return GAME_PUMP_IO_ERROR;
    }
    return GAME_PUMP_CONTINUE;
}

GamePumpStatus game_pump_run(GamePump *pump, GamePumpOutput *output)
{
    GamePumpStatus status;
    do { status = game_pump_once(pump, output); } while (status == GAME_PUMP_CONTINUE);
    return status;
}
