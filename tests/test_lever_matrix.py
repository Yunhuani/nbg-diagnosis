import pytest

from solution.lever_matrix import generate_lever_matrix


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
                "statement": "营销和财务管理弱，现阶段不适合大规模品牌投放",
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
        "confirmed_reversals": [
            {
                "finding_id": "F02",
                "naive_reading": "大客户集中是风险",
                "reframe": "认证和多年适配形成切换成本",
                "mechanism": "认证、合作年限和定制适配叠加形成进入壁垒",
                "falsifier": "大客户正在询价竞品或认证已被同行普遍获得",
                "confidence": 0.7,
                "status": "needs_human_falsifier_check",
                "depends_on": ["competition.unique_assets"],
            }
        ],
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
        "key_assumptions": ["F02的反转仍依赖人工核验。"],
        "tradeoffs": ["放弃以低价通用件继续换规模。"],
    }


def _valid_lever_matrix():
    return {
        "levers": [
            {
                "name": "把北美认证客户做成工程配套白名单",
                "description": "围绕已有认证和适配记录，筛选同类工程客户，优先销售高毛利淋浴隔断五金配套包。",
                "impact": {"level": "高", "reason": "直接把增长从通用件转到认证壁垒支撑的中高端工程配套。"},
                "feasibility": {"level": "高", "reason": "依托既有认证和大客户适配资产，不需要大额品牌投放，适合现金紧张状态。"},
                "grounded_in": ["F01", "F02", "strategic_thesis", "from_to"],
                "priority": 1,
            },
            {
                "name": "砍掉低毛利通用件的接单底线",
                "description": "为通用件订单设置最低净贡献和回款账期门槛，把产能让给现金回收更快的配套订单。",
                "impact": {"level": "高", "reason": "回应先止血再切高值工程，避免继续被低毛利规模拖住。"},
                "feasibility": {"level": "中", "reason": "需要销售执行取舍，短期可能损失收入，但不需要新增大额投入。"},
                "grounded_in": ["F01", "transition_to_solution", "tradeoffs"],
                "priority": 2,
            },
            {
                "name": "把认证资料打包成工程投标素材库",
                "description": "把CE/REACH、北美合格供应商记录和定制案例整理成投标材料，缩短新工程客户信任建立周期。",
                "impact": {"level": "中", "reason": "能放大认证壁垒，但仍依赖销售触达和客户验证。"},
                "feasibility": {"level": "高", "reason": "主要复用已有资料和案例，现金投入低，匹配营销能力弱的现实。"},
                "grounded_in": ["F02", "F03", "confirmed_reversals"],
                "priority": 3,
            },
            {
                "name": "暂停高预算海外品牌投放",
                "description": "暂不做面向终端市场的大额品牌广告，把有限现金留给认证客户转化和回款改善。",
                "impact": {"level": "中", "reason": "它本身不是增长引擎，但能保护战略切换期的现金安全。"},
                "feasibility": {"level": "高", "reason": "符合现金紧张和营销能力弱的诊断，不增加投入。"},
                "grounded_in": ["F01", "F03", "tradeoffs"],
                "priority": 4,
            },
        ],
        "selected": [
            {"name": "把北美认证客户做成工程配套白名单", "reason": "影响力和可行性同时最高，最贴近战略主张。"},
            {"name": "砍掉低毛利通用件的接单底线", "reason": "现金跑道不足时必须先止血，否则高值工程承接没有安全垫。"},
        ],
    }


def test_generate_lever_matrix_returns_schema_and_grounding():
    synthesis = _synthesis_output()
    thesis = _strategic_thesis_output()

    def fake_llm(system_prompt, user_prompt):
        assert "第二层杠杆选择矩阵" in system_prompt
        assert "synthesis_output" in user_prompt
        assert "strategic_thesis_output" in user_prompt
        return _valid_lever_matrix()

    result = generate_lever_matrix(synthesis, thesis, llm_call=fake_llm)

    assert result["levers"][0]["priority"] == 1
    assert result["levers"][0]["impact"]["level"] == "高"
    assert result["selected"][0]["name"] == "把北美认证客户做成工程配套白名单"


def test_generate_lever_matrix_rejects_unknown_grounding():
    output = _valid_lever_matrix()
    output["levers"][0]["grounded_in"] = ["F99"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference synthesis findings"):
        generate_lever_matrix(_synthesis_output(), _strategic_thesis_output(), llm_call=fake_llm)


def test_generate_lever_matrix_rejects_selecting_every_candidate():
    output = _valid_lever_matrix()
    output["selected"] = [
        {"name": lever["name"], "reason": "全部都选不是聚焦。"}
        for lever in output["levers"]
    ]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="at most 3|subset"):
        generate_lever_matrix(_synthesis_output(), _strategic_thesis_output(), llm_call=fake_llm)
