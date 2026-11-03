#ifndef BEAM_CONTROL_PROTOCOL_H
#define BEAM_CONTROL_PROTOCOL_H

#include <stddef.h>
#include <stdint.h>

#define BEAM_CONTROL_MAX_LINE 192U

typedef enum {
    BEAM_CONTROL_NONE = 0,
    BEAM_CONTROL_LEVEL,
    BEAM_CONTROL_START,
    BEAM_CONTROL_RESET,
    BEAM_CONTROL_READY,
    BEAM_CONTROL_STARTED,
    BEAM_CONTROL_RESET_ACK,
    BEAM_CONTROL_ERROR
} BeamControlType;

typedef struct {
    BeamControlType type;
    uint32_t level_id;
    uint32_t nonce;
    uint64_t generation;
    int32_t x_milli, y_milli, dx_micro, dy_micro;
    uint64_t board_ms;
    uint32_t error_code;
} BeamControlMessage;

int beam_control_parse(const char *line, size_t length, BeamControlMessage *message);
int beam_control_format_ready(char *line, size_t capacity, uint32_t level_id,
                              uint64_t generation, int32_t x_milli, int32_t y_milli,
                              int32_t dx_micro, int32_t dy_micro, uint32_t nonce,
                              uint64_t board_ms);
int beam_control_format_started(char *line, size_t capacity, uint32_t level_id,
                                uint64_t generation, uint32_t nonce, uint64_t board_ms);
int beam_control_format_reset_ack(char *line, size_t capacity, uint64_t generation,
                                  uint32_t nonce, uint64_t board_ms);
int beam_control_format_error(char *line, size_t capacity, uint32_t code,
                              uint64_t generation, uint32_t nonce);

#endif
