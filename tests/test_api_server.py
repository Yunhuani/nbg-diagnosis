import api_server
import pytest
import time
from threading import Event, Lock


def _dimension_output(dimension):
    return {
        "dimension": dimension,
        "degradation": {
            "degraded": False,
            "missing_plus": [],
            "upgrade_hook": "",
        },
    }


def test_build_data_quality_classifies_dimension_and_overall_levels():
    outputs = [
        _dimension_output("market"),
        _dimension_output("competition"),
        _dimension_output("business_model"),
        _dimension_output("capability"),
        _dimension_output("finance"),
    ]

    outputs[0]["degradation"] = {
        "degraded": True,
        "missing_plus": [],
        "upgrade_hook": "可在方案深化阶段进一步量化市场窗口",
    }
    outputs[2]["degradation"] = {
        "degraded": True,
        "missing_plus": ["business_model.revenue_mix"],
        "upgrade_hook": "补充收入结构后可进一步量化",
    }

    result = api_server._build_data_quality(
        outputs,
        {"market": [], "competition": [{"claim": "公开事实"}]},
        {"tier": "full", "cash_runway_months": 6},
    )

    assert result["overall_level"] == "limited"
    assert [item["level"] for item in result["dimensions"]] == [
        "limited",
        "full",
        "partial",
        "full",
        "full",
    ]
    assert result["dimensions"][2]["missing_plus"] == ["business_model.revenue_mix"]
    assert result["dimensions"][2]["upgrade_hook"] == "补充收入结构后可进一步量化"


def test_build_data_quality_marks_basic_finance_as_limited_and_all_full_as_full():
    outputs = [
        _dimension_output(dimension)
        for dimension in (
            "market",
            "competition",
            "business_model",
            "capability",
            "finance",
        )
    ]

    full_result = api_server._build_data_quality(
        outputs,
        {"market": [{"claim": "市场事实"}], "competition": [{"claim": "竞争事实"}]},
        {"tier": "full", "cash_runway_months": 6},
    )
    assert full_result["overall_level"] == "full"
    assert all(item["level"] == "full" for item in full_result["dimensions"])

    outputs[-1]["degradation"] = {
        "degraded": True,
        "missing_plus": ["finance.product_lines"],
        "upgrade_hook": "补充产品线明细后可进一步量化",
    }
    limited_result = api_server._build_data_quality(
        outputs,
        {"market": [{"claim": "市场事实"}], "competition": [{"claim": "竞争事实"}]},
        {"tier": "basic_only", "cash_runway_months": None},
    )
    assert limited_result["overall_level"] == "limited"
    assert limited_result["dimensions"][-1]["level"] == "limited"


def test_calculate_financial_facts_accepts_null_cash_and_monthly_fixed():
    facts = api_server._calculate_financial_facts(
        {
            "finance_basic": {
                "cash": None,
                "monthly_fixed": None,
            },
            "finance_plus": None,
        }
    )

    assert facts["cash_runway_months"] is None


def test_mark_finance_basic_degradation_when_cash_runway_is_unavailable():
    outputs = [
        {
            "dimension": "finance",
            "degradation": {
                "degraded": False,
                "missing_plus": [],
                "upgrade_hook": "",
            },
        }
    ]

    api_server._mark_finance_basic_degradation(
        outputs,
        {"cash_runway_months": None},
    )

    degradation = outputs[0]["degradation"]
    assert degradation["degraded"] is True
    assert "现金安全边际已按当前经营信息做结构性判断" in degradation["upgrade_hook"]
    assert "进一步量化现金跑道和安全垫" in degradation["upgrade_hook"]


