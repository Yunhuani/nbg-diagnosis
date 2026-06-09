from __future__ import annotations

from typing import Any


def assemble_fact_base(
    intake: dict[str, Any],
    financial_facts: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the shared fact base for dimension analysis."""
    return {
        "diagnosis_intake": intake,
        "financial_facts": financial_facts,
        "availability_map": intake.get("availability_map", {}),
    }
