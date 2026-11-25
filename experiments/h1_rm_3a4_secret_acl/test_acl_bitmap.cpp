// H1-RM.3A.4 — C++ interop test driver for the frozen H1ACL01 format.
//
// Usage:  test_acl_bitmap <fixture_path> [label ...]
// Output (stdout, machine-readable; fixed test vectors only):
//   LOAD <STATUS_NAME>
//   (if LOAD OK)  LABEL <label> OK <bit>   |   LABEL <label> REJECT
// Exit code: 0 if load OK, 1 if load failed.
//
// The library (acl_bitmap.h) prints nothing: this driver is the ONLY output
// channel, and exists to let tests assert that a Python-written fixture is
// loaded and queried correctly. No real secret ACL is ever used here.

#include "acl_bitmap.h"

#include <cstdint>
#include <iostream>
#include <string>

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "usage: test_acl_bitmap <fixture_path> [label ...]\n";
        return 2;
    }
    const std::string path = argv[1];

    h1acl::AclBitmap acl;
    const h1acl::Status st = acl.load(path);
    std::cout << "LOAD " << h1acl::status_name(st) << "\n";
    if (st != h1acl::Status::Ok) {
        return 1;
    }

    for (int i = 2; i < argc; ++i) {
        std::uint64_t label = 0;
        try {
            std::size_t pos = 0;
            const std::string token(argv[i]);
            label = static_cast<std::uint64_t>(std::stoull(token, &pos, 10));
            if (pos != token.size()) {
                std::cout << "LABEL " << token << " REJECT\n";
                continue;
            }
        } catch (...) {
            std::cout << "LABEL " << argv[i] << " REJECT\n";
            continue;
        }
        const h1acl::Lookup r = acl.lookup_label(label);
        if (r.ok) {
            std::cout << "LABEL " << label << " OK " << r.bit << "\n";
        } else {
            std::cout << "LABEL " << label << " REJECT\n";
        }
    }
    return 0;
}
