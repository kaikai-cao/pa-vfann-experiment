#pragma once

// H1-RM.3A.1 / R1 — minimal storage access bridge (local engineering probe).
//
// Observation contract:
//   * The recorder receives ONLY request metadata: query id, sequence,
//     request type, internal node id, level, and a boundary tag.
//   * The recorder NEVER receives ACL bits, filter_check results, distance
//     values, candidate sets, result sets, or any node payload bytes.
//   * Search logic depends on StorageAccess, not on the recorder.
//   * LocalMemoryStorage returns ZERO-COPY views of the existing buffers, so
//     distance computations and label reads use the same bytes as upstream.
//
// R1 change (external label read boundary closure):
//   read_node()/read_label() now return a NodeView covering the FULL node
//   block (base = block start, size = size_data_per_element_). The vector,
//   external label, level-0 link-list header and delete mark are all parsed
//   from this one view by the trusted side using the index layout offsets.
//   No copy, no layout change, no extra physical read is introduced: a
//   label_read is the same block view, recorded separately so the request
//   log can express which field the trusted side asked for.

#include <cstdint>
#include <cstddef>
#include <string>

namespace hnsw_bridge {

enum class RequestType : int {
    node_read = 0,      // node block view for vector data (getDataByInternalId)
    neighbor_read = 1,  // adjacency list, level 0 or >=1 (get_linklist0/get_linklist)
    boundary = 2,       // query/group boundary tag emitted by the runner
    label_read = 3,     // node block view for external label (getExternalLabel), R1
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

// Zero-copy view of one full node block in data_level0_memory_.
//   base = data_level0_memory_ + node_id * size_data_per_element_
//   size = size_data_per_element_
// Layout (offsets are trusted-side index metadata, not payload bytes):
//   [offsetLevel0_ = 0]                         level-0 link-list header + ids
//   [offsetData_]                               vector (data_size_ bytes)
//   [label_offset_]                             external label (labeltype)
class NodeView {
public:
    const char *base{nullptr};
    std::size_t size{0};

    bool covers(std::size_t offset, std::size_t bytes) const {
        return base != nullptr && offset <= size && bytes <= size - offset;
    }
};

// Minimal storage boundary. Node block and neighbor-list reads pass here.
// All in-block metadata (external label, delete mark) is parsed from the
// returned NodeView by the trusted side; it is not a separate physical read.
class StorageAccess {
public:
    virtual ~StorageAccess() = default;
    virtual NodeView read_node(uint64_t node_id) = 0;
    virtual NodeView read_label(uint64_t node_id) = 0;
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

private:
    NodeView block_view(uint64_t node_id) const {
        return NodeView{data_level0_memory_
                            + static_cast<std::size_t>(node_id) * size_data_per_element_,
                        size_data_per_element_};
    }

    void record(RequestType type, uint64_t node_id, int level) {
        if (enabled_ && recorder_) {
            recorder_->record(StorageRequest{current_query_id_, seq_++, type,
                                             node_id, level, ""});
        }
    }

public:
    NodeView read_node(uint64_t node_id) override {
        record(RequestType::node_read, node_id, -1);
        return block_view(node_id);
    }

    NodeView read_label(uint64_t node_id) override {
        record(RequestType::label_read, node_id, -1);
        return block_view(node_id);
    }

    unsigned int *read_neighbors(uint64_t node_id, int level) override {
        record(RequestType::neighbor_read, node_id, level);
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
