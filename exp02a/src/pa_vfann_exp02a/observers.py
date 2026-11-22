"""Observer model for EXP-02A.

EXP-02 called the cross-policy difference of returned IDs ``output_id_leakage``
and implicitly read it as server leakage. That is only correct when the server
itself produces or receives the filtered Top-K (E1/E2, or E3 with explicit
client feedback). In the default E3 setting the server sends policy-independent
candidates and the client filters locally, so the resulting IDs are not visible
to the server at all.

Here the legacy metric is renamed ``cross_policy_output_distinguishability``
and a separate ``server_observable_leakage`` is computed from channels the
server can truly see.
"""

from __future__ import annotations

from typing import Any

OBSERVERS = ("O_server", "O_client", "O_network")

FIELDS = (
    "query",
    "search_trace",
    "candidate_ids",
    "candidate_distances",
    "auth_attributes",
    "topk_ids",
    "message_sizes",
    "message_counts",
    "stop_position",
    "feedback_ids",
)

LEGACY_METRIC_ALIASES = {
    "output_id_leakage": "cross_policy_output_distinguishability",
}

# Raw EXP-02 CSV metrics that a server can compare across two policies.
_TRACE_CHANNELS = (
    "discovery_leakage", "visit_leakage", "expansion_leakage",
    "visit_edit_leakage",
)


def algorithm_produces_result_locally(algorithm: str) -> bool:
    """E1/E2 filter at the server; E3 filters at the client."""
    return algorithm in ("E1_POSTFILTER", "E2_BRIDGE")


def output_id_observers(algorithm: str, feedback_ids: bool) -> tuple[str, ...]:
    """Who can observe the final Top-K IDs under this protocol setting?"""
    if algorithm_produces_result_locally(algorithm):
        return ("O_server", "O_client")
    return ("O_server", "O_client") if feedback_ids else ("O_client",)


def visibility_matrix(
    algorithm: str,
    model: str,
    feedback_ids: bool,
    network_tls: bool,
) -> dict[str, dict[str, bool]]:
    """Field-level visibility for the three defined observers.

    ``auth_attributes`` means the attribute VALUES. Holding public attributes
    is not the same as knowing the client's predicate or the match bit: the
    server never receives a match bit in any model.
    """
    model = model.upper()
    result_server = algorithm_produces_result_locally(algorithm) or feedback_ids

    server = {
        "query": True,
        "search_trace": True,
        "candidate_ids": True,
        "candidate_distances": True,
        "auth_attributes": model == "B",  # values sent, match bit never sent
        "topk_ids": bool(result_server),
        "message_sizes": True,
        "message_counts": True,
        "stop_position": True,
        "feedback_ids": bool(feedback_ids),
    }
    client = {
        "query": True,
        "search_trace": False,
        "candidate_ids": True,
        "candidate_distances": True,
        "auth_attributes": True,       # held locally or fetched in model C
        "topk_ids": True,
        "message_sizes": True,
        "message_counts": True,
        "stop_position": False,
        "feedback_ids": bool(feedback_ids),
    }
    if network_tls:
        network = {f: False for f in FIELDS}
        network["message_sizes"] = True
        network["message_counts"] = True
    else:
        network = {
            "query": True,
            "search_trace": False,
            "candidate_ids": True,
            "candidate_distances": True,
            "auth_attributes": model in ("B", "C"),
            "topk_ids": bool(result_server),
            "message_sizes": True,
            "message_counts": True,
            "stop_position": False,
            "feedback_ids": bool(feedback_ids),
        }
    return {"O_server": server, "O_client": client, "O_network": network}


def server_observable_channels(algorithm: str, feedback_ids: bool) -> tuple[str, ...]:
    """Metric names from the frozen EXP-02 leakage CSV visible to the server."""
    channels = list(_TRACE_CHANNELS)
    channels += ("stop_position_delta", "candidate_count_delta")
    if algorithm_produces_result_locally(algorithm) or feedback_ids:
        channels.append("output_id_leakage")
    return tuple(channels)


def _finite(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0  # NaN -> 0


def reclassify_leakage_row(row: dict, algorithm: str, feedback_ids: bool) -> dict:
    """Rename the legacy output metric and add server-visible leakage.

    ``server_observable_leakage`` is the maximum normalized difference over
    channels the server can actually see. Stop position and candidate count
    are normalized by policy A's own value; all other channels are already in
    [0, 1]. A value of 0 does NOT prove privacy: it only says this server saw
    no cross-policy difference in the recorded channels.
    """
    out = dict(row)
    out["cross_policy_output_distinguishability"] = _finite(row.get("output_id_leakage"))
    out["output_id_observers"] = "+".join(output_id_observers(algorithm, feedback_ids))
    out["server_can_observe_topk_ids"] = int(
        algorithm_produces_result_locally(algorithm) or feedback_ids
    )
    components = [_finite(row.get(c)) for c in _TRACE_CHANNELS]
    stop_scale = max(1.0, _finite(row.get("stop_position")))
    cand_scale = max(1.0, _finite(row.get("candidate_count")))
    components.append(min(1.0, _finite(row.get("stop_position_delta")) / stop_scale))
    components.append(min(1.0, _finite(row.get("candidate_count_delta")) / cand_scale))
    if algorithm_produces_result_locally(algorithm) or feedback_ids:
        components.append(out["cross_policy_output_distinguishability"])
    out["server_observable_leakage"] = max(components) if components else 0.0
    out["observable_channel_count"] = len(server_observable_channels(algorithm, feedback_ids))
    return out
