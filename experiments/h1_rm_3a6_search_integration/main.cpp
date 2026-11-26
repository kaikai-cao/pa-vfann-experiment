// H1-RM.3A.6 — minimal REAL HNSW search integration check.
//
// Goal (only): verify that SecretAclFilter, when passed as the isIdAllowed
// argument of a real searchKnn() call, constrains the returned labels.
//
// NOT an attack experiment: no C0/C1/C2, no A0/A1 pairs, no trace emission,
// no page/block simulation, no classifier and no attack metric.
//
// Usage:  h1_rm3a6_search <fixture_path>
// Output: machine-readable lines only (see README). Exit 0 = PASS, 1 = FAIL.
//
// The fixture is a FIXED SYNTHETIC test vector written by Python's
// encode_acl_bitmap(). No real ACL instance is ever loaded. The program never
// prints bitmap contents, the authorized member list, file paths or seeds.

#include <algorithm>
#include <cstdint>
#include <iostream>
#include <queue>
#include <set>
#include <string>
#include <vector>

#include "acl_bitmap.h"
#include "hnsw_acl_filter.h"
#include "hnswlib.h"

namespace {

constexpr int kDim = 2;
constexpr std::size_t kM = 16;
constexpr std::size_t kEfConstruction = 200;
constexpr std::size_t kEfSearch = 64;
constexpr std::size_t kRandomSeed = 100;
constexpr std::size_t kNeighborsNear = 1;   // x of unauthorized points
constexpr float kFarBase = 100.0F;          // x of authorized points
constexpr float kStep = 0.01F;

// Auxiliary only: proves the callback was invoked DURING searchKnn(). The
// main filtered search below passes a plain SecretAclFilter, as required.
class CountingSecretAclFilter : public SecretAclFilter {
public:
    explicit CountingSecretAclFilter(const h1acl::AclBitmap& acl)
        : SecretAclFilter(acl), calls_(0) {}

    bool operator()(hnswlib::labeltype id) override {
        ++calls_;
        return SecretAclFilter::operator()(id);
    }

    std::uint64_t calls() const { return calls_; }

private:
    std::uint64_t calls_;
};

using Hit = std::pair<float, hnswlib::labeltype>;

// searchKnn returns a priority_queue (not a range); copy it into a vector.
std::vector<Hit> collect_hits(std::priority_queue<Hit> q) {
    std::vector<Hit> out;
    out.reserve(q.size());
    while (!q.empty()) {
        out.push_back(q.top());
        q.pop();
    }
    return out;
}

void print_labels(const char* name, const std::vector<Hit>& hits) {
    std::cout << name;
    for (const auto& hit : hits) std::cout << ' ' << hit.second;
    std::cout << '\n';
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: h1_rm3a6_search <fixture_path>\n";
        return 2;
    }

    h1acl::AclBitmap acl;
    const h1acl::Status st = acl.load(std::string(argv[1]));
    std::cout << "LOAD " << h1acl::status_name(st) << '\n';
    if (st != h1acl::Status::Ok) return 1;

    const std::size_t n = static_cast<std::size_t>(acl.member_count());
    if (n < 2) {
        std::cout << "CHECK fixture_too_small=1\nRESULT FAIL\n";
        return 1;
    }

    // Synthetic geometry: authorized points are FAR from the query,
    // unauthorized points are NEAR. Therefore:
    //   * unfiltered Top-K contains unauthorized labels;
    //   * filtered Top-K, if the callback really runs during search, must
    //     contain authorized labels that are absent from unfiltered Top-K.
    // A post-hoc filter over unfiltered results would yield an EMPTY set here.
    hnswlib::L2Space space(kDim);
    hnswlib::HierarchicalNSW<float> index(
        &space, n, kM, kEfConstruction, kRandomSeed);
    index.setEf(kEfSearch);

