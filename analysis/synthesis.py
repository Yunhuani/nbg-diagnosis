from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from .llm_client import call_deepseek_json


SYNTHESIS_SYSTEM_PROMPT = """你是「泽思 NBG 五维诊断综合验证引擎」。你不是在汇总五段文字,而是在做交叉验证、反转复核和全局定调。

铁律:
- 只输出严格 JSON,不要前言、解释或 Markdown。
- overall_score 和 score_label 已由代码算好,是既定事实,不得重算、不得修改。
- findings[] 是 finding_id 的唯一户口。three_key_findings、confirmed_reversals、cross_resonances 只能引用 findings[].id,不得另造 id。
- 交叉呼应只保留真的:同一事实在不同维度含义不同甚至相反。甬辉案例必须检查客户集中度 65% 在财务维为风险、在竞争维为壁垒资产这类呼应。
- 反转必须按四关复核:风险真实、机制具体、可证伪、可决策。剔除无机制/不可证伪/不改决策的反转。
- reversal_candidate.status 必须透传。失效条件依赖私有信息的 needs_human_falsifier_check 不得升级为 machine_confirmed。
- overall_judgment 必须具体点出企业结构性问题,禁止只写“亚健康/需干预”。
- 诊断只给方向,不得给具体方案步骤。
"""

SYNTHESIS_USER_PROMPT = """你会收到五维完整 JSON 数组,以及代码已算好的 overall_score 和 score_label。

任务0 findings 户口:
先把五维里所有可被开方的发现收成 findings[]。来源包括:
- 每维 core_judgment
- 关键 evidence
- 通过复核的 reversal_candidate
每条分配全局稳定 id: F01、F02、F03...。这是唯一 finding_id 来源。

任务1 交叉呼应:
找同一事实在不同维度的不同甚至相反含义。甬辉标杆:客户集中度65%在财务维是风险,在竞争维是被深度绑定的壁垒资产。没有真的呼应就少写,不得硬造。

任务2 反转筛选:
复核所有 reversal_candidate。保留过关反转到 confirmed_reversals,并只用 finding_id 引用 findings[]。status 必须透传,不得擅自升级。

任务3 总体判断与评分:
overall_score 和 score_label 已由代码算好,必须原样输出。overall_judgment 要具体,点出真实结构性问题。
headline 是报告封面和总体判断页使用的动作标题,必须是 overall_judgment 的一句话提炼,不超过30个汉字/字符,不得换行,不得把 overall_judgment 原文整段复制进来。

任务4 三个关键发现:
从 findings[] 里选 2-3 个最有杀伤力的发现,three_key_findings 只能引用 finding_id,不得另造 id。

任务5 一致性自检:
检查五维结论是否矛盾,例如财务紧张但某维暗示大笔投入。有矛盾写入 consistency_flags 留人工审核;没有则空数组。

严格输出这个 JSON schema:
{
  "findings": [
    {"id":"F01", "dimension":"finance", "statement":"...", "type":"judgment|evidence|reversal", "strength":"high|medium|low", "quant_value":"..."}
  ],
  "headline": "30字以内动作标题",
  "overall_judgment": "具体总体判断",
  "overall_score": 5.0,
  "score_label": "健康|亚健康|警告",
  "cross_resonances": [
    {"fact":"客户集中度65%", "finding_ids":["F01","F04"], "dim_a":"finance", "meaning_a":"风险", "dim_b":"competition", "meaning_b":"壁垒资产"}
  ],
  "confirmed_reversals": [
    {"finding_id":"F04", "naive_reading":"...", "reframe":"...", "mechanism":"...", "falsifier":"...", "confidence":0.7, "status":"needs_human_falsifier_check", "depends_on":[]}
  ],
  "three_key_findings": [
    {"finding_id":"F01", "title":"观点结论标题", "why_surprising":"客户为什么想不到"}
  ],
  "consistency_flags": [],
  "transition_to_solution": "最大风险 + 最大机会方向"
}
"""

