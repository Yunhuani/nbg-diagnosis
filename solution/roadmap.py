from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json


ROADMAP_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第四层三阶段路线图引擎。

你的任务只做方案五层结构的第四层：roadmap。输入是诊断 synthesis、五维诊断输出，以及前三层 strategic_thesis、lever_matrix、action_map；你要把已有行动及其后续延续动作按真实时间先后和依赖关系排入三个阶段。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 阶段名称必须根据本案例的战略节奏命名，不得套用固定阶段名。
- 每个阶段的 actions 至少包含 1 个行动，不得只把行动写在 rationale 或 milestone 中。
- action_map 的已有行动都应被排入路线图；后期阶段还允许把已有行动延续或深化，例如把「开发无框样品」延续为「扩大无框产品生产」。
- 每条行动都必须用 grounded_in 注明它延续自哪条 action_map 行动或哪项真实战略/诊断依据，不得提出与战略无关的全新方向。
- 阶段顺序必须体现真实依赖：先处理前置约束和资源释放，再推进依赖这些条件的投入与扩张。例如存在亏损线处置时，应先完成止损和资源释放，再安排依赖该资源的开发投入。
- 每阶段的 goal、rationale、milestone 必须具体，写清阶段要达成的状态、排序依据和可指认里程碑；禁止只写「夯实基础」「提升能力」「实现增长」等空泛表述。
- 所有判断只能来自当前输入。不得推翻 financial_facts 的产品线盈亏事实，不得引入本案例不存在的公司、产品、行业、市场、渠道或外部机会。
- 如引用依据，只能引用当前输入中真实存在的 synthesis finding、dimension_outputs 结论、战略主张、杠杆或行动。
- 不得输出 90 天详细任务排期、预算表或前三层的重写版本。
"""

ROADMAP_USER_PROMPT = """你会收到诊断 synthesis、五维诊断输出、战略主张 strategic_thesis、杠杆矩阵 lever_matrix 和四类行动地图 action_map。基于它们生成方案第四层「三阶段路线图」。

输出 JSON schema：
{
  "phases": [
    {
      "phase_name": "按本案例战略节奏命名的阶段名",
      "goal": "本阶段要达成的具体状态",
      "actions": [
        {
          "action": "action_map 中的已有行动，或由其延续深化的后续行动",
          "grounded_in": ["真实存在的 action_map 行动、strategic_thesis、lever_matrix 或 dimension_outputs 结论"]
        }
      ],
      "rationale": "为什么这些行动必须排在此阶段，以及它们与前后阶段的依赖关系",
      "milestone": "完成本阶段时可指认、可审核的里程碑"
    }
  ]
}

