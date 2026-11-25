"""H1-RM.3A.4 — Secret ACL fixture and single-bit pairing data layer.

This module is an INDEPENDENT data-layer prototype. It deliberately does NOT
touch any HNSW search code, does not run C0/C1/C2, and does not generate real
experiment ACL instances. It exists only to make target pre-selection, private
ACL sampling, single-bit pairing and the Python/C++ binary contract
unit-testable.

Security/data-boundary notes
----------------------------
* ``sample_acl_bitmap`` uses ``secrets.randbelow`` (system CSPRNG) for every
  bit. No ``random.seed`` / global predictable RNG is used for ACL generation.
* This module never prints or logs bitmap bits, seeds, authorized counts or
  private file paths.
* A0/A1 are researcher-side counterfactuals: a future attack classifier must
  see only the ONE real state that exists in a given ACL instance, never both.

Frozen binary format (shared with acl_bitmap.h)
------------------------------------------------
    offset 0    Magic        8 B   b"H1ACL01\\x00"   (prefix + version "01" + NUL)
    offset 8    Member count 8 B   uint64 little-endian
    offset 16   Payload      ceil(N / 8) B, LSB-first:
                             authorized(i) = (payload[i // 8] >> (i % 8)) & 1

N must be strictly positive. Both Python and C++ reject N == 0, so an empty
bitmap is not a legal fixture in either language.

The format contains NO seed, NO authorized count, NO target state, NO A0/A1
pair marker, NO instance identity and NO public digest that could recover the
secret state.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Callable, Iterable, Sequence

MAGIC: bytes = b"H1ACL01\x00"
MAGIC_LEN: int = 8
COUNT_LEN: int = 8
HEADER_LEN: int = MAGIC_LEN + COUNT_LEN


# --------------------------------------------------------------------------- #
# Phase A — target pre-selection (independent of any ACL)
# --------------------------------------------------------------------------- #
def select_targets(
    n_members: int, target_count: int, public_seed: int | str
) -> list[int]:
    """Deterministically pre-select target member indices from the FULL public set.

    The function receives only public quantities: the total member count, how
    many targets to pick, and a pre-registered public seed. It does NOT accept
    an ACL, authorization state, trajectory, distance, K-hit position or any
    search result. Selection therefore happens before any ACL instance is
    generated and cannot depend on secret state.

    Ranking is by a SHA-256 keyed on ``public_seed`` and the member index, with
    the index as a deterministic tie-break; the lowest ``target_count`` ranks
    are returned in ascending index order. Same inputs always give same output.
    """
    if not isinstance(n_members, int) or isinstance(n_members, bool):
        raise TypeError("n_members must be an int")
    if not isinstance(target_count, int) or isinstance(target_count, bool):
        raise TypeError("target_count must be an int")
    if n_members <= 0:
        raise ValueError("n_members must be positive")
    if target_count < 0 or target_count > n_members:
        raise ValueError("target_count must be in [0, n_members]")

    seed_bytes = str(public_seed).encode("utf-8")

    def rank(i: int) -> tuple[bytes, int]:
        digest = hashlib.sha256(seed_bytes + b":" + str(i).encode("ascii")).digest()
        return digest, i

    chosen = sorted(range(n_members), key=rank)[:target_count]
    return sorted(chosen)


# --------------------------------------------------------------------------- #
# Phase B — private ACL bitmap from system CSPRNG
# --------------------------------------------------------------------------- #
def sample_acl_bitmap(
    n_members: int,
    p_num: int = 1,
    p_den: int = 10,
    *,
    _randbelow: Callable[[int], int] | None = None,
) -> list[int]:
    """Generate one private ACL bitmap.

    Every member is authorized independently with exact rational probability
    ``p_num / p_den`` (default 1/10: the natural prior). Bits are drawn from
    ``secrets.randbelow(p_den)`` and set when the draw is ``< p_num``.

    ``_randbelow`` is a PRIVATE test-injection hook only: it lets tests supply
    a deterministic source and prove the generation logic. It is distinct from
    the real path (which always uses ``secrets.randbelow``) and must never be
    used to produce experiment ACLs. Each call is independent: no global
    bitmap or RNG state is reused.
    """
    if not isinstance(n_members, int) or isinstance(n_members, bool):
        raise TypeError("n_members must be an int")
    if n_members <= 0:
        raise ValueError("n_members must be positive")
    if not isinstance(p_num, int) or not isinstance(p_den, int):
        raise TypeError("p_num and p_den must be ints")
    if isinstance(p_num, bool) or isinstance(p_den, bool):
        raise TypeError("p_num and p_den must be ints")
    if p_den <= 0 or p_num < 0 or p_num > p_den:
        raise ValueError("require 0 <= p_num <= p_den and p_den > 0")

    randbelow = secrets.randbelow if _randbelow is None else _randbelow
    return [1 if randbelow(p_den) < p_num else 0 for _ in range(n_members)]


# --------------------------------------------------------------------------- #
# Phase C — single-member pairing from one base ACL instance
# --------------------------------------------------------------------------- #
def derive_target_pair(
    base_acl: Sequence[int], target_index: int
) -> tuple[list[int], list[int]]:
    """Derive (A0, A1) from ONE base ACL instance, flipping only ``u``.

    A0[u] = 0 (target unauthorized), A1[u] = 1 (target authorized), and every
    other bit is copied bit-for-bit from ``base_acl``. Both outputs are fresh
    copies, so pairing one target never mutates the base or another target's
    pair. The base's original state of ``u`` is researcher-internal data and is
    intentionally discarded here.
    """
    if not isinstance(target_index, int) or isinstance(target_index, bool):
        raise TypeError("target_index must be an int")
    n = len(base_acl)
    if target_index < 0 or target_index >= n:
        raise ValueError("target_index out of range")
    for i, bit in enumerate(base_acl):
        if bit not in (0, 1):
            raise ValueError(f"base_acl[{i}] is not 0/1")

    a0 = list(base_acl)
    a1 = list(base_acl)
    a0[target_index] = 0
    a1[target_index] = 1
    return a0, a1


def diff_indices(a: Iterable[int], b: Iterable[int]) -> list[int]:
    """Return indices where two equal-length bitmaps differ (test helper)."""
    la, lb = list(a), list(b)
    if len(la) != len(lb):
        raise ValueError("bitmaps must have equal length")
    return [i for i, (x, y) in enumerate(zip(la, lb)) if x != y]


# --------------------------------------------------------------------------- #
# Phase D — Python side of the frozen binary format
# --------------------------------------------------------------------------- #
def encode_acl_bitmap(bitmap: Sequence[int]) -> bytes:
    """Encode a 0/1 bitmap into the frozen H1ACL01 binary format (LSB-first)."""
    bits = list(bitmap)
    for i, bit in enumerate(bits):
        if bit not in (0, 1):
            raise ValueError(f"bitmap[{i}] is not 0/1")
    n = len(bits)
    if n == 0:
        raise ValueError("bitmap must be non-empty (N > 0)")
    payload_len = (n + 7) // 8
    payload = bytearray(payload_len)
    for i, bit in enumerate(bits):
        if bit:
            payload[i // 8] |= 1 << (i % 8)
    return MAGIC + n.to_bytes(COUNT_LEN, "little", signed=False) + bytes(payload)


def decode_acl_bitmap(data: bytes) -> list[int]:
    """Decode and VALIDATE a frozen H1ACL01 blob into a 0/1 bitmap list.

    Rejects: bad magic/version, count inconsistency, truncated or trailing
    payload, and any non-zero padding bit beyond member count. No secret
    metadata is read because the format carries none.
    """
    raw = bytes(data)
    if len(raw) < HEADER_LEN:
        raise ValueError("blob shorter than header")
    if raw[:MAGIC_LEN] != MAGIC:
        raise ValueError("bad magic or version")
    n = int.from_bytes(raw[MAGIC_LEN:HEADER_LEN], "little", signed=False)
    if n == 0:
        raise ValueError("member count must be positive (N > 0)")
    payload_len = (n + 7) // 8
    expected = HEADER_LEN + payload_len
    if len(raw) < expected:
        raise ValueError("truncated payload")
    if len(raw) > expected:
        raise ValueError("trailing bytes")
    payload = raw[HEADER_LEN:]
    # LSB-first: valid bits occupy the LOW bits of the final byte, so tail
    # padding occupies the HIGH bits. Require those high bits to be zero.
    used_in_last = n % 8
    if used_in_last:
        mask = (0xFF << used_in_last) & 0xFF
        if payload[-1] & mask:
            raise ValueError("non-zero tail padding")
    return [(payload[i // 8] >> (i % 8)) & 1 for i in range(n)]


def label_to_index(label: int, label_base: int = 100000, label_step: int = 17) -> int:
    """Map a valid external label to a bitmap index; raise on invalid label.

    Mirrors the C++ loader rule: label must be >= base and lie exactly on the
    ``label_base + label_step * i`` grid. Invalid labels never map to a bit.
    """
    if not isinstance(label, int) or isinstance(label, bool):
        raise TypeError("label must be an int")
    if label < label_base:
        raise ValueError("label below base")
    offset = label - label_base
    if offset % label_step != 0:
        raise ValueError("label not on step grid")
    return offset // label_step
