import pytest

from solution.ninety_day_plan import generate_ninety_day_plan


def _upstream_inputs():
    synthesis = {
        "findings": [{"id": "F01", "statement": "现金紧张，需先止损"}],
        "transition_to_solution": "先释放资源，再投入增长",
    }
    dimensions = [
        {
            "dimension": "finance",
            "core_judgment": "现金安全优先于新增投入",
            "reasoning_chain": ["亏损线占用现金和产能"],
        }
    ]
    thesis = {
        "strategic_thesis": "从亏损通用件扩张转向高毛利工程配套",
        "from_to": {"from": "亏损通用件扩张", "to": "高毛利工程配套"},
    }
    levers = {
        "selected": [{"name": "砍掉亏损线释放资源", "reason": "恢复现金安全"}]
    }
    action_map = {
        "actions": [
            {
                "action": "停止亏损法兰产品的新订单并形成清仓表",
                "category": "风险财务",
                "grounded_in": ["F01"],
                "owner": "财务负责人",
                "expected_output": "清仓表",
            }
        ]
    }
    roadmap = {
        "phases": [
            {
                "phase_name": "止损释放期",
                "goal": "停止亏损线继续占用现金和产能",
                "actions": [
                    {
                        "action": "停止亏损法兰产品的新订单并形成清仓表",
                        "grounded_in": ["action_map.actions[0]"],
                    }
                ],
                "rationale": "先止损释放资源",
                "milestone": "亏损线停止接单且清仓表获批",
            },
            {
                "phase_name": "样品验证期",
                "goal": "完成样品验证",
                "actions": [{"action": "开发样品", "grounded_in": ["strategic_thesis"]}],
                "rationale": "止损后投入",
                "milestone": "样品完成",
            },
            {
                "phase_name": "客户转化期",
                "goal": "完成客户转化",
                "actions": [{"action": "提交报价", "grounded_in": ["strategic_thesis"]}],
                "rationale": "样品后转化",
                "milestone": "客户确认",
            },
        ]
    }
    return synthesis, dimensions, thesis, levers, action_map, roadmap


def _valid_plan():
    return {
        "plan": [
            {
                "task": "逐笔核对法兰在手订单并冻结低于接单底线的新订单",
                "owner": "财务负责人",
                "timeframe": "0-30天",
                "deliverable": "法兰订单处置清单",
                "metric": "全部在手订单完成毛利和回款条件标记",
                "grounded_in": ["roadmap_output.phases[0].actions[0]"],
            },
            {
                "task": "按库存和客户承诺制定法兰清仓及交付安排",
                "owner": "销售负责人",
                "timeframe": "31-60天",
                "deliverable": "清仓时间表和客户协商纪要",
                "metric": "清仓批次、责任人和客户确认状态全部登记",
                "grounded_in": ["action_map.actions[0]", "F01"],
            },
            {
                "task": "复盘止损执行结果并确认释放的现金和产能",
                "owner": "创始人",
                "timeframe": "61-90天",
                "deliverable": "止损复盘报告",
                "metric": "形成经管理层确认的现金和产能释放数据",
                "grounded_in": ["finance.core_judgment"],
            },
        ]
    }


def test_generate_ninety_day_plan_returns_schema_and_prints_raw(capsys):
    inputs = _upstream_inputs()

    def fake_llm(system_prompt, user_prompt):
        assert "第五层" in system_prompt
        assert "roadmap_first_phase" in user_prompt
        return _valid_plan()

    result = generate_ninety_day_plan(*inputs, llm_call=fake_llm)

    assert result["plan"][0]["timeframe"] == "0-30天"
    assert "=== RAW NINETY DAY PLAN RESULT ===" in capsys.readouterr().out


def test_generate_ninety_day_plan_retries_empty_field():
    inputs = _upstream_inputs()
    invalid = _valid_plan()
    invalid["plan"][0]["metric"] = ""
    responses = [invalid, _valid_plan()]
    prompts = []

    def fake_llm(_system_prompt, user_prompt):
        prompts.append(user_prompt)
        return responses.pop(0)

    result = generate_ninety_day_plan(*inputs, llm_call=fake_llm)

    assert result["plan"][0]["metric"]
    assert len(prompts) == 2
    assert "plan[0].metric must be a non-empty string" in prompts[1]


@pytest.mark.parametrize(
    "reference",
    [
        "roadmap.phases[0].actions[0]",
        "roadmap_output.phases[0].actions[0]",
        "phases[0].actions[0]",
        "actions[0]",
        "停止亏损法兰产品的新订单并形成清仓表",
        "lever_matrix.selected[0].name",
        "dimension_outputs[0].core_judgment",
    ],
)
def test_generate_ninety_day_plan_accepts_real_upstream_reference(reference):
    inputs = _upstream_inputs()
    output = _valid_plan()
    output["plan"][0]["grounded_in"] = [reference]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    result = generate_ninety_day_plan(*inputs, llm_call=fake_llm)

    assert result["plan"][0]["grounded_in"] == [reference]


@pytest.mark.parametrize(
    "reference",
    [
        "roadmap_output.phases[0].actions[99]",
        "action_map.actions[99]",
        "F99",
        "不存在的上游依据",
    ],
)
def test_generate_ninety_day_plan_rejects_missing_upstream_target(reference):
    inputs = _upstream_inputs()
    output = _valid_plan()
    output["plan"][0]["grounded_in"] = [reference]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference a real upstream"):
        generate_ninety_day_plan(*inputs, llm_call=fake_llm, max_attempts=1)
