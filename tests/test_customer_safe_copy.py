from pathlib import Path

from analysis.dimensions import (
    FINANCE_PROMPT,
    MARKET_PROMPT,
    SOURCE_CORPUS_DISCIPLINE_PROMPT,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPOSED_GAP_TERMS = (
    "未检索到,留待补充",
    "未检索到，留待补充",
    "降级分析",
    "部分数据缺失",
    "暂无证据",
    "待补充",
)


def test_prompts_do_not_instruct_model_to_expose_data_gaps():
    prompt_text = "\n".join(
        [SOURCE_CORPUS_DISCIPLINE_PROMPT, MARKET_PROMPT, FINANCE_PROMPT]
    )

    assert '写"未检索到,留待补充"' not in prompt_text
    assert "客户可见表述不得出现" in prompt_text
    assert "方案深化阶段" in prompt_text
    assert "进一步量化" in prompt_text


def test_customer_facing_engine_fallback_copy_avoids_exposed_gap_terms():
    paths = [
        REPO_ROOT / "api_server.py",
        REPO_ROOT / "report" / "generate_sample.js",
        REPO_ROOT / "report" / "generate_solution_report.js",
    ]
    combined_text = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    for term in EXPOSED_GAP_TERMS:
        assert term not in combined_text

