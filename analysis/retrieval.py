from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib import parse

from analysis.search_client import bocha_web_search
from .llm_client import call_deepseek_json


logger = logging.getLogger(__name__)

SOURCE_TIER_DOMAINS: dict[str, tuple[str, ...]] = {
    "T1": (
        # 中国政府与统计
        "gov.cn", "stats.gov.cn", "customs.gov.cn", "mofcom.gov.cn",
        "miit.gov.cn", "ndrc.gov.cn", "cnbs.gov.cn",
        # 中国交易所公告
        "sse.com.cn", "szse.cn", "cninfo.com.cn", "hkexnews.hk",
        "ifr.org", "cninfo.com.cn", "sse.com.cn", "szse.cn",
        # 行业协会
        "cccme.org.cn", "chinaccm.org.cn", "cbmf.org",
        # 国际官方
        "sec.gov", "census.gov", "bea.gov", "europa.eu",
        "worldbank.org", "oecd.org", "imf.org", "wto.org", "trademap.org",
    ),
    "T2": (
        # 中国行业研究
        "qianzhan.com", "chinabgao.com", "chyxx.com", "askci.com",
        "leadleo.com", "iresearch.com.cn", "analysys.cn", "cir.cn",
        "chinairn.com", "askci.com", "chinabgao.com", "chinabaogao.com",
        "huaon.com", "leadingir.com", "iimedia.cn", "sgpjbg.com",
        # 国际行业研究
        "gartner.com", "idc.com", "forrester.com", "frost.com",
        "mordorintelligence.com", "grandviewresearch.com",
        "fortunebusinessinsights.com", "marketsandmarkets.com",
        "researchandmarkets.com", "technavio.com", "statista.com",
        "ibisworld.com", "indexbox.io",
    ),
    "T3": (
        # 中国财经媒体
        "caixin.com", "yicai.com", "stcn.com", "cs.com.cn",
        "nbd.com.cn", "21jingji.com", "jiemian.com", "36kr.com",
        # 国际财经媒体
        "reuters.com", "bloomberg.com", "wsj.com", "ft.com",
        "cnbc.com", "businesswire.com", "prnewswire.com",
    ),
}

SOURCE_TIER_SITE_NAMES: dict[str, tuple[str, ...]] = {
    "T1": (
        "国家统计局", "海关总署", "商务部", "工业和信息化部",
        "国家发改委", "证券交易所", "巨潮资讯",
        "sec", "eurostat", "world bank", "oecd",
    ),
    "T2": (
        "前瞻产业研究院", "中国报告大厅", "观研天下", "艾媒", "艾瑞",
        "易观", "头豹",
        "gartner", "idc", "forrester", "frost", "statista", "ibisworld",
    ),
    "T3": (
        "财新", "第一财经", "证券时报", "中国证券报", "每日经济新闻",
        "21世纪经济报道", "界面新闻",
        "reuters", "bloomberg", "wall street journal", "financial times", "cnbc",
    ),
}

BLACKLIST_DOMAINS: tuple[str, ...] = (
    "docin.com", "doc88.com", "book118.com",
    "jinchutou.com", "toutiao.com", "sohu.com",
    "zhihu.com", "163.com", "baijiahao.baidu.com",
    "xueqiu.com", "1633.com", "jc123.com.cn",
    "dirak.com.cn", "leying.cn", "bf7.net", "uweb.net.cn",
)

QUALITY_MATRIX: dict[str, dict[str, str | None]] = {
    "T1": {
        "fresh": "high",
        "aging": "high",
        "stale": "needs_review",
        "unknown": "needs_review",
    },
    "T2": {
        "fresh": "high",
        "aging": "medium",
        "stale": "needs_review",
        "unknown": "needs_review",
    },
    "T3": {
        "fresh": "medium",
        "aging": "needs_review",
        "stale": None,
        "unknown": None,
    },
    "T4": {
        "fresh": None,
        "aging": None,
        "stale": None,
        "unknown": None,
    },
}


