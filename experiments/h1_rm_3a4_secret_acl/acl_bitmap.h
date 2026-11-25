// H1-RM.3A.4 — read-only loader for the frozen H1ACL01 secret-ACL bitmap.
//
// Independent data-layer prototype. Does NOT touch HNSW search, does not run
// C0/C1/C2, and does not generate experiment ACLs. Header-only on purpose.
//
// The library NEVER prints anything: no bitmap contents, no authorization
// result, no private file path, no seed, no counts. It returns status codes
// and bits to the caller; logging policy is left to the (test) caller.
//
// Frozen binary format (shared with acl_bitmap.py):
//   offset 0    Magic        8 B   "H1ACL01\0"  (prefix + version "01" + NUL)
//   offset 8    Member count 8 B   uint64 little-endian
//   offset 16   Payload      ceil(N / 8) B, LSB-first:
//               authorized(i) = (payload[i / 8] >> (i % 8)) & 1

#ifndef H1_RM_3A4_ACL_BITMAP_H_
#define H1_RM_3A4_ACL_BITMAP_H_

#include <cstdint>
#include <cstdio>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

namespace h1acl {

constexpr char kMagic[9] = {'H', '1', 'A', 'C', 'L', '0', '1', '\0', '\0'};
constexpr std::size_t kMagicLen = 8;
constexpr std::size_t kCountLen = 8;
constexpr std::size_t kHeaderLen = kMagicLen + kCountLen;
constexpr std::uint64_t kMaxMembers =
    (std::numeric_limits<std::size_t>::max() / 8) - kHeaderLen;

enum class Status {
    Ok = 0,
    OpenFailed,
    BadMagic,
    BadMemberCount,
    TruncatedPayload,
    TrailingBytes,
    BadTailPadding,
    ReadFailed,
};

inline const char* status_name(Status s) {
    switch (s) {
        case Status::Ok: return "OK";
        case Status::OpenFailed: return "OPEN_FAILED";
        case Status::BadMagic: return "BAD_MAGIC";
        case Status::BadMemberCount: return "BAD_MEMBER_COUNT";
        case Status::TruncatedPayload: return "TRUNCATED_PAYLOAD";
        case Status::TrailingBytes: return "TRAILING_BYTES";
        case Status::BadTailPadding: return "BAD_TAIL_PADDING";
        case Status::ReadFailed: return "READ_FAILED";
    }
    return "UNKNOWN";
}

// Result of an authorization lookup. `bit` is meaningful only when ok==true.
struct Lookup {
    bool ok = false;
    int bit = 0;
};

class AclBitmap {
public:
    // Load and fully validate a blob. No output; returns a status code.
    Status load(const std::string& path) {
        payload_.clear();
        n_ = 0;

        std::ifstream in(path, std::ios::binary | std::ios::ate);
        if (!in.is_open()) return Status::OpenFailed;
        const std::streamoff size = in.tellg();
        if (size < static_cast<std::streamoff>(kHeaderLen)) {
            return Status::TruncatedPayload;
        }
        in.seekg(0, std::ios::beg);

        char header[kHeaderLen];
        in.read(header, kHeaderLen);
        if (!in) return Status::ReadFailed;
        for (std::size_t i = 0; i < kMagicLen; ++i) {
            if (header[i] != kMagic[i]) return Status::BadMagic;
        }

        std::uint64_t count = 0;
        for (std::size_t i = 0; i < kCountLen; ++i) {
            const std::uint8_t byte = static_cast<std::uint8_t>(
                header[kMagicLen + i]);
            count |= static_cast<std::uint64_t>(byte) << (8 * i);
        }
        if (count == 0 || count > kMaxMembers) return Status::BadMemberCount;

        const std::uint64_t payload_len = (count + 7) / 8;
        const std::uint64_t expected =
            static_cast<std::uint64_t>(kHeaderLen) + payload_len;
        const std::uint64_t actual = static_cast<std::uint64_t>(size);
        if (actual < expected) return Status::TruncatedPayload;
        if (actual > expected) return Status::TrailingBytes;

        std::vector<std::uint8_t> payload(static_cast<std::size_t>(payload_len));
        in.read(reinterpret_cast<char*>(payload.data()),
                static_cast<std::streamsize>(payload_len));
        if (!in) return Status::ReadFailed;

        // LSB-first: valid bits occupy the LOW bits of the final byte, so
        // tail padding occupies the HIGH bits, which must be zero.
        const unsigned used_in_last = static_cast<unsigned>(count % 8);
        if (used_in_last != 0) {
            const std::uint8_t mask =
                static_cast<std::uint8_t>(0xFFu << used_in_last);
            if ((payload.back() & mask) != 0) return Status::BadTailPadding;
        }

        payload_ = std::move(payload);
        n_ = count;
        return Status::Ok;
    }

    std::uint64_t member_count() const { return n_; }

    // Map an external label to the bitmap bit. Invalid labels are REJECTED
    // (never default-authorized). Mirrors Python label_to_index.
    Lookup lookup_label(std::uint64_t label,
                        std::uint64_t label_base = 100000,
                        std::uint64_t label_step = 17) const {
        Lookup out;
        if (label < label_base) return out;
        const std::uint64_t offset = label - label_base;
        if (label_step == 0 || offset % label_step != 0) return out;
        const std::uint64_t idx = offset / label_step;
        if (idx >= n_) return out;
        out.ok = true;
        out.bit = (payload_[static_cast<std::size_t>(idx / 8)] >> (idx % 8)) & 1u;
        return out;
    }

    // Direct index lookup; out.ok=false when idx is out of range.
    Lookup lookup_index(std::uint64_t idx) const {
        Lookup out;
        if (idx >= n_) return out;
        out.ok = true;
        out.bit = (payload_[static_cast<std::size_t>(idx / 8)] >> (idx % 8)) & 1u;
        return out;
    }

private:
    std::vector<std::uint8_t> payload_;
    std::uint64_t n_ = 0;
};

}  // namespace h1acl

#endif  // H1_RM_3A4_ACL_BITMAP_H_
