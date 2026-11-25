// ---------------------------------------------------------------------------
// EXP-10A: hnswlib v0.9.0 ordered distance-evaluation trace feasibility probe.
//
// This harness is intentionally minimal:
//   - synthetic vectors only (no FiQA / qrels / model downloads);
//   - standard HierarchicalNSW::searchKnn only (no filter, no stop condition);
//   - single-thread build and query;
//   - two build modes from the SAME source:
//       * upstream:   pristine v0.9.0 headers, HNSWLIB_TRACE_ENABLED undefined
//       * instrumented: patched headers, -DHNSWLIB_TRACE_ENABLED
//
// Observation scope: HNSW query distance-evaluation trace. This is NOT a
// hardware cache / prefetch / physical-memory access trace.
// ---------------------------------------------------------------------------

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include <vector>

// In the instrumented build hnswalg.h includes hnsw_trace_sink.h, which
// declares the sink globals/emitter defined below. In the upstream build no
// sink header is pulled in at all; these definitions are simply unused.
#include "hnswlib.h"
#include "space_ip.h"
#include "hnswalg.h"

using namespace hnswlib;

// ---------------------------------------------------------------------------
// Trace-sink globals (definitions live here, in the harness).
// ---------------------------------------------------------------------------
uint64_t g_hnsw_current_query_id = 0;
uint64_t g_hnsw_dist_call_count = 0;
bool g_hnsw_trace_sink_enabled = false;

struct TraceEvent {
    uint64_t query_id;
    uint64_t event_index;
    uint64_t internal_id;
    uint64_t external_id;
    int level;
    std::string site;
};
static std::vector<TraceEvent> g_events;

void hnsw_trace_emit(uint64_t internal_id, uint64_t external_id, int level, const char *site) {
    TraceEvent e;
    e.query_id = g_hnsw_current_query_id;
    e.event_index = static_cast<uint64_t>(g_events.size());
    e.internal_id = internal_id;
    e.external_id = external_id;
    e.level = level;
    e.site = site ? site : "";
    g_events.push_back(e);
}

// ---------------------------------------------------------------------------
// Fixed synthetic configuration.
// ---------------------------------------------------------------------------
static const size_t N = 1000;
static const size_t DIM = 16;
static const size_t M = 16;
static const size_t EF_CONSTRUCTION = 200;
static const size_t EF_SEARCH = 64;
static const size_t K = 10;
static const size_t NQ = 50;
static const unsigned SEED = 2026;
static const uint64_t LABEL_BASE = 100000;
static const uint64_t LABEL_STEP = 17;

struct TopKRow {
    uint64_t query_id;
    size_t rank;
    uint64_t external_id;
    float dist;
    uint32_t dist_bits;
};

static uint32_t float_bits(float f) {
    uint32_t b = 0;
    std::memcpy(&b, &f, sizeof(b));
    return b;
}

static std::string hex32(uint32_t v) {
    std::ostringstream os;
    os << "0x" << std::hex << std::nouppercase << std::setw(8) << std::setfill('0') << v;
    return os.str();
}

// FNV-1a 64-bit over a canonical string, used for trace/top-k reproducibility.
static uint64_t fnv1a(const std::string &s) {
    uint64_t h = 14695981039346656037ULL;
    for (unsigned char c : s) {
        h ^= static_cast<uint64_t>(c);
        h *= 1099511628211ULL;
    }
    return h;
}

static std::string event_hash_input(const std::vector<TraceEvent> &ev) {
    std::ostringstream os;
    for (const auto &e : ev) {
        os << e.internal_id << ':' << e.external_id << ':' << e.level << ':' << e.site << ';';
    }
    return os.str();
}

static std::string topk_hash_input(const std::vector<TopKRow> &rows) {
    std::ostringstream os;
    for (const auto &r : rows) {
        os << r.external_id << ':' << hex32(r.dist_bits) << ';';
    }
    return os.str();
}

struct IndexBundle {
    InnerProductSpace *space;
    HierarchicalNSW<float> *index;
};

