from __future__ import annotations

from typing import Any

import config

from analysis.llm_client import DeepSeekResponseError, call_deepseek_json
from business_plan.prompts import (
    SINGLE_PAIN_POINT_PROMPT,
    TARGET_CUSTOMER_PROMPT,
    build_single_pain_point_user_prompt,
    build_target_customer_user_prompt,
)
from business_plan.schemas import (
    DemandIntake,
    FieldOutput,
    ModuleOutput,
    SourceType,
    TEXT_LENGTH_CONSTRAINTS,
)
from business_plan.validation import validate_rewrite


MAX_REWRITE_RETRIES = 2


def generate_demand_module(intake_demand: DemandIntake) -> ModuleOutput:
    """Generate BP module 1 with isolated rewrites and conservative fallback."""

    target_customer, target_source_type = _rewrite_target_customer(
        intake_demand.target_customer
    )
    rewritten_pain_points = []
    pain_points_degraded = False
    for pain_point in intake_demand.pain_points:
        rewritten, source_type = _rewrite_pain_point(
            pain_point.description,
            pain_point.why_rigid_demand,
        )
        rewritten_pain_points.append(rewritten)
        pain_points_degraded = pain_points_degraded or (
            source_type is SourceType.CLIENT_PROVIDED
        )

    fields = {
        "target_customer": FieldOutput(target_customer, target_source_type),
        "pain_points": FieldOutput(
            rewritten_pain_points,
            SourceType.CLIENT_PROVIDED
            if pain_points_degraded
            else SourceType.ENGINE_REWRITE,
        ),
        "why_now": FieldOutput("待补充", SourceType.PENDING_CUSTOMER),
    }
    constraints = {
        field_name: TEXT_LENGTH_CONSTRAINTS[f"module_1.{field_name}"]
        for field_name in fields
    }
    return ModuleOutput(
        module_id=1,
        fields=fields,
        chart_data=[],
        text_length_constraints=constraints,
    )


def _rewrite_target_customer(original_text: str) -> tuple[str, SourceType]:
    for attempt in range(MAX_REWRITE_RETRIES + 1):
        feedback: list[str] | None = None
        if attempt:
            feedback = last_issues
        try:
            response = _call_rewrite(
                TARGET_CUSTOMER_PROMPT,
                build_target_customer_user_prompt(original_text, feedback),
            )
            rewritten_text = _parse_target_customer_response(response)
            valid, last_issues = validate_rewrite(original_text, rewritten_text)
            if valid:
                return rewritten_text, SourceType.ENGINE_REWRITE
        except RewriteValidationError as exc:
            last_issues = [str(exc)]
    return original_text, SourceType.CLIENT_PROVIDED


def _rewrite_pain_point(
    description: str,
    why_rigid_demand: str,
) -> tuple[dict[str, str], SourceType]:
    original_text = f"{description}\n{why_rigid_demand}"
    for attempt in range(MAX_REWRITE_RETRIES + 1):
        feedback: list[str] | None = None
        if attempt:
            feedback = last_issues
        try:
            response = _call_rewrite(
                SINGLE_PAIN_POINT_PROMPT,
                build_single_pain_point_user_prompt(
                    description,
                    why_rigid_demand,
                    feedback,
                ),
            )
            rewritten = _parse_pain_point_response(response)
            rewritten_text = f"{rewritten['pain_point']}\n{rewritten['rigid_demand']}"
            valid, last_issues = validate_rewrite(original_text, rewritten_text)
            if valid:
                return rewritten, SourceType.ENGINE_REWRITE
        except RewriteValidationError as exc:
            last_issues = [str(exc)]
    return {
        "pain_point": description,
        "rigid_demand": why_rigid_demand,
    }, SourceType.CLIENT_PROVIDED


def _call_rewrite(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    try:
        response = call_deepseek_json(
            system_prompt,
            user_prompt,
            model=config.DEEPSEEK_MODEL,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_tokens=config.DEFAULT_MAX_TOKENS,
            max_attempts=config.LLM_MAX_ATTEMPTS,
        )
    except DeepSeekResponseError as exc:
        raise RewriteValidationError("上次输出不是有效 JSON") from exc
    if not isinstance(response, dict):
        raise RewriteValidationError("上次输出必须是 JSON 对象")
    return response


def _parse_target_customer_response(response: dict[str, Any]) -> str:
    if set(response) != {"value"}:
        raise RewriteValidationError("上次输出必须且只能包含 value")
    value = response["value"]
    if not isinstance(value, str) or not value.strip():
        raise RewriteValidationError("上次输出的 value 必须是非空字符串")
    return value


def _parse_pain_point_response(response: dict[str, Any]) -> dict[str, str]:
    if set(response) != {"pain_point", "rigid_demand"}:
        raise RewriteValidationError(
            "上次输出必须且只能包含 pain_point 与 rigid_demand"
        )
    if not all(isinstance(value, str) and value.strip() for value in response.values()):
        raise RewriteValidationError("上次输出字段必须都是非空字符串")
    return {
        "pain_point": response["pain_point"],
        "rigid_demand": response["rigid_demand"],
    }


class RewriteValidationError(ValueError):
    """Raised when an isolated rewrite is malformed or fails fact checks."""
