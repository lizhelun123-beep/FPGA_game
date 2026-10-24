/* Diagnostic MMIO ABI1. No device open, allocation, constructors or libc calls.
 * Mapping/lifetime/ownership are the caller's responsibility. Only aligned
 * 32-bit accesses are legal. A bus fault is NOT recoverable in this library.
 */
#include <stddef.h>
#include <stdint.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif

_Static_assert(sizeof(uint32_t) == 4, "32-bit word required");

static int valid(const void *base, uint32_t span, uint32_t offset)
{
    uintptr_t address = (uintptr_t)base;
    return base != NULL && (address & 3u) == 0 &&
           span >= 4 && (span & 3u) == 0 && (offset & 3u) == 0 &&
           offset <= span - 4 && address <= UINTPTR_MAX - offset;
}

static void before_access(void)
{
#if defined(__arm__)
    __asm__ volatile ("dmb sy" ::: "memory");
#else
    /* Host RAM fixture only; actual board build must be ARMv7/A9. */
    __sync_synchronize();
#endif
}

static void after_access(void)
{
#if defined(__arm__)
    __asm__ volatile ("dsb sy" ::: "memory");
#else
    __sync_synchronize();
#endif
}

EXPORT uint32_t dphy_mmio_abi(void) { return 1; }

EXPORT int dphy_mmio_read32(const void *base, uint32_t span, uint32_t offset,
                           uint32_t *value)
{
    if (!valid(base, span, offset) || value == NULL || ((uintptr_t)value & 3u))
        return -1;
    const volatile uint32_t *word =
        (const volatile uint32_t *)((uintptr_t)base + offset);
    before_access();
    uint32_t result = *word;
    after_access();
    *value = result;
    return 0;
}

EXPORT int dphy_mmio_write32(void *base, uint32_t span, uint32_t offset,
                            uint32_t value)
{
    if (!valid(base, span, offset))
        return -1;
    volatile uint32_t *word = (volatile uint32_t *)((uintptr_t)base + offset);
    before_access();
    *word = value;
    after_access();
    return 0;
}
