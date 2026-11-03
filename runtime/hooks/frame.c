// The per-frame hook (recomp/patches.py `hook`, set frame, TOTK_FRAME_HOOK, on by default). The adaptive
// present-interval controller (main+0x8f26c8, the function the fps60 sets edit) runs once per presented frame on a game
// thread, so features that call game code with rt_call, which needs a game thread's Cpu, do it here after the original:
// - TOTK_HOOK_PROBE=1 logs the first call and every 600th: the example of the mechanism;
// - rogue_flags_frame (hooks/rogue_flags.c) applies the GameData flag writes the dev panel queued;
// - rogue_run_frame (hooks/rogue_run.c) runs the roguelike's run director.
#include <stdint.h>
#include <string.h>

#include "cfg.h"
#include "cpu.h"
#include "host.h"
#include "rogue_flags.h"
#include "rogue_run.h"

void hook_frame(Cpu *c, void (*orig)(Cpu *c)) {
    static uint64_t calls;
    static int probe = -1;
    const uint64_t n = __atomic_add_fetch(&calls, 1, __ATOMIC_RELAXED);
    const uint64_t x0 = c->x[0];
    orig(c);
    if (probe < 0) {
        const char *v = cfg_get("TOTK_HOOK_PROBE");
        probe = v && strcmp(v, "0") != 0;
    }
    if (probe && (n == 1 || n % 600 == 0))
        rt_log("hooks: probe: present-interval controller call %llu (x0 %#llx in, %#llx out)", (unsigned long long)n,
               (unsigned long long)x0, (unsigned long long)c->x[0]);
    rogue_flags_frame(c);
    rogue_run_frame(c);
}
