// H1-RM.3A.5 — read-only HNSW filter adapter for the frozen H1ACL01 bitmap.
//
// This is a CALLBACK-CONTRACT adapter only. It does not run HNSW search, does
// not touch hnswalg.h / StorageAccess / main.cpp, and does not generate C0/C1/C2
// traces. Its only job is to let hnswlib's isIdAllowed callback consult a
// private ACL bitmap through the existing read boundary.
//
// Trust boundary:
//   * The adapter holds a CONST REFERENCE to the caller's AclBitmap. It never
//     copies, regenerates, serializes or mutates the bitmap.
//   * Every decision FAILS CLOSED: an off-grid label, an out-of-range label, an
//     unloaded ACL or a corrupt/invalid ACL state is always denied.
//   * The adapter NEVER prints or logs authorization results, bitmap contents,
//     file paths, member counts, seeds or any other secret metadata.
//
// Compile against the frozen hnswlib v0.9.0 headers (pristine or RM2
// instrumented). The callback signature is hnswlib::BaseFilterFunctor's
//   virtual bool operator()(hnswlib::labeltype id) = 0-equivalent.

#ifndef H1_RM_3A5_HNSW_ACL_FILTER_H_
#define H1_RM_3A5_HNSW_ACL_FILTER_H_

#include <cstdint>
#include <type_traits>

#include "acl_bitmap.h"
#include "hnswlib.h"

class SecretAclFilter : public hnswlib::BaseFilterFunctor {
public:
    // Only a non-owning, read-only handle is retained.
    explicit SecretAclFilter(const h1acl::AclBitmap& acl) : acl_(acl) {}

    // The exact callback invoked by hnswlib's search paths. Direct invocation
    // and invocation through a BaseFilterFunctor* both resolve here.
    bool operator()(hnswlib::labeltype id) override {
        const h1acl::Lookup r = acl_.lookup_label(static_cast<std::uint64_t>(id));
        return r.ok && (r.bit == 1);
    }

private:
    const h1acl::AclBitmap& acl_;
};

static_assert(std::is_base_of<hnswlib::BaseFilterFunctor,
                              SecretAclFilter>::value,
              "SecretAclFilter must be a real hnswlib BaseFilterFunctor");

#endif  // H1_RM_3A5_HNSW_ACL_FILTER_H_
