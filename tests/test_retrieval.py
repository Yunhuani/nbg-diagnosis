from datetime import UTC, datetime
from urllib import error

import pytest

from analysis import retrieval


@pytest.mark.parametrize(
    ("url", "site_name", "expected"),
    [
        ("https://stats.gov.cn/sj/", "国家统计局", "T1"),
        ("https://sub.sec.gov/Archives/", "SEC", "T1"),
        ("https://www.gartner.com/en/research", "Gartner", "T2"),
        ("https://example.com/report", "Statista", "T2"),
        ("https://www.reuters.com/markets/", "Reuters", "T3"),
        ("https://unknown.example/report", "Unknown", "T4"),
        ("https://www.customs.gov.cn/xxx", "海关总署", "T1"),
        ("https://www.qianzhan.com/xxx", "前瞻产业研究院", "T2"),
        ("https://www.yicai.com/xxx", "第一财经", "T3"),
        ("https://xgov.cn/fake", "某站", "T4"),
        ("https://www.sohu.com/xxx", "搜狐", "T4"),
        ("https://www.docin.com/p-123", "豆丁网", "T4"),
        ("https://www.toutiao.com/article/1", "今日头条", "T4"),
        ("https://www.chinairn.com/x", "中研网", "T2"),
        ("https://www.askci.com/x", "中商情报网", "T2"),
    ],
)
def test_classify_source_tier(url, site_name, expected):
    assert retrieval.classify_source_tier(url, site_name) == expected


@pytest.mark.parametrize(
    ("year", "published_at", "expected"),
    [
        (2026, None, "fresh"),
        (2025, None, "fresh"),
        (2024, None, "aging"),
        (2023, None, "stale"),
        (2020, None, "stale"),
        (2028, None, "fresh"),
        (None, "2025-06-01", "fresh"),
        (None, None, "unknown"),
    ],
)
def test_classify_freshness(year, published_at, expected):
    now = datetime(2026, 7, 9, tzinfo=UTC)
    assert retrieval.classify_freshness(year, published_at, now) == expected


@pytest.mark.parametrize(
    ("tier", "freshness", "expected"),
    [
        ("T1", "fresh", "high"),
        ("T1", "aging", "high"),
        ("T1", "stale", "needs_review"),
        ("T1", "unknown", "needs_review"),
        ("T2", "fresh", "high"),
        ("T2", "aging", "medium"),
        ("T2", "stale", "needs_review"),
        ("T2", "unknown", "needs_review"),
        ("T3", "fresh", "medium"),
        ("T3", "aging", "needs_review"),
        ("T3", "stale", None),
        ("T3", "unknown", None),
        ("T4", "fresh", None),
        ("T4", "aging", None),
        ("T4", "stale", None),
        ("T4", "unknown", None),
    ],
)
def test_compute_quality_all_branches(tier, freshness, expected):
    assert retrieval.compute_quality(tier, freshness) == expected


def test_normalize_source_url_removes_mobile_www_query_fragment_and_page_suffix():
    assert retrieval.normalize_source_url(
        "https://m.askci.com/news/a_3.shtml?from=search#top"
    ) == retrieval.normalize_source_url("https://www.askci.com/news/a.shtml")


def test_normalize_search_terms_returns_original_when_llm_raises(monkeypatch):
    def fake_llm(system_prompt, user_prompt):
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr(retrieval, "call_deepseek_json", fake_llm)

    assert retrieval.normalize_search_terms(
        "浙江卫浴五金出口商",
        "淋浴隔断五金、排水配件、浴室置物架及定制小单",
        ["欧美及中东"],
    ) == (
        "浙江卫浴五金出口商",
        "淋浴隔断五金、排水配件、浴室置物架及定制小单",
        ["欧美及中东"],
    )


def test_normalize_search_terms_falls_back_to_original_for_empty_values(monkeypatch):
    def fake_llm(system_prompt, user_prompt):
        return {"industry": "", "product_category": "", "regions": []}

    monkeypatch.setattr(retrieval, "call_deepseek_json", fake_llm)

    assert retrieval.normalize_search_terms(
        "浙江卫浴五金出口商",
        "淋浴隔断五金、排水配件、浴室置物架及定制小单",
        ["欧美及中东"],
    ) == (
        "浙江卫浴五金出口商",
        "淋浴隔断五金、排水配件、浴室置物架及定制小单",
        ["欧美及中东"],
    )


