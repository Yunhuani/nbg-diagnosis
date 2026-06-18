from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json
from .roadmap import (
    _collect_string_values,
    _is_text_reference,
    _json_path_exists,
    _reference_resolves,
)


NINETY_DAY_PLAN_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第五层 90 天行动计划引擎。

你的任务只做方案五层结构的第五层：ninety_day_plan。输入是诊断结论和前四层方案；你要把 roadmap 第一阶段，也就是当前最紧急阶段的行动，细化成未来 90 天内可直接执行的任务。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 只细化 roadmap 第一阶段，不得把第二、第三阶段的后续事项提前塞进 90 天计划。
- 按清晰时间段排列，例如 0-30 天、31-60 天、61-90 天，或更具体的周节点。
- 每项任务必须写清具体对象、执行动作、负责人、完成时间、可指认产出物和可核验衡量标准。禁止只写「加强管理」「提升效率」「优化流程」等空泛任务。
- 每项任务必须用 grounded_in 注明它来自哪条 roadmap 第一阶段行动或真实上游结论；引用格式不限，但目标必须真实存在。
- 不得推翻 financial_facts 的产品线盈亏事实，不得引入本案例不存在的公司、产品、行业、市场、渠道或外部机会。
- 不得重写战略主张、杠杆矩阵、行动地图或三阶段路线图。
"""

NINETY_DAY_PLAN_USER_PROMPT = """你会收到 synthesis、dimension_outputs、strategic_thesis、lever_matrix、action_map 和 roadmap。请把 roadmap 第一阶段的行动细化为 90 天行动计划。

输出 JSON schema：
{
  "plan": [
    {
      "task": "具体可执行任务",
      "owner": "明确负责方向或岗位",
      "timeframe": "0-30天、31-60天、61-90天，或具体周节点",
      "deliverable": "可指认的交付物",
      "metric": "可核验的完成标准",
      "grounded_in": ["真实存在的 roadmap 第一阶段行动或上游结论"]
    }
  ]
}