REQUIRED_SYNTHESIS_KEYS = {
    "findings",
    "headline",
    "overall_judgment",
    "overall_score",
    "score_label",
    "cross_resonances",
    "confirmed_reversals",
    "three_key_findings",
    "consistency_flags",
    "transition_to_solution",
}
VALID_SCORE_LABELS = {"健康", "亚健康", "警告"}
VALID_FINDING_TYPES = {"judgment", "evidence", "reversal"}
VALID_STRENGTHS = {"high", "medium", "low"}


def call_synthesis_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_SYNTHESIS_MODEL"),
    )


def synthesize_diagnosis(
    dimension_outputs: list[dict[str, Any]],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_synthesis_json,
) -> dict[str, Any]:
    score_summary = calculate_overall_score(dimension_outputs)
    user_prompt = _build_synthesis_user_prompt(dimension_outputs, score_summary)
    result = llm_call(SYNTHESIS_SYSTEM_PROMPT, user_prompt)
    validate_synthesis_output(result, score_summary)
    return result


def calculate_overall_score(dimension_outputs: list[dict[str, Any]]) -> dict[str, Any]:
    if len(dimension_outputs) != 5:
        raise ValueError(f"dimension_outputs must contain exactly five dimensions, got {len(dimension_outputs)}")

    scores: list[int] = []
    for index, item in enumerate(dimension_outputs):
        score = item.get("score")
        if not isinstance(score, dict) or "value" not in score:
            raise ValueError(f"dimension_outputs[{index}].score.value is missing")
        value = score["value"]
        if not isinstance(value, int) or not 1 <= value <= 10:
            raise ValueError(f"dimension_outputs[{index}].score.value must be an integer from 1 to 10")
        scores.append(value)

    overall_score = round(sum(scores) / len(scores), 1)
    return {
        "overall_score": overall_score,
        "score_label": _score_label(overall_score),
    }


def validate_synthesis_output(output: dict[str, Any], score_summary: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"synthesis output must be an object, got {type(output).__name__}")

    missing = REQUIRED_SYNTHESIS_KEYS - set(output)
    if missing:
        raise ValueError(f"synthesis output missing keys: {sorted(missing)}")

    if output["overall_score"] != score_summary["overall_score"]:
        raise ValueError(
            f"overall_score must equal computed value {score_summary['overall_score']}, got {output['overall_score']!r}"
        )
    if output["score_label"] != score_summary["score_label"]:
        raise ValueError(
            f"score_label must equal computed value {score_summary['score_label']!r}, got {output['score_label']!r}"
        )
    if output["score_label"] not in VALID_SCORE_LABELS:
        raise ValueError(f"score_label must be one of {sorted(VALID_SCORE_LABELS)}, got {output['score_label']!r}")
    if not isinstance(output["headline"], str):
        raise ValueError(f"headline must be a string, got {type(output['headline']).__name__}")
    headline = output["headline"].strip()
    if not headline:
        raise ValueError("headline must be non-empty")
    if "\n" in headline or "\r" in headline:
        raise ValueError("headline must be a single line")
    if len(headline) > 30:
        raise ValueError(f"headline must be 30 characters or fewer, got {len(headline)}")
    if not isinstance(output["overall_judgment"], str):
        raise ValueError(f"overall_judgment must be a string, got {type(output['overall_judgment']).__name__}")
    if not isinstance(output["transition_to_solution"], str):
        raise ValueError(
            f"transition_to_solution must be a string, got {type(output['transition_to_solution']).__name__}"
        )

    finding_ids = _validate_findings(output["findings"])
    _validate_cross_resonances(output["cross_resonances"], finding_ids)
    _validate_confirmed_reversals(output["confirmed_reversals"], finding_ids)
    _validate_three_key_findings(output["three_key_findings"], finding_ids)
    if not isinstance(output["consistency_flags"], list):
        raise ValueError(
            f"consistency_flags must be an array, got {type(output['consistency_flags']).__name__}"
        )


def _score_label(score: float) -> str:
    if score >= 8:
        return "健康"
    if score >= 5:
        return "亚健康"
    return "警告"