def test_run_diagnosis_completes_and_marks_finance_degraded_for_null_basic_finance(
    monkeypatch,
):
    intake = {
        "company": {"name": "甬辉"},
        "finance_basic": {
            "cash": None,
            "monthly_fixed": None,
        },
        "finance_plus": None,
    }

    monkeypatch.setattr(
        api_server,
        "_run_dimension_with_retry",
        lambda dimension, fact_base, source_corpora: _dimension_output(dimension),
    )
    monkeypatch.setattr(api_server, "calculate_overall_score", lambda outputs: {})
    monkeypatch.setattr(api_server, "synthesize_diagnosis", lambda outputs: {})
    monkeypatch.setattr(
        api_server,
        "run_redline_check",
        lambda *args, **kwargs: {"passed": True, "failures": []},
    )

    result = api_server._run_diagnosis(
        intake,
        {"market": [], "competition": []},
    )

    finance_output = next(
        output
        for output in result["dimension_outputs"]
        if output["dimension"] == "finance"
    )
    assert finance_output["degradation"]["degraded"] is True
    assert (
        "现金安全边际已按当前经营信息做结构性判断"
        in finance_output["degradation"]["upgrade_hook"]
    )
    assert "进一步量化现金跑道和安全垫" in finance_output["degradation"]["upgrade_hook"]
    assert result["data_quality"]["overall_level"] == "limited"
    assert len(result["data_quality"]["dimensions"]) == 5


def test_run_diagnosis_executes_five_dimensions_in_parallel_and_preserves_order(
    monkeypatch,
):
    dimensions = [
        "market",
        "competition",
        "business_model",
        "capability",
        "finance",
    ]
    release = Event()
    lock = Lock()
    active = 0
    peak_active = 0
    synthesis_inputs = []

    def fake_dimension(dimension, fact_base, source_corpora):
        nonlocal active, peak_active
        with lock:
            active += 1
            peak_active = max(peak_active, active)
            if active == 3:
                release.set()
        assert release.wait(timeout=1)
        time.sleep(0.05)
        try:
            return {
                **_dimension_output(dimension),
                "score": {"value": 5},
            }
        finally:
            with lock:
                active -= 1

    def fake_synthesis(outputs, **kwargs):
        synthesis_inputs.append(outputs)
        return {"status": "complete"}

    monkeypatch.setattr(api_server, "_run_dimension_with_retry", fake_dimension)
    monkeypatch.setattr(api_server, "_run_synthesis_with_retry", fake_synthesis)
    monkeypatch.setattr(
        api_server,
        "_calculate_financial_facts",
        lambda intake: {"cash_runway_months": 1.6},
    )

    result = api_server._run_diagnosis(
        {"availability_map": {}},
        {"market": [], "competition": []},
    )

    assert [item["dimension"] for item in result["dimension_outputs"]] == dimensions
    assert synthesis_inputs == [result["dimension_outputs"]]
    assert peak_active == 3


def test_run_diagnosis_does_not_start_synthesis_when_parallel_dimension_fails(
    monkeypatch,
):
    release = Event()
    lock = Lock()
    started = 0
    synthesis_called = False

    def fake_dimension(dimension, fact_base, source_corpora):
        nonlocal started
        with lock:
            started += 1
            if started == 3:
                release.set()
        assert release.wait(timeout=1)
        if dimension == "capability":
            raise RuntimeError("capability failed after 3 attempts")
        return {
            **_dimension_output(dimension),
            "score": {"value": 5},
        }

    def fake_synthesis(outputs, **kwargs):
        nonlocal synthesis_called
        synthesis_called = True
        return {}

    monkeypatch.setattr(api_server, "_run_dimension_with_retry", fake_dimension)
    monkeypatch.setattr(api_server, "_run_synthesis_with_retry", fake_synthesis)
    monkeypatch.setattr(
        api_server,
        "_calculate_financial_facts",
        lambda intake: {"cash_runway_months": 1.6},
    )

    with pytest.raises(
        RuntimeError,
        match="capability failed after 3 attempts",
    ):
        api_server._run_diagnosis(
            {"availability_map": {}},
            {"market": [], "competition": []},
        )

    assert synthesis_called is False