质量要求：
1. plan 至少包含 1 项任务，并按 timeframe 的执行先后排列。
2. 每项任务必须服务于 roadmap 第一阶段目标和行动，不得引入无关新方向。
3. task、owner、timeframe、deliverable、metric 必须具体且非空。
4. grounded_in 必须指向真实存在的 roadmap 行动、action_map 行动、战略/杠杆字段、finding_id 或 dimension_outputs 结论。
5. 计划覆盖未来 90 天，但不要求三个时间段平均分配任务。
"""

REQUIRED_PLAN_KEYS = {"plan"}
REQUIRED_PLAN_ITEM_KEYS = {
    "task",
    "owner",
    "timeframe",
    "deliverable",
    "metric",
    "grounded_in",
}


def call_ninety_day_plan_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_NINETY_DAY_PLAN_MODEL"),
    )


def generate_ninety_day_plan(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    roadmap_output: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_ninety_day_plan_json,
    max_attempts: int = 3,
) -> dict[str, Any]:
    user_prompt = _build_ninety_day_plan_user_prompt(
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
        action_map_output,
        roadmap_output,
    )
    last_error: ValueError | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = user_prompt
        if last_error is not None:
            prompt += (
                "\n\n上一次输出未通过客观 schema 校验。"
                f"校验错误：{last_error}。"
                "请只修正字段、类型、空值或 grounding 引用错误，重新输出完整 JSON。"
            )

        result = llm_call(NINETY_DAY_PLAN_SYSTEM_PROMPT, prompt)
        print("=== RAW NINETY DAY PLAN RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2))
        try:
            validate_ninety_day_plan_output(
                result,
                synthesis_output,
                dimension_outputs,
                strategic_thesis_output,
                lever_matrix_output,
                action_map_output,
                roadmap_output,
            )
        except ValueError as error:
            last_error = error
            if attempt < max_attempts:
                print(
                    f"=== RETRY NINETY DAY PLAN ATTEMPT "
                    f"{attempt + 1}/{max_attempts}: {error} ==="
                )
                continue
            raise
        return result

    raise RuntimeError("ninety day plan generation exhausted without a result")


def validate_ninety_day_plan_output(
    output: dict[str, Any],
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    roadmap_output: dict[str, Any],
) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"ninety day plan output must be an object, got {type(output).__name__}")

    missing = REQUIRED_PLAN_KEYS - set(output)
    if missing:
        raise ValueError(f"ninety day plan output missing keys: {sorted(missing)}")

    plan = output["plan"]
    if not isinstance(plan, list):
        raise ValueError(f"plan must be an array, got {type(plan).__name__}")
    if not plan:
        raise ValueError("plan must not be empty")

    for index, item in enumerate(plan):
        _validate_plan_item(
            item,
            index,
            synthesis_output,
            dimension_outputs,
            strategic_thesis_output,
            lever_matrix_output,
            action_map_output,
            roadmap_output,
        )


def _validate_plan_item(
    item: Any,
    index: int,
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    roadmap_output: dict[str, Any],
) -> None:
    path = f"plan[{index}]"
    if not isinstance(item, dict):
        raise ValueError(f"{path} must be an object, got {type(item).__name__}")

    missing = REQUIRED_PLAN_ITEM_KEYS - set(item)
    if missing:
        raise ValueError(f"{path} missing keys: {sorted(missing)}")

    for key in ("task", "owner", "timeframe", "deliverable", "metric"):
        value = item[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}.{key} must be a non-empty string")

    grounded_in = item["grounded_in"]
    if not isinstance(grounded_in, list):
        raise ValueError(f"{path}.grounded_in must be an array")
    if not grounded_in:
        raise ValueError(f"{path}.grounded_in must not be empty")
    for reference_index, reference in enumerate(grounded_in):
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(
                f"{path}.grounded_in[{reference_index}] must be a non-empty string"
            )
        if not _plan_reference_resolves(
            reference,
            synthesis_output,
            dimension_outputs,
            strategic_thesis_output,
            lever_matrix_output,
            action_map_output,
            roadmap_output,
        ):
            raise ValueError(
                f"{path}.grounded_in[{reference_index}] must reference a real upstream "
                f"action or conclusion, got {reference!r}"
            )


def _build_ninety_day_plan_user_prompt(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    roadmap_output: dict[str, Any],
) -> str:
    phases = roadmap_output.get("phases", [])
    first_phase = phases[0] if isinstance(phases, list) and phases else None
    payload = {
        "synthesis_output": synthesis_output,
        "dimension_outputs": dimension_outputs,
        "strategic_thesis_output": strategic_thesis_output,
        "lever_matrix_output": lever_matrix_output,
        "action_map_output": action_map_output,
        "roadmap_output": roadmap_output,
        "roadmap_first_phase": first_phase,
    }
    return f"""{NINETY_DAY_PLAN_USER_PROMPT}

输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _plan_reference_resolves(
    reference: str,
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    roadmap_output: dict[str, Any],
) -> bool:
    text = reference.strip()

    roadmap_path = _roadmap_path_reference(text, roadmap_output)
    if roadmap_path is not None:
        return roadmap_path

    roadmap_values = _collect_string_values(roadmap_output)
    if any(_is_text_reference(text, value) for value in roadmap_values):
        return True

    finding_ids = {
        item["id"]
        for item in synthesis_output.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    return _reference_resolves(
        text,
        finding_ids,
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
        action_map_output,
    )


def _roadmap_path_reference(
    reference: str,
    roadmap_output: dict[str, Any],
) -> bool | None:
    roots = ("roadmap", "roadmap_output")
    if reference in roots:
        return True
    for root in roots:
        prefix = f"{root}."
        if reference.startswith(prefix):
            return _json_path_exists(roadmap_output, reference[len(prefix):])

    if reference.startswith("phases["):
        return _json_path_exists(roadmap_output, reference)

    first_phase_actions = re.fullmatch(
        r"(?:(?:roadmap_first_phase|first_phase)\.)?actions\[(\d+)\]",
        reference,
    )
    if first_phase_actions:
        phases = roadmap_output.get("phases", [])
        if not isinstance(phases, list) or not phases:
            return False
        actions = phases[0].get("actions", []) if isinstance(phases[0], dict) else []
        return int(first_phase_actions.group(1)) < len(actions)
    return None
