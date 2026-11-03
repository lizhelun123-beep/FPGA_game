#ifndef BEAM_WIRE_PROTOCOL_H
#define BEAM_WIRE_PROTOCOL_H
#include "beam_control_protocol.h"
#include "game_beam.h"

#define BEAM_WIRE_VERSION 3U
#define BEAM_WIRE_MAX_PAYLOAD 160U
#define BEAM_WIRE_MAX_RAW (BEAM_WIRE_MAX_PAYLOAD+10U)
#define BEAM_WIRE_MAX_ENCODED (BEAM_WIRE_MAX_RAW+1U)
#define BEAM_WIRE_MAX_PACKET (BEAM_WIRE_MAX_ENCODED+3U)
#define BEAM_WIRE_POSE_HEADER 56U
#define BEAM_WIRE_OBJECT_BYTES 12U

typedef enum {
    BEAM_WIRE_SYNC=1, BEAM_WIRE_SYNC_REPLY, BEAM_WIRE_LEVEL,
    BEAM_WIRE_READY, BEAM_WIRE_START, BEAM_WIRE_STARTED,
    BEAM_WIRE_RESET, BEAM_WIRE_RESET_ACK, BEAM_WIRE_ERROR, BEAM_WIRE_POSE
} BeamWireType;
typedef struct {
    unsigned type, length;
    uint8_t payload[BEAM_WIRE_MAX_PAYLOAD];
} BeamWirePacket;
typedef struct {
    unsigned state, used, rejected;
    uint8_t encoded[BEAM_WIRE_MAX_ENCODED];
} BeamWireParser;

uint64_t beam_wire_le(const uint8_t *p, unsigned n);
void beam_wire_put(uint8_t *p, uint64_t value, unsigned n);
int beam_wire_encode(char *wire, size_t capacity, unsigned type,
                     const uint8_t *payload, unsigned length);
/* Feed bytes in order. 1=one CRC/length/version-checked packet,0=none. */
int beam_wire_feed(BeamWireParser *parser, uint8_t byte, BeamWirePacket *packet);
int beam_wire_control_decode(const BeamWirePacket *packet, BeamControlMessage *message);
int beam_wire_control_encode(char *wire, size_t capacity, const BeamControlMessage *message);
/* Existing state machine returns an internal ASCII representation; only the
 * checked binary conversion below is transmitted. ASCII v2 is not accepted. */
int beam_wire_control_reply(char *wire, size_t capacity, const char *internal, size_t length);
int beam_wire_pose_encode(char *wire, size_t capacity, const GameBeamSnapshot *snapshot,
                          const BeamControlMessage *level, uint32_t tx, uint64_t published_ms);
int beam_wire_sync_reply(char *wire, size_t capacity, uint32_t nonce,
                         uint64_t received_ms, uint64_t sent_ms);
#endif