def test_retrieve_market_corpus_third_query_uses_market_demand_without_export(monkeypatch):
    queries = []

    monkeypatch.setattr(
        retrieval,
        "normalize_search_terms",
        lambda industry, product, regions: (industry, product, regions),
    )
    monkeypatch.setattr(retrieval, "_retrieve_corpus", lambda received: queries.extend(received) or [])

    retrieval.retrieve_market_corpus("美容连锁", "皮肤管理", ["华东"])

    assert len(queries) == 3
    assert "出口" not in queries[2]
    assert queries[2] == "美容连锁 华东 市场需求 趋势 2026 2025"


def test_build_entries_deduplicates_same_article_mobile_and_pc_without_multi_source_note():
    search_results = [
        {
            "url": "https://m.chinabgao.com/info/1299373_3.html",
            "siteName": "报告大厅",
            "datePublished": "2026-04-07T02:21:26+08:00",
        },
        {
            "url": "https://www.chinabgao.com/info/1299373.html",
            "siteName": "报告大厅",
            "datePublished": "2026-04-07T02:21:26+08:00",
        },
    ]
    extracted_items = [
        {
            "source_index": 0,
            "claim": "2024年全球工业机器人市场规模达1016亿元",
            "value": "1016亿元",
            "year": 2024,
            "is_forecast": False,
        },
        {
            "source_index": 1,
            "claim": "2024年全球工业机器人市场规模达1016亿元",
            "value": "1016亿元",
            "year": 2024,
            "is_forecast": False,
        },
    ]

    result = retrieval._build_entries(
        search_results,
        extracted_items,
        datetime(2026, 7, 9, tzinfo=UTC),
    )

    assert len(result) == 1
    assert result[0]["quality_note"] is None


def test_build_entries_keeps_same_fact_from_different_domains_and_marks_multi_source():
    search_results = [
        {
            "url": "https://www.askci.com/news/a.shtml",
            "siteName": "中商情报网",
            "datePublished": "2026-01-05T11:07:00+08:00",
        },
        {
            "url": "https://www.chinabgao.com/info/a.html",
            "siteName": "报告大厅",
            "datePublished": "2026-04-07T02:21:26+08:00",
        },
    ]
    extracted_items = [
        {
            "source_index": 0,
            "claim": "2024年全球工业机器人市场规模达1016亿元",
            "value": "1016亿元",
            "year": 2024,
            "is_forecast": False,
        },
        {
            "source_index": 1,
            "claim": "2024年全球工业机器人市场规模达1016亿元",
            "value": "1016亿元",
            "year": 2024,
            "is_forecast": False,
        },
    ]

    result = retrieval._build_entries(
        search_results,
        extracted_items,
        datetime(2026, 7, 9, tzinfo=UTC),
    )

    assert len(result) == 2
    assert all("该数值有多个独立来源印证" in item["quality_note"] for item in result)


def test_retrieve_market_corpus_returns_empty_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("BOCHA_API_KEY", raising=False)
    monkeypatch.setattr(
        retrieval,
        "normalize_search_terms",
        lambda industry, product, regions: (industry, product, regions),
    )

    assert retrieval.retrieve_market_corpus("卫浴五金", "淋浴房五金", ["北美"]) == []


def test_retrieve_market_corpus_continues_after_one_query_failure(monkeypatch):
    calls = []

    def fake_search(query):
        calls.append(query)
        if len(calls) == 1:
            raise RuntimeError("temporary search failure")
        return [{"url": f"https://www.askci.com/{len(calls)}"}]

    def fake_extract(search_results):
        return [
            {
                "source_index": 0,
                "claim": f"claim {search_results[0]['url']}",
                "value": "增长 10%",
                "year": 2026,
                "is_forecast": False,
            }
        ]

    def fake_build_entries(search_results, extracted_items, now):
        return [
            {
                "claim": item["claim"],
                "value": item["value"],
                "year": item["year"],
                "is_forecast": item["is_forecast"],
                "source_url": search_results[item["source_index"]]["url"],
                "source_name": "Example",
                "published_at": "2026-01-01",
                "source_tier": "T2",
                "freshness": "fresh",
                "quality": "high",
                "quality_note": None,
            }
            for item in extracted_items
        ]

    monkeypatch.setattr(retrieval, "bocha_web_search", fake_search)
    monkeypatch.setattr(retrieval, "_extract_facts", fake_extract)
    monkeypatch.setattr(retrieval, "_build_entries", fake_build_entries)
    monkeypatch.setattr(
        retrieval,
        "normalize_search_terms",
        lambda industry, product, regions: (industry, product, regions),
    )

    result = retrieval.retrieve_market_corpus("卫浴五金", "地漏", ["中东"])

    assert len(calls) == 3
    assert [item["source_url"] for item in result] == [
        "https://www.askci.com/2",
        "https://www.askci.com/3",
    ]
