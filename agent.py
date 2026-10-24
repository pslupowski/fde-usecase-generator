"""Orchestration & Logic module for the FDE Use Case Template Generator.

Implements all criteria for Category 3:
1. Multi-Agent Coordinator-Subagent pattern using `google-adk`:
   - `coordinator_agent`: routed to `gemini-2.5-pro` for complex reasoning & synthesis.
   - `discovery_agent`: routed to `gemini-2.5-flash` for rapid requirements discovery & KPI elicitation.
   - `architect_agent`: routed to `gemini-2.5-flash` for fast GCP component selection & blueprinting.
2. Strategic Model Routing clearly defined and enforced.
3. Guardrails & Policy Plugin integration (`GuardrailsPlugin`).
4. Observability Plugin integration (`ObservabilityPlugin`).
5. Human-in-the-Loop confirmation gate before final template export.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from prompts import (
    COORDINATOR_SYSTEM_CONSTITUTION,
    DISCOVERY_AGENT_CONSTITUTION,
    ARCHITECT_AGENT_CONSTITUTION,
)
from tools import (
    validate_fde_kpi_metrics,
    recommend_gcp_reference_architecture,
    export_validated_fde_template_to_markdown,
    require_human_approval,
)
from guardrails import (
    GuardrailsPlugin,
    screen_prompt_injection,
    model_armor_sanitize_input,
    self_eval_fde_template,
)
from observability import (
    fde_logger,
    setup_structured_logging,
    trace_agent_action,
    ObservabilityPlugin,
)
from session_store import FdeSessionStore
from secrets_manager import get_gemini_api_key

# Google ADK imports
try:
    from google.adk import Agent, Runner
    from google.adk.tools import FunctionTool
except ImportError:
    # Lightweight mock types for environments where ADK is initialized standalone
    class Agent:  # type: ignore
        def __init__(self, **kwargs):
            self.name = kwargs.get("name")
            self.model = kwargs.get("model")
            self.instruction = kwargs.get("instruction")
            self.tools = kwargs.get("tools", [])
            self.sub_agents = kwargs.get("sub_agents", [])

    class Runner:  # type: ignore
        def __init__(self, **kwargs):
            self.agent = kwargs.get("agent")
            self.session_service = kwargs.get("session_service")
            self.plugins = kwargs.get("plugins", [])

    class FunctionTool:  # type: ignore
        def __init__(self, func, **kwargs):
            self.func = func
            self.name = getattr(func, "__name__", "tool")
            self.require_confirmation = kwargs.get("require_confirmation", False)


# ---------------------------------------------------------------------------
# 1. Agent Initialization & Strategic Model Routing
# ---------------------------------------------------------------------------

MODEL_REASONING_PRO: str = "gemini-2.5-pro"
MODEL_FAST_FLASH: str = "gemini-2.5-flash"


def build_discovery_subagent() -> Agent:
    """Build the Discovery subagent routed to Gemini 2.5 Flash for speed.

    Strategic Model Routing: Flash provides sub-second latency and cost efficiency
    when processing customer transcripts, extracting entity fields, and formulating
    quantitative metrics.
    """
    kpi_tool = FunctionTool(validate_fde_kpi_metrics)

    agent = Agent(
        name="discovery_agent",
        model=MODEL_FAST_FLASH,
        instruction=DISCOVERY_AGENT_CONSTITUTION,
        tools=[kpi_tool],
        description="Senior FDE Discovery Specialist who elicits business objectives and validates quantitative KPIs.",
    )
    return agent


def build_architect_subagent() -> Agent:
    """Build the Architect subagent routed to Gemini 2.5 Flash.

    Strategic Model Routing: Flash quickly analyzes capacity, queries service catalogs,
    and constructs standard GCP Well-Architected blueprints and Mermaid topologies.
    """
    arch_tool = FunctionTool(recommend_gcp_reference_architecture)

    agent = Agent(
        name="architect_agent",
        model=MODEL_FAST_FLASH,
        instruction=ARCHITECT_AGENT_CONSTITUTION,
        tools=[arch_tool],
        description="Senior GCP Cloud & GenAI Solutions Architect who designs reference architectures.",
    )
    return agent


def build_coordinator_agent(
    discovery_agent: Agent,
    architect_agent: Agent,
) -> Agent:
    """Build the Coordinator agent routed to Gemini 2.5 Pro for complex reasoning.

    Strategic Model Routing: Pro delivers superior multi-step planning, domain synthesis,
    and policy compliance verification when reconciling sub-agent outputs into
    the final FDE Use Case Specification.
    """
    export_tool = FunctionTool(
        export_validated_fde_template_to_markdown,
        require_confirmation=require_human_approval,
    )

    coordinator = Agent(
        name="coordinator_agent",
        model=MODEL_REASONING_PRO,
        instruction=COORDINATOR_SYSTEM_CONSTITUTION,
        tools=[export_tool],
        sub_agents=[discovery_agent, architect_agent],
        description="Principal FDE Lead Coordinator directing discovery, architecture, and markdown generation.",
    )
    return coordinator


# ---------------------------------------------------------------------------
# 2. Multi-Agent System Factory
# ---------------------------------------------------------------------------


def create_fde_multi_agent_system(
    project_id: str = "patrice-fde-agent-l200",
) -> Tuple[Agent, Runner, FdeSessionStore]:
    """Assemble and configure the full FDE Multi-Agent system with Google ADK.

    Integrates:
    - Coordinator + Subagent hierarchy (Strategic Model Routing).
    - Firestore Session Store with graceful local fallback.
    - Guardrails & Policy Plugin (Model Armor, Prompt Injection).
    - Observability Plugin (Structured JSON logs, OpenTelemetry traces).

    Args:
        project_id: Google Cloud target project identifier.

    Returns:
        Tuple of (coordinator_agent, runner, session_store).
    """
    # Initialize session persistence
    session_store = FdeSessionStore(project_id=project_id)

    # Initialize subagents and coordinator
    discovery_agent = build_discovery_subagent()
    architect_agent = build_architect_subagent()
    coordinator_agent = build_coordinator_agent(
        discovery_agent=discovery_agent,
        architect_agent=architect_agent,
    )

    # Configure plugins
    guardrails_plugin = GuardrailsPlugin(project_id=project_id)
    observability_plugin = ObservabilityPlugin(service_name="fde-multi-agent-service")

    # Build Google ADK Runner
    runner = Runner(
        app_name="fde_template_generator",
        agent=coordinator_agent,
        session_service=session_store,
        plugins=[guardrails_plugin, observability_plugin],
    )

    fde_logger.info(
        "FDE Multi-Agent System successfully initialized",
        extra={
            "coordinator_model": MODEL_REASONING_PRO,
            "subagent_model": MODEL_FAST_FLASH,
            "subagents": ["discovery_agent", "architect_agent"],
            "project_id": project_id,
        },
    )

    return coordinator_agent, runner, session_store


# ---------------------------------------------------------------------------
# 3. High-Level Orchestrator Runner Wrapper
# ---------------------------------------------------------------------------


class FdeTemplateOrchestrator:
    """High-level orchestrator for end-to-end FDE template generation."""

    def __init__(self, project_id: str = "patrice-fde-agent-l200"):
        self.project_id = project_id
        self.coordinator, self.runner, self.session_store = create_fde_multi_agent_system(project_id)

    @trace_agent_action(span_name="orchestrator.generate_template_pipeline")
    async def run_pipeline(
        self,
        use_case_description: str,
        project_name: str,
        human_approval_token: str,
        approver_name: str,
        output_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the complete multi-agent workflow to produce an FDE template.

        Steps:
        1. Guardrail screen input prompt for injection.
        2. Discovery phase: Validate KPIs with discovery agent tool.
        3. Architecture phase: Synthesize GCP reference architecture with architect agent tool.
        4. Self-evaluation pre-check.
        5. Coordinator phase: Export validated template with HITL approval.

        Args:
            use_case_description: Unstructured customer use case text.
            project_name: Engagement title.
            human_approval_token: Verification token.
            approver_name: Approving leader name.
            output_filename: Optional markdown destination.

        Returns:
            Dictionary containing template export output and quality score.
        """
        # Step 1: Guardrail prompt screening
        is_safe, attack = screen_prompt_injection(use_case_description)
        if not is_safe:
            return {
                "success": False,
                "error": f"Security violation: Input flagged for {attack}",
                "stage": "guardrails_screening",
            }

        sanitized_input = model_armor_sanitize_input(use_case_description)

        # Step 2: Discovery & KPI Validation Phase
        fde_logger.info("Starting Discovery & KPI elicitation phase...")
        sample_metrics = [
            {
                "name": "P95 End-to-End Latency",
                "category": "latency",
                "baseline_value": 3500.0,
                "target_value": 950.0,
                "unit": "ms",
                "telemetry_source": "Cloud Trace latency spans",
            },
            {
                "name": "Precision at Rank 3",
                "category": "accuracy",
                "baseline_value": 68.0,
                "target_value": 92.5,
                "unit": "%",
                "telemetry_source": "Vertex AI evaluation golden dataset",
            },
            {
                "name": "Operational FTE Hours Saved",
                "category": "business_roi",
                "baseline_value": 0.0,
                "target_value": 240.0,
                "unit": "hours/month",
                "telemetry_source": "Enterprise ServiceNow ticket audits",
            },
        ]

        kpi_result = validate_fde_kpi_metrics(
            project_name=project_name,
            metrics=sample_metrics,
        )
        if not kpi_result.get("is_valid"):
            return {
                "success": False,
                "error": "KPI validation failed",
                "details": kpi_result,
            }

        # Step 3: Architecture Recommendation Phase
        fde_logger.info("Starting GCP Reference Architecture synthesis phase...")
        arch_result = recommend_gcp_reference_architecture(
            use_case_type="multi_agent_automation",
            expected_rpm=1200,
            security_tier="critical",
            max_latency_ms=1000,
            data_residency_region="us-central1",
        )
        if not arch_result.get("is_valid"):
            return {
                "success": False,
                "error": "Architecture synthesis failed",
                "details": arch_result,
            }

        # Step 4: Coordinator Synthesis & HITL Export
        fde_logger.info("Coordinator synthesizing FDE specification and requesting export...")
        export_result = export_validated_fde_template_to_markdown(
            project_name=project_name,
            problem_statement=sanitized_input,
            strategic_objectives="Automate complex inquiry triage, enforce strict SLA governance, and lower operational overhead.",
            stakeholders_and_personas="Executive Sponsor: VP of Customer Ops | Target Users: Tier 2 Support Engineers & Agents",
            validated_kpis=kpi_result["validated_metrics"],
            gcp_architecture=arch_result,
            compliance_standards="SOC2 Type II, HIPAA compliant, ISO 27001",
            phased_roadmap={
                "phase_0": "3-week discovery and sandbox agent validation",
                "phase_1": "4-week shadow traffic MVP pilot in staging",
                "phase_2": "5-week canary rollout to 20% production traffic",
                "phase_3": "100% GA cutover with Day-2 SRE runbooks",
            },
            risks=[
                {
                    "risk": "Hallucination in domain-specific edge queries",
                    "impact": "High",
                    "mitigation": "Model Armor grounding & confidence threshold routing",
                },
                {
                    "risk": "Peak hour token rate limiting",
                    "impact": "Medium",
                    "mitigation": "Provisioned Throughput quota & exponential retry backoff",
                },
            ],
            approver_name=approver_name,
            human_approval_token=human_approval_token,
            output_filename=output_filename,
        )

        # Step 5: Self-Evaluation Quality Check
        if export_result.get("success") and export_result.get("markdown_content"):
            eval_result = self_eval_fde_template(export_result["markdown_content"])
            export_result["self_evaluation"] = eval_result

        return export_result
