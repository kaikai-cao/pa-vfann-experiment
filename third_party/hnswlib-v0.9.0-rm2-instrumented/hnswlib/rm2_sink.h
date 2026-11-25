#pragma once

// H1-RM.2 observation-only instrumentation interface.
// Included by the instrumented hnswalg.h ONLY when HNSWLIB_RM2_TRACE_ENABLED
// is defined. The harness in experiments/h1_rm2_native_stop/main.cpp defines
// the globals and the emitter. No distance formula is reimplemented.

#include <cstdint>
#include "hnswlib.h"

extern uint64_t g_rm2_current_query_id;
extern bool g_rm2_enabled;

extern void rm2_emit(const char *event_type,
                     uint64_t internal_id,
                     uint64_t external_id,
                     int level,
                     float dist,
                     int64_t extra);
