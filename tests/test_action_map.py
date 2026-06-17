import pytest

from solution.action_map import generate_action_map


def _synthesis_output():
    return {
        "findings": [
            {
                "id": "F01",
                "dimension": "finance",
                "statement": "现金跑道只有1.6个月，不能承受长周期高投入动作",
                "type": "judgment",
                "strength": "high",
                "quant_value": "1.6个月",
            },
            {
                "id": "F02",
                "dimension": "competition",
                "statement": "北美大客户认证和多年适配形成切换成本",
                "type": "reversal",
                "strength": "high",
                "quant_value": "65%",
            },
            {
                "id": "F03",
                "dimension": "capability",
                "statement": "营销和财务管理弱，不适合大规模品牌投放",
                "type": "judgment",
                "strength": "medium",
                "quant_value": "定性",
            },
        ],
        "headline": "先止血再切高值工程",
        "overall_judgment": "公司不是没有增长机会，而是现金承压和通用代工模式限制了高值机会承接。",
        "overall_score": 4.8,
        "score_label": "警告",
        "cross_resonances": [],
        "confirmed_reversals": [],
        "three_key_findings": [{"finding_id": "F01", "title": "现金跑道不足", "why_surprising": "订单不少不等于现金安全"}],
        "consistency_flags": [],
        "transition_to_solution": "先止住财务失血，再围绕认证壁垒重排增长方向",
    }


def _strategic_thesis_output():
    return {
        "strategic_thesis": "从消耗现金的通用件代工，转向认证壁垒支撑的中高端工程配套",
        "from_to": {
            "from": "继续用通用件和低毛利订单保规模",
            "to": "围绕认证和大客户适配能力承接中高端工程配套",
        },
        "reasoning": [
            "F01显示现金安全边际不足，不能继续靠低毛利规模消耗现金。",
            "F02显示认证和大客户绑定可能是壁垒，因此增长方向应围绕高切换成本客户展开。",
        ],
        "grounded_in": ["F01", "F02", "transition_to_solution"],
        "key_assumptions": [],
        "tradeoffs": ["放弃以低价通用件继续换规模。"],
    }


def _lever_matrix_output():
    return {
        "levers": [
            {
                "name": "把北美认证客户做成工程配套白名单",
                "description": "围绕已有认证和适配记录，筛选同类工程客户，优先销售高毛利配套包。",
                "impact": {"level": "高", "reason": "直接转向中高端工程配套。"},
                "feasibility": {"level": "高", "reason": "复用既有认证资产，现金投入低。"},
                "grounded_in": ["F01", "F02", "strategic_thesis"],
                "priority": 1,
            },
            {
                "name": "砍掉低毛利通用件的接单底线",
                "description": "为通用件订单设置最低净贡献和账期门槛，把产能让给回款更快的配套订单。",
                "impact": {"level": "高", "reason": "回应先止血。"},
                "feasibility": {"level": "中", "reason": "需要销售取舍。"},
                "grounded_in": ["F01", "tradeoffs"],
                "priority": 2,
            },
            {
                "name": "把认证资料打包成工程投标素材库",
                "description": "把认证、供应商记录和定制案例整理成投标材料，缩短新客户信任建立周期。",
                "impact": {"level": "中", "reason": "放大认证壁垒。"},
                "feasibility": {"level": "高", "reason": "主要复用已有资料。"},
                "grounded_in": ["F02", "F03"],
                "priority": 3,
            },
        ],
        "selected": [
            {"name": "把北美认证客户做成工程配套白名单", "reason": "最贴近战略主张。"},
            {"name": "砍掉低毛利通用件的接单底线", "reason": "现金紧张时必须先止血。"},
        ],
    }


def _valid_action_map():
    return {
        "actions": [
            {
                "action": "把北美A/B同类工程客户筛成认证配套白名单",
                "category": "战略方向",
                "grounded_in": ["F02", "strategic_thesis", "把北美认证客户做成工程配套白名单"],
                "owner": "创始人",
                "expected_output": "工程客户白名单",
            },
            {
                "action": "为通用件订单设置最低全成本净贡献和回款账期门槛",
                "category": "风险财务",
                "grounded_in": ["F01", "砍掉低毛利通用件的接单底线", "tradeoffs"],
                "owner": "财务负责人",
                "expected_output": "接单底线规则表",
            },
            {
                "action": "用CE/REACH认证和北美供应商记录整理工程投标素材包",
                "category": "战术方向",
                "grounded_in": ["F02", "把北美认证客户做成工程配套白名单"],
                "owner": "销售负责人",
                "expected_output": "工程投标素材包",
            },
            {
                "action": "将销售报价流程拆分为通用件止血审批和工程配套优先跟进",
                "category": "管理方向",
                "grounded_in": ["F01", "F03", "砍掉低毛利通用件的接单底线"],
                "owner": "销售负责人",
                "expected_output": "报价审批流程模板",
            },
        ]
    }


def test_generate_action_map_returns_schema_and_grounding():
    def fake_llm(system_prompt, user_prompt):
        assert "第三层四类行动地图" in system_prompt
        assert "战略方向" in system_prompt
        assert "lever_matrix_output" in user_prompt
        return _valid_action_map()

    result = generate_action_map(
        _synthesis_output(),
        _strategic_thesis_output(),
        _lever_matrix_output(),
        llm_call=fake_llm,
    )

    assert result["actions"][0]["category"] == "战略方向"
    assert result["actions"][2]["category"] == "战术方向"


def test_generate_action_map_rejects_vague_action_without_mechanism():
    output = _valid_action_map()
    output["actions"][0]["action"] = "加强品牌"

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="concrete object and execution mechanism"):
        generate_action_map(_synthesis_output(), _strategic_thesis_output(), _lever_matrix_output(), llm_call=fake_llm)


def test_generate_action_map_allows_specific_action_containing_tisheng():
    output = _valid_action_map()
    output["actions"][2]["action"] = "用耗材订阅包提升复购率并绑定私域会员"
    output["actions"][2]["expected_output"] = "耗材订阅包方案"

    def fake_llm(_system_prompt, _user_prompt):
        return output

    result = generate_action_map(
        _synthesis_output(),
        _strategic_thesis_output(),
        _lever_matrix_output(),
        llm_call=fake_llm,
    )

    assert "提升复购率" in result["actions"][2]["action"]


def test_generate_action_map_rejects_unknown_grounding():
    output = _valid_action_map()
    output["actions"][0]["grounded_in"] = ["F99"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference synthesis"):
        generate_action_map(_synthesis_output(), _strategic_thesis_output(), _lever_matrix_output(), llm_call=fake_llm)


def test_generate_action_map_requires_strategy_and_tactical_coverage():
    output = _valid_action_map()
    output["actions"][2]["category"] = "管理方向"

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must cover categories"):
        generate_action_map(_synthesis_output(), _strategic_thesis_output(), _lever_matrix_output(), llm_call=fake_llm)
