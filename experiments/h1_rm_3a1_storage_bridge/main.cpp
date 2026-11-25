// ---------------------------------------------------------------------------
// H1-RM.2: Native HNSW filter/stop semantics probe.
//
// Three controlled groups on the SAME index, queries, and filter:
//   C0  standard HierarchicalNSW::searchKnn(q, K, filter)
//   C1  searchStopConditionClosest(q, EfReplayStopCondition, filter)
//       where the stop condition replays the standard ef rule (ef=64) with a
//       real result set, NOT a scalar counter.
//   C2  C1 plus a K-hit stop (K authorized filter passes).
//
// NO ACL leakage attack. NO new data. Uses the fixed synthetic config of
// EXP-10A: 1000 vectors, dim 16, IP, M=16, efC=200, efS=64, k=10, 50 queries,
// seed 2026, external label = 100000 + 17*i.
//
// Observation scope: HNSW query control-flow events. NOT hardware/cache trace.
// ---------------------------------------------------------------------------

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <queue>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "hnswlib.h"
#include "space_ip.h"
#include "hnswalg.h"
#ifdef HNSWLIB_RM31_BRIDGE
#include "storage_access.h"
#endif

using namespace hnswlib;

// ---- globals required by rm2_sink.h (defined by the instrumented header) ----
uint64_t g_rm2_current_query_id = 0;
bool g_rm2_enabled = false;
static uint64_t g_rm2_event_seq = 0;
static uint64_t g_rm2_auth_hits = 0;
static int64_t g_rm2_khit_event_index = -1;
static std::string g_rm2_group = "";

struct Rm2Event {
    uint64_t query_id;
    uint64_t event_index;
    std::string group;
    std::string event_type;
    uint64_t internal_id;
    uint64_t external_id;
    int level;
    uint32_t dist_bits;
    int64_t extra;
};
static std::vector<Rm2Event> g_events;

static uint32_t float_bits(float f) {
    uint32_t b = 0;
    std::memcpy(&b, &f, sizeof(b));
    return b;
}

void rm2_emit(const char *event_type,
              uint64_t internal_id,
              uint64_t external_id,
              int level,
              float dist,
              int64_t extra) {
    Rm2Event e;
    e.query_id = g_rm2_current_query_id;
    e.event_index = g_rm2_event_seq++;
    e.group = g_rm2_group;
    e.event_type = event_type ? event_type : "";
    e.internal_id = internal_id;
    e.external_id = external_id;
    e.level = level;
    e.dist_bits = float_bits(dist);
    e.extra = extra;
    g_events.push_back(e);
}

#ifdef HNSWLIB_RM31_BRIDGE
// ---- H1-RM.3A.1 storage request recorder -----------------------------
// Receives ONLY StorageRequest metadata. It never sees ACL bits, filter
// results, distance values, candidate sets, or result sets.
struct JsonlRequestRecorder : hnsw_bridge::RequestRecorder {
    std::vector<hnsw_bridge::StorageRequest> requests;
    void record(const hnsw_bridge::StorageRequest &req) override {
        requests.push_back(req);
    }
};

static const char *request_type_name(hnsw_bridge::RequestType t) {
    switch (t) {
        case hnsw_bridge::RequestType::node_read: return "node_read";
        case hnsw_bridge::RequestType::neighbor_read: return "neighbor_read";
        case hnsw_bridge::RequestType::boundary: return "boundary";
        default: return "unknown";
    }
}
#endif

// ---- fixed synthetic configuration (identical to EXP-10A) ----
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
static const size_t EF_RULE = 64;  // == std::max(ef_, k) in searchKnn

// Deterministic synthetic authorization: 10% of external labels.
static bool authorized(labeltype label) {
    uint64_t h = static_cast<uint64_t>(label) * 2654435761ULL;
    h ^= h >> 15;
    return (h % 100) < 10;
}

static int64_t internal_of(labeltype label) {
    int64_t v = (static_cast<int64_t>(label) - static_cast<int64_t>(LABEL_BASE));
    return v / static_cast<int64_t>(LABEL_STEP);
}

