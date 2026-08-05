from types import SimpleNamespace
from unittest.mock import patch
from urllib import request

from analysis import llm_client
from business_plan import generator
from business_plan.schemas import FieldOutput, ModuleOutput, SourceType


def _module_output(module_id: int) -> ModuleOutput:
    return ModuleOutput(
        module_id=module_id,
        headline=FieldOutput("", SourceType.PENDING_CUSTOMER),
        sub_headline=FieldOutput("", SourceType.PENDING_CUSTOMER),
        fields={
            "summary": FieldOutput(
                "面向中小制造企业解决设备状态不透明与被动维修问题",
                SourceType.ENGINE_REWRITE,
            )
        },
        chart_data=[],
        text_length_constraints={},
    )


def test_headline_generation_succeeds_in_one_attempt():
    response = {"headline": "设备运行透明化，正成为中小制造企业提升运营韧性的关键基础"}
    with patch.object(generator, "call_deepseek_json", return_value=response) as llm:
        headline, attempts = generator.generate_module_headline(_module_output(1))

    assert headline.value == response["headline"]
    assert headline.source_type is SourceType.ENGINE_REWRITE
    assert attempts == 1
    assert llm.call_count == 1


def test_headline_generation_degrades_to_empty_after_three_failures():
    with patch.object(
        generator,
        "call_deepseek_json",
        return_value={"headline": "需求分析"},
    ) as llm:
        headline, attempts = generator.generate_module_headline(_module_output(1))

    assert headline.value == ""
    assert headline.source_type is SourceType.PENDING_CUSTOMER
    assert attempts == 3
    assert llm.call_count == 3


def test_module_zero_overview_has_pending_headline_without_llm_call():
    intake = SimpleNamespace(
        bp_title="智造云商业计划书",
        company_name="深圳智造云科技有限公司",
        founded="2022年3月",
        one_liner="工业设备联网与数据分析平台",
        business_summary="面向中小制造企业的工业设备联网与数据分析SaaS",
        team_scale="46人",
        website=None,
        slogan="设备联网、数据驱动、让制造更聪明",
        mission=None,
        vision=None,
    )
    with (
        patch.object(
            generator,
            "_rewrite_qualitative_field",
            return_value=FieldOutput("专业化业务概述", SourceType.ENGINE_REWRITE),
        ),
        patch.object(generator, "call_deepseek_json") as llm,
    ):
        output = generator.generate_overview_module(intake)

    assert output.headline.value == ""
    assert output.headline.source_type is SourceType.PENDING_CUSTOMER
    assert llm.call_count == 0


def test_headline_validation_rejects_new_numeric_fact():
    response = {"headline": "设备透明化可将制造企业运营损失降低30%并提升经营韧性"}
    with patch.object(generator, "call_deepseek_json", return_value=response):
        headline, attempts = generator.generate_module_headline(_module_output(1))

    assert headline.source_type is SourceType.PENDING_CUSTOMER
    assert attempts == 3


def test_headline_retry_explicitly_forbids_a_new_indicator():
    prompts = []

    def fake_llm(_system_prompt, user_prompt, **_kwargs):
        prompts.append(user_prompt)
        if "后续输出不得再次出现以下新增指标词：成本" in user_prompt:
            return {"headline": "以轻量订阅与边缘智能，破解中小制造设备黑箱与被动维修难题"}
        return {"headline": "以低成本边缘智能，破解中小制造设备黑箱与被动维修难题"}

    output = _module_output(2)
    output.fields["summary"].value += "，方案便宜且可快速部署"
    with patch.object(generator, "call_deepseek_json", side_effect=fake_llm):
        headline, attempts = generator.generate_module_headline(output)

    assert headline.source_type is SourceType.ENGINE_REWRITE
    assert attempts == 2
    assert len(prompts) == 2