static IndexBundle build_index(const std::vector<float> &base) {
    IndexBundle b;
    b.space = new InnerProductSpace(DIM);
    b.index = new HierarchicalNSW<float>(b.space, N, M, EF_CONSTRUCTION, SEED, false);
    b.index->setEf(EF_SEARCH);
    // Single-threaded insertion in a fixed order; non-contiguous external labels.
    for (size_t i = 0; i < N; ++i) {
        b.index->addPoint(base.data() + i * DIM, static_cast<labeltype>(LABEL_BASE + LABEL_STEP * i));
    }
    return b;
}

static void free_index(IndexBundle &b) {
    delete b.index;
    b.index = nullptr;
    delete b.space;
    b.space = nullptr;
}

// Runs one query and captures top-k in deterministic pop order.
static std::vector<TopKRow> search_topk(HierarchicalNSW<float> &index,
                                        const float *q,
                                        uint64_t query_id) {
    auto pq = index.searchKnn(q, K);
    std::vector<TopKRow> rows;
    rows.reserve(pq.size());
    size_t rank = 0;
    while (!pq.empty()) {
        auto item = pq.top();
        pq.pop();
        TopKRow r;
        r.query_id = query_id;
        r.rank = rank++;
        r.external_id = static_cast<uint64_t>(item.second);
        r.dist = item.first;
        r.dist_bits = float_bits(item.first);
        rows.push_back(r);
    }
    return rows;
}

static void write_topk(std::ofstream &out, const std::vector<TopKRow> &rows) {
    for (const auto &r : rows) {
        out << "{\"query_id\":" << r.query_id
            << ",\"rank\":" << r.rank
            << ",\"external_id\":" << r.external_id
            << ",\"dist_bits\":\"" << hex32(r.dist_bits) << "\""
            << ",\"dist\":" << std::setprecision(9) << r.dist
            << "}\n";
    }
}

static void write_events(std::ofstream &out, const std::vector<TraceEvent> &ev) {
    for (const auto &e : ev) {
        out << "{\"query_id\":" << e.query_id
            << ",\"event_index\":" << e.event_index
            << ",\"internal_id\":" << e.internal_id
            << ",\"external_id\":" << e.external_id
            << ",\"level\":" << e.level
            << ",\"event_site\":\"" << e.site << "\"}\n";
    }
}