    std::size_t authorized_count = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const h1acl::Lookup lk = acl.lookup_index(static_cast<std::uint64_t>(i));
        if (!lk.ok) {
            std::cout << "CHECK acl_index_invalid=1\nRESULT FAIL\n";
            return 1;
        }
        const float x = lk.bit ? (kFarBase + kStep * static_cast<float>(i))
                               : (static_cast<float>(kNeighborsNear) +
                                  kStep * static_cast<float>(i));
        const float point[kDim] = {x, 0.0F};
        const hnswlib::labeltype label =
            static_cast<hnswlib::labeltype>(100000 + 17 * i);
        index.addPoint(point, label);
        if (lk.bit) ++authorized_count;
    }
    const std::size_t unauthorized_count = n - authorized_count;
    const std::size_t k = std::min<std::size_t>(5,
        std::min(authorized_count, unauthorized_count));
    if (k == 0) {
        std::cout << "CHECK insufficient_class_count=1\nRESULT FAIL\n";
        return 1;
    }

    const float query[kDim] = {0.0F, 0.0F};

    // Same index, same query, same k and same ef for BOTH searches.
    auto plain = collect_hits(index.searchKnn(query, k, nullptr));
    SecretAclFilter filter(acl);
    auto filtered = collect_hits(index.searchKnn(query, k, &filter));

    // Auxiliary run: derived filter counts real callback invocations.
    CountingSecretAclFilter counting_filter(acl);
    auto counting = collect_hits(index.searchKnn(query, k, &counting_filter));

    print_labels("UNFILTERED", plain);
    print_labels("FILTERED", filtered);
    std::cout << "META n=" << n << " k=" << k << " ef=" << kEfSearch
              << " callback_calls=" << counting_filter.calls() << '\n';

    std::set<hnswlib::labeltype> plain_set;
    bool plain_has_unauthorized = false;
    for (const auto& hit : plain) {
        plain_set.insert(hit.second);
        const h1acl::Lookup lk = acl.lookup_label(
            static_cast<std::uint64_t>(hit.second));
        if (lk.ok && lk.bit == 0) plain_has_unauthorized = true;
    }

    bool filtered_nonempty = !filtered.empty();
    bool filtered_all_authorized = !filtered.empty();
    bool filtered_outside_plain = false;
    for (const auto& hit : filtered) {
        const h1acl::Lookup lk = acl.lookup_label(
            static_cast<std::uint64_t>(hit.second));
        if (!lk.ok || lk.bit != 1) filtered_all_authorized = false;
        if (plain_set.find(hit.second) == plain_set.end()) {
            filtered_outside_plain = true;
        }
    }
    // Counting run must obey the same authorization invariant.
    bool counting_all_authorized = !counting.empty();
    for (const auto& hit : counting) {
        const h1acl::Lookup lk = acl.lookup_label(
            static_cast<std::uint64_t>(hit.second));
        if (!lk.ok || lk.bit != 1) counting_all_authorized = false;
    }

    std::cout << "CHECK unfiltered_has_unauthorized="
              << (plain_has_unauthorized ? 1 : 0) << '\n'
              << "CHECK filtered_nonempty="
              << (filtered_nonempty ? 1 : 0) << '\n'
              << "CHECK filtered_all_authorized="
              << (filtered_all_authorized ? 1 : 0) << '\n'
              << "CHECK filtered_outside_unfiltered_topk="
              << (filtered_outside_plain ? 1 : 0) << '\n'
              << "CHECK callback_invocations_positive="
              << (counting_filter.calls() > 0 ? 1 : 0) << '\n'
              << "CHECK counting_run_all_authorized="
              << (counting_all_authorized ? 1 : 0) << '\n';

    const bool pass = plain_has_unauthorized && filtered_nonempty &&
                      filtered_all_authorized && filtered_outside_plain &&
                      counting_filter.calls() > 0 && counting_all_authorized;
    std::cout << "RESULT " << (pass ? "PASS" : "FAIL") << '\n';
    return pass ? 0 : 1;
}