// Recording filter: calls the upstream authorization predicate and emits a
// filter_check event ONLY when the callback is actually invoked by hnswlib.
struct RecordingFilter : BaseFilterFunctor {
    bool authorize_value = false;
    bool operator()(labeltype id) override {
        bool ok = authorized(id);
        // filter_check carries pass/fail in `extra`; internal id is recovered
        // from the known synthetic label rule (report states this explicitly).
        // Emit is gated by the sink switch so trace-off runs write no events;
        // authorization and hit counting stay unconditional so C2 stop
        // behaviour is identical in both modes.
        if (g_rm2_enabled) {
            rm2_emit("filter_check",
                     static_cast<uint64_t>(internal_of(id)),
                     static_cast<uint64_t>(id),
                     -1,
                     0.0f,
                     ok ? 1 : 0);
        }
        if (ok) {
            ++g_rm2_auth_hits;
            if (g_rm2_auth_hits == static_cast<uint64_t>(K) && g_rm2_khit_event_index < 0) {
                g_rm2_khit_event_index = static_cast<int64_t>(g_rm2_event_seq) - 1;
            }
        }
        authorize_value = ok;
        return ok;
    }
};

// Mirror of hnswlib's CompareByFirst: order by distance only.
struct DistCompare {
    bool operator()(const std::pair<float, labeltype> &a,
                    const std::pair<float, labeltype> &b) const noexcept {
        return a.first < b.first;
    }
};

// C1 stop condition: replay the standard searchBaseLayerST<false> ef rule
// using a REAL result set R (mirroring top_candidates), not a counter.
class EfReplayStopCondition : public BaseSearchStopCondition<float> {
protected:
    size_t ef_;
    std::priority_queue<std::pair<float, labeltype>,
                        std::vector<std::pair<float, labeltype>>,
                        DistCompare> R_;

public:
    explicit EfReplayStopCondition(size_t ef) : ef_(ef) {}

    void add_point_to_result(labeltype label, const void *, float dist) override {
        R_.emplace(dist, label);
    }
    void remove_point_from_result(labeltype, const void *, float) override {
        // hnswlib pops top_candidates.top() immediately before this callback;
        // pop the mirror identically. Do NOT rely on the dist argument (the
        // upstream passes the current candidate dist, not the removed id's).
        if (!R_.empty()) R_.pop();
    }
    bool should_stop_search(float candidate_dist, float lowerBound) override {
        return candidate_dist > lowerBound && R_.size() == ef_;
    }
    bool should_consider_candidate(float candidate_dist, float lowerBound) override {
        return R_.size() < ef_ || lowerBound > candidate_dist;
    }
    bool should_remove_extra() override {
        return R_.size() > ef_;
    }
    void filter_results(std::vector<std::pair<float, labeltype>> &) override {
        // C1: no extra change, exactly as the task requires.
    }
    size_t result_size() const { return R_.size(); }
};

// C2: C1 plus K-hit stop. Filter passes are counted by the global counter
// incremented in RecordingFilter::operator().
class KHitStopCondition : public EfReplayStopCondition {
public:
    explicit KHitStopCondition(size_t ef) : EfReplayStopCondition(ef) {}
    bool should_stop_search(float candidate_dist, float lowerBound) override {
        if (g_rm2_auth_hits >= static_cast<uint64_t>(K)) return true;
        return EfReplayStopCondition::should_stop_search(candidate_dist, lowerBound);
    }
};

struct IndexBundle {
    InnerProductSpace *space;
    HierarchicalNSW<float> *index;
};

static IndexBundle build_index(const std::vector<float> &base) {
    IndexBundle b;
    b.space = new InnerProductSpace(DIM);
    b.index = new HierarchicalNSW<float>(b.space, N, M, EF_CONSTRUCTION, SEED, false);
    b.index->setEf(EF_SEARCH);
    for (size_t i = 0; i < N; ++i) {
        b.index->addPoint(base.data() + i * DIM,
                          static_cast<labeltype>(LABEL_BASE + LABEL_STEP * i));
    }
    return b;
}

static void free_index(IndexBundle &b) {
    delete b.index; b.index = nullptr;
    delete b.space; b.space = nullptr;
}

struct TopRow {
    uint32_t dist_bits;
    uint64_t external_id;
    float dist;
};

static std::vector<TopRow> normalize_from_pq(
        std::priority_queue<std::pair<float, labeltype>> pq) {
    std::vector<TopRow> rows;
    while (!pq.empty()) {
        auto it = pq.top(); pq.pop();
        rows.push_back({float_bits(it.first), static_cast<uint64_t>(it.second), it.first});
    }
    std::sort(rows.begin(), rows.end(), [](const TopRow &a, const TopRow &b) {
        if (a.dist != b.dist) return a.dist < b.dist;
        return a.external_id < b.external_id;
    });
    if (rows.size() > K) rows.resize(K);
    return rows;
}