def test_dimension_retry_recovers_from_schema_validation_error(monkeypatch):
    attempts = 0

    def fake_run_dimension(dimension, fact_base, source_corpora):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("evidence[1] missing keys: ['benchmark']")
        return _dimension_output(dimension)

    monkeypatch.setattr(api_server, "_run_dimension", fake_run_dimension)
    monkeypatch.setattr(
        api_server,
        "run_redline_check",
        lambda *args, **kwargs: {"passed": True, "failures": []},
    )

    result = api_server._run_dimension_with_retry(
        "business_model",
        {
            "financial_facts": {},
            "availability_map": {},
            "diagnosis_intake": {},
        },
        {"market": [], "competition": []},
    )

    assert result["dimension"] == "business_model"
    assert attempts == 2


def test_dimension_retry_raises_clear_error_after_schema_attempts_exhausted(
    monkeypatch,
):
    attempts = 0

    def fake_run_dimension(dimension, fact_base, source_corpora):
        nonlocal attempts
        attempts += 1
        raise ValueError("invalid schema")

    monkeypatch.setattr(api_server, "_run_dimension", fake_run_dimension)

    with pytest.raises(
        RuntimeError,
        match="dimension business_model failed after 3 attempts",
    ):
        api_server._run_dimension_with_retry(
            "business_model",
            {
                "financial_facts": {},
                "availability_map": {},
                "diagnosis_intake": {},
            },
            {"market": [], "competition": []},
        )

    assert attempts == 3


def test_synthesis_retry_recovers_from_schema_error(monkeypatch):
    attempts = 0

    def fake_synthesis(outputs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("synthesis output missing keys")
        return {"attempt": attempts}

    monkeypatch.setattr(api_server, "synthesize_diagnosis", fake_synthesis)
    monkeypatch.setattr(
        api_server,
        "run_redline_check",
        lambda *args, **kwargs: {"passed": True, "failures": []},
    )

    result = api_server._run_synthesis_with_retry(
        [_dimension_output("market")],
        financial_facts={},
        source_corpora={"market": [], "competition": []},
        availability_map={},
        diagnosis_intake={},
    )

    assert result == {"attempt": 2}
    assert attempts == 2


def test_synthesis_retry_retries_final_redline_failure(monkeypatch):
    synthesis_attempts = 0
    redline_attempts = 0

    def fake_synthesis(outputs):
        nonlocal synthesis_attempts
        synthesis_attempts += 1
        return {"attempt": synthesis_attempts}

    def fake_redline(*args, **kwargs):
        nonlocal redline_attempts
        redline_attempts += 1
        if redline_attempts == 1:
            return {
                "passed": False,
                "failures": [{"check": "synthesis_headline", "path": "headline"}],
            }
        return {"passed": True, "failures": []}

    monkeypatch.setattr(api_server, "synthesize_diagnosis", fake_synthesis)
    monkeypatch.setattr(api_server, "run_redline_check", fake_redline)

    result = api_server._run_synthesis_with_retry(
        [_dimension_output("market")],
        financial_facts={},
        source_corpora={"market": [], "competition": []},
        availability_map={},
        diagnosis_intake={},
    )

    assert result == {"attempt": 2}
    assert synthesis_attempts == 2


def test_diagnosis_job_records_clear_error_status(monkeypatch):
    job_id = "retry-exhausted"
    api_server._jobs[job_id] = {
        "status": "pending",
        "result": None,
        "error": None,
    }
    monkeypatch.setattr(
        api_server,
        "_run_diagnosis",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("synthesis failed after 3 attempts")
        ),
    )

    api_server._run_diagnosis_job(
        job_id,
        {},
        {"market": [], "competition": []},
    )

    assert api_server._jobs[job_id] == {
        "status": "error",
        "result": None,
        "error": "synthesis failed after 3 attempts",
    }
