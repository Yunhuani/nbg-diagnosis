from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json


STRATEGIC_THESIS_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第一层战略主张引擎。

你的任务只做方案五层结构的第一层：strategic_thesis。不要输出增长杠杆、行动组合、阶段路径、90天路线图或任何执行清单。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 战略主张必须是一句话方向性抉择，必须是「从X转向Y」结构。
- 主张必须有取舍：写清做什么、不做什么，不能全都要。
- 主张必须从诊断 synthesis 推导，直接回应 three_key_findings、overall_judgment、各维 core_judgment、confirmed_reversals、transition_to_solution。
- 不得重新分析行业，不得新增外部事实，不得凭空创造 finding_id。
- 不得用「加强、优化、提升」这类无具体指向的空泛动词作为主张。
- 如果战略成立依赖 confirmed_reversals 中 status=needs_human_falsifier_check 的反转，必须写入 key_assumptions，交人工判断。
"""

STRATEGIC_THESIS_USER_PROMPT = """你会收到诊断阶段完整输出。基于它生成方案第一层「战略主张」。

输出 JSON schema：
{
  "strategic_thesis": "一句话主张，必须是从X转向Y",
  "from_to": {
    "from": "明确放弃或收缩什么",
    "to": "明确转向什么"
  },
  "reasoning": [
    "依据链1：为什么这个方向直接回应诊断结论",
    "依据链2：为什么不是其他方向",
    "依据链3：这个选择如何处理核心矛盾"
  ],
  "grounded_in": [
    "引用 synthesis.findings[].id、three_key_findings 的 finding_id，或 overall_judgment / transition_to_solution / confirmed_reversals 等结论名"
  ],
  "key_assumptions": [
    "战略成立依赖的前提，尤其是待人工核验的反转"
  ],
  "tradeoffs": [
    "明确放弃了什么，不做什么"
  ]
}

质量要求：
1. strategic_thesis 只能一句话，且包含「从」和「转向」。
2. reasoning 必须说明：为什么是这个方向、放弃了哪些其他方向、依据诊断里哪几条。
3. grounded_in 优先引用 synthesis.findings[].id；如引用总体结论，写结论字段名。
4. tradeoffs 不能空泛，必须是战略选择里真实放弃的方向。
5. 只做第一层战略主张，不要输出后续层级。
"""

REQUIRED_THESIS_KEYS = {
    "strategic_thesis",
    "from_to",
    "reasoning",
    "grounded_in",
    "key_assumptions",
    "tradeoffs",
}
BANNED_THESIS_WORDS = ("加强", "优化", "提升")


def call_strategic_thesis_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_THESIS_MODEL"),
    )


def generate_strategic_thesis(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]] | None = None,
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_strategic_thesis_json,
) -> dict[str, Any]:
    user_prompt = _build_strategic_thesis_user_prompt(synthesis_output, dimension_outputs)
    result = llm_call(STRATEGIC_THESIS_SYSTEM_PROMPT, user_prompt)
    validate_strategic_thesis_output(result, synthesis_output)
    return result


def validate_strategic_thesis_output(output: dict[str, Any], synthesis_output: dict[str, Any]) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"strategic thesis output must be an object, got {type(output).__name__}")

    missing = REQUIRED_THESIS_KEYS - set(output)
    if missing:
        raise ValueError(f"strategic thesis output missing keys: {sorted(missing)}")

    thesis = output["strategic_thesis"]
    if not isinstance(thesis, str) or not thesis.strip():
        raise ValueError("strategic_thesis must be a non-empty string")
    if "\n" in thesis or "\r" in thesis:
        raise ValueError("strategic_thesis must be a single sentence on one line")
    if "从" not in thesis or "转向" not in thesis:
        raise ValueError("strategic_thesis must use a from-to choice: 从X转向Y")
    for word in BANNED_THESIS_WORDS:
        if word in thesis:
            raise ValueError(f"strategic_thesis must not use vague verb {word!r}")

    from_to = output["from_to"]
    if not isinstance(from_to, dict):
        raise ValueError("from_to must be an object")
    for key in ("from", "to"):
        value = from_to.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"from_to.{key} must be a non-empty string")

    for key in ("reasoning", "grounded_in", "key_assumptions", "tradeoffs"):
        _validate_string_array(output[key], key)

    if not output["reasoning"]:
        raise ValueError("reasoning must not be empty")
    if not output["grounded_in"]:
        raise ValueError("grounded_in must not be empty")
    if not output["tradeoffs"]:
        raise ValueError("tradeoffs must not be empty")

    _validate_grounding(output["grounded_in"], synthesis_output)


def _build_strategic_thesis_user_prompt(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]] | None,
) -> str:
    payload: dict[str, Any] = {"synthesis_output": synthesis_output}
    if dimension_outputs is not None:
        payload["dimension_outputs"] = dimension_outputs
    return f"""{STRATEGIC_THESIS_USER_PROMPT}

诊断输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _validate_string_array(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")


def _validate_grounding(grounded_in: list[str], synthesis_output: dict[str, Any]) -> None:
    finding_ids = {
        item["id"]
        for item in synthesis_output.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    known_conclusions = {
        "overall_judgment",
        "three_key_findings",
        "confirmed_reversals",
        "cross_resonances",
        "transition_to_solution",
    }
    for index, item in enumerate(grounded_in):
        if item in known_conclusions or item in finding_ids:
            continue
        if any(finding_id in item for finding_id in finding_ids):
            continue
        if any(name in item for name in known_conclusions):
            continue
        raise ValueError(
            f"grounded_in[{index}] must reference a synthesis finding_id or known conclusion field, got {item!r}"
        )
