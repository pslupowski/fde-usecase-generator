"""Unit tests for tools.py in the FDE Use Case Template Generator."""

from __future__ import annotations

import os
import pytest
from tools import (
    validate_fde_kpi_metrics,
    recommend_gcp_reference_architecture,
    export_validated_fde_template_to_markdown,
    require_human_approval,
    get_fde_tools,
)


def test_validate_fde_kpi_metrics_success():
    """Test successful KPI validation."""
    metrics = [
        {
            "name": "P95 Latency",
            "category": "latency",
            "baseline_value": 2000.0,
            "target_value": 800.0,
            "unit": "ms",
            "telemetry_source": "Cloud Trace",
        },
        {
            "name": "Task Accuracy",
            "category": "accuracy",
            "baseline_value": 80.0,
            "target_value": 95.0,
            "unit": "%",
            "telemetry_source": "BigQuery evaluation table",
        },
    ]

    res = validate_fde_kpi_metrics("Retail Project", metrics)
    assert res["is_valid"] is True
    assert len(res["validated_metrics"]) == 2
    assert len(res["errors"]) == 0
    assert "All 2 KPI metrics passed" in res["summary"]


def test_validate_fde_kpi_metrics_schema_failure():
    """Test that schema violations produce actionable recovery instructions."""
    # Pass bad category and invalid type
    res = validate_fde_kpi_metrics(
        "Invalid Project",
        [{"name": "Bad", "category": "non_existent_category", "baseline_value": "abc"}],  # type: ignore
    )
    assert res["is_valid"] is False
    assert len(res["actionable_recovery_instructions"]) > 0


def test_recommend_gcp_reference_architecture_success():
    """Test standard architecture recommendation."""
    res = recommend_gcp_reference_architecture(
        use_case_type="search_and_discovery",
        expected_rpm=2000,
        security_tier="high",
        max_latency_ms=1000,
        data_residency_region="us-central1",
    )
    assert res["is_valid"] is True
    assert "Cloud Run" in res["compute_layer"]
    assert "Vertex AI (Gemini 2.5 Pro & Flash)" in res["recommended_services"]
    assert "Model Armor" in res["mermaid_diagram"]


def test_recommend_gcp_reference_architecture_high_scale():
    """Test GKE selection under high RPM traffic."""
    res = recommend_gcp_reference_architecture(
        use_case_type="multi_agent_automation",
        expected_rpm=10000,
        security_tier="critical",
        max_latency_ms=500,
        data_residency_region="us-central1",
    )
    assert res["is_valid"] is True
    assert "GKE Enterprise" in res["compute_layer"]
    assert "VPC Service Controls" in str(res["security_controls"])


def test_require_human_approval_logic():
    """Test human confirmation evaluation logic."""
    assert require_human_approval({"human_approval_token": "APPROVED-LEAD-2026", "approver_name": "Patrice"}) is True
    assert require_human_approval({"human_approval_token": "", "approver_name": "Patrice"}) is False
    assert require_human_approval({"human_approval_token": "RANDOM_STRING", "approver_name": "Patrice"}) is False


def test_get_fde_tools_wrapper():
    """Verify tool registration factory returns list of tools."""
    tools_list = get_fde_tools()
    assert len(tools_list) == 3