static bool open_of(std::ofstream &out, const std::string &path) {
    out.open(path, std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        std::cerr << "FATAL: cannot open output file: " << path << "\n";
        return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        std::cerr << "usage: exp10a_probe <upstream|instrumented> <outdir>\n";
        return 2;
    }
    const std::string mode = argv[1];
    const std::string outdir = argv[2];
    if (mode != "upstream" && mode != "instrumented") {
        std::cerr << "FATAL: unknown mode: " << mode << "\n";
        return 2;
    }

    // ---- fixed-random synthetic data ----
    std::vector<float> base(N * DIM);
    std::vector<float> queries(NQ * DIM);
    {
        std::mt19937 rng(SEED);
        std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
        for (auto &v : base) v = dist(rng);
        for (auto &v : queries) v = dist(rng);
    }

    std::ofstream topk_out, sinkoff_out, trace_out, summary_out;
    const std::string topk_path = outdir + "/exp10a_" + mode + "_topk.jsonl";
    if (!open_of(topk_out, topk_path)) return 3;

    std::ofstream *sinkoff = nullptr;
    std::ofstream *trace = nullptr;
    std::ofstream *summary = nullptr;
    if (mode == "instrumented") {
        sinkoff = new std::ofstream();
        trace = new std::ofstream();
        summary = new std::ofstream();
        if (!open_of(*sinkoff, outdir + "/exp10a_sinkoff_topk.jsonl") ||
            !open_of(*trace, outdir + "/exp10a_synthetic_trace.jsonl") ||
            !open_of(*summary, outdir + "/exp10a_probe_summary.jsonl")) {
            return 3;
        }
    }

    IndexBundle ix = build_index(base);

    // ---- pass 1: primary run ----
    for (size_t q = 0; q < NQ; ++q) {
        const float *qv = queries.data() + q * DIM;
        uint64_t qid = static_cast<uint64_t>(q);

        g_hnsw_current_query_id = qid;
        g_hnsw_dist_call_count = 0;
        g_events.clear();
        g_hnsw_trace_sink_enabled = (mode == "instrumented");
        std::vector<TopKRow> rows = search_topk(*ix.index, qv, qid);
        g_hnsw_trace_sink_enabled = false;

        write_topk(topk_out, rows);

        if (mode == "instrumented") {
            const uint64_t event_count = static_cast<uint64_t>(g_events.size());
            const uint64_t call_count = g_hnsw_dist_call_count;
            bool has_level0 = false, has_upper = false;
            for (const auto &e : g_events) {
                if (e.level == 0) has_level0 = true;
                if (e.level > 0) has_upper = true;
            }
            const uint64_t trace_hash = fnv1a(event_hash_input(g_events));
            write_events(*trace, g_events);
            *summary << "{\"query_id\":" << qid
                     << ",\"record\":\"primary\""
                     << ",\"event_count\":" << event_count
                     << ",\"distance_call_count\":" << call_count
                     << ",\"has_level0\":" << (has_level0 ? "true" : "false")
                     << ",\"has_upper\":" << (has_upper ? "true" : "false")
                     << ",\"trace_hash\":\"0x" << std::hex << std::setw(16)
                     << std::setfill('0') << trace_hash << std::dec << "\""
                     << ",\"topk_hash\":\"0x" << std::hex << std::setw(16)
                     << std::setfill('0') << fnv1a(topk_hash_input(rows)) << std::dec << "\"";
            // sink-off run: identical top-k, and NO emitted events.
            g_hnsw_current_query_id = qid;
            g_hnsw_dist_call_count = 0;
            g_events.clear();
            g_hnsw_trace_sink_enabled = false;
            std::vector<TopKRow> rows_off = search_topk(*ix.index, qv, qid);
            write_topk(*sinkoff, rows_off);
            *summary << ",\"sinkoff_event_count\":" << g_events.size()
                     << ",\"sinkoff_topk_hash\":\"0x" << std::hex << std::setw(16)
                     << std::setfill('0') << fnv1a(topk_hash_input(rows_off)) << std::dec << "\"";
            // repeat on the SAME index: trace hash must be identical.
            g_hnsw_current_query_id = qid;
            g_hnsw_dist_call_count = 0;
            g_events.clear();
            g_hnsw_trace_sink_enabled = true;
            search_topk(*ix.index, qv, qid);
            g_hnsw_trace_sink_enabled = false;
            *summary << ",\"repeat_trace_hash\":\"0x" << std::hex << std::setw(16)
                     << std::setfill('0') << fnv1a(event_hash_input(g_events)) << std::dec << "\"}\n";
        }
    }

    if (mode == "instrumented") {
        // ---- pass 2: rebuild with identical seed / order, compare trace hash ----
        free_index(ix);
        ix = build_index(base);
        for (size_t q = 0; q < NQ; ++q) {
            g_hnsw_current_query_id = static_cast<uint64_t>(q);
            g_hnsw_dist_call_count = 0;
            g_events.clear();
            g_hnsw_trace_sink_enabled = true;
            search_topk(*ix.index, queries.data() + q * DIM, static_cast<uint64_t>(q));
            g_hnsw_trace_sink_enabled = false;
            // Appended as separate records; the analysis script pairs by query_id.
            *summary << "{\"query_id\":" << q
                     << ",\"record\":\"rebuilt\""
                     << ",\"rebuilt_trace_hash\":\"0x" << std::hex << std::setw(16)
                     << std::setfill('0') << fnv1a(event_hash_input(g_events)) << std::dec
                     << "\"}\n";
        }
        delete summary;
        delete trace;
        delete sinkoff;
    }

    free_index(ix);
    topk_out.close();

    std::cout << "mode=" << mode << " queries=" << NQ
              << " topk_path=" << topk_path << "\n";
    return 0;
}
