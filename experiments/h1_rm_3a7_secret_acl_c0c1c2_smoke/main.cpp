// H1-RM.3A.7 — C0/C1/C2 smoke with a PRIVATE ACL + strict observation split.
//
// One ACL fixture, one index, one batch of queries. Three groups:
//   C0  searchKnn(q, K, &SecretAclRecordingFilter)
//   C1  searchStopConditionClosest(q, EfReplayStopCondition, filter)
//   C2  C1 + K-hit stop (counts AUTHORIZED filter passes only)
//
// This is NOT an attack experiment: no A0/A1 pair, no classifier, no BA/AUC,
// no page/block simulation and no real ACL instance. The fixture is a fixed
// synthetic vector written by the existing encode_acl_bitmap().
//
// OUTPUT IS STRICTLY LAYERED:
//   internal_diagnostics_C{0,1,2}.jsonl  trusted, NOT attacker-observable.
//   observer_proxy_C{0,1,2}.jsonl        logical observation proxy ONLY;
//                                        NOT a physical page trace.
//
// Usage: h1rm3a7_smoke <fixture_path> <outdir>
// Exit 0 = all invariants hold; non-zero otherwise.

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <queue>
#include <random>
#include <sstream>
#include <string>
#include <vector>

#include "hnswlib.h"
#include "space_ip.h"
#include "hnswalg.h"
#include "acl_bitmap.h"
#include "hnsw_acl_filter.h"

using namespace hnswlib;

// ---- globals required by rm2_sink.h (macro body in instrumented hnswalg.h) ----
uint64_t g_rm2_current_query_id = 0;
bool g_rm2_enabled = true;  // diagnostics are always collected in this smoke
static std::string g_current_group = "";

struct Rm2Event {
    uint64_t query_id = 0;
    uint64_t event_index = 0;
    std::string group;
    std::string event_type;
    uint64_t internal_id = 0;
    uint64_t external_id = 0;
    int level = 0;
    uint32_t dist_bits = 0;
    int64_t extra = 0;
};
static std::vector<Rm2Event> g_events;

static uint32_t float_bits(float f) {
    uint32_t b = 0;
    std::memcpy(&b, &f, sizeof(b));
    return b;
}

void rm2_emit(const char *event_type, uint64_t internal_id,
              uint64_t external_id, int level, float dist, int64_t extra) {
    Rm2Event e;
    e.query_id = g_rm2_current_query_id;
    e.event_index = static_cast<uint64_t>(g_events.size());
    e.group = g_current_group;
    e.event_type = event_type ? event_type : "";
    e.internal_id = internal_id;
    e.external_id = external_id;
    e.level = level;
    e.dist_bits = float_bits(dist);
    e.extra = extra;
    g_events.push_back(e);
}

// ---- fixed synthetic configuration (independent smoke scale) ----
static const size_t DIM = 8;
static const size_t M = 16;
static const size_t EF_CONSTRUCTION = 200;
static const size_t EF_SEARCH = 64;
static const size_t K = 5;
static const size_t NQ = 6;
static const unsigned SEED = 2026;
static const uint64_t LABEL_BASE = 100000;
static const uint64_t LABEL_STEP = 17;
static const size_t EF_RULE = 64;  // replay of std::max(ef_, k)

static uint64_t g_auth_hits = 0;
static int64_t g_khit_event_index = -1;

static int64_t internal_of(labeltype label) {
    return (static_cast<int64_t>(label) - static_cast<int64_t>(LABEL_BASE)) /
           static_cast<int64_t>(LABEL_STEP);
}

// Real callback: delegates every decision to the 3A.5 SecretAclFilter. The
// public-hash authorized() of RM2 is NEVER used here.
struct SecretAclRecordingFilter : public SecretAclFilter {
    explicit SecretAclRecordingFilter(const h1acl::AclBitmap& acl)
        : SecretAclFilter(acl) {}

    bool operator()(labeltype id) override {
        const bool ok = SecretAclFilter::operator()(id);
        // INTERNAL ONLY: carries the authorization bit in `extra`.
        rm2_emit("filter_check", static_cast<uint64_t>(internal_of(id)),
                 static_cast<uint64_t>(id), -1, 0.0f, ok ? 1 : 0);
        if (ok) {
            ++g_auth_hits;
            if (g_auth_hits == static_cast<uint64_t>(K) &&
                g_khit_event_index < 0) {
                g_khit_event_index =
                    static_cast<int64_t>(g_events.size()) - 1;
            }
        }
        return ok;
    }
};

struct DistCompare {
    bool operator()(const std::pair<float, labeltype>& a,
                    const std::pair<float, labeltype>& b) const noexcept {
        return a.first < b.first;
    }
};

// C1: replay the standard ef rule with a real result-set mirror.
class EfReplayStopCondition : public BaseSearchStopCondition<float> {
protected:
    size_t ef_;
    std::priority_queue<std::pair<float, labeltype>,
                        std::vector<std::pair<float, labeltype>>,
                        DistCompare> R_;

public:
    explicit EfReplayStopCondition(size_t ef) : ef_(ef) {}

