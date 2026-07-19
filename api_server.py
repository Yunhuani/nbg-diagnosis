from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from analysis import (
    analyze_business_model,
    analyze_capability,
    analyze_competition,
    analyze_finance,
    analyze_market,
    assemble_fact_base,
    calculate_overall_score,
    run_redline_check,
    synthesize_diagnosis,
)
from finance import calculate_financial_facts

logger = logging.getLogger(__name__)

DIMENSIONS = (
    "market",
    "competition",
    "business_model",
    "capability",
    "finance",
)
MAX_DIMENSION_WORKERS = 3


class MarketBrief(BaseModel):
    market: list[dict[str, Any]] = Field(default_factory=list)
    competition: list[dict[str, Any]] = Field(default_factory=list)


class DiagnoseRequest(BaseModel):
    diagnosis_intake: dict[str, Any]
    market_brief: MarketBrief | None = None


app = FastAPI(title="NBG Diagnosis API")

_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = Lock()

RETRY_GUARDRAIL = (
    "上一次输出未通过单维红线自检。只填写本维度前缀的 degradation.missing_plus；"
    "reasoning_chain 不得包含 financial_facts.、diagnosis_intake. 或链接等来源路径；"
    "缺失或为 null 的财务字段不得作为 computed evidence 引用。"
)


