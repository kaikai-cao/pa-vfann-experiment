"""Explicit protocol communication models for E3 client-side filtering.

EXP-02 reported only ``candidate_transfer_bytes`` = 4 B ID + 4 B squared L2
distance per candidate. That is a LOWER BOUND: it carries no ACL, TTL or other
predicate metadata, so the client cannot actually evaluate the authorization
predicate from that record alone.

This module defines three auditable models. Attribute lengths are scan
parameters, not measured constants.

  A  ID + distance                     -- lower bound; filtering not executable
  B  ID + distance + full attributes   -- one server->client message
  C  ID + distance + attribute refs    -- extra attribute fetch round, non-zero

No cryptography is introduced. These are byte-accounting models only.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import AuditConfig

MODELS = ("A", "B", "C")

MODEL_FIELDS: dict[str, tuple[str, ...]] = {
    "A": ("candidate_id", "query_distance"),
    "B": ("candidate_id", "query_distance", "acl_attributes",
          "ttl_expiration", "other_predicate_metadata"),
    "C": ("candidate_id", "query_distance", "metadata_reference",
          "attribute_fetch"),
}

MODEL_DESCRIPTIONS = {
    "A": "ID + distance only (EXP-02 lower bound; client cannot evaluate predicate)",
    "B": "ID + distance + full ACL/TTL/predicate metadata in one message",
    "C": "ID + distance + metadata reference; attributes fetched in an extra round",
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    holder: str
    currently_transmitted: bool
    client_can_obtain_locally: str
    byte_formula: str
    note: str


def field_requirements() -> tuple[FieldSpec, ...]:
    """What the client needs in order to evaluate an authorization predicate."""
    return (
        FieldSpec(
            "candidate_id", "server (graph node id)", True, "no",
            "id_bytes per candidate",
            "Already in EXP-02. Without it the client cannot name the record.",
        ),
        FieldSpec(
            "query_distance", "server (lazy distance cache)", True,
            "yes, but only with the full vector",
            "distance_bytes per candidate",
            "Already in EXP-02. Client can recompute only if it has the vector.",
        ),
        FieldSpec(
            "acl_attributes", "authorization data source / policy owner", False,
            "conditional: only if client holds a local ACL replica",
            "acl_bytes per candidate (scan parameter)",
            "Not in EXP-02. Model B sends it; model C sends a reference instead.",
        ),
        FieldSpec(
            "ttl_expiration", "authorization data source", False,
            "conditional: only with a local freshness source",
            "ttl_bytes per candidate (scan parameter)",
            "Not in EXP-02. Expiration is part of the predicate, not of the match bit.",
        ),
        FieldSpec(
            "other_predicate_metadata", "authorization data source", False,
            "conditional: only with a local metadata replica",
            "extra_bytes per candidate (scan parameter)",
            "Not in EXP-02. Placeholder for any further predicate input.",
        ),
        FieldSpec(
            "metadata_reference", "server (as opaque pointer)", False,
            "no", "reference_bytes per candidate (scan parameter)",
            "Model C only. The reference is not the attribute value.",
        ),
    )


@dataclass(frozen=True)
class TransferCost:
    model: str
    n_candidates: int
    fields: tuple[str, ...]
    server_to_client_bytes: int
    attribute_request_bytes: int
    attribute_response_bytes: int
    feedback_bytes: int
    total_bytes: int
    messages: int
    attribute_record_bytes: int
    includes_acl: bool
    includes_ttl: bool

    @property
    def is_executable_filter(self) -> bool:
        """Whether the client can actually evaluate the predicate from this model."""
        return self.model in ("B", "C")


def attribute_record_bytes(acl_bytes: int, ttl_bytes: int, extra_bytes: int) -> int:
    return max(0, int(acl_bytes)) + max(0, int(ttl_bytes)) + max(0, int(extra_bytes))


def compute_transfer(
    n_candidates: int,
    model: str,
    config: AuditConfig,
    *,
    acl_bytes: int | None = None,
    ttl_bytes: int | None = None,
    extra_bytes: int | None = None,
    ref_bytes: int | None = None,
    feedback_ids: bool | None = None,
) -> TransferCost:
    """Byte accounting for one query's candidate batch.

    Model A and B report pure field bytes (no framing) so A matches EXP-02's
    ``candidate_transfer_bytes`` exactly. Model C adds framing because it adds
    a real request/response round; its attribute cost is never silently zero.
    """
    model = model.upper()
    if model not in MODELS:
        raise ValueError(f"unknown transfer model: {model}")
    n = max(0, int(n_candidates))
    ser = config["serialization"]
    proto = config["protocol"]
    base = config["attribute_fields"]["baseline"]
    acl = int(base["acl_bytes"] if acl_bytes is None else acl_bytes)
    ttl = int(base["ttl_bytes"] if ttl_bytes is None else ttl_bytes)
    extra = int(base["extra_bytes"] if extra_bytes is None else extra_bytes)
    ref = int(8 if ref_bytes is None else ref_bytes)
    feedback = bool(proto["default_feedback_ids"] if feedback_ids is None else feedback_ids)
    id_b = int(ser["id_bytes"])
    dist_b = int(ser["distance_bytes"])
    attr_b = attribute_record_bytes(acl, ttl, extra)

    if model == "A":
        s2c = n * (id_b + dist_b)
        req = resp = 0
        messages = 1
    elif model == "B":
        s2c = n * (id_b + dist_b + attr_b)
        req = resp = 0
        messages = 1
    else:
        s2c = n * (id_b + dist_b + ref)
        req = int(proto["request_header_bytes"]) + n * ref
        resp = int(proto["response_header_bytes"]) + n * attr_b
        messages = 3

    fb = int(proto["top_k"]) * id_b if feedback else 0
    if feedback:
        messages += 1

    return TransferCost(
        model=model,
        n_candidates=n,
        fields=MODEL_FIELDS[model],
        server_to_client_bytes=s2c,
        attribute_request_bytes=req,
        attribute_response_bytes=resp,
        feedback_bytes=fb,
        total_bytes=s2c + req + resp + fb,
        messages=messages,
        attribute_record_bytes=attr_b,
        includes_acl=model in ("B", "C"),
        includes_ttl=model in ("B", "C"),
    )
