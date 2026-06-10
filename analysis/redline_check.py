from __future__ import annotations

import re
from typing import Any

from .synthesis import calculate_overall_score


VALID_SOURCE_TYPES = {"computed", "verified", "inferred", "client_provided"}
EXTERNAL_SOURCE_TYPES = {"verified", "inferred"}
REVERSAL_REQUIRED_FIELDS = {
    "naive_reading",
    "reframe",
    "mechanism",
    "falsifier",
}
REFERENCE_FIELDS = {
    "three_key_findings": "finding_id",
    "confirmed_reversals": "finding_id",
}
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z])[-+]?\$?\d+(?:\.\d+)?%?")
NUMERIC_TOLERANCE = 0.05
COMPUTED_SOURCE_STYLE = (
    "Computed evidence source must be financial_facts paths using dot notation "
    "and optional [n] list indexes; multiple paths are comma-separated. "
    "For robustness, shorthand fields after a comma inherit the previous parent path."
)


def run_redline_check(
    dimension_outputs: list[dict[str, Any]],
    synthesis_output: dict[str, Any],
    *,
    financial_facts: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    score_check = _score_check_summary(dimension_outputs, synthesis_output)
    _check_brainmade_external_numbers(dimension_outputs, source_corpora, failures)
    _check_bare_numbers(dimension_outputs, failures)
    _check_computed_financial_consistency(dimension_outputs, financial_facts, failures)
    _check_reversal_integrity(synthesis_output, failures)
    _check_finding_references(synthesis_output, failures)
    _check_key_finding_counts(synthesis_output, failures)
    _check_overall_score(dimension_outputs, synthesis_output, failures)
    return {
        "passed": not failures,
        "score_check": score_check,
        "failures": failures,
    }


def _add_failure(failures: list[dict[str, str]], check: str, path: str, reason: str) -> None:
    failures.append({"check": check, "path": path, "reason": reason})


def _check_brainmade_external_numbers(
    dimension_outputs: list[dict[str, Any]],
    source_corpora: dict[str, list[dict[str, Any]]],
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        dimension = dim.get("dimension", f"#{dim_index}")
        if dimension not in {"market", "competition"}:
            continue
        allowed_sources = {
            item.get("source_url")
            for item in source_corpora.get(dimension, [])
            if item.get("source_url")
        }
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            source_type = evidence.get("source_type")
            if source_type not in EXTERNAL_SOURCE_TYPES:
                continue
            value = str(evidence.get("value", ""))
            if not _contains_number(value):
                continue
            source = evidence.get("source")
            if source not in allowed_sources:
                _add_failure(
                    failures,
                    "brainmade_external_number",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source",
                    f"external numeric evidence source {source!r} is not in {dimension} source_corpus",
                )


def _check_bare_numbers(
    dimension_outputs: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            value = str(evidence.get("value", ""))
            if not _contains_number(value):
                continue
            source_type = evidence.get("source_type")
            if source_type not in VALID_SOURCE_TYPES:
                _add_failure(
                    failures,
                    "bare_number",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source_type",
                    f"numeric evidence value {value!r} has invalid or missing source_type {source_type!r}",
                )


def _check_computed_financial_consistency(
    dimension_outputs: list[dict[str, Any]],
    financial_facts: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            if evidence.get("source_type") != "computed":
                continue
            source = str(evidence.get("source", ""))
            if not source.startswith("financial_facts"):
                continue

            financial_values = _financial_values_for_source(financial_facts, source)
            if financial_values is None:
                _add_failure(
                    failures,
                    "computed_financial_consistency",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source",
                    f"computed evidence source {source!r} does not resolve inside financial_facts",
                )
                continue

            mentions = _extract_numeric_mentions(str(evidence.get("value", "")))
            for mention in mentions:
                if not any(_matches_financial_value(mention, value) for value in financial_values):
                    _add_failure(
                        failures,
                        "computed_financial_consistency",
                        f"dimensions[{dim_index}].evidence[{evidence_index}].value",
                        (
                            f"computed financial number {mention['raw']!r} does not match "
                            f"financial_facts values referenced by {source!r}"
                        ),
                    )


def _check_reversal_integrity(
    synthesis_output: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    for index, reversal in enumerate(synthesis_output.get("confirmed_reversals", [])):
        for field in REVERSAL_REQUIRED_FIELDS:
            if not str(reversal.get(field, "")).strip():
                _add_failure(
                    failures,
                    "reversal_integrity",
                    f"synthesis.confirmed_reversals[{index}].{field}",
                    f"confirmed reversal field {field} must be non-empty",
                )
        if reversal.get("status") == "machine_confirmed":
            _add_failure(
                failures,
                "reversal_integrity",
                f"synthesis.confirmed_reversals[{index}].status",
                "confirmed reversal status must not be machine_confirmed when private-info falsifier checks are required",
            )


def _check_finding_references(
    synthesis_output: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    finding_ids = {
        item.get("id")
        for item in synthesis_output.get("findings", [])
    }
    for section, field in REFERENCE_FIELDS.items():
        for index, item in enumerate(synthesis_output.get(section, [])):
            _check_finding_ref(
                item.get(field),
                finding_ids,
                failures,
                f"synthesis.{section}[{index}].{field}",
            )
    for index, item in enumerate(synthesis_output.get("cross_resonances", [])):
        refs = item.get("finding_ids", [])
        if not isinstance(refs, list):
            _add_failure(
                failures,
                "finding_id_reference",
                f"synthesis.cross_resonances[{index}].finding_ids",
                "finding_ids must be an array",
            )
            continue
        for ref_index, ref in enumerate(refs):
            _check_finding_ref(
                ref,
                finding_ids,
                failures,
                f"synthesis.cross_resonances[{index}].finding_ids[{ref_index}]",
            )


def _check_finding_ref(
    ref: Any,
    finding_ids: set[Any],
    failures: list[dict[str, str]],
    path: str,
) -> None:
    if ref not in finding_ids:
        _add_failure(
            failures,
            "finding_id_reference",
            path,
            f"finding_id {ref!r} does not exist in synthesis.findings",
        )


def _check_key_finding_counts(
    synthesis_output: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    three_key_findings = synthesis_output.get("three_key_findings", [])
    if len(three_key_findings) != 3:
        _add_failure(
            failures,
            "key_finding_count",
            "synthesis.three_key_findings",
            f"three_key_findings must contain exactly 3 items, got {len(three_key_findings)}",
        )
    cross_resonances = synthesis_output.get("cross_resonances", [])
    if len(cross_resonances) < 1:
        _add_failure(
            failures,
            "key_finding_count",
            "synthesis.cross_resonances",
            "cross_resonances must contain at least 1 item",
        )


def _check_overall_score(
    dimension_outputs: list[dict[str, Any]],
    synthesis_output: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    expected = calculate_overall_score(dimension_outputs)
    actual = synthesis_output.get("overall_score")
    if actual != expected["overall_score"]:
        scores = {
            dim.get("dimension", f"#{index}"): dim.get("score", {}).get("value")
            for index, dim in enumerate(dimension_outputs)
        }
        _add_failure(
            failures,
            "overall_score",
            "synthesis.overall_score",
            f"overall_score mismatch: expected {expected['overall_score']}, got {actual}; dimension scores={scores}",
        )


def _score_check_summary(
    dimension_outputs: list[dict[str, Any]],
    synthesis_output: dict[str, Any],
) -> dict[str, Any]:
    expected = calculate_overall_score(dimension_outputs)
    return {
        "dimension_scores": {
            dim.get("dimension", f"#{index}"): dim.get("score", {}).get("value")
            for index, dim in enumerate(dimension_outputs)
        },
        "computed_overall_score": expected["overall_score"],
        "computed_score_label": expected["score_label"],
        "synthesis_overall_score": synthesis_output.get("overall_score"),
        "synthesis_score_label": synthesis_output.get("score_label"),
    }


def _contains_number(value: str) -> bool:
    return bool(_extract_numeric_mentions(value))


def _extract_numeric_mentions(value: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for match in NUMBER_PATTERN.finditer(value):
        raw = match.group(0)
        normalized = raw.strip().lstrip("$")
        is_percent = normalized.endswith("%")
        if is_percent:
            normalized = normalized[:-1]
        mentions.append(
            {
                "raw": raw,
                "value": float(normalized),
                "is_percent": is_percent,
            }
        )
    return mentions


def _financial_values_for_source(
    financial_facts: dict[str, Any],
    source: str,
) -> list[float] | None:
    paths = _expand_financial_source_paths(source)
    if not paths:
        return None

    values: list[float] = []
    for path in paths:
        target = _resolve_financial_path(financial_facts, path)
        if target is None:
            return None
        values.extend(_collect_numeric_values(target))
    return values


def _expand_financial_source_paths(source: str) -> list[str]:
    expanded: list[str] = []
    current_parent = ""
    for raw_path in source.split(","):
        path = raw_path.strip()
        if not path:
            continue
        if path == "financial_facts" or path.startswith("financial_facts."):
            expanded.append(path)
            current_parent = _parent_path(path)
            continue
        if current_parent:
            expanded.append(f"{current_parent}.{path}")
        else:
            expanded.append(path)
    return expanded


def _parent_path(path: str) -> str:
    if "." not in path:
        return path
    return path.rsplit(".", 1)[0]


def _resolve_financial_path(financial_facts: dict[str, Any], path: str) -> Any:
    if path == "financial_facts":
        return financial_facts
    if not path.startswith("financial_facts."):
        return None

    target: Any = financial_facts
    for part in path.removeprefix("financial_facts.").split("."):
        field_match = re.fullmatch(r"([^\[\]]+)(?:\[(\d+)\])?", part)
        if not field_match:
            return None
        field, index_text = field_match.groups()
        if not isinstance(target, dict) or field not in target:
            return None
        target = target[field]
        if index_text is not None:
            if not isinstance(target, list):
                return None
            index = int(index_text)
            if index >= len(target):
                return None
            target = target[index]
    return target


def _collect_numeric_values(value: Any) -> list[float]:
    numbers: list[float] = []

    def walk(child: Any) -> None:
        if isinstance(child, dict):
            for value in child.values():
                walk(value)
        elif isinstance(child, list):
            for value in child:
                walk(value)
        elif isinstance(child, bool) or child is None:
            return
        elif isinstance(child, (int, float)):
            numbers.append(float(child))

    walk(value)
    return numbers


def _matches_financial_value(mention: dict[str, Any], fact_value: float) -> bool:
    candidates = {fact_value, abs(fact_value)}
    if abs(fact_value) <= 1:
        candidates.add(fact_value * 100)
        candidates.add(abs(fact_value) * 100)
    for candidate in candidates:
        if abs(mention["value"] - candidate) <= NUMERIC_TOLERANCE:
            return True
        if round(candidate, 1) == round(mention["value"], 1):
            return True
        if round(candidate) == round(mention["value"]):
            return True
    return False
