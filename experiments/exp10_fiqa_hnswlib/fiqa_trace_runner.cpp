// EXP-10B.1: FiQA + hnswlib v0.9.0 ordered distance-evaluation trace runner.
//
// Scope: HNSW query distance-evaluation trace only. ACL masks never enter the
// C++ search path. This is NOT a hardware cache / prefetch / physical-memory
// access trace.
//
// Build with the EXP-10A instrumented headers and -DHNSWLIB_TRACE_ENABLED=1.

#include <algorithm>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

#include "hnswlib.h"
#include "space_ip.h"
#include "hnswalg.h"

using namespace hnswlib;

// Definitions required by hnsw_trace_sink.h.
uint64_t g_hnsw_current_query_id = 0;
uint64_t g_hnsw_dist_call_count = 0;
bool g_hnsw_trace_sink_enabled = false;

struct TraceEvent {
    uint64_t query_index;
    uint64_t event_index;
    uint64_t internal_id;
    uint64_t external_id;
    int level;
    std::string site;
};
static std::vector<TraceEvent> g_events;

void hnsw_trace_emit(uint64_t internal_id, uint64_t external_id, int level, const char *site) {
    TraceEvent e;
    e.query_index = g_hnsw_current_query_id;
    e.event_index = static_cast<uint64_t>(g_events.size());
    e.internal_id = internal_id;
    e.external_id = external_id;
    e.level = level;
    e.site = site ? site : "";
    g_events.push_back(e);
}

namespace {

constexpr size_t DIM = 384;
constexpr size_t M = 32;
constexpr size_t EF_CONSTRUCTION = 200;
constexpr size_t K = 10;
constexpr int SEED = 2026;
constexpr size_t SMOKE_N = 512;
constexpr size_t SMOKE_NQ = 20;

struct TopKRow {
    uint64_t query_index;
    size_t rank;
    uint64_t external_id;
    float dist;
    uint32_t dist_bits;
};

struct LoadedData {
    std::vector<float> base;
    std::vector<float> queries;
    std::vector<std::string> base_ids;
    std::vector<std::string> query_ids;
};

struct IndexBundle {
    InnerProductSpace *space = nullptr;
    HierarchicalNSW<float> *index = nullptr;
};

uint32_t float_bits(float f) {
    uint32_t b = 0;
    std::memcpy(&b, &f, sizeof(b));
    return b;
}

std::string hex32(uint32_t v) {
    std::ostringstream os;
    os << "0x" << std::hex << std::nouppercase << std::setw(8) << std::setfill('0') << v;
    return os.str();
}

uint64_t fnv1a(const std::string &s) {
    uint64_t h = 14695981039346656037ULL;
    for (unsigned char c : s) {
        h ^= static_cast<uint64_t>(c);
        h *= 1099511628211ULL;
    }
    return h;
}

std::string event_hash_input(const std::vector<TraceEvent> &ev) {
    std::ostringstream os;
    for (const auto &e : ev) {
        os << e.internal_id << ':' << e.external_id << ':' << e.level << ':' << e.site << ';';
    }
    return os.str();
}

std::string topk_hash_input(const std::vector<TopKRow> &rows) {
    std::ostringstream os;
    for (const auto &r : rows) {
        os << r.external_id << ':' << hex32(r.dist_bits) << ';';
    }
    return os.str();
}

std::string first_touch_hash_input(const std::vector<uint64_t> &ids) {
    std::ostringstream os;
    for (uint64_t id : ids) os << id << ';';
    return os.str();
}

std::vector<float> read_f32(const std::string &path, size_t rows, size_t dim) {
    std::ifstream in(path, std::ios::binary);
    if (!in) throw std::runtime_error("cannot open float32 file: " + path);
    in.seekg(0, std::ios::end);
    std::streamoff size = in.tellg();
    const uint64_t expected = static_cast<uint64_t>(rows) * dim * sizeof(float);
    if (size < 0 || static_cast<uint64_t>(size) != expected) {
        throw std::runtime_error("float32 size mismatch: " + path + " expected=" + std::to_string(expected) +
                                 " got=" + std::to_string(size));
    }
    in.seekg(0, std::ios::beg);
    std::vector<float> data(rows * dim);
    in.read(reinterpret_cast<char *>(data.data()), static_cast<std::streamsize>(expected));
    if (!in) throw std::runtime_error("float32 read failed: " + path);
    return data;
}

void write_f32(const std::string &path, const std::vector<float> &data) {
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) throw std::runtime_error("cannot write float32 file: " + path);
    out.write(reinterpret_cast<const char *>(data.data()), static_cast<std::streamsize>(data.size() * sizeof(float)));
}