def retrieve_market_corpus(
    industry: str,
    product_category: str,
    target_regions: list[str],
) -> list[dict]:
    try:
        industry, product_category, target_regions = normalize_search_terms(
            industry,
            product_category,
            target_regions,
        )
        now = datetime.now(UTC)
        year_hint = f"{now.year} {now.year - 1}"
        queries = [
            f"{industry} 市场规模 增速 CAGR {year_hint}",
            f"{industry} {product_category} 市场规模 {year_hint}",
            f"{industry} {' '.join(target_regions)} 市场需求 趋势 {year_hint}",
        ]
        return _retrieve_corpus(queries)
    except Exception:
        return []


def normalize_search_terms(
    raw_industry: str,
    raw_product: str,
    raw_regions: list[str],
) -> tuple[str, str, list[str]]:
    original = (raw_industry, raw_product, raw_regions)
    try:
        result = call_deepseek_json(
            "你是检索关键词归一化器，只输出 JSON。",
            (
                "输入是客户在问卷里的自述，可能混杂地域、企业身份、渠道、无关补充说明。\n\n"
                "任务：提取三个干净的检索关键词。\n\n"
                "industry：标准行业称谓。必须能在行业研究报告中被检索到。\n"
                "  - 去除地域词（浙江、广东、华东）\n"
                "  - 去除身份词（出口商、制造商、公司、厂）\n"
                "  - 去除渠道与经营模式词（外贸、跨境、代工、OEM、直营、连锁、加盟、电商、线上、线下）\n"
                "  - 保留行业本身的品类层级\n\n"
                "product_category：主营产品品类，简短名词短语。\n"
                "  - 服务类业务填服务品类（如皮肤管理、企业SaaS），不必是实物产品\n"
                "  - 去除\"及定制小单\"\"等\"\"其他\"这类非产品表述\n"
                "  - 最多保留三个核心品类，用顿号分隔\n\n"
                "regions：业务覆盖区域列表。\n"
                "  - 把合并表述拆成独立地区（如\"华东华南\"拆成\"华东\"、\"华南\"）\n"
                "  - 只保留地理名词,去除\"同一省会城市\"\"9家门店\"这类描述性或含数量的表述\n\n"
                "禁止编造输入中不存在的行业或产品。\n"
                "若某个字段无法归一化，原样返回输入值。\n\n"
                "输入：\n"
                f"industry: {raw_industry}\n"
                f"product: {raw_product}\n"
                f"regions: {raw_regions}\n\n"
                "返回 JSON: {\"industry\":\"...\",\"product_category\":\"...\",\"regions\":[\"...\",\"...\"]}"
            ),
        )
        normalized_industry = str(result.get("industry") or "").strip() or raw_industry
        normalized_product = str(result.get("product_category") or "").strip() or raw_product
        raw_normalized_regions = result.get("regions")
        if isinstance(raw_normalized_regions, list):
            normalized_regions = [
                text
                for item in raw_normalized_regions
                if (text := str(item).strip())
            ]
        else:
            normalized_regions = []
        return (
            normalized_industry,
            normalized_product,
            normalized_regions or raw_regions,
        )
    except Exception:
        return original


def classify_source_tier(url: str, site_name: str) -> str:
    domain = _domain_from_url(url)
    if _matches_domain_rules(domain, BLACKLIST_DOMAINS):
        return "T4"
    site = site_name.strip().lower()
    for tier in ("T1", "T2", "T3"):
        if _matches_domain_rules(domain, SOURCE_TIER_DOMAINS[tier]):
            return tier
        if _matches_site_name_rules(site, SOURCE_TIER_SITE_NAMES[tier]):
            return tier
    return "T4"


def normalize_source_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    parsed = parse.urlparse(text)
    hostname = (parsed.hostname or "").lower()
    for prefix in ("www.", "m."):
        if hostname.startswith(prefix):
            hostname = hostname.removeprefix(prefix)
            break
    path = re.sub(r"_\d+(\.[^./]+)$", r"\1", parsed.path or "")
    return f"{hostname}{path}"


