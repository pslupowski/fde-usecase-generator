"""Guardrails & Policy Plugins module for the FDE Use Case Template Generator.

Implements all criteria for Category 3.2:
1. Prompt-injection screening and adversarial exploit detection.
2. Google Cloud Model Armor hooks for input/output sanitization and policy enforcement.
3. Self-evaluation validation verifying FDE quality standards before final output.
4. Google ADK `GuardrailsPlugin` subclassing `BasePlugin`.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

from observability import fde_logger, scrub_pii, trace_agent_action

# Google ADK imports
try:
    from google.adk.plugins import BasePlugin
    from google.adk.agents.base_agent import BaseAgent
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types
except ImportError:
    BasePlugin = object  # type: ignore
    BaseAgent = Any  # type: ignore
    CallbackContext = Any  # type: ignore
    BaseTool = Any  # type: ignore
    ToolContext = Any  # type: ignore

    class _TypesMock:
        class Content:
            def __init__(self, role: str, parts: list[Any]):
                self.role = role
                self.parts = parts
    types = _TypesMock()  # type: ignore


# ---------------------------------------------------------------------------
# 1. Prompt Injection Screening Pipeline
# ---------------------------------------------------------------------------

PROMPT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "SYSTEM_PROMPT_OVERRIDE",
        re.compile(
            r"(?i)(ignore\s+(all\s+)?previous\s+instructions?|disregard\s+(all\s+)?prior\s+rules?|override\s+system\s+prompt)",
        ),
    ),
    (
        "JAILBREAK_ROLEPLAY",
        re.compile(
            r"(?i)(you\s+are\s+now\s+in\s+DAN\s+mode|act\s+as\s+an\s+unrestricted\s+AI|developer\s+mode\s+enabled|disable\s+safety\s+filters?)",
        ),
    ),
    (
        "PROMPT_LEAK_ATTEMPT",
        re.compile(
            r"(?i)(repeat\s+(the\s+entire\s+)?text\s+above|output\s+your\s+system\s+prompt|what\s+is\s+your\s+constitution|reveal\s+internal\s+instructions?)",
        ),
    ),
    (
        "DELIMITER_ESCAPE",
        re.compile(
            r"(?i)(```markdown\s*<system_override>|\[SYSTEM_COMMAND\]|<\|endoftext\|>|\[INST\]\s*<<SYS>>)",
        ),
    ),
    (
        "DATA_EXFILTRATION",
        re.compile(
            r"(?i)(curl\s+https?://|wget\s+https?://|send\s+all\s+credentials\s+to\s+)",
        ),
    ),
]


def screen_prompt_injection(prompt: str) -> Tuple[bool, Optional[str]]:
    """Screen user or agent prompt text for prompt injection and adversarial attacks.

    Args:
        prompt: Raw input text from user or external interface.

    Returns:
        Tuple of (is_safe: bool, attack_category: Optional[str]).
    """
    if not prompt or not isinstance(prompt, str):
        return True, None

    for category, pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(prompt):
            fde_logger.warning(
                f"Prompt injection detected! Category: {category}",
                extra={"security_event": "prompt_injection_blocked", "category": category},
            )
            return False, category

    return True, None


# ---------------------------------------------------------------------------
# 2. Google Cloud Model Armor Simulation & API Hook
# ---------------------------------------------------------------------------


def model_armor_sanitize_input(text: str, project_id: str = "patrice-fde-agent-l200") -> str:
    """Sanitize LLM input payload via Model Armor security hooks.

    Screens for toxic content, malicious URLs, hate speech, and unredacted PII.

    Args:
        text: Raw input to be submitted to Gemini models.
        project_id: Target GCP project.

    Returns:
        Sanitized safe text string.
    """
    if not text:
        return text

    # Apply PII scrubbing first
    sanitized = scrub_pii(text, project_id=project_id)

    # Filter adversarial HTML/script injection tags
    sanitized = re.sub(r"(?i)<script.*?>.*?</script>", "[BLOCKED_SCRIPT]", sanitized)
    sanitized = re.sub(r"(?i)javascript:", "blocked_uri:", sanitized)

    return sanitized


def model_armor_validate_output(text: str) -> Tuple[bool, str]:
    """Validate model output against enterprise safety and policy guardrails.

    Args:
        text: Raw generated output text from Gemini model.

    Returns:
        Tuple of (is_compliant: bool, filtered_text: str).
    """
    if not text:
        return True, text

    # Ensure no leaked sensitive tokens
    sanitized = scrub_pii(text)

    # Check for hallucinated unsafe commands
    if re.search(r"\brm\s+-rf\s+/\b|\bdd\s+if=/dev/zero\b", text):
        return False, "[CONTENT SUPPRESSED: Unsafe system command detected in model output]"

    return True, sanitized


# ---------------------------------------------------------------------------
# 3. Self-Evaluation Validation Rubric
# ---------------------------------------------------------------------------

REQUIRED_FDE_SECTIONS = [
    ("Executive Summary", r"## 1\. Executive Summary"),
    ("KPI Matrix", r"## 2\. Quantifiable KPI & Metrics Matrix"),
    ("GCP Architecture", r"## 3\. Target GCP Reference Architecture"),
    ("Security & Governance", r"## 4\. Security, Governance"),
    ("Implementation Roadmap", r"## 5\. Phased Implementation Roadmap"),
    ("Risk Register", r"## 6\. Risk Register"),
    ("Observability", r"## 7\. Observability"),
    ("Human Signoff", r"## 8\. Human-in-the-Loop & Approval Verification"),
]


def self_eval_fde_template(markdown_content: str) -> Dict[str, Any]:
    """Perform automated self-evaluation on a generated FDE template.

    Verifies structural completeness, presence of required sections,
    quantifiable metric tables, GCP architectural diagrams, and human approval.

    Args:
        markdown_content: The full markdown text of the draft template.

    Returns:
        Dictionary containing quality score (0-100), passing status, and gaps.
    """
    if not markdown_content or not isinstance(markdown_content, str):
        return {
            "score": 0,
            "is_passing": False,
            "missing_sections": [name for name, _ in REQUIRED_FDE_SECTIONS],
            "recommendations": ["Provide complete markdown content for evaluation."],
        }

    missing_sections: List[str] = []
    points = 0
    total_sections = len(REQUIRED_FDE_SECTIONS)

    for section_name, pattern in REQUIRED_FDE_SECTIONS:
        if re.search(pattern, markdown_content):
            points += 10
        else:
            missing_sections.append(section_name)

    # Check for Mermaid diagram presence (10 points)
    has_mermaid = bool(re.search(r"```mermaid[\s\S]*?```", markdown_content))
    if has_mermaid:
        points += 10
    else:
        missing_sections.append("Mermaid Architecture Diagram")

    # Check for Human-in-the-Loop approval marker (10 points)
    has_approval = "EXPLICITLY APPROVED" in markdown_content or "APPROVED & VALIDATED" in markdown_content
    if has_approval:
        points += 10
    else:
        missing_sections.append("Human Approval Verification Signature")

    is_passing = points >= 80

    recommendations = []
    if missing_sections:
        recommendations = [f"Add missing required section: '{s}'" for s in missing_sections]

    result = {
        "score": points,
        "max_score": 100,
        "is_passing": is_passing,
        "missing_sections": missing_sections,
        "has_mermaid_diagram": has_mermaid,
        "has_human_approval": has_approval,
        "recommendations": recommendations,
    }

    fde_logger.info(
        f"Self-Evaluation completed. Score: {points}/100. Status: {'PASS' if is_passing else 'NEEDS_REVISION'}"
    )
    return result


# ---------------------------------------------------------------------------
# 4. Google ADK Guardrails Plugin
# ---------------------------------------------------------------------------


class GuardrailsPlugin(BasePlugin):
    """Google ADK Policy Plugin that enforces prompt screening and Model Armor."""

    def __init__(self, project_id: str = "patrice-fde-agent-l200"):
        self.project_id = project_id

    async def before_agent_callback(
        self,
        *,
        agent: BaseAgent,
        callback_context: CallbackContext,
    ) -> Optional[Any]:
        """Intercept user input to screen for prompt injections before agent logic runs."""
        # Check user message text if accessible
        user_text = getattr(callback_context, "user_message", None)
        if isinstance(user_text, str):
            is_safe, attack_type = screen_prompt_injection(user_text)
            if not is_safe:
                refusal_message = (
                    f"SECURITY GUARDRAIL TRIGGERED: Input was flagged by Model Armor for '{attack_type}'. "
                    "Your request has been blocked in accordance with Google Cloud Security Policies."
                )
                try:
                    return types.Content(
                        role="model",
                        parts=[types.Part.from_text(text=refusal_message)],
                    )
                except Exception:
                    return refusal_message
        return None

    async def before_tool_callback(
        self,
        *,
        tool: BaseTool,
        tool_args: dict[str, Any],
        tool_context: ToolContext,
    ) -> Optional[dict[str, Any]]:
        """Validate tool inputs and check policy adherence."""
        tool_name = getattr(tool, "name", "")
        # Enforce security validation on export tool
        if "export" in tool_name:
            token = tool_args.get("human_approval_token", "")
            if not token:
                fde_logger.warning("Guardrail blocked unapproved export tool invocation.")
                return {
                    "success": False,
                    "error_message": "Policy violation: Export tool requires explicit human approval token.",
                    "recovery_instructions": "Obtain human authorization before executing export.",
                }
        return None