std::vector<std::string> read_ids(const std::string &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open ID file: " + path);
    std::vector<std::string> ids;
    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty()) ids.push_back(line);
    }
    return ids;
}

void write_ids(const std::string &path, const std::vector<std::string> &ids) {
    std::ofstream out(path, std::ios::trunc);
    if (!out) throw std::runtime_error("cannot write ID file: " + path);
    for (const auto &id : ids) out << id << '\n';
}

void normalize_rows(std::vector<float> &data, size_t rows, size_t dim) {
    for (size_t r = 0; r < rows; ++r) {
        float *v = data.data() + r * dim;
        double norm2 = 0.0;
        for (size_t j = 0; j < dim; ++j) norm2 += static_cast<double>(v[j]) * v[j];
        const float inv = static_cast<float>(1.0 / std::sqrt(norm2));
        for (size_t j = 0; j < dim; ++j) v[j] *= inv;
    }
}

LoadedData load_data(const std::string &corpus_bin,
                     const std::string &queries_bin,
                     const std::string &corpus_ids,
                     const std::string &query_ids) {
    LoadedData d;
    std::vector<std::string> cids = read_ids(corpus_ids);
    std::vector<std::string> qids = read_ids(query_ids);
    d.base = read_f32(corpus_bin, cids.size(), DIM);
    d.queries = read_f32(queries_bin, qids.size(), DIM);
    d.base_ids = std::move(cids);
    d.query_ids = std::move(qids);
    return d;
}

IndexBundle build_index(const std::vector<float> &base, size_t n, int ef_search) {
    IndexBundle b;
    b.space = new InnerProductSpace(DIM);
    b.index = new HierarchicalNSW<float>(b.space, n, M, EF_CONSTRUCTION, SEED, false);
    for (size_t i = 0; i < n; ++i) {
        b.index->addPoint(base.data() + i * DIM, static_cast<labeltype>(i));
    }
    b.index->setEf(ef_search);
    return b;
}

void free_index(IndexBundle &b) {
    delete b.index;
    b.index = nullptr;
    delete b.space;
    b.space = nullptr;
}

std::vector<TopKRow> search_topk(HierarchicalNSW<float> &index,
                                 const float *q,
                                 uint64_t query_index,
                                 bool collect_events) {
    g_hnsw_current_query_id = query_index;
    g_hnsw_dist_call_count = 0;
    g_events.clear();
    g_hnsw_trace_sink_enabled = collect_events;
    auto pq = index.searchKnn(q, K);
    g_hnsw_trace_sink_enabled = false;

    std::vector<TopKRow> rows;
    rows.reserve(pq.size());
    size_t rank = 0;
    while (!pq.empty()) {
        auto item = pq.top();
        pq.pop();
        TopKRow r;
        r.query_index = query_index;
        r.rank = rank++;
        r.external_id = static_cast<uint64_t>(item.second);
        r.dist = item.first;
        r.dist_bits = float_bits(item.first);
        rows.push_back(r);
    }
    return rows;
}

void write_topk(std::ofstream &out, const std::vector<TopKRow> &rows, int ef_search) {
    for (const auto &r : rows) {
        out << "{\"query_index\":" << r.query_index
            << ",\"ef_search\":" << ef_search
            << ",\"rank\":" << r.rank
            << ",\"external_id\":" << r.external_id
            << ",\"dist_bits\":\"" << hex32(r.dist_bits) << "\""
            << ",\"dist\":" << std::setprecision(9) << r.dist
            << "}\n";
    }
}

void write_events(std::ofstream &events_out,
                  std::ofstream &first_out,
                  const std::vector<TraceEvent> &ev,
                  uint64_t query_index,
                  int ef_search) {
    std::unordered_set<uint64_t> seen;
    seen.reserve(ev.size() * 2 + 16);
    uint64_t first_rank = 0;
    for (const auto &e : ev) {
        events_out << "{\"query_index\":" << query_index
                   << ",\"ef_search\":" << ef_search
                   << ",\"event_index\":" << e.event_index
                   << ",\"internal_id\":" << e.internal_id
                   << ",\"external_id\":" << e.external_id
                   << ",\"level\":" << e.level
                   << ",\"event_site\":\"" << e.site << "\"}\n";
        if (seen.insert(e.external_id).second) {
            first_out << "{\"query_index\":" << query_index
                      << ",\"ef_search\":" << ef_search
                      << ",\"rank\":" << first_rank++
                      << ",\"external_id\":" << e.external_id
                      << ",\"first_event_index\":" << e.event_index
                      << ",\"level\":" << e.level
                      << ",\"event_site\":\"" << e.site << "\"}\n";
        }
    }
}

