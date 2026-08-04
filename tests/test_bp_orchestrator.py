from types import SimpleNamespace
from unittest.mock import patch
from urllib import request

from analysis import llm_client, search_client
from business_plan import generator, search
from business_plan.schemas import FieldOutput, ModuleOutput, SourceType


def _module_output(module_id: int, fields: dict[str, FieldOutput]) -> ModuleOutput:
    return ModuleOutput(
        module_id=module_id,
        fields=fields,
        chart_data=[],
        text_length_constraints={},
    )


def _intake() -> SimpleNamespace:
    return SimpleNamespace(
        project_overview=SimpleNamespace(bp_title="test bp", business_summary="summary"),
        demand=SimpleNamespace(target_customer="customer", pain_points=(1, 2, 3)),
        product_model=SimpleNamespace(solutions=[1], core_values=("a", "b", "c"), sales_model="sales"),
        market=SimpleNamespace(basis=None),
        competition=SimpleNamespace(differentiations=("a", "b", "c")),
        current_state=SimpleNamespace(product_status="status", endorsements="endorsement"),
        plan=SimpleNamespace(roadmap=[]),
        funding=SimpleNamespace(use_of_funds=[]),
        team=SimpleNamespace(members=[]),
    )


def test_orchestrator_isolates_module_errors_and_records_actual_calls():
    from business_plan import orchestrator

    def successful_module(_intake):
        generator.call_deepseek_json("system", "user")
        search.bocha_web_search("query")
        return _module_output(
            0,
            {
                "business_summary": FieldOutput(
                    "original", SourceType.CLIENT_PROVIDED
                ),
                "needed": FieldOutput("待补充", SourceType.PENDING_CUSTOMER),
                "nested": FieldOutput(
                    [FieldOutput("待补充", SourceType.PENDING_CUSTOMER)],
                    SourceType.CLIENT_PROVIDED,
                ),
            },
        )

    def failed_module(_intake):
        raise ValueError("invalid required intake")

    module_specs = [
        orchestrator.ModuleSpec(
            module_id=0,
            result_field="project_overview",
            intake_field="project_overview",
            generator=successful_module,
            minimum_llm_calls=lambda _: 1,
        ),
        orchestrator.ModuleSpec(
            module_id=1,
            result_field="demand",
            intake_field="demand",
            generator=failed_module,
            minimum_llm_calls=lambda _: 0,
        ),
    ]
    def fake_llm(*_args, **_kwargs):
        llm_client.request.urlopen(
            request.Request("https://api.deepseek.com/chat/completions")
        )
        return {}

    def fake_search(*_args, **_kwargs):
        search_client.request.urlopen(
            request.Request(search_client.BOCHA_SEARCH_URL)
        )
        return []

    with (
        patch.object(orchestrator, "MODULE_SPECS", module_specs),
        patch.object(generator, "call_deepseek_json", fake_llm),
        patch.object(search, "bocha_web_search", fake_search),
        patch.object(llm_client.request, "urlopen", lambda *_args, **_kwargs: None),
    ):
        result = orchestrator.generate_business_plan(_intake())

    assert result.project_overview is not None
    assert result.demand is None
    assert result.module_statuses[0].status == "success"
    assert result.module_statuses[1].status == "error"
    assert "invalid required intake" in result.module_statuses[1].error_message
    assert result.generation_stats.llm_call_count == 1
    assert result.generation_stats.search_call_count == 1
    assert result.generation_stats.minimum_llm_call_count == 1
    assert [(item.module_id, item.field_name) for item in result.pending_items] == [
        (0, "needed"),
        (0, "nested[0]"),
    ]
    assert [(item.module_id, item.field_name) for item in result.generation_stats.degraded_fields] == [
        (0, "business_summary")
    ]


def test_orchestrator_keeps_running_when_one_future_raises():
    from business_plan import orchestrator

    def success(module_id):
        return lambda _intake: _module_output(
            module_id,
            {"value": FieldOutput("ok", SourceType.ENGINE_REWRITE)},
        )

    def failure(_intake):
        raise RuntimeError("module failure")

    with patch.object(
        orchestrator,
        "MODULE_SPECS",
        [
            orchestrator.ModuleSpec(0, "project_overview", "project_overview", success(0), lambda _: 0),
            orchestrator.ModuleSpec(1, "demand", "demand", failure, lambda _: 0),
            orchestrator.ModuleSpec(2, "product_model", "product_model", success(2), lambda _: 0),
        ],
    ):
        result = orchestrator.generate_business_plan(_intake())

    assert result.project_overview is not None
    assert result.demand is None
    assert result.product_model is not None
    assert result.module_statuses[1].status == "error"


def test_degraded_fields_excludes_numeric_roadmap_deliverables():
    from business_plan import orchestrator

    output = _module_output(
        6,
        {
            "roadmap": FieldOutput(
                [
                    {
                        "objective": FieldOutput(
                            "rewritten", SourceType.ENGINE_REWRITE
                        ),
                        "deliverables": FieldOutput(
                            "客户做到3000家", SourceType.CLIENT_PROVIDED
                        ),
                    },
                    {
                        "objective": FieldOutput(
                            "original", SourceType.CLIENT_PROVIDED
                        ),
                        "deliverables": FieldOutput(
                            "完成区域覆盖", SourceType.CLIENT_PROVIDED
                        ),
                    },
                ],
                SourceType.CLIENT_PROVIDED,
            )
        },
    )

    degraded = orchestrator._collect_degraded_fields({"plan": output})

    assert [(item.module_id, item.field_name) for item in degraded] == [
        (6, "roadmap[1].objective"),
        (6, "roadmap[1].deliverables"),
    ]


def test_orchestrator_isolates_missing_required_module_input(monkeypatch=None):
    from business_plan import orchestrator

    intake = _intake()
    intake.demand = None
    successful = lambda _value: _module_output(
        0, {"value": FieldOutput("ok", SourceType.ENGINE_REWRITE)}
    )
    module_specs = [
        orchestrator.ModuleSpec(0, "project_overview", "project_overview", successful, lambda _: 0),
        orchestrator.ModuleSpec(1, "demand", "demand", generator.generate_demand_module, lambda _: 0),
    ]

    with patch.object(orchestrator, "MODULE_SPECS", module_specs):
        result = orchestrator.generate_business_plan(intake)

    assert result.project_overview is not None
    assert result.demand is None
    assert result.module_statuses[1].status == "error"
    assert "AttributeError" in result.module_statuses[1].error_message