    void add_point_to_result(labeltype label, const void*, float dist) override {
        R_.emplace(dist, label);
    }
    void remove_point_from_result(labeltype, const void*, float) override {
        if (!R_.empty()) R_.pop();
    }
    bool should_stop_search(float candidate_dist, float lowerBound) override {
        return candidate_dist > lowerBound && R_.size() == ef_;
    }
    bool should_consider_candidate(float d, float lowerBound) override {
        return R_.size() < ef_ || lowerBound > d;
    }
    bool should_remove_extra() override { return R_.size() > ef_; }
    void filter_results(std::vector<std::pair<float, labeltype>>&) override {}
};

// C2: C1 plus the original K-hit stop. Counts only authorized callbacks.
class KHitStopCondition : public EfReplayStopCondition {
public:
    explicit KHitStopCondition(size_t ef) : EfReplayStopCondition(ef) {}
    bool should_stop_search(float candidate_dist, float lowerBound) override {
        if (g_auth_hits >= static_cast<uint64_t>(K)) return true;
        return EfReplayStopCondition::should_stop_search(candidate_dist,
                                                         lowerBound);
    }
};

static std::string hex32(uint32_t v) {
    std::ostringstream os;
    os << "0x" << std::hex << std::nouppercase << std::setw(8)
       << std::setfill('0') << v;
    return os.str();
}

static bool open_of(std::ofstream& out, const std::string& path) {
    out.open(path, std::ios::out | std::ios::trunc);
    if (!out.is_open()) {
        std::cerr << "FATAL: cannot open output: " << path << "\n";
        return false;
    }
    return true;
}