@app.post("/diagnose")
def create_diagnosis(request: DiagnoseRequest) -> dict[str, str]:
    job_id = str(uuid4())
    source_corpora = {
        "market": list(request.market_brief.market) if request.market_brief else [],
        "competition": (
            list(request.market_brief.competition) if request.market_brief else []
        ),
    }

    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "result": None,
            "error": None,
        }

    Thread(
        target=_run_diagnosis_job,
        args=(job_id, request.diagnosis_intake, source_corpora),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/diagnose/{job_id}")
def get_diagnosis(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_id not found")
        return dict(job)


def _run_diagnosis_job(
    job_id: str,
    diagnosis_intake: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> None:
    _update_job(job_id, status="running")
    try:
        result = _run_diagnosis(diagnosis_intake, source_corpora)
    except Exception as exc:
        _update_job(job_id, status="error", result=None, error=str(exc))
        return

    _update_job(job_id, status="done", result=result, error=None)


def _run_diagnosis(
    diagnosis_intake: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    financial_facts = _calculate_financial_facts(diagnosis_intake)
    fact_base = assemble_fact_base(diagnosis_intake, financial_facts)

    with ThreadPoolExecutor(
        max_workers=MAX_DIMENSION_WORKERS,
        thread_name_prefix="diagnosis-dimension",
    ) as executor:
        futures = {
            dimension: executor.submit(
                _run_dimension_task,
                dimension,
                fact_base,
                source_corpora,
            )
            for dimension in DIMENSIONS
        }
        dimension_outputs = [
            futures[dimension].result()
            for dimension in DIMENSIONS
        ]
    _mark_external_brief_degradation(dimension_outputs, source_corpora)
    _mark_finance_basic_degradation(dimension_outputs, financial_facts)
    data_quality = _build_data_quality(
        dimension_outputs,
        source_corpora,
        financial_facts,
    )

    score_summary = calculate_overall_score(dimension_outputs)
    synthesis_output = _run_synthesis_with_retry(
        dimension_outputs,
        financial_facts=financial_facts,
        source_corpora=source_corpora,
        availability_map=fact_base.get("availability_map", {}),
        diagnosis_intake=diagnosis_intake,
    )

    return {
        "dimension_outputs": dimension_outputs,
        "synthesis_output": synthesis_output,
        "score_summary": score_summary,
        "data_quality": data_quality,
    }


def _run_dimension_task(
    dimension: str,
    fact_base: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    logger.info("Dimension %s started", dimension)
    try:
        output = _run_dimension_with_retry(dimension, fact_base, source_corpora)
    except Exception:
        logger.exception("Dimension %s failed", dimension)
        raise
    logger.info("Dimension %s completed", dimension)
    return output


def _run_dimension_with_retry(
    dimension: str,
    fact_base: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
    *,
    max_attempts: int = 3,
) -> dict[str, Any]:
    current_fact_base = fact_base
    last_failure: Any = None
    for attempt in range(1, max_attempts + 1):
        try:
            output = _run_dimension(dimension, current_fact_base, source_corpora)
        except ValueError as exc:
            last_failure = exc
            if attempt == max_attempts:
                logger.error(
                    "Dimension %s failed after %s attempts: %s",
                    dimension,
                    max_attempts,
                    exc,
                )
                raise RuntimeError(
                    f"dimension {dimension} failed after {max_attempts} attempts: {exc}"
                ) from exc
            logger.warning(
                "Dimension %s retry %s/%s after output validation error: %s",
                dimension,
                attempt,
                max_attempts,
                exc,
            )
            current_fact_base = _fact_base_with_retry_failure(
                fact_base,
                [{"check": "output_validation", "reason": str(exc)}],
            )
            continue

        report = run_redline_check(
            [output],
            None,
            financial_facts=fact_base["financial_facts"],
            source_corpora=source_corpora,
            availability_map=fact_base.get("availability_map", {}),
            diagnosis_intake=fact_base["diagnosis_intake"],
            scope="single",
        )
        if report["passed"]:
            return output
        last_failure = report["failures"]
        if attempt == max_attempts:
            logger.error(
                "Dimension %s failed redline after %s attempts: %s",
                dimension,
                max_attempts,
                report["failures"],
            )
            raise RuntimeError(
                f"dimension {dimension} failed after {max_attempts} attempts: "
                f"{report['failures']}"
            )
        logger.warning(
            "Dimension %s retry %s/%s after redline failure: %s",
            dimension,
            attempt,
            max_attempts,
            report["failures"],
        )
        current_fact_base = _fact_base_with_retry_failure(
            fact_base,
            report["failures"],
        )

    raise RuntimeError(
        f"dimension {dimension} failed after {max_attempts} attempts: {last_failure}"
    )


def _fact_base_with_retry_failure(
    fact_base: dict[str, Any],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    retry_fact_base = deepcopy(fact_base)
    retry_fact_base["llm_retry_instruction"] = {
        "message": RETRY_GUARDRAIL,
        "previous_redline_failures": failures,
    }
    return retry_fact_base


def _run_synthesis_with_retry(
    dimension_outputs: list[dict[str, Any]],
    *,
    financial_facts: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
    availability_map: dict[str, Any],
    diagnosis_intake: dict[str, Any],
    max_attempts: int = 3,
) -> dict[str, Any]:
    last_failure: Any = None
    for attempt in range(1, max_attempts + 1):
        try:
            synthesis_output = synthesize_diagnosis(dimension_outputs)
        except ValueError as exc:
            last_failure = exc
            if attempt == max_attempts:
                logger.error(
                    "Synthesis failed after %s attempts: %s",
                    max_attempts,
                    exc,
                )
                raise RuntimeError(
                    f"synthesis failed after {max_attempts} attempts: {exc}"
                ) from exc
            logger.warning(
                "Synthesis retry %s/%s after output validation error: %s",
                attempt,
                max_attempts,
                exc,
            )
            continue

        report = run_redline_check(
            dimension_outputs,
            synthesis_output,
            financial_facts=financial_facts,
            source_corpora=source_corpora,
            availability_map=availability_map,
            diagnosis_intake=diagnosis_intake,
            scope="full",
        )
        if report["passed"]:
            return synthesis_output

        last_failure = report["failures"]
        if attempt == max_attempts:
            logger.error(
                "Synthesis failed redline after %s attempts: %s",
                max_attempts,
                report["failures"],
            )
            raise RuntimeError(
                f"synthesis failed after {max_attempts} attempts: "
                f"{report['failures']}"
            )
        logger.warning(
            "Synthesis retry %s/%s after redline failure: %s",
            attempt,
            max_attempts,
            report["failures"],
        )

    raise RuntimeError(
        f"synthesis failed after {max_attempts} attempts: {last_failure}"
    )


def _run_dimension(
    dimension: str,
    fact_base: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    if dimension == "market":
        return analyze_market(fact_base, source_corpora["market"])
    if dimension == "competition":
        return analyze_competition(fact_base, source_corpora["competition"])
    analyzers = {
        "business_model": analyze_business_model,
        "capability": analyze_capability,
        "finance": analyze_finance,
    }
    return analyzers[dimension](fact_base)


def _calculate_financial_facts(diagnosis_intake: dict[str, Any]) -> dict[str, Any]:
    finance_basic = diagnosis_intake.get("finance_basic") or {}
    finance_plus = diagnosis_intake.get("finance_plus") or {}
    ar = finance_plus.get("ar") or {}

    cash = _optional_number(finance_basic, "cash")
    monthly_fixed = _optional_number(finance_basic, "monthly_fixed")
    if monthly_fixed is not None and monthly_fixed == 0:
        raise ValueError("diagnosis_intake.finance_basic.monthly_fixed must not be zero")

    return calculate_financial_facts(
        product_lines=finance_plus.get("product_lines"),
        customers=finance_plus.get("customers"),
        cash=cash,
        monthly_fixed=monthly_fixed,
        ar_balance=ar.get("balance"),
        ar_days=ar.get("days"),
    )


def _optional_number(data: dict[str, Any], field: str) -> float | None:
    value = data.get(field)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"diagnosis_intake.finance_basic.{field} must be a number"
        ) from exc


def _mark_finance_basic_degradation(
    dimension_outputs: list[dict[str, Any]],
    financial_facts: dict[str, Any],
) -> None:
    if financial_facts.get("cash_runway_months") is not None:
        return

    message = "现金安全边际已按当前经营信息做结构性判断；若补充账上现金与每月固定支出，可进一步量化现金跑道和安全垫。"
    for output in dimension_outputs:
        if output.get("dimension") != "finance":
            continue
        degradation = output["degradation"]
        degradation["degraded"] = True
        existing_hook = degradation["upgrade_hook"].strip()
        degradation["upgrade_hook"] = " ".join(
            part for part in (existing_hook, message) if part
        )


DATA_QUALITY_SUMMARIES = {
    "full": "当前五个维度均有足够信息支撑判断；如需进一步精细化，可在方案深化阶段补充更细颗粒度经营数据。",
    "partial": "当前报告已形成五维判断，部分维度可在方案深化阶段结合补充数据进一步量化。",
    "limited": "当前报告以结构性判断为主，部分维度可在方案深化阶段结合经营与市场数据进一步量化。",
}


def _build_data_quality(
    dimension_outputs: list[dict[str, Any]],
    source_corpora: dict[str, list[dict[str, Any]]],
    financial_facts: dict[str, Any],
) -> dict[str, Any]:
    outputs_by_dimension = {
        output.get("dimension"): output
        for output in dimension_outputs
    }
    dimensions: list[dict[str, Any]] = []

    for dimension in DIMENSIONS:
        output = outputs_by_dimension.get(dimension, {})
        degradation = output.get("degradation") or {}
        degraded = degradation.get("degraded") is True
        missing_plus = degradation.get("missing_plus")
        upgrade_hook = degradation.get("upgrade_hook")

        if dimension in {"market", "competition"} and not source_corpora.get(dimension):
            level = "limited"
        elif dimension == "finance" and (
            financial_facts.get("tier") == "basic_only"
            or financial_facts.get("cash_runway_months") is None
        ):
            level = "limited"
        elif degraded:
            level = "partial"
        else:
            level = "full"

        dimensions.append(
            {
                "dimension": dimension,
                "level": level,
                "missing_plus": list(missing_plus) if isinstance(missing_plus, list) else [],
                "upgrade_hook": upgrade_hook if isinstance(upgrade_hook, str) else "",
            }
        )

    levels = [item["level"] for item in dimensions]
    if "limited" in levels:
        overall_level = "limited"
    elif "partial" in levels:
        overall_level = "partial"
    else:
        overall_level = "full"

    return {
        "overall_level": overall_level,
        "summary": DATA_QUALITY_SUMMARIES[overall_level],
        "dimensions": dimensions,
    }


def _mark_external_brief_degradation(
    dimension_outputs: list[dict[str, Any]],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> None:
    messages = {
        "market": "市场机会判断已按当前经营信息形成结构性结论；若进入方案深化阶段，可结合目标市场订单、渠道反馈与价格带数据进一步量化窗口规模。",
        "competition": "竞争判断已按当前对手描述与客户价值维度形成结构性结论；若进入方案深化阶段，可结合标杆企业清单、赢单/流失记录进一步量化差异。",
    }
    for output in dimension_outputs:
        dimension = output.get("dimension")
        if dimension not in messages or source_corpora[dimension]:
            continue
        degradation = output["degradation"]
        degradation["degraded"] = True
        existing_hook = degradation["upgrade_hook"].strip()
        degradation["upgrade_hook"] = " ".join(
            part for part in (existing_hook, messages[dimension]) if part
        )


def _update_job(job_id: str, **changes: Any) -> None:
    with _jobs_lock:
        _jobs[job_id].update(changes)