static std::vector<TopRow> normalize_from_vec(
        const std::vector<std::pair<float, labeltype>> &vec) {
    std::vector<TopRow> rows;
    for (const auto &it : vec) {
        rows.push_back({float_bits(it.first), static_cast<uint64_t>(it.second), it.first});
    }
    std::sort(rows.begin(), rows.end(), [](const TopRow &a, const TopRow &b) {
        if (a.dist != b.dist) return a.dist < b.dist;
        return a.external_id < b.external_id;
    });
    if (rows.size() > K) rows.resize(K);
    return rows;
}

static std::string hex32(uint32_t v) {
    std::ostringstream os;
    os << "0x" << std::hex << std::nouppercase << std::setw(8) << std::setfill('0') << v;
    return os.str();
}

static bool open_of(std::ofstream &out, const std::string &path) {
    out.open(path, std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        std::cerr << "FATAL: cannot open output: " << path << "\n";
        return false;
    }
    return true;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr << "usage: h1rm31_bridge <outdir> <trace:0|1> <bridge:0|1>\n";
        return 2;
    }
    const std::string outdir = argv[1];
    const bool trace = (std::string(argv[2]) == "1");
    const bool use_bridge = (std::string(argv[3]) == "1");

    std::vector<float> base(N * DIM), queries(NQ * DIM);
    {
        std::mt19937 rng(SEED);
        std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
        for (auto &v : base) v = dist(rng);
        for (auto &v : queries) v = dist(rng);
    }

    std::ofstream events_out, topk_out, summary_out;
#ifdef HNSWLIB_RM31_BRIDGE
    std::ofstream requests_out;
#endif
    if (!open_of(events_out, outdir + "/events.jsonl") ||
        !open_of(topk_out, outdir + "/topk.jsonl") ||
        !open_of(summary_out, outdir + "/run_summary.jsonl")) return 3;
#ifdef HNSWLIB_RM31_BRIDGE
    if (!open_of(requests_out, outdir + "/requests.jsonl")) return 3;
#endif

    IndexBundle ix = build_index(base);

#ifdef HNSWLIB_RM31_BRIDGE
    hnsw_bridge::LocalMemoryStorage storage;
    JsonlRequestRecorder request_recorder;
    storage.data_level0_memory_ = ix.index->data_level0_memory_;
    storage.linkLists_ = ix.index->linkLists_;
    storage.size_data_per_element_ = ix.index->size_data_per_element_;
    storage.size_links_per_element_ = ix.index->size_links_per_element_;
    storage.offsetData_ = ix.index->offsetData_;
    storage.offsetLevel0_ = ix.index->offsetLevel0_;
    storage.recorder_ = &request_recorder;
    // Baseline: storage_access_ left nullptr => upstream direct memory reads.
    // Bridged:  inject the boundary => every node/neighbor read routed + logged.
    if (use_bridge) {
        ix.index->setStorageAccess(&storage);
    }
