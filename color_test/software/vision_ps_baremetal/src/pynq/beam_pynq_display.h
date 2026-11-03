#ifndef BEAM_PYNQ_DISPLAY_H
#define BEAM_PYNQ_DISPLAY_H
#include "beam_pynq.h"
#include "game_linux_display.h"
typedef struct BeamPynqDisplay BeamPynqDisplay;
BEAM_PYNQ_API size_t beam_pynq_platform_size(void);
BEAM_PYNQ_API int beam_pynq_barrier(void);
BEAM_PYNQ_API BeamPynqDisplay *beam_pynq_display_new(void);
BEAM_PYNQ_API int beam_pynq_display_prepare(BeamPynqDisplay *, const GameDisplayPlatform *);
BEAM_PYNQ_API int beam_pynq_display_submit(BeamPynqDisplay *, const uint8_t *, size_t);
BEAM_PYNQ_API int beam_pynq_display_poll(BeamPynqDisplay *);
BEAM_PYNQ_API int beam_pynq_display_stop(BeamPynqDisplay *);
BEAM_PYNQ_API int beam_pynq_display_free(BeamPynqDisplay *);
#endif
