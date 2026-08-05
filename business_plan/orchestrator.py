"""Concurrent, failure-isolated orchestration for the nine BP modules."""

from __future__ import annotations

import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable

import config

from analysis import llm_client as llm_client_module
from analysis import search_client as search_client_module
from business_plan.generator import (
    generate_competition_module,
    generate_demand_module,
    generate_funding_module,
    generate_market_module,
    generate_module_headline,
    generate_module_sub_headline,
    generate_overview_module,
    generate_plan_module,
    generate_product_module,
    generate_team_module,
    generate_traction_module,
)
from business_plan.schemas import (
    BPIntake,
    BPResult,
    ContactOutput,
    DegradedField,
    FieldOutput,
    GenerationStats,
    ModuleGenerationStatus,
    ModuleOutput,
    PendingItem,
    SourceType,
)


@dataclass(frozen=True)
class ModuleSpec:
    module_id: int
    result_field: str
    intake_field: str
    generator: Callable[[Any], ModuleOutput]
    minimum_llm_calls: Callable[[Any], int]


# The existing clients share urllib.request.urlopen. This lock keeps temporary
# request instrumentation isolated while module futures still run concurrently
# inside one BP generation.
_INSTRUMENTATION_LOCK = threading.RLock()

# Only B-class rewrite fields are eligible to be reported as fallbacks. A/C
# fields also use CLIENT_PROVIDED, so they must never appear in this list.
_REWRITE_FIELD_PATHS: dict[int, tuple[tuple[str, ...], ...]] = {
    0: (("business_summary",),),
    1: (("target_customer",), ("pain_points",)),
    2: (("solution",), ("core_value",), ("sales_model",)),
    3: (("market_narrative",),),
    4: (("differentiation",),),
    5: (("traction", "product_status"), ("traction", "endorsements")),
    6: (("roadmap", "*", "objective"), ("roadmap", "*", "deliverables")),
    7: (("use_of_funds", "*", "description"),),
    8: (("team", "*", "background"),),
}


def generate_business_plan(intake: BPIntake) -> BPResult:
    """Generate all BP modules concurrently while retaining partial results."""

    started_at = perf_counter()
    with _INSTRUMENTATION_LOCK:
        llm_call_count = 0
        headline_call_count = 0
        sub_headline_call_count = 0
        search_call_count = 0
        counter_lock = threading.Lock()
        original_urlopen = llm_client_module.request.urlopen

        def counted_urlopen(*args: Any, **kwargs: Any) -> Any:
            nonlocal llm_call_count
            nonlocal headline_call_count
            nonlocal sub_headline_call_count
            nonlocal search_call_count
            request_url = str(getattr(args[0], "full_url", "")) if args else ""
            with counter_lock:
                if request_url.endswith("/chat/completions"):
                    llm_call_count += 1
                    request_data = getattr(args[0], "data", b"") if args else b""
                    if b"[BP_MODULE_HEADLINE]" in (request_data or b""):
                        headline_call_count += 1
                    elif b"[BP_MODULE_SUB_HEADLINE]" in (request_data or b""):
                        sub_headline_call_count += 1
                elif request_url == search_client_module.BOCHA_SEARCH_URL:
                    search_call_count += 1
            return original_urlopen(*args, **kwargs)

        llm_client_module.request.urlopen = counted_urlopen
        try:
            outputs, statuses = _run_modules(intake)
        finally:
            llm_client_module.request.urlopen = original_urlopen

    pending_items = _collect_pending_items(outputs)
    degraded_fields = _collect_degraded_fields(outputs)
    minimum_llm_call_count = sum(
        spec.minimum_llm_calls(getattr(intake, spec.intake_field))
        for spec in MODULE_SPECS
    ) + sum(
        1
        for module_id, status in statuses.items()
        if 1 <= module_id <= 8 and status.status == "success"
    ) + sum(
        1
        for module_id, status in statuses.items()
        if module_id in (2, 3, 4, 6) and status.status == "success"
    )
    total_duration_seconds = perf_counter() - started_at
    generation_stats = GenerationStats(
        llm_call_count=llm_call_count,
        headline_call_count=headline_call_count,
        sub_headline_call_count=sub_headline_call_count,
        search_call_count=search_call_count,
        minimum_llm_call_count=minimum_llm_call_count,
        retry_llm_call_count=max(llm_call_count - minimum_llm_call_count, 0),
        total_duration_seconds=total_duration_seconds,
        module_durations={module_id: status.duration_seconds for module_id, status in statuses.items()},
        degraded_fields=degraded_fields,
    )
    return BPResult(
        bp_title=intake.project_overview.bp_title,
        contact=_build_contact_output(getattr(intake, "contact", None), intake.project_overview),
        executive_summary=None,
        project_overview=outputs.get("project_overview"),
        demand=outputs.get("demand"),
        product_model=outputs.get("product_model"),
        market=outputs.get("market"),
        competition=outputs.get("competition"),
        current_state=outputs.get("current_state"),
        plan=outputs.get("plan"),
        funding=outputs.get("funding"),
        team=outputs.get("team"),
        pending_items=pending_items,
        module_statuses=statuses,
        generation_stats=generation_stats,
    )