#endif

    for (size_t q = 0; q < NQ; ++q) {
        const float *qv = queries.data() + q * DIM;
        g_rm2_current_query_id = static_cast<uint64_t>(q);

        for (int gi = 0; gi < 3; ++gi) {
            const std::string group = (gi == 0) ? "C0" : (gi == 1) ? "C1" : "C2";
            g_rm2_group = group;
            g_rm2_event_seq = 0;
            g_rm2_auth_hits = 0;
            g_rm2_khit_event_index = -1;
            g_events.clear();
            g_rm2_enabled = trace;

#ifdef HNSWLIB_RM31_BRIDGE
            storage.reset_query(static_cast<uint64_t>(q));
            storage.enabled_ = (trace && use_bridge);
            if (trace && use_bridge) {
                request_recorder.record(hnsw_bridge::StorageRequest{
                    static_cast<uint64_t>(q), storage.seq_++,
                    hnsw_bridge::RequestType::boundary, 0, -1, "query_start"});
            }
#endif

            RecordingFilter filter;
            std::vector<TopRow> rows;
            size_t returned_size = 0;
            if (gi == 0) {
                auto pq = ix.index->searchKnn(qv, K, &filter);
                returned_size = pq.size();
                rows = normalize_from_pq(std::move(pq));
            } else if (gi == 1) {
                EfReplayStopCondition sc(EF_RULE);
                auto vec = ix.index->searchStopConditionClosest(qv, sc, &filter);
                returned_size = vec.size();
                rows = normalize_from_vec(vec);
            } else {
                KHitStopCondition sc(EF_RULE);
                auto vec = ix.index->searchStopConditionClosest(qv, sc, &filter);
                returned_size = vec.size();
                rows = normalize_from_vec(vec);
            }
            g_rm2_enabled = false;

#ifdef HNSWLIB_RM31_BRIDGE
            if (trace && use_bridge) {
                request_recorder.record(hnsw_bridge::StorageRequest{
                    static_cast<uint64_t>(q), storage.seq_++,
                    hnsw_bridge::RequestType::boundary, 0, -1, "query_end"});
            }
#endif

            // event log
            if (trace) {
                for (const auto &e : g_events) {
                    events_out << "{\"query_id\":" << e.query_id
                               << ",\"event_index\":" << e.event_index
                               << ",\"group\":\"" << e.group << "\""
                               << ",\"event_type\":\"" << e.event_type << "\""
                               << ",\"internal_id\":" << e.internal_id
                               << ",\"external_id\":" << e.external_id
                               << ",\"level\":" << e.level
                               << ",\"dist_bits\":\"" << hex32(e.dist_bits) << "\""
                               << ",\"extra\":" << e.extra << "}\n";
                }
            }

            // top-k rows
            for (size_t r = 0; r < rows.size(); ++r) {
                const auto &row = rows[r];
                topk_out << "{\"query_id\":" << q
                         << ",\"group\":\"" << group << "\""
                         << ",\"rank\":" << r
                         << ",\"external_id\":" << row.external_id
                         << ",\"dist_bits\":\"" << hex32(row.dist_bits) << "\""
                         << "}\n";
            }

            // per (query,group) summary
            uint64_t n_dist = 0, n_filter = 0, n_filter_ok = 0, n_consider = 0;
            uint64_t n_stop_check = 0, n_search_stop = 0, n_result_add = 0, n_result_remove = 0;
            int64_t first_search_stop = -1;
            for (const auto &e : g_events) {
                if (e.event_type == "distance_eval") ++n_dist;
                else if (e.event_type == "filter_check") {
                    ++n_filter;
                    if (e.extra == 1) ++n_filter_ok;
                } else if (e.event_type == "candidate_consider") ++n_consider;
                else if (e.event_type == "stop_check") ++n_stop_check;
                else if (e.event_type == "search_stop") {
                    ++n_search_stop;
                    if (first_search_stop < 0) first_search_stop = static_cast<int64_t>(e.event_index);
                } else if (e.event_type == "result_add") ++n_result_add;
                else if (e.event_type == "result_remove") ++n_result_remove;
            }
            summary_out << "{\"query_id\":" << q
                        << ",\"group\":\"" << group << "\""
                        << ",\"returned_size\":" << returned_size
                        << ",\"auth_hits\":" << g_rm2_auth_hits
                        << ",\"khit_event_index\":" << g_rm2_khit_event_index
                        << ",\"first_search_stop_index\":" << first_search_stop
                        << ",\"n_distance_eval\":" << n_dist
                        << ",\"n_filter_check\":" << n_filter
                        << ",\"n_filter_ok\":" << n_filter_ok
                        << ",\"n_candidate_consider\":" << n_consider
                        << ",\"n_result_add\":" << n_result_add
                        << ",\"n_result_remove\":" << n_result_remove
                        << ",\"n_stop_check\":" << n_stop_check
                        << ",\"n_search_stop\":" << n_search_stop
                        << ",\"event_count\":" << g_events.size()
                        << "}\n";

#ifdef HNSWLIB_RM31_BRIDGE
            // storage request log for this (query, group); group from runner
            for (const auto &r : request_recorder.requests) {
                requests_out << "{\"query_id\":" << r.query_id
                             << ",\"group\":\"" << group << "\""
                             << ",\"seq\":" << r.seq
                             << ",\"request_type\":\"" << request_type_name(r.type) << "\""
                             << ",\"node_id\":" << r.node_id
                             << ",\"level\":" << r.level
                             << ",\"boundary\":\"" << r.boundary << "\"}\n";
            }
            request_recorder.requests.clear();
#endif
        }
    }

    free_index(ix);
    events_out.close(); topk_out.close(); summary_out.close();
#ifdef HNSWLIB_RM31_BRIDGE
    requests_out.close();
#endif

    uint64_t authorized_nodes = 0;
    for (size_t i = 0; i < N; ++i) {
        if (authorized(static_cast<labeltype>(LABEL_BASE + LABEL_STEP * i))) ++authorized_nodes;
    }
    std::cout << "mode=H1-RM.3A.1 trace=" << trace
              << " bridge=" << (use_bridge ? 1 : 0)
              << " queries=" << NQ
              << " authorized_nodes=" << authorized_nodes
              << " outdir=" << outdir << "\n";
    return 0;
}