def test_orchestrator_counts_headline_calls_and_adds_minimum_call():
    from business_plan import orchestrator

    spec = orchestrator.ModuleSpec(
        module_id=1,
        result_field="demand",
        intake_field="demand",
        generator=lambda _intake: _module_output(1),
        minimum_llm_calls=lambda _intake: 0,
    )
    intake = SimpleNamespace(
        project_overview=SimpleNamespace(bp_title="test bp"),
        demand=SimpleNamespace(),
    )

    def fake_llm(*_args, **_kwargs):
        llm_client.request.urlopen(
            request.Request(
                "https://api.deepseek.com/chat/completions",
                data=b"[BP_MODULE_HEADLINE]",
            )
        )
        return {"headline": "设备运行透明化，正成为中小制造企业提升运营韧性的关键基础"}

    with (
        patch.object(orchestrator, "MODULE_SPECS", [spec]),
        patch.object(generator, "call_deepseek_json", fake_llm),
        patch.object(llm_client.request, "urlopen", lambda *_args, **_kwargs: None),
    ):
        result = orchestrator.generate_business_plan(intake)

    assert result.generation_stats.llm_call_count == 1
    assert result.generation_stats.headline_call_count == 1
    assert result.generation_stats.minimum_llm_call_count == 1
    assert result.module_statuses[1].headline_attempts == 1


def test_product_sub_headline_uses_only_business_model_and_sales_model():
    output = _module_output(2)
    output.fields = {
        "solution": FieldOutput("EXCLUDED_SOLUTION", SourceType.ENGINE_REWRITE),
        "core_value": FieldOutput("EXCLUDED_CORE_VALUE", SourceType.ENGINE_REWRITE),
        "business_model": FieldOutput(
            {
                "revenue_sources": "SaaS订阅占比",
                "gross_margin": "毛利率",
                "net_margin": "净利率",
            },
            SourceType.CLIENT_PROVIDED,
        ),
        "sales_model": FieldOutput("直销与渠道协同", SourceType.ENGINE_REWRITE),
    }
    prompts = []

    def fake_llm(_system_prompt, user_prompt, **_kwargs):
        prompts.append(user_prompt)
        return {"headline": "订阅收入与渠道协同，构成可持续扩张的商业模式基础"}

    with patch.object(generator, "call_deepseek_json", side_effect=fake_llm):
        sub_headline, attempts = generator.generate_module_sub_headline(output)

    assert sub_headline.source_type is SourceType.ENGINE_REWRITE
    assert attempts == 1
    assert "SaaS订阅占比" in prompts[0]
    assert "直销与渠道协同" in prompts[0]
    assert "EXCLUDED_SOLUTION" not in prompts[0]
    assert "EXCLUDED_CORE_VALUE" not in prompts[0]


def test_split_module_main_headlines_exclude_second_page_fields():
    cases = {
        2: ({"solution": "MAIN_2", "core_value": "MAIN_VALUE_2"}, {"business_model": "SUB_2", "sales_model": "SUB_SALES_2"}),
        3: ({"market_size": "MAIN_3", "market_narrative": "MAIN_NARRATIVE_3"}, {"growth_forecast": "SUB_3"}),
        4: ({"competitors": "MAIN_4"}, {"differentiation": "SUB_4"}),
        6: ({"roadmap": "MAIN_6"}, {"financial_projection": "SUB_6"}),
    }
    for module_id, (main_fields, sub_fields) in cases.items():
        output = _module_output(module_id)
        output.fields = {
            key: FieldOutput(value, SourceType.CLIENT_PROVIDED)
            for key, value in {**main_fields, **sub_fields}.items()
        }
        prompts = []
        with patch.object(
            generator,
            "call_deepseek_json",
            side_effect=lambda _system, user, **_kwargs: (
                prompts.append(user)
                or {"headline": "既有业务基础形成明确判断，并支撑后续路径持续推进"}
            ),
        ):
            generator.generate_module_headline(output)
        for value in main_fields.values():
            assert value in prompts[0]
        for value in sub_fields.values():
            assert value not in prompts[0]


def test_sub_headline_field_whitelists_are_strict():
    expected = {
        3: ("growth_forecast", "market_size"),
        4: ("differentiation", "competitors"),
    }
    for module_id, (included, excluded) in expected.items():
        output = _module_output(module_id)
        output.fields = {
            included: FieldOutput(f"INCLUDED_{module_id}", SourceType.CLIENT_PROVIDED),
            excluded: FieldOutput(f"EXCLUDED_{module_id}", SourceType.CLIENT_PROVIDED),
        }
        prompts = []
        with patch.object(
            generator,
            "call_deepseek_json",
            side_effect=lambda _system, user, **_kwargs: (
                prompts.append(user)
                or {"headline": "既有预测结构表明业务增长路径具备持续放大的明确基础"}
            ),
        ):
            generator.generate_module_sub_headline(output)
        assert f"INCLUDED_{module_id}" in prompts[0]
        assert f"EXCLUDED_{module_id}" not in prompts[0]