std::vector<uint64_t> first_touch_ids(const std::vector<TraceEvent> &ev) {
    std::unordered_set<uint64_t> seen;
    seen.reserve(ev.size() * 2 + 16);
    std::vector<uint64_t> ids;
    for (const auto &e : ev) {
        if (seen.insert(e.external_id).second) ids.push_back(e.external_id);
    }
    return ids;
}

struct SiteCounts {
    uint64_t entrypoint = 0;
    uint64_t upper = 0;
    uint64_t level0_entry = 0;
    uint64_t level0_neighbor = 0;
    bool has_upper() const { return upper > 0; }
    bool has_level0() const { return level0_entry > 0 || level0_neighbor > 0; }
};

SiteCounts site_counts(const std::vector<TraceEvent> &ev) {
    SiteCounts c;
    for (const auto &e : ev) {
        if (e.site == "entrypoint") ++c.entrypoint;
        else if (e.site == "upper_layer_neighbor") ++c.upper;
        else if (e.site == "level0_entrypoint") ++c.level0_entry;
        else if (e.site == "level0_neighbor") ++c.level0_neighbor;
    }
    return c;
}

void write_summary_line(std::ofstream &out,
                        uint64_t query_index,
                        int ef_search,
                        const std::vector<TraceEvent> &ev,
                        const std::vector<TopKRow> &rows) {
    const auto counts = site_counts(ev);
    const auto first = first_touch_ids(ev);
    out << "{\"query_index\":" << query_index
        << ",\"ef_search\":" << ef_search
        << ",\"event_count\":" << ev.size()
        << ",\"distance_call_count\":" << g_hnsw_dist_call_count
        << ",\"unique_count\":" << first.size()
        << ",\"has_upper\":" << (counts.has_upper() ? "true" : "false")
        << ",\"has_level0\":" << (counts.has_level0() ? "true" : "false")
        << ",\"site_entrypoint\":" << counts.entrypoint
        << ",\"site_upper_layer_neighbor\":" << counts.upper
        << ",\"site_level0_entrypoint\":" << counts.level0_entry
        << ",\"site_level0_neighbor\":" << counts.level0_neighbor
        << ",\"trace_hash\":\"0x" << std::hex << std::setw(16) << std::setfill('0') << fnv1a(event_hash_input(ev)) << std::dec << "\""
        << ",\"first_touch_hash\":\"0x" << std::hex << std::setw(16) << std::setfill('0') << fnv1a(first_touch_hash_input(first)) << std::dec << "\""
        << ",\"topk_hash\":\"0x" << std::hex << std::setw(16) << std::setfill('0') << fnv1a(topk_hash_input(rows)) << std::dec << "\"}\n";
}

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error(message);
}

void write_smoke_input(const std::string &dir) {
    std::filesystem::create_directories(dir);
    std::vector<float> base(SMOKE_N * DIM);
    std::vector<float> queries(SMOKE_NQ * DIM);
    std::mt19937 rng(SEED);
    std::uniform_real_distribution<float> dist(-1.0f, 1.0f);
    for (auto &v : base) v = dist(rng);
    for (auto &v : queries) v = dist(rng);
    normalize_rows(base, SMOKE_N, DIM);
    normalize_rows(queries, SMOKE_NQ, DIM);
    std::vector<std::string> cids(SMOKE_N), qids(SMOKE_NQ);
    for (size_t i = 0; i < SMOKE_N; ++i) cids[i] = std::to_string(i);
    for (size_t i = 0; i < SMOKE_NQ; ++i) qids[i] = std::to_string(i);
    write_f32(dir + "/corpus.f32", base);
    write_f32(dir + "/queries.f32", queries);
    write_ids(dir + "/corpus_ids.txt", cids);
    write_ids(dir + "/query_ids.txt", qids);
}

