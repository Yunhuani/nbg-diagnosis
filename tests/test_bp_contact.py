from types import SimpleNamespace
from unittest.mock import patch

from business_plan import orchestrator
from business_plan.schemas import SourceType


def test_contact_output_copies_customer_facts_and_reuses_overview_website():
    contact = SimpleNamespace(
        contact_person="张明",
        phone="13800000000",
        email="contact@example.com",
        address=None,
    )
    overview = SimpleNamespace(website="https://example.com")

    with patch("business_plan.generator.call_deepseek_json") as llm:
        output = orchestrator._build_contact_output(contact, overview)

    assert output.contact_person.value == "张明"
    assert output.phone.value == "13800000000"
    assert output.email.value == "contact@example.com"
    assert output.address.value == "待补充"
    assert output.address.source_type is SourceType.PENDING_CUSTOMER
    assert output.website.value == "https://example.com"
    assert output.website.source_type is SourceType.CLIENT_PROVIDED
    assert llm.call_count == 0


def test_absent_contact_outputs_all_pending_except_reused_website():
    output = orchestrator._build_contact_output(
        None,
        SimpleNamespace(website=None),
    )

    for field in (
        output.contact_person,
        output.phone,
        output.email,
        output.address,
        output.website,
    ):
        assert field.source_type is SourceType.PENDING_CUSTOMER
