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
FINANCIAL_FACTS_TOP_LEVEL_FIELDS = {
    "tier",
    "product_lines",
    "customer_concentration",
    "cash_runway_months",
    "ar",
}
COMPUTED_SOURCE_STYLE = (
    "Computed evidence source must be financial_facts paths using dot notation "
    "and optional [n] list indexes; multiple paths are comma-separated. "
    "For robustness, shorthand fields after a comma inherit the previous parent path."
)
EXTERNAL_OPPORTUNITY_TERMS = (
    "中东",
    "GCC",
    "北美",
    "欧洲",
    "欧美",
    "美国",
    "海外",
    "酒店",
    "会所",
    "SPA",
    "高端工程",
    "无框",
    "有框",
    "高端饰面",
    "淋浴",
    "卫浴",
    "五金",
)


def run_redline_check(
    dimension_outputs: list[dict[str, Any]],
    synthesis_output: dict[str, Any] | None,
    *,
    financial_facts: dict[str, Any],
    source_corpora: dict[str, list[dict[str, Any]]],
    availability_map: dict[str, Any] | None = None,
    diagnosis_intake: dict[str, Any] | None = None,
    scope: str = "full",
) -> dict[str, Any]:
    if scope not in {"single", "full"}:
        raise ValueError(f"scope must be 'single' or 'full', got {scope!r}")

    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    score_check = None if scope == "single" else _score_check_summary(dimension_outputs, synthesis_output)
    _check_brainmade_external_numbers(dimension_outputs, source_corpora, failures)
    _check_bare_numbers(dimension_outputs, failures)
    _check_evidence_source_type_mapping(dimension_outputs, failures)
    _check_computed_financial_consistency(
        dimension_outputs,
        financial_facts,
        failures,
        warnings,
    )
    _check_product_loss_claim_consistency(dimension_outputs, financial_facts, failures)
    _check_degradation_missing_plus(dimension_outputs, availability_map, failures)
    _check_reasoning_chain_source_leaks(dimension_outputs, failures)
    _check_unsupported_external_opportunities(dimension_outputs, source_corpora, diagnosis_intake, failures)
    if scope == "full" and synthesis_output is not None:
        _check_synthesis_headline(synthesis_output, failures)
        _check_reversal_integrity(synthesis_output, failures)
        _check_finding_references(synthesis_output, failures)
        _check_key_finding_counts(synthesis_output, failures)
        _check_overall_score(dimension_outputs, synthesis_output, failures)
    return {
        "passed": not failures,
        "score_check": score_check,
        "failures": failures,
        "warnings": warnings,
    }


def _add_failure(failures: list[dict[str, str]], check: str, path: str, reason: str) -> None:
    failures.append({"check": check, "path": path, "reason": reason})


def _add_warning(warnings: list[dict[str, str]], check: str, path: str, reason: str) -> None:
    warnings.append({"check": check, "path": path, "reason": reason})


def _normalize_source_url(source: Any) -> str:
    text = str(source or "").strip()
    markdown_link = re.fullmatch(r"\[[^\]]+\]\(([^)]+)\)", text)
    if markdown_link:
        text = markdown_link.group(1).strip()
    text = re.sub(r"^https?://", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^www\.", "", text, flags=re.IGNORECASE)
    return text.rstrip("/")


def _split_external_sources(source: Any) -> list[str]:
    text = str(source or "").strip()
    if not text:
        return []
    return [
        normalized
        for part in re.split(r"[,;]", text)
        if (normalized := _normalize_source_url(part))
    ]


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
            _normalize_source_url(item.get("source_url"))
            for item in source_corpora.get(dimension, [])
            if item.get("source_url")
        }
        for item in source_corpora.get(dimension, []):
            allowed_sources.update(_split_external_sources(item.get("source_url")))
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            source_type = evidence.get("source_type")
            if source_type not in EXTERNAL_SOURCE_TYPES:
                continue
            source = evidence.get("source")
            source_text = str(source or "").strip()
            if source_text.startswith(("financial_facts.", "diagnosis_intake.")):
                continue
            for field in ("value", "benchmark"):
                value = str(evidence.get(field, ""))
                if not _contains_number(value):
                    continue
                normalized_sources = _split_external_sources(source)
                if not normalized_sources or any(item not in allowed_sources for item in normalized_sources):
                    field_label = " benchmark" if field == "benchmark" else ""
                    _add_failure(
                        failures,
                        "brainmade_external_number",
                        f"dimensions[{dim_index}].evidence[{evidence_index}].source",
                        f"external numeric evidence{field_label} source {source!r} is not in {dimension} source_corpus",
                    )


