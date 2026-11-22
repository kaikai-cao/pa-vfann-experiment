"""Tests 3, 4 and 5: transfer accounting models."""

from __future__ import annotations

import pytest

from pa_vfann_exp02a.transfer_models import (
    MODEL_FIELDS, compute_transfer, field_requirements,
)


def test_3_attribute_length_changes_transfer_cost(audit_config):
    short = compute_transfer(1000, "B", audit_config, acl_bytes=8, ttl_bytes=0, extra_bytes=0)
    long = compute_transfer(1000, "B", audit_config, acl_bytes=64, ttl_bytes=0, extra_bytes=0)
    assert long.total_bytes > short.total_bytes
    assert long.total_bytes - short.total_bytes == (64 - 8) * 1000
    short_c = compute_transfer(1000, "C", audit_config, acl_bytes=8, ttl_bytes=0, extra_bytes=0)
    long_c = compute_transfer(1000, "C", audit_config, acl_bytes=64, ttl_bytes=0, extra_bytes=0)
    assert long_c.total_bytes - short_c.total_bytes == (64 - 8) * 1000


def test_4_id_distance_model_has_no_acl_or_ttl(audit_config):
    fields = MODEL_FIELDS["A"]
    assert "acl_attributes" not in fields
    assert "ttl_expiration" not in fields
    cost = compute_transfer(500, "A", audit_config, acl_bytes=64, ttl_bytes=8, extra_bytes=16)
    assert cost.server_to_client_bytes == 500 * (4 + 4)
    assert cost.total_bytes == 500 * 8
    assert cost.includes_acl is False and cost.includes_ttl is False
    assert cost.is_executable_filter is False
    spec = {f.name: f for f in field_requirements()}
    for name in ("acl_attributes", "ttl_expiration", "other_predicate_metadata"):
        assert spec[name].currently_transmitted is False


def test_5_metadata_reference_fetch_cost_is_never_zero(audit_config):
    cost = compute_transfer(500, "C", audit_config, acl_bytes=0, ttl_bytes=0, extra_bytes=0)
    assert cost.attribute_request_bytes > 0
    assert cost.attribute_response_bytes > 0
    assert cost.messages >= 3
    low = compute_transfer(500, "A", audit_config, acl_bytes=0, ttl_bytes=0, extra_bytes=0)
    assert cost.total_bytes > low.total_bytes
    assert cost.is_executable_filter is True

    with pytest.raises(ValueError):
        compute_transfer(10, "D", audit_config)
