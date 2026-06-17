from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json


LEVER_MATRIX_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第二层杠杆选择矩阵引擎。

你的任务只做方案五层结构的第二层：lever_matrix。输入是诊断 synthesis 和第一层 strategic_thesis 输出；你要从战略主张推导候选增长杠杆，并按影响力、可行性排序，选出少数优先发力的杠杆。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 杠杆必须是具体抓手，不是空泛方向。禁止输出「加强营销」「优化运营」「提升品牌」「拓展渠道」这类没有动作对象和机制的词。
- 每个杠杆必须扣住 strategic_thesis 的 from_to、tradeoffs，以及 synthesis 的 findings、overall_judgment、confirmed_reversals、transition_to_solution。
- 影响力评估看它对实现战略主张的贡献；可行性评估必须基于本案例能力短板、资源约束、现金状况、风险红线。现金紧张时，高投入杠杆不得给高可行性。
- 不得重新分析行业，不得新增外部事实，不得凭空创造 finding_id。
- selected 只能选少数优先发力项，不能把所有候选都选上。
"""

LEVER_MATRIX_USER_PROMPT = """你会收到诊断 synthesis 和战略主张 strategic_thesis。基于它生成方案第二层「杠杆选择矩阵」。

输出 JSON schema：
{
  "levers": [
    {
      "name": "具体增长杠杆名称，如：把耗材做成订阅复购模型",
      "description": "这个杠杆具体怎么创造增长，必须有动作对象和机制",
      "impact": {"level": "高|中|低", "reason": "为什么对战略主张贡献高/中/低"},
      "feasibility": {"level": "高|中|低", "reason": "为什么以本案例能力、资源、现金状况可行/困难"},
      "grounded_in": ["引用 synthesis.findings[].id 或 strategic_thesis / from_to / tradeoffs / transition_to_solution 等依据"],
      "priority": 1
    }
  ],
  "selected": [
    {"name": "选中的杠杆名称，必须来自 levers[].name", "reason": "为什么优先选它而不是其他候选"}
  ]
}