def _build_synthesis_user_prompt(
    dimension_outputs: list[dict[str, Any]],
    score_summary: dict[str, Any],
) -> str:
    payload = {
        "dimension_outputs": dimension_outputs,
        "score_summary": score_summary,
    }
    return f"""{SYNTHESIS_USER_PROMPT}

输入如下:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _validate_findings(findings: Any) -> set[str]:
    if not isinstance(findings, list):
        raise ValueError(f"findings must be an array, got {type(findings).__name__}")

    ids: set[str] = set()
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ValueError(f"findings[{index}] must be an object, got {type(item).__name__}")
        required = {"id", "dimension", "statement", "type", "strength", "quant_value"}
        missing = required - set(item)
        if missing:
            raise ValueError(f"findings[{index}] missing keys: {sorted(missing)}")
        finding_id = item["id"]
        if not isinstance(finding_id, str) or not finding_id.startswith("F"):
            raise ValueError(f"findings[{index}].id must be a string like F01, got {finding_id!r}")
        if finding_id in ids:
            raise ValueError(f"duplicate finding id: {finding_id}")
        if item["type"] not in VALID_FINDING_TYPES:
            raise ValueError(f"findings[{index}].type must be one of {sorted(VALID_FINDING_TYPES)}")
        if item["strength"] not in VALID_STRENGTHS:
            raise ValueError(f"findings[{index}].strength must be one of {sorted(VALID_STRENGTHS)}")
        ids.add(finding_id)
    return ids


def _validate_cross_resonances(cross_resonances: Any, finding_ids: set[str]) -> None:
    if not isinstance(cross_resonances, list):
        raise ValueError(f"cross_resonances must be an array, got {type(cross_resonances).__name__}")
    for index, item in enumerate(cross_resonances):
        if not isinstance(item, dict):
            raise ValueError(f"cross_resonances[{index}] must be an object")
        required = {"fact", "finding_ids", "dim_a", "meaning_a", "dim_b", "meaning_b"}
        missing = required - set(item)
        if missing:
            raise ValueError(f"cross_resonances[{index}] missing keys: {sorted(missing)}")
        _validate_finding_id_refs(f"cross_resonances[{index}].finding_ids", item["finding_ids"], finding_ids)


def _validate_confirmed_reversals(confirmed_reversals: Any, finding_ids: set[str]) -> None:
    if not isinstance(confirmed_reversals, list):
        raise ValueError(f"confirmed_reversals must be an array, got {type(confirmed_reversals).__name__}")
    required = {
        "finding_id",
        "naive_reading",
        "reframe",
        "mechanism",
        "falsifier",
        "confidence",
        "status",
        "depends_on",
    }
    for index, item in enumerate(confirmed_reversals):
        if not isinstance(item, dict):
            raise ValueError(f"confirmed_reversals[{index}] must be an object")
        missing = required - set(item)
        if missing:
            raise ValueError(f"confirmed_reversals[{index}] missing keys: {sorted(missing)}")
        _validate_finding_id_ref(f"confirmed_reversals[{index}].finding_id", item["finding_id"], finding_ids)
        if not isinstance(item["depends_on"], list):
            raise ValueError(f"confirmed_reversals[{index}].depends_on must be an array")


def _validate_three_key_findings(three_key_findings: Any, finding_ids: set[str]) -> None:
    if not isinstance(three_key_findings, list):
        raise ValueError(f"three_key_findings must be an array, got {type(three_key_findings).__name__}")
    for index, item in enumerate(three_key_findings):
        if not isinstance(item, dict):
            raise ValueError(f"three_key_findings[{index}] must be an object")
        required = {"finding_id", "title", "why_surprising"}
        missing = required - set(item)
        if missing:
            raise ValueError(f"three_key_findings[{index}] missing keys: {sorted(missing)}")
        _validate_finding_id_ref(f"three_key_findings[{index}].finding_id", item["finding_id"], finding_ids)


def _validate_finding_id_refs(field: str, refs: Any, finding_ids: set[str]) -> None:
    if not isinstance(refs, list):
        raise ValueError(f"{field} must be an array, got {type(refs).__name__}")
    for ref in refs:
        _validate_finding_id_ref(field, ref, finding_ids)


def _validate_finding_id_ref(field: str, ref: Any, finding_ids: set[str]) -> None:
    if ref not in finding_ids:
        raise ValueError(f"{field} references unknown finding id {ref!r}")
