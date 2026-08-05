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