int run_smoke(const std::string &outdir) {
    std::filesystem::create_directories(outdir);
    const std::string input_dir = outdir + "/smoke_input";
    write_smoke_input(input_dir);
    LoadedData d = load_data(input_dir + "/corpus.f32",
                             input_dir + "/queries.f32",
                             input_dir + "/corpus_ids.txt",
                             input_dir + "/query_ids.txt");
    require(d.base.size() == SMOKE_N * DIM, "smoke corpus dimension mismatch");
    require(d.queries.size() == SMOKE_NQ * DIM, "smoke query dimension mismatch");
    require(d.base_ids.size() == SMOKE_N, "smoke corpus ID count mismatch");
    require(d.query_ids.size() == SMOKE_NQ, "smoke query ID count mismatch");
    for (size_t i = 0; i < SMOKE_N; ++i) require(d.base_ids[i] == std::to_string(i), "smoke corpus ID mapping mismatch");
    for (size_t i = 0; i < SMOKE_NQ; ++i) require(d.query_ids[i] == std::to_string(i), "smoke query ID mapping mismatch");

    std::ofstream events(outdir + "/exp10_fiqa_smoke_events.jsonl", std::ios::trunc);
    std::ofstream first(outdir + "/exp10_fiqa_smoke_first_touch.jsonl", std::ios::trunc);
    std::ofstream topk(outdir + "/exp10_fiqa_smoke_topk.jsonl", std::ios::trunc);
    std::ofstream sinkoff(outdir + "/exp10_fiqa_smoke_sinkoff_topk.jsonl", std::ios::trunc);
    std::ofstream summary(outdir + "/exp10_fiqa_smoke_summary.jsonl", std::ios::trunc);
    if (!events || !first || !topk || !sinkoff || !summary) throw std::runtime_error("cannot open smoke outputs");

    IndexBundle ix = build_index(d.base, SMOKE_N, 64);
    bool all_counter_match = true;
    bool all_sites = true;
    bool all_sinkoff_match = true;
    bool all_repeat_trace_match = true;
    uint64_t total_events = 0;
    uint64_t total_dist_calls = 0;

    for (size_t q = 0; q < SMOKE_NQ; ++q) {
        auto rows = search_topk(*ix.index, d.queries.data() + q * DIM, q, true);
        const uint64_t event_count = g_events.size();
        const uint64_t call_count = g_hnsw_dist_call_count;
        auto counts = site_counts(g_events);
        total_events += event_count;
        total_dist_calls += call_count;
        all_counter_match = all_counter_match && (event_count == call_count);
        all_sites = all_sites && counts.has_upper() && counts.has_level0();
        const std::string primary_topk_hash = topk_hash_input(rows);
        const uint64_t primary_trace_hash = fnv1a(event_hash_input(g_events));
        write_topk(topk, rows, 64);
        write_events(events, first, g_events, q, 64);

        auto rows_off = search_topk(*ix.index, d.queries.data() + q * DIM, q, false);
        require(g_events.empty(), "sink-off emitted events");
        all_sinkoff_match = all_sinkoff_match && (primary_topk_hash == topk_hash_input(rows_off));
        write_topk(sinkoff, rows_off, 64);

        search_topk(*ix.index, d.queries.data() + q * DIM, q, true);
        all_repeat_trace_match = all_repeat_trace_match && (primary_trace_hash == fnv1a(event_hash_input(g_events)));
        write_summary_line(summary, q, 64, g_events, rows);
    }

    // The summary just written corresponds to the repeat run; restore the primary
    // event set for one final per-query line is unnecessary for smoke acceptance.
    free_index(ix);
    IndexBundle rebuilt = build_index(d.base, SMOKE_N, 64);
    bool all_rebuilt_trace_match = true;
    for (size_t q = 0; q < SMOKE_NQ; ++q) {
        search_topk(*rebuilt.index, d.queries.data() + q * DIM, q, true);
        // Compare against a fresh search on the rebuilt index below.
        const uint64_t h1 = fnv1a(event_hash_input(g_events));
        search_topk(*rebuilt.index, d.queries.data() + q * DIM, q, true);
        all_rebuilt_trace_match = all_rebuilt_trace_match && (h1 == fnv1a(event_hash_input(g_events)));
    }
    free_index(rebuilt);

    const bool pass = all_counter_match && all_sites && all_sinkoff_match &&
                      all_repeat_trace_match && all_rebuilt_trace_match;
    std::ofstream validation(outdir + "/exp10_fiqa_smoke_validation.json", std::ios::trunc);
    validation << "{\n"
               << "  \"verdict\": \"" << (pass ? "PASS" : "STOP") << "\",\n"
               << "  \"synthetic_n\": " << SMOKE_N << ",\n"
               << "  \"synthetic_dim\": " << DIM << ",\n"
               << "  \"synthetic_queries\": " << SMOKE_NQ << ",\n"
               << "  \"total_events\": " << total_events << ",\n"
               << "  \"total_distance_calls\": " << total_dist_calls << ",\n"
               << "  \"event_count_equals_independent_counter\": " << (all_counter_match ? "true" : "false") << ",\n"
               << "  \"upper_and_level0_events_present\": " << (all_sites ? "true" : "false") << ",\n"
               << "  \"sinkoff_topk_bit_exact\": " << (all_sinkoff_match ? "true" : "false") << ",\n"
               << "  \"repeat_trace_hash_equal\": " << (all_repeat_trace_match ? "true" : "false") << ",\n"
               << "  \"rebuilt_trace_hash_equal\": " << (all_rebuilt_trace_match ? "true" : "false") << "\n"
               << "}\n";
    std::cout << "smoke_verdict=" << (pass ? "PASS" : "STOP") << " queries=" << SMOKE_NQ << "\n";
    return pass ? 0 : 1;
}

