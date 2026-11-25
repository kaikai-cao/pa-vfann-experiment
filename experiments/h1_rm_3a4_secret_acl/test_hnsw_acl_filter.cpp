// H1-RM.3A.5 — C++ contract driver for SecretAclFilter.
//
// Usage:
//   test_hnsw_acl_filter <fixture_path> [label ...]
//   test_hnsw_acl_filter --unloaded [label ...]
//
// Output (stdout, machine-readable; fixed test vectors only):
//   LOAD OK | LOAD <STATUS_NAME> | LOAD UNLOADED
//   (when a filter exists) FILTER <token> ALLOW | FILTER <token> DENY
//
// Exit code: 0 for OK/UNLOADED, 1 for load failure, 2 for usage error.
//
// This driver calls the filter functor through an hnswlib::BaseFilterFunctor*
// pointer (the same pointer type hnswlib passes to searchKnn). It does NOT
// construct an HNSW index, does NOT execute a query, and does NOT emit traces.
// The library headers print nothing; this driver is the only output channel.

#include <cstdint>
#include <iostream>
#include <string>

#include "acl_bitmap.h"
#include "hnsw_acl_filter.h"
#include "hnswlib.h"

namespace {

bool parse_label(const std::string& token, hnswlib::labeltype& out) {
    try {
        std::size_t pos = 0;
        const unsigned long long v = std::stoull(token, &pos, 10);
        if (pos != token.size()) return false;
        out = static_cast<hnswlib::labeltype>(v);
        return true;
    } catch (...) {
        return false;
    }
}

// The real callback shape: hnswlib holds a BaseFilterFunctor* and calls it.
bool call_through_base(hnswlib::BaseFilterFunctor* cb, hnswlib::labeltype id) {
    return (*cb)(id);
}

void report_labels(hnswlib::BaseFilterFunctor* cb, int argc, char** argv,
                   int first_label_arg) {
    for (int i = first_label_arg; i < argc; ++i) {
        const std::string token(argv[i]);
        hnswlib::labeltype label = 0;
        if (!parse_label(token, label)) {
            // Unparseable input never reaches the callback; fail closed.
            std::cout << "FILTER " << token << " DENY\n";
            continue;
        }
        const bool allowed = call_through_base(cb, label);
        std::cout << "FILTER " << label << (allowed ? " ALLOW" : " DENY") << "\n";
    }
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: test_hnsw_acl_filter <fixture_path> [label ...]\n"
                  << "       test_hnsw_acl_filter --unloaded [label ...]\n";
        return 2;
    }

    h1acl::AclBitmap acl;
    if (std::string(argv[1]) == "--unloaded") {
        // A default-constructed (never loaded) ACL is an invalid ACL state.
        // Every label must be denied; absence of data must NOT be authorization.
        std::cout << "LOAD UNLOADED\n";
        SecretAclFilter filter(acl);
        hnswlib::BaseFilterFunctor* cb = &filter;
        report_labels(cb, argc, argv, 2);
        return 0;
    }

    const h1acl::Status st = acl.load(std::string(argv[1]));
    std::cout << "LOAD " << h1acl::status_name(st) << "\n";
    if (st != h1acl::Status::Ok) {
        return 1;
    }

    SecretAclFilter filter(acl);
    hnswlib::BaseFilterFunctor* cb = &filter;
    report_labels(cb, argc, argv, 2);
    return 0;
}
