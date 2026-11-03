// The proof hook of recomp/patches.py `hook` lines: it counts the calls of the adaptive present-interval controller
// (main+0x8f26c8, the function the fps60 patch set edits; the game runs it once per presented frame), logs the first
// call and every 600th, and runs the original unchanged. Patch set hook_probe (TOTK_HOOK_PROBE, default off).
#include <stdint.h>

#include "cpu.h"
#include "host.h"

void hook_probe_present_interval(Cpu *c, void (*orig)(Cpu *c)) {
    static uint64_t calls;
    const uint64_t n = __atomic_add_fetch(&calls, 1, __ATOMIC_RELAXED);
    const uint64_t x0 = c->x[0];
    orig(c);
    if (n == 1 || n % 600 == 0)
        rt_log("hooks: probe: present-interval controller call %llu (x0 %#llx in, %#llx out)", (unsigned long long)n,
               (unsigned long long)x0, (unsigned long long)c->x[0]);
}
