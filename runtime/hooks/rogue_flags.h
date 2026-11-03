// GameData flag writes from host code (hooks/rogue_flags.c): the dev panel (ui/rogue_dev.cpp) queues them from the
// render thread, the per-frame hook (hooks/frame.c) applies them on a game thread.
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Cpu Cpu;

uint32_t rogue_flag_hash(const char *name);               // murmur3_32 of the flag name, seed 0 (GameDataList keys)
int rogue_flag_request(const char *name, int value);     // queue setBool(name, value); 0 when the queue is full
void rogue_flags_frame(Cpu *c);                           // per-frame hook: apply the queued writes
const char *rogue_flags_status(void);                     // the last applied write, for the panel ("" before any)
int rogue_dev_enabled(void);                              // TOTK_ROGUE_DEV set and not 0

#ifdef __cplusplus
}
#endif