def classify_freshness(year: int | None, published_at: str | None, now: datetime) -> str:
    reference = now
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)

    resolved_year = year
    if resolved_year is None and published_at and str(published_at).strip():
        parsed = _parse_published_at(str(published_at))
        if parsed is not None:
            resolved_year = parsed.year
    if resolved_year is None:
        return "unknown"

    age = reference.year - resolved_year
    if age < 0:
        return "fresh"
    if age <= 1:
        return "fresh"
    if age == 2:
        return "aging"
    return "stale"


def compute_quality(tier: str, freshness: str) -> str | None:
    return QUALITY_MATRIX.get(tier, {}).get(freshness)


def _retrieve_corpus(queries: list[str]) -> list[dict]:
    all_search_results: list[dict[str, Any]] = []
    all_extracted_items: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for query in queries:
        try:
            search_results = bocha_web_search(query)
        except Exception as exc:
            logger.warning("Bocha search failed for query %r: %s", query, exc)
            continue
        if not search_results:
            logger.warning("Bocha search returned empty results for query %r", query)
            continue
        extraction_results = _filter_search_results_for_extraction(search_results)
        if not extraction_results:
            logger.warning("Bocha search returned no non-T4 results for query %r", query)
            continue
        extracted_items = _extract_facts(extraction_results)
        offset = len(all_search_results)
        all_search_results.extend(extraction_results)
        all_extracted_items.extend(
            {**item, "source_index": item["source_index"] + offset}
            for item in extracted_items
        )
    return _build_entries(all_search_results, all_extracted_items, now)


def _filter_search_results_for_extraction(search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in search_results
        if classify_source_tier(
            str(item.get("url") or ""),
            str(item.get("siteName") or ""),
        ) != "T4"
    ]


def _extract_facts(search_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = [
        {
            "index": index,
            "name": item.get("name"),
            "siteName": item.get("siteName"),
            "summary": item.get("summary"),
            "snippet": item.get("snippet"),
            "datePublished": item.get("datePublished"),
        }
        for index, item in enumerate(search_results)
    ]
    result = call_deepseek_json(
        "你是市场情报事实抽取器，只输出 JSON。",
        (
            "从搜索摘要中提取市场规模类事实。严格规则：\n\n"
            "【必须满足全部条件才提取】\n"
            "1. 含具体数值（金额、增速、CAGR、保有量、渗透率），不是\"快速增长\"\"前景广阔\"这类定性描述\n"
            "2. 数值有明确的所属年份（如\"2024年市场规模达XX亿元\"）\n"
            "3. 数值直接描述市场规模、增速、保有量或渗透率\n\n"
            "【必须丢弃】\n"
            "- 无年份的数值（如\"占世界总量的35%\"）\n"
            "- 缺少基准年的预测数字\n"
            "- 定性描述、行业定义、报告目录、招商广告\n\n"
            "【禁止】\n"
            "- 编造任何数字\n"
            "- 改写、换算、四舍五入原文数字\n"
            "- 接收、推断或输出客户公司名与客户财务数据\n\n"
            "【year 字段】\n"
            "填入该数值所属年份（整数）。无法确定年份的条目直接丢弃。\n"
            "若为预测值（如\"预计2028年达到\"），year 填预测年份，并在 is_forecast 填 true。\n\n"
            "返回 JSON:\n"
            "{\"items\":[{\"source_index\":0,\"claim\":\"...\",\"value\":\"...\",\"year\":2024,\"is_forecast\":false}]}\n"
            f"搜索结果：{json.dumps(payload, ensure_ascii=False)}"
        ),
    )
    items = result.get("items")
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("claim", "")).strip()
        and str(item.get("value", "")).strip()
        and isinstance(item.get("source_index"), int)
        and isinstance(item.get("year"), int)
        and not isinstance(item.get("year"), bool)
        and isinstance(item.get("is_forecast"), bool)
    ]


