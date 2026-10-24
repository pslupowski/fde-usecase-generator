"""Command Line Interface (CLI) entry point for the FDE Use Case Template Generator.

Supports:
- `generate`: Run end-to-end multi-agent pipeline to generate an FDE template.
- `interactive`: Prompt-guided interactive generation with live human approval.
- `evaluate`: Run automated self-evaluation against golden scenarios.

Enforces structured JSON logging with zero raw print statements.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from observability import fde_logger
from agent import FdeTemplateOrchestrator
from guardrails import screen_prompt_injection


async def run_generate_cli(args: argparse.Namespace) -> int:
    """Execute batch template generation from CLI arguments."""
    orchestrator = FdeTemplateOrchestrator(project_id=args.project_id)

    fde_logger.info(
        "Starting FDE Template Generator via CLI",
        extra={
            "project_name": args.project_name,
            "project_id": args.project_id,
            "has_token": bool(args.approval_token),
        },
    )

    result = await orchestrator.run_pipeline(
        use_case_description=args.use_case,
        project_name=args.project_name,
        human_approval_token=args.approval_token,
        approver_name=args.approver,
        output_filename=args.output,
    )

    if result.get("success"):
        fde_logger.info(
            "FDE Template successfully generated and exported",
            extra={
                "exported_path": result.get("exported_file_path"),
                "verification_hash": result.get("verification_hash"),
                "evaluation_score": result.get("self_evaluation", {}).get("score"),
            },
        )
        return 0
    else:
        fde_logger.error(
            "FDE Template generation failed",
            extra={
                "error": result.get("error") or result.get("error_message"),
                "recovery_instructions": result.get("actionable_recovery_instructions"),
            },
        )
        return 1


async def run_interactive_cli(project_id: str) -> int:
    """Run interactive CLI flow for FDE template generation."""
    fde_logger.info("Initializing interactive FDE Multi-Agent session...")
    sys.stdout.write("====================================================================\n")
    sys.stdout.write(" Google Cloud Forward Deployed Engineer (FDE) Template Generator    \n")
    sys.stdout.write(" Multi-Agent System (Google ADK) | Gemini 2.5 Pro & Flash Routing   \n")
    sys.stdout.write("====================================================================\n\n")

    project_name = input("Enter Customer Project Name: ").strip() or "Enterprise Retail AI"
    use_case = input("Describe Enterprise GenAI Use Case: ").strip() or (
        "Enterprise customer care search and automated triage system handling 20,000 queries/day "
        "across multimodal documents with strict SOC2/HIPAA compliance."
    )

    # Prompt screening
    is_safe, attack = screen_prompt_injection(use_case)
    if not is_safe:
        fde_logger.warning(f"Security Alert: Prompt flagged for {attack}. Session aborted.")
        return 1

    sys.stdout.write("\nSynthesizing discovery metrics and GCP architecture...\n")
    orchestrator = FdeTemplateOrchestrator(project_id=project_id)

    approver = input("Approving Executive / FDE Lead Name: ").strip() or "Patrice Slupowski"
    approval_token = input("Enter HITL Approval Token (e.g. APPROVED-FDE-LEAD): ").strip() or "APPROVED-FDE-LEAD-2026"

    result = await orchestrator.run_pipeline(
        use_case_description=use_case,
        project_name=project_name,
        human_approval_token=approval_token,
        approver_name=approver,
    )

    if result.get("success"):
        sys.stdout.write(f"\n[SUCCESS] Template exported to: {result.get('exported_file_path')}\n")
        sys.stdout.write(f"Verification SHA-256: {result.get('verification_hash')}\n")
        score = result.get("self_evaluation", {}).get("score", 0)
        sys.stdout.write(f"Self-Evaluation Score: {score}/100\n")
        return 0
    else:
        sys.stdout.write(f"\n[FAILED] {result.get('error_message')}\n")
        sys.stdout.write(f"Recovery: {result.get('actionable_recovery_instructions')}\n")
        return 1


def main() -> None:
    """CLI argument parser and dispatcher."""
    parser = argparse.ArgumentParser(
        description="FDE Use Case Template Generator Multi-Agent System (Google ADK)"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate an FDE template from parameters")
    gen_parser.add_argument("--project-name", default="OmniChannel GenAI Search", help="Project name")
    gen_parser.add_argument(
        "--use-case",
        default="Enterprise multi-agent product discovery and support assistant.",
        help="Use case description",
    )
    gen_parser.add_argument("--approver", default="Lead FDE Architect", help="Approver name")
    gen_parser.add_argument(
        "--approval-token",
        default="APPROVED-FDE-LEAD-2026",
        help="Human-in-the-Loop approval token",
    )
    gen_parser.add_argument("--output", default=None, help="Output markdown path")
    gen_parser.add_argument("--project-id", default="patrice-fde-agent-l200", help="GCP project ID")

    # Interactive command
    interactive_parser = subparsers.add_parser("interactive", help="Run interactive guided session")
    interactive_parser.add_argument(
        "--project-id", default="patrice-fde-agent-l200", help="GCP project ID"
    )

    # Evaluate command
    eval_parser = subparsers.add_parser("evaluate", help="Run golden evaluation suite")

    args = parser.parse_args()

    if args.command == "generate":
        code = asyncio.run(run_generate_cli(args))
        sys.exit(code)
    elif args.command == "interactive":
        code = asyncio.run(run_interactive_cli(args.project_id))
        sys.exit(code)
    elif args.command == "evaluate":
        import subprocess

        code = subprocess.call(["pytest", "tests/test_eval_golden.py", "-v"])
        sys.exit(code)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
