// The roguelike's run director, version 0 (hooks/rogue_run.c): chambers from rogue-run.txt next to totk.exe, cleared
// when no living enemy is left within the chamber's radius (the clear flag then unseals its Ascend exit), and a warp to
// the next chamber once the player is above the chamber's ceiling. Driven from the per-frame hook (hooks/frame.c).
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

typedef struct Cpu Cpu;

enum { ROGUE_RUN_START = 1, ROGUE_RUN_STOP = 2 };

void rogue_run_command(int command);        // from the dev panel (render thread): start or stop a run
void rogue_run_frame(Cpu *c);               // per-frame hook (game thread)
const char *rogue_run_status(void);         // one line for the panel

#ifdef __cplusplus
}
#endif
