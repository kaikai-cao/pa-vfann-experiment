"""Candidate transfer byte accounting (explicit serialization model).

Server sends the discovered candidate set after the search to the client.
Each candidate record uses little-endian fixed-width fields:

  * ID only:            <I                       = 4 bytes
  * ID + metadata:      <I (id) + <f (squared L2 distance) = 8 bytes
  * ID + full vector:   <I + dimension x <f      = 4 + 4*dim bytes

The server never sends an authorization bit: it does not know the match result.
The default deployed assumption in this experiment is "ID + metadata", which
is reported as ``candidate_transfer_bytes``. The other two modes are reported
separately so the reader can see the effect of vector transport.
"""

from __future__ import annotations


def candidate_transfer_bytes(n_candidates: int, dimension: int) -> dict[str, int]:
    n = max(int(n_candidates), 0)
    d = max(int(dimension), 0)
    id_bytes = 4 * n
    metadata_bytes = 8 * n
    vector_bytes = (4 + 4 * d) * n
    return {
        "candidate_id_bytes": id_bytes,
        "candidate_meta_bytes": metadata_bytes,
        "candidate_vector_bytes": vector_bytes,
        "candidate_transfer_bytes": metadata_bytes,
    }