质量要求：
1. phases 必须正好 3 个，并按执行先后排列。
2. 每个阶段的 actions 至少包含 1 个行动，不得只写在 rationale/milestone 中。
3. action_map 的已有行动都应被安排；后期阶段还可以包含已有行动的合理延续或深化，但每条行动必须填写 grounded_in，说明它来自哪条已有行动或战略依据。
4. phase_name、goal、rationale、milestone 必须结合本案例和本阶段行动具体书写。
5. 阶段划分要体现现金、能力、资源和业务动作之间的真实依赖，不做平均分配。
"""

REQUIRED_ROADMAP_KEYS = {"phases"}
REQUIRED_PHASE_KEYS = {"phase_name", "goal", "actions", "rationale", "milestone"}
REQUIRED_ROADMAP_ACTION_KEYS = {"action", "grounded_in"}


def call_roadmap_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_ROADMAP_MODEL"),
    )


def generate_roadmap(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_roadmap_json,
    max_attempts: int = 3,
) -> dict[str, Any]:
    user_prompt = _build_roadmap_user_prompt(
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
        action_map_output,
    )
    last_error: ValueError | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = user_prompt
        if last_error is not None:
            prompt += (
                "\n\n上一次输出未通过客观 schema 校验。"
                f"校验错误：{last_error}。"
                "请只修正字段、类型、阶段数量或行动引用错误，重新输出完整 JSON。"
            )

        result = llm_call(ROADMAP_SYSTEM_PROMPT, prompt)
        print("=== RAW ROADMAP RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2))
        try:
            validate_roadmap_output(
                result,
                synthesis_output,
                dimension_outputs,
                strategic_thesis_output,
                lever_matrix_output,
                action_map_output,
            )
        except ValueError as error:
            last_error = error
            if attempt < max_attempts:
                print(f"=== RETRY ROADMAP ATTEMPT {attempt + 1}/{max_attempts}: {error} ===")
                continue
            raise
        return result

    raise RuntimeError("roadmap generation exhausted without a result")


def validate_roadmap_output(
    output: dict[str, Any],
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"roadmap output must be an object, got {type(output).__name__}")

    missing = REQUIRED_ROADMAP_KEYS - set(output)
    if missing:
        raise ValueError(f"roadmap output missing keys: {sorted(missing)}")

    phases = output["phases"]
    if not isinstance(phases, list):
        raise ValueError(f"phases must be an array, got {type(phases).__name__}")
    if len(phases) != 3:
        raise ValueError(f"phases must contain exactly 3 phases, got {len(phases)}")

    phase_names: set[str] = set()

    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError(f"phases[{index}] must be an object, got {type(phase).__name__}")

        missing_phase = REQUIRED_PHASE_KEYS - set(phase)
        if missing_phase:
            raise ValueError(f"phases[{index}] missing keys: {sorted(missing_phase)}")

        for key in ("phase_name", "goal", "rationale", "milestone"):
            value = phase[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"phases[{index}].{key} must be a non-empty string")

        phase_name = phase["phase_name"].strip()
        if phase_name in phase_names:
            raise ValueError(f"duplicate phase_name: {phase_name!r}")
        phase_names.add(phase_name)

        actions = phase["actions"]
        if not isinstance(actions, list):
            raise ValueError(f"phases[{index}].actions must be an array")
        if not actions:
            raise ValueError(f"phases[{index}].actions must not be empty")
        for action_index, action_item in enumerate(actions):
            _validate_roadmap_action(
                action_item,
                f"phases[{index}].actions[{action_index}]",
                synthesis_output,
                dimension_outputs,
                strategic_thesis_output,
                lever_matrix_output,
                action_map_output,
            )


def _build_roadmap_user_prompt(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> str:
    payload = {
        "synthesis_output": synthesis_output,
        "dimension_outputs": dimension_outputs,
        "strategic_thesis_output": strategic_thesis_output,
        "lever_matrix_output": lever_matrix_output,
        "action_map_output": action_map_output,
    }
    return f"""{ROADMAP_USER_PROMPT}

输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _validate_roadmap_action(
    item: Any,
    path: str,
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"{path} must be an object, got {type(item).__name__}")

    missing = REQUIRED_ROADMAP_ACTION_KEYS - set(item)
    if missing:
        raise ValueError(f"{path} missing keys: {sorted(missing)}")

    action = item["action"]
    if not isinstance(action, str) or not action.strip():
        raise ValueError(f"{path}.action must be a non-empty string")

    grounded_in = item["grounded_in"]
    if not isinstance(grounded_in, list):
        raise ValueError(f"{path}.grounded_in must be an array")
    if not grounded_in:
        raise ValueError(f"{path}.grounded_in must not be empty")
    for index, reference in enumerate(grounded_in):
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError(f"{path}.grounded_in[{index}] must be a non-empty string")

    _validate_grounding(
        grounded_in,
        path,
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
        action_map_output,
    )