def _check_bare_numbers(
    dimension_outputs: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            for field in ("value", "benchmark"):
                value = str(evidence.get(field, ""))
                if not _contains_number(value):
                    continue
                source_type = evidence.get("source_type")
                if source_type not in VALID_SOURCE_TYPES:
                    _add_failure(
                        failures,
                        "bare_number",
                        f"dimensions[{dim_index}].evidence[{evidence_index}].source_type",
                        (
                            f"numeric evidence {field} {value!r} has invalid or "
                            f"missing source_type {source_type!r}"
                        ),
                    )


def _check_evidence_source_type_mapping(
    dimension_outputs: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        for evidence_index, evidence in enumerate(dim.get("evidence", [])):
            source_type = evidence.get("source_type")
            source = str(evidence.get("source", ""))
            if source.startswith("financial_facts.") and source_type != "computed":
                _add_failure(
                    failures,
                    "evidence_source_type_mapping",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source_type",
                    (
                        "financial_facts evidence must be marked computed, "
                        f"got {source_type!r}"
                    ),
                )
            if source_type == "computed" and not source.startswith("financial_facts"):
                _add_failure(
                    failures,
                    "evidence_source_type_mapping",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source_type",
                    f"computed evidence must point to financial_facts, got source {source!r}",
                )
            if source.startswith("diagnosis_intake.") and source_type != "client_provided":
                _add_failure(
                    failures,
                    "evidence_source_type_mapping",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source_type",
                    (
                        "diagnosis_intake evidence must be marked client_provided, "
                        f"got {source_type!r}"
                    ),
                )


def _check_computed_financial_consistency(
    dimension_outputs: list[dict[str, Any]],
    financial_facts: dict[str, Any],
    failures: list[dict[str, str]],
    warnings: list[dict[str, str]],
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
                evidence["source_type"] = "inferred"
                _add_warning(
                    warnings,
                    "computed_financial_consistency",
                    f"dimensions[{dim_index}].evidence[{evidence_index}].source",
                    (
                        f"computed evidence source {source!r} does not resolve inside "
                        "financial_facts; source_type downgraded to inferred for manual review"
                    ),
                )
                continue

            direct_values = _direct_numeric_values_for_source(financial_facts, source)
            if direct_values is None:
                continue

            for field in ("value", "benchmark"):
                mentions = _extract_numeric_mentions(str(evidence.get(field, "")))
                for mention in mentions:
                    if not any(_matches_financial_value(mention, value) for value in direct_values):
                        _add_failure(
                            failures,
                            "computed_financial_consistency",
                            f"dimensions[{dim_index}].evidence[{evidence_index}].{field}",
                            (
                                f"computed financial number {mention['raw']!r} does not match "
                                f"financial_facts values referenced by {source!r}"
                            ),
                        )


def _check_product_loss_claim_consistency(
    dimension_outputs: list[dict[str, Any]],
    financial_facts: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    product_lines = financial_facts.get("product_lines") or []
    profitable_lines = [
        line for line in product_lines
        if line.get("is_loss") is False and str(line.get("name", "")).strip()
    ]
    if not profitable_lines:
        return

    for dim_index, dim in enumerate(dimension_outputs):
        dimension = dim.get("dimension", f"#{dim_index}")
        for path, text in _dimension_claim_texts(dim_index, dim):
            for line in profitable_lines:
                product_name = str(line["name"])
                if _claims_loss_about_product(text, product_name):
                    _add_failure(
                        failures,
                        "product_loss_consistency",
                        path,
                        (
                            f"{dimension} claims product line {product_name!r} is loss-making, "
                            "but financial_facts.product_lines marks is_loss=false"
                        ),
                    )


def _dimension_claim_texts(dim_index: int, dim: dict[str, Any]) -> list[tuple[str, str]]:
    texts: list[tuple[str, str]] = []
    for chain_index, item in enumerate(dim.get("reasoning_chain", [])):
        texts.append((f"dimensions[{dim_index}].reasoning_chain[{chain_index}]", str(item)))
    for evidence_index, evidence in enumerate(dim.get("evidence", [])):
        if not isinstance(evidence, dict):
            continue
        for field in ("claim", "value", "benchmark"):
            texts.append((
                f"dimensions[{dim_index}].evidence[{evidence_index}].{field}",
                str(evidence.get(field, "")),
            ))
    return texts


def _claims_loss(text: str) -> bool:
    negated_loss_terms = ("不是亏损", "并非亏损", "不亏损", "未亏损", "没有亏损", "无亏损", "非亏损")
    if any(term in text for term in negated_loss_terms):
        return False
    loss_terms = ("亏损", "亏钱", "净亏", "年亏", "亏了", "亏掉", "负贡献")
    if any(term in text for term in loss_terms):
        return True
    return "亏" in text


def _claims_loss_about_product(text: str, product_name: str) -> bool:
    if not product_name or product_name not in text or not _claims_loss(text):
        return False

    escaped_name = re.escape(product_name)
    loss_nouns = (
        "亏损产品线",
        "亏损线",
        "亏损产品",
        "亏钱产品",
        "负贡献产品线",
        "负贡献产品",
        "利润黑洞",
        "失血点",
    )
    loss_terms = ("亏损", "亏钱", "净亏", "年亏", "亏了", "亏掉", "负贡献", "利润黑洞", "失血")
    subject_markers = ("是", "为", "作为", "属于", "变成", "成为", "构成", "也在", "仍在", "都在", "都是")

    product_then_loss = (
        rf"{escaped_name}[^。；;，,\n]{{0,12}}"
        rf"(?:{'|'.join(map(re.escape, subject_markers))})?"
        rf"[^。；;，,\n]{{0,8}}(?:{'|'.join(map(re.escape, loss_terms + loss_nouns))})"
    )
    loss_then_product = (
        rf"(?:{'|'.join(map(re.escape, loss_nouns))})"
        rf"[^。；;，,\n]{{0,10}}(?:是|为|包括|包含|来自|落在|集中在)?"
        rf"[^。；;，,\n]{{0,8}}{escaped_name}"
    )
    grouped_subject_loss = (
        rf"{escaped_name}[^。；;，,\n]{{0,20}}"
        rf"(?:都是|均为|均是|都属于|也在|仍在)"
        rf"[^。；;，,\n]{{0,8}}(?:{'|'.join(map(re.escape, loss_terms + loss_nouns))})"
    )
    return any(
        re.search(pattern, text)
        for pattern in (product_then_loss, loss_then_product, grouped_subject_loss)
    )


def _check_degradation_missing_plus(
    dimension_outputs: list[dict[str, Any]],
    availability_map: dict[str, Any] | None,
    failures: list[dict[str, str]],
) -> None:
    if availability_map is None:
        return

    allowed = set(availability_map.get("plus_missing") or [])
    for dim_index, dim in enumerate(dimension_outputs):
        dimension = dim.get("dimension", f"#{dim_index}")
        missing_plus = dim.get("degradation", {}).get("missing_plus", [])
        if not isinstance(missing_plus, list):
            continue
        for item_index, item in enumerate(missing_plus):
            if item not in allowed:
                _add_failure(
                    failures,
                    "degradation_missing_plus",
                    f"dimensions[{dim_index}].degradation.missing_plus[{item_index}]",
                    (
                        f"{dimension} degradation.missing_plus item {item!r} is not in "
                        "availability_map.plus_missing"
                    ),
                )
                continue
            expected_prefix = f"{dimension}."
            if isinstance(dimension, str) and not str(item).startswith(expected_prefix):
                _add_failure(
                    failures,
                    "degradation_missing_plus",
                    f"dimensions[{dim_index}].degradation.missing_plus[{item_index}]",
                    (
                        f"{dimension} degradation.missing_plus item {item!r} belongs to another "
                        f"dimension; expected prefix {expected_prefix!r}"
                    ),
                )


def _check_reasoning_chain_source_leaks(
    dimension_outputs: list[dict[str, Any]],
    failures: list[dict[str, str]],
) -> None:
    leak_markers = ("source_url", "http://", "https://", "financial_facts.", "diagnosis_intake.")
    for dim_index, dim in enumerate(dimension_outputs):
        for chain_index, item in enumerate(dim.get("reasoning_chain", [])):
            text = str(item)
            marker = next((marker for marker in leak_markers if marker in text), None)
            if marker is None:
                continue
            _add_failure(
                failures,
                "reasoning_chain_source_leak",
                f"dimensions[{dim_index}].reasoning_chain[{chain_index}]",
                f"reasoning_chain must not embed source/link/path marker {marker!r}",
            )



def _check_unsupported_external_opportunities(
    dimension_outputs: list[dict[str, Any]],
    source_corpora: dict[str, list[dict[str, Any]]],
    diagnosis_intake: dict[str, Any] | None,
    failures: list[dict[str, str]],
) -> None:
    for dim_index, dim in enumerate(dimension_outputs):
        dimension = dim.get("dimension", f"#{dim_index}")
        if dimension not in {"market", "competition"}:
            continue
        support_text = _external_support_text(source_corpora.get(dimension, []), diagnosis_intake)
        text_fields = [("core_judgment", str(dim.get("core_judgment", "")))]
        text_fields.extend(
            (f"reasoning_chain[{chain_index}]", str(item))
            for chain_index, item in enumerate(dim.get("reasoning_chain", []))
        )
        for field, text in text_fields:
            for term in EXTERNAL_OPPORTUNITY_TERMS:
                if term not in text or term in support_text:
                    continue
                _add_failure(
                    failures,
                    "unsupported_external_opportunity",
                    f"dimensions[{dim_index}].{field}",
                    (
                        f"{dimension} mentions external opportunity/fact term {term!r} "
                        "in core_judgment/reasoning_chain, but this term is absent from source_corpus and diagnosis_intake"
                    ),
                )


def _external_support_text(
    source_corpus: list[dict[str, Any]],
    diagnosis_intake: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    for item in source_corpus:
        for field in ("claim", "value"):
            parts.append(str(item.get(field, "")))
    if diagnosis_intake is not None:
        parts.append(_stringify_nested_text(diagnosis_intake))
    return "\n".join(parts)


def _stringify_nested_text(value: Any) -> str:
    if isinstance(value, dict):
        return "\n".join(_stringify_nested_text(child) for child in value.values())
    if isinstance(value, list):
        return "\n".join(_stringify_nested_text(child) for child in value)
    if value is None:
        return ""
    return str(value)

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


def _check_synthesis_headline(
    synthesis_output: dict[str, Any],
    failures: list[dict[str, str]],
) -> None:
    headline = synthesis_output.get("headline")
    if not isinstance(headline, str):
        _add_failure(
            failures,
            "synthesis_headline",
            "synthesis.headline",
            f"headline must be a string, got {type(headline).__name__}",
        )
        return
    stripped = headline.strip()
    if not stripped:
        _add_failure(
            failures,
            "synthesis_headline",
            "synthesis.headline",
            "headline must be non-empty",
        )
        return
    if "\n" in stripped or "\r" in stripped:
        _add_failure(
            failures,
            "synthesis_headline",
            "synthesis.headline",
            "headline must be a single line",
        )
    if len(stripped) > 30:
        _add_failure(
            failures,
            "synthesis_headline",
            "synthesis.headline",
            f"headline must be 30 characters or fewer, got {len(stripped)}",
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
    synthesis_output: dict[str, Any] | None,
) -> dict[str, Any]:
    expected = calculate_overall_score(dimension_outputs)
    return {
        "dimension_scores": {
            dim.get("dimension", f"#{index}"): dim.get("score", {}).get("value")
            for index, dim in enumerate(dimension_outputs)
        },
        "computed_overall_score": expected["overall_score"],
        "computed_score_label": expected["score_label"],
        "synthesis_overall_score": None if synthesis_output is None else synthesis_output.get("overall_score"),
        "synthesis_score_label": None if synthesis_output is None else synthesis_output.get("score_label"),
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


def _direct_numeric_values_for_source(
    financial_facts: dict[str, Any],
    source: str,
) -> list[float] | None:
    paths = _expand_financial_source_paths(source)
    if len(paths) != 1:
        return None
    target = _resolve_financial_path(financial_facts, paths[0])
    if isinstance(target, bool) or target is None:
        return None
    if isinstance(target, (int, float)):
        return [float(target)]
    if paths[0] == "financial_facts":
        return []
    return None


def _expand_financial_source_paths(source: str) -> list[str]:
    expanded: list[str] = []
    current_parent = ""
    for raw_path in re.split(r"[,;]", source):
        path = raw_path.split("=", 1)[0].strip()
        if not path:
            continue
        if path.startswith("diagnosis_intake."):
            continue
        if path == "financial_facts" or path.startswith("financial_facts."):
            expanded.append(path)
            current_parent = _parent_path(path)
            continue
        first_part = path.split(".", 1)[0].split("[", 1)[0]
        if first_part in FINANCIAL_FACTS_TOP_LEVEL_FIELDS:
            expanded_path = f"financial_facts.{path}"
            expanded.append(expanded_path)
            current_parent = _parent_path(expanded_path)
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