def _run_modules(
    intake: BPIntake,
) -> tuple[dict[str, ModuleOutput | None], dict[int, ModuleGenerationStatus]]:
    outputs: dict[str, ModuleOutput | None] = {}
    statuses: dict[int, ModuleGenerationStatus] = {}
    max_workers = max(1, config.MAX_DIMENSION_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict[Future[tuple[ModuleOutput | None, ModuleGenerationStatus]], ModuleSpec] = {
            executor.submit(_run_single_module, spec, intake): spec
            for spec in MODULE_SPECS
        }
        for future in as_completed(futures):
            spec = futures[future]
            output, status = future.result()
            outputs[spec.result_field] = output
            statuses[spec.module_id] = status
    return outputs, statuses


def _run_single_module(
    spec: ModuleSpec,
    intake: BPIntake,
) -> tuple[ModuleOutput | None, ModuleGenerationStatus]:
    started_at = perf_counter()
    try:
        output = spec.generator(getattr(intake, spec.intake_field))
    except Exception as exc:  # Preserve other modules when one module fails.
        return None, ModuleGenerationStatus(
            module_id=spec.module_id,
            status="error",
            duration_seconds=perf_counter() - started_at,
            error_message=f"{type(exc).__name__}: {exc}",
        )
    headline, headline_attempts = generate_module_headline(output)
    output.headline = headline
    sub_headline, sub_headline_attempts = generate_module_sub_headline(output)
    output.sub_headline = sub_headline
    return output, ModuleGenerationStatus(
        module_id=spec.module_id,
        status="success",
        duration_seconds=perf_counter() - started_at,
        headline_attempts=headline_attempts,
        sub_headline_attempts=sub_headline_attempts,
    )


def _collect_pending_items(
    outputs: dict[str, ModuleOutput | None],
) -> list[PendingItem]:
    pending_items: list[PendingItem] = []
    for output in outputs.values():
        if output is not None:
            if output.module_id != 0:
                _walk_pending(output.headline, output.module_id, "headline", pending_items)
            if output.module_id in (2, 3, 4, 6):
                _walk_pending(output.sub_headline, output.module_id, "sub_headline", pending_items)
            _walk_pending(output.fields, output.module_id, "", pending_items)
    return pending_items


def _build_contact_output(contact: Any, project_overview: Any) -> ContactOutput:
    # C-class customer facts: copy verbatim and never send to the LLM, exactly
    # like slogan, one_liner, mission, and vision.
    def direct(value: str | None) -> FieldOutput:
        if value is None or not value.strip():
            return FieldOutput("待补充", SourceType.PENDING_CUSTOMER)
        return FieldOutput(value, SourceType.CLIENT_PROVIDED)

    return ContactOutput(
        contact_person=direct(contact.contact_person if contact else None),
        phone=direct(contact.phone if contact else None),
        email=direct(contact.email if contact else None),
        address=direct(contact.address if contact else None),
        website=direct(getattr(project_overview, "website", None)),
    )


def _walk_pending(
    value: Any,
    module_id: int,
    path: str,
    pending_items: list[PendingItem],
) -> None:
    if isinstance(value, FieldOutput):
        if value.source_type is SourceType.PENDING_CUSTOMER:
            pending_items.append(
                PendingItem(
                    module_id=module_id,
                    field_name=path or "field",
                    message=value.message or "待客户补充",
                )
            )
            return
        _walk_pending(value.value, module_id, path, pending_items)
    elif isinstance(value, dict):
        for key, item in value.items():
            _walk_pending(item, module_id, _join_path(path, str(key)), pending_items)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _walk_pending(item, module_id, f"{path}[{index}]", pending_items)


def _collect_degraded_fields(
    outputs: dict[str, ModuleOutput | None],
) -> list[DegradedField]:
    degraded_fields: list[DegradedField] = []
    for output in outputs.values():
        if output is None:
            continue
        for path in _REWRITE_FIELD_PATHS.get(output.module_id, ()):
            for field_name, field_output in _field_outputs_at_path(output.fields, path):
                if field_output.source_type is SourceType.CLIENT_PROVIDED:
                    if (
                        output.module_id == 6
                        and field_name.endswith(".deliverables")
                        and re.search(r"\d", str(field_output.value))
                    ):
                        continue
                    degraded_fields.append(
                        DegradedField(output.module_id, field_name)
                    )
    return degraded_fields


def _field_outputs_at_path(
    value: Any,
    path: tuple[str, ...],
    label: str = "",
) -> list[tuple[str, FieldOutput]]:
    if isinstance(value, FieldOutput):
        if not path:
            return [(label, value)]
        return _field_outputs_at_path(value.value, path, label)
    if not path:
        return []
    part, *rest = path
    if part == "*" and isinstance(value, (list, tuple)):
        return [
            item
            for index, child in enumerate(value)
            for item in _field_outputs_at_path(child, tuple(rest), f"{label}[{index}]")
        ]
    if isinstance(value, dict) and part in value:
        return _field_outputs_at_path(
            value[part],
            tuple(rest),
            _join_path(label, part),
        )
    return []


def _join_path(prefix: str, segment: str) -> str:
    return f"{prefix}.{segment}" if prefix else segment


def _has_text(value: str | None) -> int:
    return int(bool(value and value.strip()))


def _overview_minimum_calls(intake: Any) -> int:
    return _has_text(intake.business_summary)


def _demand_minimum_calls(intake: Any) -> int:
    return _has_text(intake.target_customer) + len(intake.pain_points)


def _product_minimum_calls(intake: Any) -> int:
    return (
        len(intake.solutions)
        + sum(_has_text(value) for value in intake.core_values)
        + _has_text(intake.sales_model)
    )


def _market_minimum_calls(intake: Any) -> int:
    return _has_text(intake.basis)


def _competition_minimum_calls(intake: Any) -> int:
    return sum(_has_text(value) for value in intake.differentiations)


def _traction_minimum_calls(intake: Any) -> int:
    return _has_text(intake.product_status) + _has_text(intake.endorsements)


def _plan_minimum_calls(intake: Any) -> int:
    return sum(
        _has_text(stage.objective)
        + int(bool(stage.deliverables and not re.search(r"\d", stage.deliverables)))
        for stage in intake.roadmap
    )


def _funding_minimum_calls(intake: Any) -> int:
    return sum(_has_text(item.description) for item in intake.use_of_funds)


def _team_minimum_calls(intake: Any) -> int:
    return sum(_has_text(member.background) for member in intake.members)


MODULE_SPECS = [
    ModuleSpec(0, "project_overview", "project_overview", generate_overview_module, _overview_minimum_calls),
    ModuleSpec(1, "demand", "demand", generate_demand_module, _demand_minimum_calls),
    ModuleSpec(2, "product_model", "product_model", generate_product_module, _product_minimum_calls),
    ModuleSpec(3, "market", "market", generate_market_module, _market_minimum_calls),
    ModuleSpec(4, "competition", "competition", generate_competition_module, _competition_minimum_calls),
    ModuleSpec(5, "current_state", "current_state", generate_traction_module, _traction_minimum_calls),
    ModuleSpec(6, "plan", "plan", generate_plan_module, _plan_minimum_calls),
    ModuleSpec(7, "funding", "funding", generate_funding_module, _funding_minimum_calls),
    ModuleSpec(8, "team", "team", generate_team_module, _team_minimum_calls),
]