def _validate_grounding(
    grounded_in: list[str],
    path: str,
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> None:
    finding_ids = {
        item["id"]
        for item in synthesis_output.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for index, reference in enumerate(grounded_in):
        if _reference_resolves(
            reference,
            finding_ids,
            synthesis_output,
            dimension_outputs,
            strategic_thesis_output,
            lever_matrix_output,
            action_map_output,
        ):
            continue
        raise ValueError(
            f"{path}.grounded_in[{index}] must reference a real upstream action or conclusion, "
            f"got {reference!r}"
        )


def _reference_resolves(
    reference: str,
    finding_ids: set[str],
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> bool:
    text = reference.strip()

    action_indexes = re.findall(
        r"(?:(?:action_map(?:_output)?\.)?actions)\[(\d+)\]",
        text,
    )
    if action_indexes:
        action_count = len(action_map_output.get("actions", []))
        return all(int(index) < action_count for index in action_indexes)

    referenced_findings = re.findall(r"(?<![A-Za-z0-9_])F\d+(?![A-Za-z0-9_])", text)
    if referenced_findings:
        return all(finding_id in finding_ids for finding_id in referenced_findings)

    field_resolution = _resolve_explicit_field_reference(
        text,
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
    )
    if field_resolution is not None:
        return field_resolution

    upstream_values = (
        _collect_string_values(synthesis_output)
        | _collect_string_values(dimension_outputs)
        | _collect_string_values(strategic_thesis_output)
        | _collect_string_values(lever_matrix_output)
        | _collect_string_values(action_map_output)
    )
    return any(_is_text_reference(text, value) for value in upstream_values)


def _resolve_explicit_field_reference(
    reference: str,
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
) -> bool | None:
    roots = {
        "synthesis": synthesis_output,
        "synthesis_output": synthesis_output,
        "strategic_thesis": strategic_thesis_output,
        "strategic_thesis_output": strategic_thesis_output,
        "lever_matrix": lever_matrix_output,
        "lever_matrix_output": lever_matrix_output,
    }
    if reference in roots:
        return True
    for root_name, root_value in roots.items():
        prefix = f"{root_name}."
        if reference.startswith(prefix):
            return _json_path_exists(root_value, reference[len(prefix):])

    indexed_dimension = re.fullmatch(
        r"dimension_outputs\[(\d+)\]\.(.+)",
        reference,
    )
    if indexed_dimension:
        index = int(indexed_dimension.group(1))
        if index >= len(dimension_outputs):
            return False
        return _json_path_exists(dimension_outputs[index], indexed_dimension.group(2))

    dimension_fields = _dimension_fields(dimension_outputs)
    dimension_match = re.fullmatch(
        r"(?:(?:dimension_outputs)\.)?([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
        reference,
    )
    if dimension_match and dimension_match.group(1) in dimension_fields:
        dimension, field = dimension_match.groups()
        return field in dimension_fields[dimension]

    top_level_fields = (
        set(synthesis_output)
        | set(strategic_thesis_output)
        | set(lever_matrix_output)
    )
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", reference):
        return reference in top_level_fields
    return None


def _json_path_exists(value: Any, path: str) -> bool:
    normalized = re.sub(r"\[(\d+)\]", r".\1", path)
    parts = normalized.split(".")
    if not parts or any(not part for part in parts):
        return False

    current = value
    for part in parts:
        if part.isdigit():
            numeric_index = int(part)
            if not isinstance(current, list) or numeric_index >= len(current):
                return False
            current = current[numeric_index]
        else:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part):
                return False
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
    return True


def _dimension_fields(
    dimension_outputs: list[dict[str, Any]],
) -> dict[str, set[str]]:
    fields: dict[str, set[str]] = {}
    for item in dimension_outputs:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            continue
        fields[dimension] = set(item)
    return fields


def _is_text_reference(reference: str, upstream_value: str) -> bool:
    if reference == upstream_value:
        return True
    if len(reference) < 4 or len(upstream_value) < 4:
        return False
    return reference in upstream_value or upstream_value in reference


def _collect_string_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, str) and value.strip():
        values.add(value.strip())
    elif isinstance(value, dict):
        for item in value.values():
            values.update(_collect_string_values(item))
    elif isinstance(value, list):
        for item in value:
            values.update(_collect_string_values(item))
    return values