def _build_entries(
    search_results: list[dict[str, Any]],
    extracted_items: list[dict[str, Any]],
    now: datetime,
) -> list[dict]:
    entries: list[dict] = []
    deduplicated_items = _deduplicate_extracted_items(search_results, extracted_items)
    multi_source_keys = _multi_source_fact_keys(search_results, deduplicated_items)
    for item in deduplicated_items:
        source_index = item["source_index"]
        if source_index < 0 or source_index >= len(search_results):
            continue

        source = search_results[source_index]
        url = str(source.get("url") or "").strip()
        site_name = str(source.get("siteName") or "").strip()
        published_at = source.get("datePublished")
        published_text = str(published_at).strip() if published_at else None
        year = item["year"]
        is_forecast = item["is_forecast"]
        tier = classify_source_tier(url, site_name)
        freshness = classify_freshness(year, published_text, now)
        quality = compute_quality(tier, freshness)
        if quality is None:
            continue
        quality_note = _quality_note(freshness) if quality == "needs_review" else None
        if is_forecast:
            forecast_note = "该数值为预测值，非实际统计"
            quality_note = f"{quality_note}；{forecast_note}" if quality_note else forecast_note
        if (_normalize_claim(str(item["claim"])), str(item["value"]).strip(), year) in multi_source_keys:
            multi_source_note = "该数值有多个独立来源印证"
            quality_note = (
                f"{quality_note}；{multi_source_note}"
                if quality_note
                else multi_source_note
            )
        entries.append(
            {
                "claim": str(item["claim"]).strip(),
                "value": str(item["value"]).strip(),
                "year": year,
                "is_forecast": is_forecast,
                "source_url": url,
                "source_name": site_name,
                "published_at": published_text,
                "source_tier": tier,
                "freshness": freshness,
                "quality": quality,
                "quality_note": quality_note,
            }
        )
    return entries


def _deduplicate_extracted_items(
    search_results: list[dict[str, Any]],
    extracted_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, str]] = set()
    for item in extracted_items:
        source_index = item["source_index"]
        if source_index < 0 or source_index >= len(search_results):
            continue
        source_url = normalize_source_url(str(search_results[source_index].get("url") or ""))
        key = (
            _normalize_claim(str(item["claim"])),
            str(item["value"]).strip(),
            item["year"],
            source_url,
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(item)
    return deduplicated


def _multi_source_fact_keys(
    search_results: list[dict[str, Any]],
    extracted_items: list[dict[str, Any]],
) -> set[tuple[str, str, int]]:
    sources_by_fact: dict[tuple[str, str, int], set[str]] = {}
    for item in extracted_items:
        source_index = item["source_index"]
        if source_index < 0 or source_index >= len(search_results):
            continue
        fact_key = (
            _normalize_claim(str(item["claim"])),
            str(item["value"]).strip(),
            item["year"],
        )
        source_domain = _domain_from_normalized_url(
            normalize_source_url(str(search_results[source_index].get("url") or ""))
        )
        sources_by_fact.setdefault(fact_key, set()).add(source_domain)
    return {
        fact_key
        for fact_key, source_urls in sources_by_fact.items()
        if len(source_urls) > 1
    }


def _normalize_claim(claim: str) -> str:
    return re.sub(r"\s+", "", claim)


def _domain_from_normalized_url(url: str) -> str:
    return url.split("/", 1)[0]


def _quality_note(freshness: str) -> str:
    if freshness == "aging":
        return "数据已超一年，建议复核"
    if freshness == "stale":
        return "数据已超三年，建议复核"
    if freshness == "unknown":
        return "来源未提供发布日期，建议复核"
    return "来源可信度有限，建议复核"


def _matches_domain_rules(domain: str, rules: tuple[str, ...]) -> bool:
    for rule in rules:
        normalized = rule.lower()
        if "." in normalized:
            if domain == normalized or domain.endswith(f".{normalized}"):
                return True
            continue
        if domain == normalized or domain.endswith(f".{normalized}"):
            return True
    return False


def _matches_site_name_rules(site_name: str, rules: tuple[str, ...]) -> bool:
    for rule in rules:
        if rule.lower() in site_name:
            return True
    return False


def _domain_from_url(url: str) -> str:
    text = str(url or "").strip().lower()
    if not text:
        return ""
    if "://" not in text:
        text = f"https://{text}"
    hostname = parse.urlparse(text).hostname or ""
    return hostname.removeprefix("www.")


def _parse_published_at(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    candidates = [text, text.replace("Z", "+00:00")]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None