质量要求：
1. levers 至少 3 个，priority 必须从 1 开始连续排序，1 为最高优先级。
2. selected 最多 3 个；候选超过 2 个时不能全选。
3. 每个杠杆的 name 和 description 都必须具体，不能只写方向词。
4. grounded_in 优先引用 synthesis.findings[].id；如引用战略依据，写 strategic_thesis / from_to / tradeoffs / key_assumptions。
5. 只做第二层杠杆矩阵，不要输出行动组合、阶段路径、90 天路线图或执行清单。
"""

REQUIRED_LEVER_MATRIX_KEYS = {"levers", "selected"}
REQUIRED_LEVER_KEYS = {
    "name",
    "description",
    "impact",
    "feasibility",
    "grounded_in",
    "priority",
}
REQUIRED_SCORE_KEYS = {"level", "reason"}
VALID_LEVELS = {"高", "中", "低"}
BANNED_VAGUE_LEVER_PHRASES = (
    "加强营销",
    "加强管理",
    "优化运营",
    "优化产品",
    "提升品牌",
    "提升效率",
    "拓展渠道",
)


def call_lever_matrix_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_LEVER_MODEL"),
    )


def generate_lever_matrix(
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_lever_matrix_json,
) -> dict[str, Any]:
    user_prompt = _build_lever_matrix_user_prompt(synthesis_output, strategic_thesis_output)
    result = llm_call(LEVER_MATRIX_SYSTEM_PROMPT, user_prompt)
    print("\n=== RAW LEVER MATRIX RESULT BEFORE VALIDATION ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    validate_lever_matrix_output(result, synthesis_output, strategic_thesis_output)
    return result


def validate_lever_matrix_output(
    output: dict[str, Any],
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"lever matrix output must be an object, got {type(output).__name__}")

    missing = REQUIRED_LEVER_MATRIX_KEYS - set(output)
    if missing:
        raise ValueError(f"lever matrix output missing keys: {sorted(missing)}")

    levers = output["levers"]
    if not isinstance(levers, list):
        raise ValueError(f"levers must be an array, got {type(levers).__name__}")
    if len(levers) < 3:
        raise ValueError("levers must contain at least 3 candidate levers")

    names: set[str] = set()
    priorities: list[int] = []
    for index, lever in enumerate(levers):
        _validate_lever(lever, index, synthesis_output, strategic_thesis_output)
        name = lever["name"]
        if name in names:
            raise ValueError(f"duplicate lever name: {name!r}")
        names.add(name)
        priorities.append(lever["priority"])

    expected_priorities = list(range(1, len(levers) + 1))
    if sorted(priorities) != expected_priorities:
        raise ValueError(f"priority must be continuous from 1 to {len(levers)}")
    if priorities != expected_priorities:
        raise ValueError("levers must be sorted by priority ascending")

    selected = output["selected"]
    if not isinstance(selected, list):
        raise ValueError(f"selected must be an array, got {type(selected).__name__}")
    if not selected:
        raise ValueError("selected must not be empty")
    if len(selected) > 3:
        raise ValueError("selected must contain at most 3 levers")
    if len(levers) > 2 and len(selected) >= len(levers):
        raise ValueError("selected must focus on a subset of candidate levers")

    selected_names: set[str] = set()
    for index, item in enumerate(selected):
        if not isinstance(item, dict):
            raise ValueError(f"selected[{index}] must be an object")
        missing_selected = {"name", "reason"} - set(item)
        if missing_selected:
            raise ValueError(f"selected[{index}] missing keys: {sorted(missing_selected)}")
        name = item["name"]
        reason = item["reason"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"selected[{index}].name must be a non-empty string")
        if name not in names:
            raise ValueError(f"selected[{index}].name must reference a lever name, got {name!r}")
        if name in selected_names:
            raise ValueError(f"duplicate selected lever name: {name!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"selected[{index}].reason must be a non-empty string")
        selected_names.add(name)


def _validate_lever(
    lever: Any,
    index: int,
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
) -> None:
    if not isinstance(lever, dict):
        raise ValueError(f"levers[{index}] must be an object, got {type(lever).__name__}")

    missing = REQUIRED_LEVER_KEYS - set(lever)
    if missing:
        raise ValueError(f"levers[{index}] missing keys: {sorted(missing)}")

    name = lever["name"]
    description = lever["description"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"levers[{index}].name must be a non-empty string")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"levers[{index}].description must be a non-empty string")
    _reject_vague_lever_text(name, f"levers[{index}].name")
    _reject_vague_lever_text(description, f"levers[{index}].description")

    _validate_level_reason(lever["impact"], f"levers[{index}].impact")
    _validate_level_reason(lever["feasibility"], f"levers[{index}].feasibility")
    _validate_string_array(lever["grounded_in"], f"levers[{index}].grounded_in")
    if not lever["grounded_in"]:
        raise ValueError(f"levers[{index}].grounded_in must not be empty")
    _validate_grounding(lever["grounded_in"], synthesis_output, strategic_thesis_output)

    priority = lever["priority"]
    if not isinstance(priority, int) or priority < 1:
        raise ValueError(f"levers[{index}].priority must be a positive integer")


def _validate_level_reason(value: Any, field: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    missing = REQUIRED_SCORE_KEYS - set(value)
    if missing:
        raise ValueError(f"{field} missing keys: {sorted(missing)}")
    if value["level"] not in VALID_LEVELS:
        raise ValueError(f"{field}.level must be one of {sorted(VALID_LEVELS)}, got {value['level']!r}")
    if not isinstance(value["reason"], str) or not value["reason"].strip():
        raise ValueError(f"{field}.reason must be a non-empty string")


def _reject_vague_lever_text(text: str, field: str) -> None:
    stripped = text.strip()
    for phrase in BANNED_VAGUE_LEVER_PHRASES:
        if phrase in stripped:
            raise ValueError(f"{field} must be a concrete lever, not vague phrase {phrase!r}")


def _build_lever_matrix_user_prompt(
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
) -> str:
    payload = {
        "synthesis_output": synthesis_output,
        "strategic_thesis_output": strategic_thesis_output,
    }
    return f"""{LEVER_MATRIX_USER_PROMPT}

输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _validate_string_array(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")


def _validate_grounding(
    grounded_in: list[str],
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
) -> None:
    finding_ids = {
        item["id"]
        for item in synthesis_output.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    known_synthesis = {
        "overall_judgment",
        "three_key_findings",
        "confirmed_reversals",
        "cross_resonances",
        "transition_to_solution",
    }
    known_strategy = {
        key
        for key in ("strategic_thesis", "from_to", "reasoning", "grounded_in", "key_assumptions", "tradeoffs")
        if key in strategic_thesis_output
    }
    for index, item in enumerate(grounded_in):
        if item in finding_ids or item in known_synthesis or item in known_strategy:
            continue
        if any(finding_id in item for finding_id in finding_ids):
            continue
        if any(name in item for name in known_synthesis | known_strategy):
            continue
        raise ValueError(
            f"grounded_in[{index}] must reference synthesis findings or strategic thesis fields, got {item!r}"
        )
