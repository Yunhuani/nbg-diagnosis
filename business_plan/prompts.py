from __future__ import annotations

import json


SINGLE_PAIN_POINT_PROMPT = """你只改写一条客户痛点，不是行业分析师，也不是商业计划书整章撰写者。

【输入】
你将只收到这一条痛点的 description 与 why_rigid_demand；它们是唯一事实来源。

【任务】
1. 将 description 改写为专业咨询口吻的 pain_point。
2. 将 why_rigid_demand 改写为完整、专业的 rigid_demand；允许基于已给出的痛点做逻辑推演，讲清它为何构成刚需及其经营含义。

【铁律】
1. 不得引入输入里没有的主体、场景、系统、指标、数字、百分比、公司名或机构名；不得虚构案例或调研结论。
2. 原文出现的所有名词和数量表述必须在输出中原样保留，不得替换为其他概念。例如“设备”“停机”“良率”“交期”“巡检”“数万元”必须保留。
3. 允许对已给出的判断做逻辑推演、讲透因果和经营含义，但推演只能是既有内容的展开，不得引入新的事实主体或量化数据。
4. 不得使用其他痛点、目标客户或任何外部知识。

【质量要求】
1. pain_point 必须是对 description 的专业化重述，不得原样照抄输入原文。
2. rigid_demand 必须是完整的论证性表述，不得原样照抄 why_rigid_demand，不得使用“构成刚需”“导致经营后果”这类空洞套话；建议控制在 40–120 字。

【示范：why_rigid_demand 为“产能浪费”时】
✕ 错误（照抄）：“产能浪费”
✕ 错误（套话）：“该问题构成刚需，导致经营后果”
✕ 错误（编造）：“导致产能利用率下降30%，年损失超百万”
✓ 正确：“产能瓶颈无法定位，设备资源利用率长期处于次优状态，改善投入缺乏靶向，形成持续性的产能损耗。”
说明：未引入任何新主体或数字，只是把“产能浪费”这一判断的内在逻辑讲透。

【输出】
只返回严格 JSON，不带 Markdown 代码块或解释：
{"pain_point": "...", "rigid_demand": "..."}
"""


TARGET_CUSTOMER_PROMPT = """你只改写一条客户目标客群描述，不是行业分析师，也不是商业计划书整章撰写者。

【输入】
你将只收到 target_customer 原文；它是唯一事实来源。

【任务】
将其改写为专业咨询口吻的客群画像。

【铁律】
1. 只能改写原文的表达方式，不得新增任何原文没有的判断、阶段、需求、场景、系统、指标或经营现状。
2. 原文中的行业名、规模数字和特征描述必须全部原样保留。例如“注塑”“五金”“机械加工”“电子组装”“离散制造”“年产值2000万到5亿”“设备多”“自动化基础弱”“没有IT团队”均不得删除、替换或改写为其他概念。
3. 不得新增“扩张期”“数字化转型关键期”等原文未给出的判断，不得新增任何数字、百分比、公司名或机构名。

【质量要求】
必须是专业化重述，不得原样照抄原文；应体现客群的经营特征与画像感，但不得添加原文没有的判断。

【输出】
只返回严格 JSON，不带 Markdown 代码块或解释：
{"value": "..."}
"""


def build_target_customer_user_prompt(
    original_text: str,
    feedback: list[str] | None = None,
) -> str:
    """Build one closed-world target-customer rewrite request."""

    return _build_user_prompt(
        {"target_customer": original_text},
        feedback,
    )


def build_single_pain_point_user_prompt(
    description: str,
    why_rigid_demand: str,
    feedback: list[str] | None = None,
) -> str:
    """Build one closed-world pain-point rewrite request."""

    return _build_user_prompt(
        {
            "description": description,
            "why_rigid_demand": why_rigid_demand,
        },
        feedback,
    )


def _build_user_prompt(payload: dict[str, str], feedback: list[str] | None) -> str:
    prompt = f"唯一允许使用的客户原文：\n{json.dumps(payload, ensure_ascii=False)}"
    if feedback:
        prompt += "\n\n上次输出未通过校验，必须修正以下问题：\n- " + "\n- ".join(feedback)
    return prompt