static bool is_internal_only_event(const std::string& t) {
    return t == "filter_check" || t == "result_add" || t == "result_remove";
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: h1rm3a7_smoke <fixture_path> <outdir>\n";
        return 2;
    }
    const std::string fixture = argv[1];
    const std::string outdir = argv[2];

    h1acl::AclBitmap acl;
    const h1acl::Status st = acl.load(fixture);
    if (st != h1acl::Status::Ok) {
        std::cout << "LOAD " << h1acl::status_name(st) << "\n";
        return 1;
    }
    const size_t n = static_cast<size_t>(acl.member_count());
    if (n < K) {
        std::cerr << "FATAL: fixture too small\n";
        return 1;
    }

    std::ofstream internal[3], observer[3];
    const char* groups[3] = {"C0", "C1", "C2"};
    for (int i = 0; i < 3; ++i) {
        if (!open_of(internal[i], outdir + "/internal_diagnostics_" +
                                      groups[i] + ".jsonl") ||
            !open_of(observer[i], outdir + "/observer_proxy_" + groups[i] +
                                      ".jsonl")) {
            return 3;
        }
        internal[i] << "{\"record_type\":\"internal_trusted_notice\","
                       "\"trust\":\"internal_diagnostics_only\","
                       "\"attacker_observable\":false,"
                       "\"do_not_use_for_attack_evaluation\":true}\n";
        observer[i] << "{\"record_type\":\"observer_proxy_notice\","
                       "\"trust\":\"untrusted_observer_view\","
                       "\"trace_kind\":\"logical_observation_proxy\","
                       "\"is_physical_page_trace\":false,"
                       "\"filtered_internal_event_types\":"
                       "[\"filter_check\",\"result_add\",\"result_remove\"]}\n";
    }

    std::vector<float> base(n * DIM), queries(NQ * DIM);
    {
        std::mt19937 rng(SEED);
        std::uniform_real_distribution<float> d(-1.0f, 1.0f);
        for (auto& v : base) v = d(rng);
        for (auto& v : queries) v = d(rng);
    }

    InnerProductSpace space(DIM);
    HierarchicalNSW<float> index(&space, n, M, EF_CONSTRUCTION, SEED, false);
    index.setEf(EF_SEARCH);
    for (size_t i = 0; i < n; ++i) {
        index.addPoint(base.data() + i * DIM,
                       static_cast<labeltype>(LABEL_BASE + LABEL_STEP * i));
    }

    bool all_ok = true;
    bool c2_khit_seen = false;

    for (size_t q = 0; q < NQ; ++q) {
        const float* qv = queries.data() + q * DIM;
        g_rm2_current_query_id = static_cast<uint64_t>(q);

        for (int gi = 0; gi < 3; ++gi) {
            g_current_group = groups[gi];
            g_events.clear();
            g_auth_hits = 0;
            g_khit_event_index = -1;
            // Observer-only dense index: reset for every (query, group) and
            // incremented ONLY for events actually written to the observer
            // proxy. It deliberately does NOT reuse the internal event_index,
            // so gaps caused by removed internal-only events are not leaked.
            uint64_t observer_event_index = 0;

            SecretAclRecordingFilter filter(acl);
            std::vector<labeltype> returned;
            if (gi == 0) {
                auto pq = index.searchKnn(qv, K, &filter);
                while (!pq.empty()) {
                    returned.push_back(pq.top().second);
                    pq.pop();
                }
            } else if (gi == 1) {
                EfReplayStopCondition sc(EF_RULE);
                auto vec = index.searchStopConditionClosest(qv, sc, &filter);
                // Upstream v0.9.0 quirk: searchKnn() converts internal ids to
                // external labels, but searchStopConditionClosest() copies the
                // internal tableint directly into the returned pair. Convert
                // here in the harness; DO NOT modify the frozen header.
                for (const auto& hit : vec) {
                    returned.push_back(index.getExternalLabel(
                        static_cast<tableint>(hit.second)));
                }
            } else {
                KHitStopCondition sc(EF_RULE);
                auto vec = index.searchStopConditionClosest(qv, sc, &filter);
                for (const auto& hit : vec) {
                    returned.push_back(index.getExternalLabel(
                        static_cast<tableint>(hit.second)));
                }
            }

            bool result_all_authorized = !returned.empty();
            for (labeltype label : returned) {
                const h1acl::Lookup lk = acl.lookup_label(
                    static_cast<uint64_t>(label));
                if (!lk.ok || lk.bit != 1) result_all_authorized = false;
            }
            if (!result_all_authorized) all_ok = false;
            if (gi == 2 && g_khit_event_index >= 0) c2_khit_seen = true;

            uint64_t n_dist = 0, n_filter = 0, n_filter_ok = 0;
            uint64_t n_add = 0, n_remove = 0, n_consider = 0;
            uint64_t n_stop_check = 0, n_search_stop = 0;
            for (const auto& e : g_events) {
                if (e.event_type == "distance_eval") ++n_dist;
                else if (e.event_type == "filter_check") {
                    ++n_filter;
                    if (e.extra == 1) ++n_filter_ok;
                } else if (e.event_type == "result_add") ++n_add;
                else if (e.event_type == "result_remove") ++n_remove;
                else if (e.event_type == "candidate_consider") ++n_consider;
                else if (e.event_type == "stop_check") ++n_stop_check;
                else if (e.event_type == "search_stop") ++n_search_stop;
            }

            // ---- internal diagnostics: full trusted fields ----
            for (const auto& e : g_events) {
                internal[gi] << "{\"query_id\":" << e.query_id
                             << ",\"event_index\":" << e.event_index
                             << ",\"group\":\"" << e.group << "\""
                             << ",\"event_type\":\"" << e.event_type << "\""
                             << ",\"internal_id\":" << e.internal_id
                             << ",\"external_id\":" << e.external_id
                             << ",\"level\":" << e.level
                             << ",\"dist_bits\":\"" << hex32(e.dist_bits)
                             << "\",\"extra\":" << e.extra << "}\n";
            }
            internal[gi] << "{\"record_type\":\"group_summary\""
                         << ",\"query_id\":" << q
                         << ",\"group\":\"" << g_current_group << "\""
                         << ",\"returned_size\":" << returned.size()
                         << ",\"result_all_authorized\":"
                         << (result_all_authorized ? 1 : 0)
                         << ",\"auth_hits\":" << g_auth_hits
                         << ",\"khit_event_index\":" << g_khit_event_index
                         << ",\"n_distance_eval\":" << n_dist
                         << ",\"n_filter_check\":" << n_filter
                         << ",\"n_filter_ok\":" << n_filter_ok
                         << ",\"n_result_add\":" << n_add
                         << ",\"n_result_remove\":" << n_remove
                         << ",\"n_candidate_consider\":" << n_consider
                         << ",\"n_stop_check\":" << n_stop_check
                         << ",\"n_search_stop\":" << n_search_stop
                         << ",\"event_count\":" << g_events.size() << "}\n";

            // ---- observer proxy: no authorization bit, no result-set events ----
            // event_index here is a DENSE OBSERVER-ONLY counter:
            //   - reset above at the start of every (query, group);
            //   - incremented only for events actually emitted below;
            //   - independent of the internal e.event_index.
            // The sparse internal sequence (and hence the count/position of
            // removed internal-only events) is NOT encoded in this field.
            for (const auto& e : g_events) {
                if (is_internal_only_event(e.event_type)) continue;
                observer[gi] << "{\"query_id\":" << e.query_id
                             << ",\"event_index\":" << observer_event_index++
                             << ",\"group\":\"" << e.group << "\""
                             << ",\"event_type\":\"" << e.event_type << "\"";
                if (e.event_type == "distance_eval") {
                    observer[gi] << ",\"external_id\":" << e.external_id
                                 << ",\"level\":" << e.level
                                 << ",\"dist_bits\":\""
                                 << hex32(e.dist_bits) << "\"";
                }
                observer[gi] << "}\n";
            }
        }
    }

    for (int i = 0; i < 3; ++i) {
        internal[i].close();
        observer[i].close();
    }
    std::cout << "mode=H1-RM.3A.7 fixture=synthetic queries=" << NQ
              << " all_results_authorized=" << (all_ok ? 1 : 0)
              << " c2_khit_seen=" << (c2_khit_seen ? 1 : 0)
              << " outdir=" << outdir << "\n";
    return (all_ok && c2_khit_seen) ? 0 : 1;
}
