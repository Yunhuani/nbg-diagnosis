import pytest

from solution.roadmap import generate_roadmap


def _upstream_inputs():
    synthesis = {
        "findings": [{"id": "F01", "statement": "现金紧张，需先止损"}],
        "transition_to_solution": "先释放资源，再投入增长",
    }
    dimension_outputs = [
        {
            "dimension": "finance",
            "core_judgment": "现金安全优先于新增投入",
            "reasoning_chain": ["亏损线占用现金和产能"],
        }
    ]
    thesis = {
        "strategic_thesis": "从亏损通用件扩张转向高毛利工程配套",
        "from_to": {"from": "亏损通用件扩张", "to": "高毛利工程配套"},
        "tradeoffs": ["停止亏损线新增投入"],
    }
    levers = {
        "selected": [
            {"name": "砍掉亏损线释放资源", "reason": "先恢复现金安全"},
            {"name": "开发认证工程客户", "reason": "承接高毛利增长"},
        ]
    }
    action_map = {
        "actions": [
            {
                "action": "停止亏损法兰产品的新订单并形成清仓表",
                "category": "风险财务",
                "grounded_in": ["F01"],
                "owner": "财务负责人",
                "expected_output": "清仓表",
            },
            {
                "action": "把释放的产能排给认证工程配套样品",
                "category": "战术方向",
                "grounded_in": ["开发认证工程客户"],
                "owner": "生产负责人",
                "expected_output": "样品排产表",
            },
            {
                "action": "向认证客户提交工程配套样品和报价",
                "category": "战术方向",
                "grounded_in": ["开发认证工程客户"],
                "owner": "销售负责人",
                "expected_output": "样品反馈和报价单",
            },
            {
                "action": "根据客户反馈修订工程配套报价和交付方案",
                "category": "战术方向",
                "grounded_in": ["开发认证工程客户"],
                "owner": "销售负责人",
                "expected_output": "修订报价和交付方案",
            },
        ]
    }
    return synthesis, dimension_outputs, thesis, levers, action_map


def _valid_roadmap():
    return {
        "phases": [
            {
                "phase_name": "止损释放期",
                "goal": "停止亏损线继续占用现金和产能",
                "actions": [
                    {
                        "action": "停止亏损法兰产品的新订单并形成清仓表",
                        "grounded_in": ["停止亏损法兰产品的新订单并形成清仓表"],
                    }
                ],
                "rationale": "先完成止损，才能释放后续样品开发所需产能",
                "milestone": "亏损线停止接单且清仓表获批",
            },
            {
                "phase_name": "样品验证期",
                "goal": "完成认证工程配套样品交付准备",
                "actions": [
                    {
                        "action": "把释放的产能排给认证工程配套样品",
                        "grounded_in": ["开发认证工程客户"],
                    }
                ],
                "rationale": "产能释放后才能安排样品生产",
                "milestone": "首批工程配套样品完成",
            },
            {
                "phase_name": "客户转化期",
                "goal": "取得认证客户对样品和报价的明确反馈",
                "actions": [
                    {
                        "action": "扩大认证工程配套的稳定生产和客户转化",
                        "grounded_in": ["向认证客户提交工程配套样品和报价", "finance.core_judgment"],
                    }
                ],
                "rationale": "样品完成后才能进入客户验证和商务转化",
                "milestone": "收到客户书面反馈并形成下一轮报价",
            },
        ]
    }


def test_generate_roadmap_returns_three_phases_and_prints_raw(capsys):
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()

    def fake_llm(system_prompt, user_prompt):
        assert "第四层" in system_prompt
        assert "dimension_outputs" in user_prompt
        assert "finance.core_judgment" not in user_prompt
        assert "现金安全优先于新增投入" in user_prompt
        return _valid_roadmap()

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert len(result["phases"]) == 3
    assert "=== RAW ROADMAP RESULT ===" in capsys.readouterr().out


def test_generate_roadmap_retries_schema_validation_failure():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    invalid = _valid_roadmap()
    del invalid["phases"][0]["milestone"]
    responses = [invalid, _valid_roadmap()]
    prompts = []

    def fake_llm(_system_prompt, user_prompt):
        prompts.append(user_prompt)
        return responses.pop(0)

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert result["phases"][0]["milestone"]
    assert len(prompts) == 2
    assert "上一次输出未通过客观 schema 校验" in prompts[1]
    assert "milestone" in prompts[1]


def test_generate_roadmap_retries_when_third_phase_actions_are_empty():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    invalid = _valid_roadmap()
    invalid["phases"][2]["actions"] = []
    responses = [invalid, _valid_roadmap()]
    prompts = []

    def fake_llm(system_prompt, user_prompt):
        assert "每个阶段的 actions 至少包含 1 个行动" in system_prompt
        prompts.append(user_prompt)
        return responses.pop(0)

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert result["phases"][2]["actions"]
    assert len(prompts) == 2
    assert "phases[2].actions must not be empty" in prompts[1]


def test_generate_roadmap_accepts_continuation_action_with_real_grounding():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()

    def fake_llm(_system_prompt, _user_prompt):
        return output

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert result["phases"][2]["actions"][0]["action"].startswith("扩大")


def test_generate_roadmap_rejects_continuation_action_with_unknown_grounding():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = ["不存在的上层依据"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference a real upstream"):
        generate_roadmap(
            synthesis,
            dimensions,
            thesis,
            levers,
            action_map,
            llm_call=fake_llm,
            max_attempts=1,
        )


def test_generate_roadmap_rejects_generic_nested_field_as_grounding():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = ["action"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference a real upstream"):
        generate_roadmap(
            synthesis,
            dimensions,
            thesis,
            levers,
            action_map,
            llm_call=fake_llm,
            max_attempts=1,
        )


@pytest.mark.parametrize(
    "reference",
    [
        "action_map.actions[2]",
        "action_map_output.actions[3]",
        "actions[1]",
    ],
)
def test_generate_roadmap_accepts_existing_action_index_reference(reference):
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = [reference]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert result["phases"][2]["actions"][0]["grounded_in"] == [reference]


def test_generate_roadmap_rejects_out_of_range_action_index():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = ["action_map_output.actions[99]"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference a real upstream"):
        generate_roadmap(
            synthesis,
            dimensions,
            thesis,
            levers,
            action_map,
            llm_call=fake_llm,
            max_attempts=1,
        )


def test_generate_roadmap_rejects_invented_finding_id():
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = ["F99"]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    with pytest.raises(ValueError, match="must reference a real upstream"):
        generate_roadmap(
            synthesis,
            dimensions,
            thesis,
            levers,
            action_map,
            llm_call=fake_llm,
            max_attempts=1,
        )


@pytest.mark.parametrize(
    "reference",
    [
        "lever_matrix_output.selected[0].name",
        "strategic_thesis.from_to.to",
        "dimension_outputs[0].core_judgment",
    ],
)
def test_generate_roadmap_accepts_existing_upstream_json_path(reference):
    synthesis, dimensions, thesis, levers, action_map = _upstream_inputs()
    output = _valid_roadmap()
    output["phases"][2]["actions"][0]["grounded_in"] = [reference]

    def fake_llm(_system_prompt, _user_prompt):
        return output

    result = generate_roadmap(
        synthesis,
        dimensions,
        thesis,
        levers,
        action_map,
        llm_call=fake_llm,
    )

    assert result["phases"][2]["actions"][0]["grounded_in"] == [reference]