def test_modules_without_split_page_skip_sub_headline_llm():
    for module_id in (0, 1, 5, 7, 8):
        with patch.object(generator, "call_deepseek_json") as llm:
            sub_headline, attempts = generator.generate_module_sub_headline(
                _module_output(module_id)
            )
        assert sub_headline.value == ""
        assert sub_headline.source_type is SourceType.PENDING_CUSTOMER
        assert attempts == 0
        assert llm.call_count == 0


def test_plan_sub_headline_accepts_existing_net_profit_indicator():
    output = _module_output(6)
    output.fields = {
        "financial_projection": FieldOutput(
            [
                {
                    "year": FieldOutput("2030", SourceType.CLIENT_PROVIDED),
                    "revenue": FieldOutput("4.5亿", SourceType.CLIENT_PROVIDED),
                    "net_profit": FieldOutput("1.1亿", SourceType.CLIENT_PROVIDED),
                }
            ],
            SourceType.CLIENT_PROVIDED,
        ),
        "roadmap": FieldOutput("EXCLUDED_ROADMAP", SourceType.CLIENT_PROVIDED),
    }
    prompts = []
    with patch.object(
        generator,
        "call_deepseek_json",
        side_effect=lambda _system, user, **_kwargs: (
            prompts.append(user)
            or {"headline": "收入持续增长并实现盈利，净利润释放规模化经营价值"}
        ),
    ):
        sub_headline, attempts = generator.generate_module_sub_headline(output)

    assert "净利润" in prompts[0]
    assert "EXCLUDED_ROADMAP" not in prompts[0]
    assert sub_headline.source_type is SourceType.ENGINE_REWRITE
    assert attempts == 1


def test_orchestrator_counts_sub_headline_calls_separately():
    from business_plan import orchestrator

    output = _module_output(2)
    output.fields = {
        "solution": FieldOutput("设备联网形成透明管理", SourceType.ENGINE_REWRITE),
        "core_value": FieldOutput("轻量订阅快速部署", SourceType.ENGINE_REWRITE),
        "business_model": FieldOutput(
            {
                "revenue_sources": "订阅收入结构",
                "gross_margin": "毛利表现",
                "net_margin": "净利表现",
            },
            SourceType.CLIENT_PROVIDED,
        ),
        "sales_model": FieldOutput("直销与渠道协同", SourceType.ENGINE_REWRITE),
    }
    spec = orchestrator.ModuleSpec(
        2,
        "product_model",
        "product_model",
        lambda _intake: output,
        lambda _intake: 0,
    )
    intake = SimpleNamespace(
        project_overview=SimpleNamespace(bp_title="test bp", website=None),
        product_model=SimpleNamespace(),
        contact=None,
    )

    def fake_llm(system_prompt, _user_prompt, **_kwargs):
        marker = (
            b"[BP_MODULE_SUB_HEADLINE]"
            if "[BP_MODULE_SUB_HEADLINE]" in system_prompt
            else b"[BP_MODULE_HEADLINE]"
        )
        llm_client.request.urlopen(
            request.Request(
                "https://api.deepseek.com/chat/completions",
                data=marker,
            )
        )
        return {"headline": "轻量订阅与渠道协同，构成商业模式持续扩张的明确基础"}

    with (
        patch.object(orchestrator, "MODULE_SPECS", [spec]),
        patch.object(generator, "call_deepseek_json", fake_llm),
        patch.object(llm_client.request, "urlopen", lambda *_args, **_kwargs: None),
    ):
        result = orchestrator.generate_business_plan(intake)

    assert result.generation_stats.headline_call_count == 1
    assert result.generation_stats.sub_headline_call_count == 1
    assert result.generation_stats.minimum_llm_call_count == 2
    assert result.module_statuses[2].sub_headline_attempts == 1
