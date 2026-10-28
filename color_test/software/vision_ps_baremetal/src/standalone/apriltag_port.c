/* OS services only. Tag decoding/quad extraction remain upstream AprilTag. */
#include "common/workerpool.h"
#include "common/time_util.h"
#include "xtime_l.h"
#include <assert.h>
#include <stdlib.h>

struct task { void (*function)(void *); void *argument; };
struct workerpool { zarray_t *tasks; };

workerpool_t *workerpool_create(int nthreads)
{
    workerpool_t *pool;
    if (nthreads != 1) return NULL;
    pool = calloc(1, sizeof(*pool));
    if (pool) pool->tasks = zarray_create(sizeof(struct task));
    return pool;
}
void workerpool_destroy(workerpool_t *pool)
{
    if (!pool) return;
    zarray_destroy(pool->tasks);
    free(pool);
}
void workerpool_add_task(workerpool_t *pool, void (*function)(void *), void *argument)
{
    struct task task = {function, argument};
    assert(pool && function);
    zarray_add(pool->tasks, &task);
}
void workerpool_run_single(workerpool_t *pool)
{
    int i;
    for (i=0; i<zarray_size(pool->tasks); ++i) {
        struct task task;
        zarray_get(pool->tasks, i, &task);
        task.function(task.argument);
    }
    zarray_clear(pool->tasks);
}
void workerpool_run(workerpool_t *pool) { workerpool_run_single(pool); }
int workerpool_get_nthreads(workerpool_t *pool) { (void)pool; return 1; }
int workerpool_get_nprocs(void) { return 1; }

int64_t utime_now(void)
{
    XTime ticks;
    XTime_GetTime(&ticks);
    return (int64_t)((ticks/COUNTS_PER_SECOND)*1000000ULL +
        (ticks%COUNTS_PER_SECOND)*1000000ULL/COUNTS_PER_SECOND);
}