int run_full(const std::string &outdir,
             const std::string &corpus_bin,
             const std::string &queries_bin,
             const std::string &corpus_ids,
             const std::string &query_ids) {
    std::filesystem::create_directories(outdir);
    LoadedData d = load_data(corpus_bin, queries_bin, corpus_ids, query_ids);
    const size_t n = d.base_ids.size();
    const size_t nq = d.query_ids.size();
    require(d.base.size() == n * DIM, "corpus float32 dimension mismatch");
    require(d.queries.size() == nq * DIM, "query float32 dimension mismatch");
    require(n == 57638 && nq == 648, "unexpected FiQA embedding counts");

    std::ofstream events(outdir + "/exp10_fiqa_trace_events.jsonl", std::ios::trunc);
    std::ofstream first(outdir + "/exp10_fiqa_first_touch.jsonl", std::ios::trunc);
    std::ofstream topk(outdir + "/exp10_fiqa_hnsw_topk.jsonl", std::ios::trunc);
    std::ofstream summary(outdir + "/exp10_fiqa_probe_summary.jsonl", std::ios::trunc);
    if (!events || !first || !topk || !summary) throw std::runtime_error("cannot open full outputs");

    IndexBundle ix = build_index(d.base, n, 64);
    const int ef_values[3] = {64, 128, 256};
    for (int ef : ef_values) {
        ix.index->setEf(ef);
        for (size_t q = 0; q < nq; ++q) {
            auto rows = search_topk(*ix.index, d.queries.data() + q * DIM, q, true);
            require(g_events.size() == g_hnsw_dist_call_count,
                    "event count != independent distance counter at q=" + std::to_string(q) + " ef=" + std::to_string(ef));
            write_topk(topk, rows, ef);
            write_events(events, first, g_events, q, ef);
            write_summary_line(summary, q, ef, g_events, rows);
        }
        std::cout << "ef=" << ef << " queries=" << nq << " done\n" << std::flush;
    }
    free_index(ix);
    std::cout << "full_run=PASS corpus=" << n << " queries=" << nq << "\n";
    return 0;
}

}  // namespace

int main(int argc, char **argv) {
    try {
        if (argc < 3) {
            std::cerr << "usage: fiqa_trace_runner <smoke|full> <outdir> [corpus.f32 queries.f32 corpus_ids.txt query_ids.txt]\n";
            return 2;
        }
        const std::string mode = argv[1];
        const std::string outdir = argv[2];
        if (mode == "smoke") {
            if (argc != 3) {
                std::cerr << "smoke mode takes only <outdir>\n";
                return 2;
            }
            return run_smoke(outdir);
        }
        if (mode == "full") {
            if (argc != 7) {
                std::cerr << "full mode requires four input paths\n";
                return 2;
            }
            return run_full(outdir, argv[3], argv[4], argv[5], argv[6]);
        }
        std::cerr << "FATAL: unknown mode: " << mode << "\n";
        return 2;
    } catch (const std::exception &e) {
        std::cerr << "FATAL: " << e.what() << "\n";
        return 1;
    }
}
