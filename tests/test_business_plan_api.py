from unittest.mock import patch

import api_server
from fastapi import HTTPException


def _complete_payload() -> dict:
    return {
        "project_overview": {
            "bp_title": "BP",
            "company_name": "Company",
            "founded": "2024",
            "one_liner": "One liner",
            "business_summary": "Summary",
            "team_scale": "1",
            "slogan": "Slogan",
        },
        "demand": {
            "target_customer": "Customer",
            "pain_points": [
                {"description": "Pain 1", "why_rigid_demand": "Why 1"},
                {"description": "Pain 2", "why_rigid_demand": "Why 2"},
                {"description": "Pain 3", "why_rigid_demand": "Why 3"},
            ],
        },
        "product_model": {
            "solutions": [{"pain_point": "Pain", "solution": "Solution"}],
            "core_values": ["A", "B", "C"],
            "revenue_sources": [{"source": "SaaS", "share": "100%"}],
            "gross_margin": "", "net_margin": "", "sales_model": "Direct",
        },
        "market": {"market_size": {"tam": "", "sam": "", "som": ""}, "growth_forecast": []},
        "competition": {"competitors": [], "differentiations": ["A", "B", "C"]},
        "current_state": {
            "product_status": "Live", "customer_count": "", "device_count": "",
            "coverage": "", "financials": {}, "team_size": "", "endorsements": "",
        },
        "plan": {"roadmap": [], "financial_projection": []},
        "funding": {"funding_amount": "", "dilution_range": "", "use_of_funds": []},
        "team": {"members": []},
    }


def test_parse_bp_intake_reports_all_missing_required_paths():
    payload = _complete_payload()
    del payload["demand"]["target_customer"]
    del payload["product_model"]["sales_model"]
    del payload["market"]

    try:
        api_server._parse_bp_intake(payload)
    except api_server.BPIntakeValidationError as exc:
        assert exc.missing_fields == [
            "bp_intake.demand.target_customer",
            "bp_intake.market",
            "bp_intake.product_model.sales_model",
        ]
    else:
        raise AssertionError("missing BP fields must raise BPIntakeValidationError")


def test_create_business_plan_rejects_missing_intake_with_400():
    try:
        api_server.create_business_plan(api_server.BusinessPlanRequest(bp_intake=None))
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["missing_fields"] == ["bp_intake"]
    else:
        raise AssertionError("missing bp_intake must return HTTP 400")


def test_business_plan_jobs_are_isolated_from_diagnosis_jobs():
    payload = _complete_payload()

    def complete_job(job_id, _intake):
        api_server._update_business_plan_job(
            job_id, status="done", result={"module_statuses": {}}, error=None
        )

    with patch.object(api_server, "_run_business_plan_job", complete_job):
        response = api_server.create_business_plan(
            api_server.BusinessPlanRequest(bp_intake=payload)
        )

    job_id = response["job_id"]
    assert job_id in api_server._business_plan_jobs
    assert job_id not in api_server._jobs
    assert api_server.get_business_plan(job_id)["status"] == "done"


def test_optional_contact_is_parsed_without_repeating_website():
    payload = _complete_payload()
    payload["project_overview"]["website"] = "https://example.com"
    payload["contact"] = {
        "contact_person": "张明",
        "phone": "13800000000",
        "email": "contact@example.com",
        "address": "深圳市南山区",
    }

    intake = api_server._parse_bp_intake(payload)

    assert intake.contact.contact_person == "张明"
    assert not hasattr(intake.contact, "website")
    assert intake.project_overview.website == "https://example.com"


def test_missing_contact_remains_optional():
    intake = api_server._parse_bp_intake(_complete_payload())
    assert intake.contact is None


def test_competitors_missing_null_and_empty_are_optional():
    for value in ("missing", None, []):
        payload = _complete_payload()
        if value == "missing":
            del payload["competition"]["competitors"]
        else:
            payload["competition"]["competitors"] = value
        intake = api_server._parse_bp_intake(payload)
        assert intake.competition.competitors == []


def test_variable_length_required_arrays_accept_one_to_three_and_reject_other_sizes():
    for field_path in (
        ("demand", "pain_points"),
        ("product_model", "core_values"),
        ("competition", "differentiations"),
    ):
        for count in (1, 2, 3):
            payload = _complete_payload()
            section, field = field_path
            values = payload[section][field]
            payload[section][field] = values[:count]
            api_server._parse_bp_intake(payload)
        for count in (0, 4):
            payload = _complete_payload()
            section, field = field_path
            values = payload[section][field]
            payload[section][field] = values[:1] * count
            try:
                api_server._parse_bp_intake(payload)
            except api_server.BPIntakeValidationError:
                pass
            else:
                raise AssertionError(f"{section}.{field} with {count} items must fail")
