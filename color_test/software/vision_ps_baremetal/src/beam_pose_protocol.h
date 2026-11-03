#ifndef BEAM_POSE_PROTOCOL_H
#define BEAM_POSE_PROTOCOL_H
#include "game_beam.h"

/* POSE2 is for restored, already committed poses. scene-v1 remains the legacy
 * raw-observation ABI. Explicit LE fields and CRC; never serialize C structs. */
#define BEAM_POSE_HEADER_BYTES 52U
#define BEAM_POSE_OBJECT_BYTES 28U
#define BEAM_POSE_MAX_LINE (12U+2U*(BEAM_POSE_HEADER_BYTES+28U*GAME_BEAM_MAX_OBJECTS+4U))
int beam_pose_encode(char *line, size_t capacity, const GameBeamSnapshot *snapshot,
                     uint32_t tx_sequence, uint64_t published_ms);
#endif
