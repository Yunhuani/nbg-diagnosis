from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import config

from analysis.llm_client import DeepSeekResponseError, call_deepseek_json
from business_plan.prompts import (
    QUALITATIVE_FIELD_REWRITE_PROMPT,
    SINGLE_PAIN_POINT_PROMPT,
    TEAM_BACKGROUND_REWRITE_PROMPT,
    TARGET_CUSTOMER_PROMPT,
    build_field_rewrite_user_prompt,
    build_single_pain_point_user_prompt,
    build_target_customer_user_prompt,
)
from business_plan.schemas import (
    DemandIntake,
    FieldOutput,
    FundingIntake,
    ModuleOutput,
    PlanIntake,
    ProductModelIntake,
    ProjectOverviewIntake,
    SourceType,
    TeamIntake,
    TEXT_LENGTH_CONSTRAINTS,
    CurrentStateIntake,
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


def generate_overview_module(intake: ProjectOverviewIntake) -> ModuleOutput:
    """Generate BP module 0 with direct hard facts and isolated rewrites."""

    business_summary = _rewrite_qualitative_field(
        "business_summary", intake.business_summary, QUALITATIVE_FIELD_REWRITE_PROMPT
    )
    # C 类品牌与价值观字段是客户的品牌资产：原样搬运，绝不调用 LLM 改写。
    fields = {
        "bp_title": _client_or_pending(intake.bp_title),
        "company_name": _client_or_pending(intake.company_name),
        "founded": _client_or_pending(intake.founded),
        "one_liner": _client_or_pending(intake.one_liner),
        "business_summary": business_summary,
        "team_scale": _client_or_pending(intake.team_scale),
        "website": _client_or_pending(intake.website),
        "slogan": _client_or_pending(intake.slogan),
        "mission": _client_or_pending(intake.mission),
        "vision": _client_or_pending(intake.vision),
    }
    return _module_output(0, fields)


def generate_product_module(intake: ProductModelIntake) -> ModuleOutput:
    """Generate BP module 2 without exposing financial facts to the LLM."""

    rewritten_solutions = [
        {
            "pain_point": _client_or_pending(item.pain_point),
            "solution": _rewrite_qualitative_field(
                "solution", item.solution, QUALITATIVE_FIELD_REWRITE_PROMPT
            ),
        }
        for item in intake.solutions
    ]
    rewritten_core_values = [
        _rewrite_qualitative_field("core_value", value, QUALITATIVE_FIELD_REWRITE_PROMPT)
        for value in intake.core_values
    ]
    sales_model = _rewrite_qualitative_field(
        "sales_model", intake.sales_model, QUALITATIVE_FIELD_REWRITE_PROMPT
    )
    solution_source = _nested_source_type(rewritten_solutions, "solution")
    core_value_source = _field_list_source_type(rewritten_core_values)
    fields = {
        "solution": FieldOutput(rewritten_solutions, solution_source),
        "core_value": FieldOutput(rewritten_core_values, core_value_source),
        "business_model": FieldOutput(
            {
                "revenue_sources": [
                    {
                        "source": _client_or_pending(item.source),
                        "share": _client_or_pending(item.share),
                    }
                    for item in intake.revenue_sources
                ],
                "gross_margin": _client_or_pending(intake.gross_margin),
                "net_margin": _client_or_pending(intake.net_margin),
            },
            SourceType.CLIENT_PROVIDED,
        ),
        "sales_model": sales_model,
    }
    return _module_output(2, fields)


def generate_traction_module(intake: CurrentStateIntake) -> ModuleOutput:
    """Generate BP module 5 while copying all operating metrics verbatim."""

    product_status = _rewrite_qualitative_field(
        "product_status", intake.product_status, QUALITATIVE_FIELD_REWRITE_PROMPT
    )
    endorsements = _rewrite_qualitative_field(
        "endorsements", intake.endorsements, QUALITATIVE_FIELD_REWRITE_PROMPT
    )
    fields = {
        "traction": FieldOutput(
            {
                "product_status": product_status,
                "customer_count": _client_or_pending(intake.customer_count),
                "device_count": _client_or_pending(intake.device_count),
                "financials": {
                    name: _client_or_pending(value)
                    for name, value in intake.financials.items()
                },
                "team_size": _client_or_pending(intake.team_size),
                "coverage": _client_or_pending(intake.coverage),
                "endorsements": endorsements,
            },
            _field_list_source_type([product_status, endorsements]),
        )
    }
    return _module_output(5, fields)


def generate_plan_module(intake: PlanIntake) -> ModuleOutput:
    """Generate BP module 6 with direct forecasts and rewritten roadmap prose."""

    roadmap = []
    for stage in intake.roadmap:
        objective = _rewrite_qualitative_field(
            "roadmap_objective", stage.objective, QUALITATIVE_FIELD_REWRITE_PROMPT
        )
        deliverables = _rewrite_or_copy_hard_fact(
            "roadmap_deliverables", stage.deliverables
        )
        roadmap.append(
            {
                "period": _client_or_pending(stage.period),
                "objective": objective,
                "deliverables": deliverables,
            }
        )
    fields = {
        "roadmap": FieldOutput(roadmap, _nested_source_type(roadmap, "objective", "deliverables")),
        "financial_projection": FieldOutput(
            [
                {
                    "year": _client_or_pending(item.year),
                    "revenue": _client_or_pending(item.revenue),
                    "net_profit": _client_or_pending(item.net_profit),
                }
                for item in intake.financial_projection
            ],
            SourceType.CLIENT_PROVIDED,
        ),
    }
    return _module_output(6, fields)


def generate_funding_module(intake: FundingIntake) -> ModuleOutput:
    """Generate BP module 7 while preserving funding amounts and allocations."""

    use_of_funds = []
    for item in intake.use_of_funds:
        description = _rewrite_qualitative_field(
            "use_of_funds_description",
            item.description,
            QUALITATIVE_FIELD_REWRITE_PROMPT,
        )
        use_of_funds.append(
            {
                "purpose": _client_or_pending(item.purpose),
                "percentage": _client_or_pending(item.percentage),
                "description": description,
            }
        )
    fields = {
        "funding_ask": FieldOutput(
            {
                "funding_amount": _client_or_pending(intake.funding_amount),
                "dilution_range": _client_or_pending(intake.dilution_range),
            },
            SourceType.CLIENT_PROVIDED,
        ),
        "use_of_funds": FieldOutput(
            use_of_funds, _nested_source_type(use_of_funds, "description")
        ),
    }
    return _module_output(7, fields)


def generate_team_module(intake: TeamIntake) -> ModuleOutput:
    """Generate BP module 8 without sending names or roles to the LLM."""

    members = []
    for member in intake.members:
        background = _rewrite_qualitative_field(
            "team_background", member.background, TEAM_BACKGROUND_REWRITE_PROMPT
        )
        members.append(
            {
                "name": _client_or_pending(member.name),
                "role": _client_or_pending(member.role),
                "background": background,
            }
        )
    return _module_output(
        8,
        {"team": FieldOutput(members, _nested_source_type(members, "background"))},
    )


def _rewrite_qualitative_field(
    field_name: str,
    original_text: str | None,
    system_prompt: str,
) -> FieldOutput:
    if not original_text or not original_text.strip():
        return FieldOutput("待补充", SourceType.PENDING_CUSTOMER)
    max_chars = _short_field_max_chars(field_name)
    rewritten, source_type = _rewrite_text_field(
        original_text,
        system_prompt,
        lambda feedback: build_field_rewrite_user_prompt(
            field_name, original_text, feedback, max_chars=max_chars
        ),
        max_chars=max_chars,
    )
    return FieldOutput(rewritten, source_type)


def _rewrite_or_copy_hard_fact(field_name: str, original_text: str) -> FieldOutput:
    if re.search(r"\d", original_text):
        return _client_or_pending(original_text)
    return _rewrite_qualitative_field(
        field_name, original_text, QUALITATIVE_FIELD_REWRITE_PROMPT
    )


def _rewrite_text_field(
    original_text: str,
    system_prompt: str,
    build_user_prompt: Callable[[list[str] | None], str],
    *,
    max_chars: int | None = None,
) -> tuple[str, SourceType]:
    last_issues: list[str] = []
    for attempt in range(MAX_REWRITE_RETRIES + 1):
        try:
            response = _call_rewrite(
                system_prompt,
                build_user_prompt(last_issues if attempt else None),
            )
            rewritten_text = _parse_target_customer_response(response)
            valid, last_issues = validate_rewrite(
                original_text,
                rewritten_text,
                max_chars=max_chars,
            )
            if valid:
                return rewritten_text, SourceType.ENGINE_REWRITE
        except RewriteValidationError as exc:
            last_issues = [str(exc)]
    return original_text, SourceType.CLIENT_PROVIDED


def _client_or_pending(value: str | None) -> FieldOutput:
    if value is None or not value.strip():
        return FieldOutput("待补充", SourceType.PENDING_CUSTOMER)
    return FieldOutput(value, SourceType.CLIENT_PROVIDED)


def _short_field_max_chars(field_name: str) -> int | None:
    constraint_key = {
        "one_liner": "module_0.one_liner",
        "slogan": "module_0.slogan",
        "core_value": "module_2.core_value",
    }.get(field_name)
    if constraint_key is None:
        return None
    return TEXT_LENGTH_CONSTRAINTS[constraint_key].max_chars


def _field_list_source_type(fields: list[FieldOutput]) -> SourceType:
    if fields and all(field.source_type is SourceType.ENGINE_REWRITE for field in fields):
        return SourceType.ENGINE_REWRITE
    return SourceType.CLIENT_PROVIDED


def _nested_source_type(items: list[dict[str, Any]], *field_names: str) -> SourceType:
    nested_fields = [
        item[field_name]
        for item in items
        for field_name in field_names
        if isinstance(item[field_name], FieldOutput)
    ]
    return _field_list_source_type(nested_fields)


def _module_output(module_id: int, fields: dict[str, FieldOutput]) -> ModuleOutput:
    constraints = {
        field_name: TEXT_LENGTH_CONSTRAINTS[f"module_{module_id}.{field_name}"]
        for field_name in fields
        if f"module_{module_id}.{field_name}" in TEXT_LENGTH_CONSTRAINTS
    }
    return ModuleOutput(
        module_id=module_id,
        fields=fields,
        chart_data=[],
        text_length_constraints=constraints,
    )


def _rewrite_target_customer(original_text: str) -> tuple[str, SourceType]:
    return _rewrite_text_field(
        original_text,
        TARGET_CUSTOMER_PROMPT,
        lambda feedback: build_target_customer_user_prompt(original_text, feedback),
    )


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
