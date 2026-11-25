#pragma once

// H1-RM.3A.1 — minimal storage access bridge (local engineering probe).
//
// Observation contract:
//   * The recorder receives ONLY request metadata: query id, sequence,
//     request type, internal node id, level, and a boundary tag.
//   * The recorder NEVER receives ACL bits, filter_check results, distance
//     values, candidate sets, result sets, or any node payload bytes.
//   * Search logic depends on StorageAccess, not on the recorder.
//   * LocalMemoryStorage returns a ZERO-COPY view of the existing buffers, so
//     distance computations read the same bytes as upstream hnswlib.

#include <cstdint>
#include <cstddef>
#include <string>

namespace hnsw_bridge {

enum class RequestType : int {
    node_read = 0,      // node vector data (getDataByInternalId)
    neighbor_read = 1,  // adjacency list, level 0 or >=1 (get_linklist0/get_linklist)
    boundary = 2,       // query/group boundary tag emitted by the runner
};

struct StorageRequest {
    uint64_t query_id;
    uint64_t seq;           // request sequence, reset per (query, group)
    RequestType type;
    uint64_t node_id;       // internal id; 0 for boundary records
    int level;              // -1 when not applicable
    std::string boundary;   // "query_start" / "query_end" / ""
};

class RequestRecorder {
public:
    virtual ~RequestRecorder() = default;
    virtual void record(const StorageRequest &req) = 0;
};

// Minimal storage boundary. Only node data and neighbor-list reads pass here.
// Metadata fields (external label, delete mark) live inside the same node
// block and are parsed from the returned view; they are not separate reads.
class StorageAccess {
public:
    virtual ~StorageAccess() = default;
    virtual char *read_node(uint64_t node_id) = 0;
    virtual unsigned int *read_neighbors(uint64_t node_id, int level) = 0;
};

// Local memory implementation: zero-copy views of the index buffers.
// Every method call records exactly one request when enabled; no extra index
// reads are introduced for the sake of recording.
class LocalMemoryStorage final : public StorageAccess {
public:
    char *data_level0_memory_ = nullptr;
    char **linkLists_ = nullptr;
    std::size_t size_data_per_element_ = 0;
    std::size_t size_links_per_element_ = 0;
    std::size_t offsetData_ = 0;
    std::size_t offsetLevel0_ = 0;

    RequestRecorder *recorder_ = nullptr;
    bool enabled_ = false;
    uint64_t current_query_id_ = 0;
    uint64_t seq_ = 0;

    void reset_query(uint64_t qid) {
        current_query_id_ = qid;
        seq_ = 0;
    }

    char *read_node(uint64_t node_id) override {
        if (enabled_ && recorder_) {
            recorder_->record(StorageRequest{current_query_id_, seq_++,
                                             RequestType::node_read,
                                             node_id, -1, ""});
        }
        return data_level0_memory_
               + static_cast<std::size_t>(node_id) * size_data_per_element_
               + offsetData_;
    }

    unsigned int *read_neighbors(uint64_t node_id, int level) override {
        if (enabled_ && recorder_) {
            recorder_->record(StorageRequest{current_query_id_, seq_++,
                                             RequestType::neighbor_read,
                                             node_id, level, ""});
        }
        if (level == 0) {
            return reinterpret_cast<unsigned int *>(
                data_level0_memory_
                + static_cast<std::size_t>(node_id) * size_data_per_element_
                + offsetLevel0_);
        }
        return reinterpret_cast<unsigned int *>(
            linkLists_[node_id]
            + static_cast<std::size_t>(level - 1) * size_links_per_element_);
    }
};

}  // namespace hnsw_bridge
