#pragma once

// ---------------------------------------------------------------------------
// EXP-10A observation-only instrumentation interface.
//
// This header is included by the instrumented hnswalg.h ONLY when
// HNSWLIB_TRACE_ENABLED is defined. It defines:
//   - the runtime trace-sink switch and independent distance-call counter;
//   - a DISTFUNC wrapper that delegates to the upstream function pointer
//     (it never reimplements any vector-distance formula);
//   - the declaration of the event emitter implemented by the probe harness.
//
// Scope: single index instance, single-thread query. No concurrency claim.
// ---------------------------------------------------------------------------

#include <cstdint>
#include "hnswlib.h"

// Set by the harness immediately before each searchKnn call.
extern uint64_t g_hnsw_current_query_id;
// Independent count of actual DISTFUNC invocations (reset before each query).
extern uint64_t g_hnsw_dist_call_count;
// Runtime switch: when false, the instrumented sites emit no events.
extern bool g_hnsw_trace_sink_enabled;

// Implemented in experiments/exp10a_hnswlib_probe/main.cpp.
extern void hnsw_trace_emit(uint64_t internal_id,
                            uint64_t external_id,
                            int level,
                            const char *event_site);

// Per-dist_t state for the counting wrapper. One index instance is assumed.
template <typename T>
struct HnswTraceDistState {
    static hnswlib::DISTFUNC<T> orig;
    static void *orig_param;
};

template <typename T>
hnswlib::DISTFUNC<T> HnswTraceDistState<T>::orig = nullptr;

template <typename T>
void *HnswTraceDistState<T>::orig_param = nullptr;

// Drop-in DISTFUNC replacement. Increments the independent counter, then calls
// the exact upstream distance function with the exact upstream parameters.
// The third argument supplied by callers is ignored because dist_func_param_
// in hnswalg.h is deliberately left UNCHANGED by the instrumentation patch.
template <typename T>
static T hnsw_trace_counting_distfunc(const void *a, const void *b, const void *) {
    ++g_hnsw_dist_call_count;
    return HnswTraceDistState<T>::orig(a, b, HnswTraceDistState<T>::orig_param);
}
