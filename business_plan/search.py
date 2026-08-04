from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from typing import Any
from urllib.parse import urlparse

from analysis.search_client import bocha_web_search
from business_plan.schemas import SearchEvidence, SourceReference, SourceType


ALLOWED_SEARCH_MODULE_IDS = frozenset({3, 4})
LOW_QUALITY_DOMAIN_MARKERS = (
    "baidu.com",
    "zhihu.com",
    "toutiao.com",
    "sohu.com",
    "sina.com",
    "163.com",
    "qq.com",
    "csdn.net",
    "jianshu.com",
    "bilibili.com",
    "book118.com",
    "doc88.com",
    "docin.com",
    "11467.com",
    "waitang.com",
    "hangyan.co",
)
SOURCE_NAME_KEYS = ("siteName", "source", "publisher", "site_name")
CONTENT_KEYS = ("name", "title", "summary", "snippet", "description")
FORECAST_TERMS = ("预测", "预计", "预期", "未来", "CAGR", "复合增长")
SOURCE_NAME_TERMS = ("报告", "白皮书", "研究", "统计", "协会", "中心", "院", "局")
RELEVANCE_MATCH_RATIO_THRESHOLD = 0.5
GENERIC_CONTEXT_TERMS = (
    "企业",
    "市场",
    "行业",
    "规模",
    "产业",
    "公司",
    "领域",
    "平台",
    "服务",
    "系统",
    "解决方案",
    "数字化",
    "智能",
    "中国",
    "国内",
    "总体",
    "整体",
)
CONTEXT_COMPOUND_TERMS = (
    "工业设备",
    "设备联网",
    "工业互联网",
    "智能制造",
    "离散制造",
    "制造业",
    "工业软件",
    "物联网",
    "供应链",
)
GENERAL_TECHNICAL_TERMS = frozenset(
    {"saas", "iaas", "paas", "ai", "it", "ict", "云", "云计算", "数据", "软件", "技术", "中小"}
)
YEAR_RE = re.compile(r"(?:19|20)\d{2}")
MARKET_VALUE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:万亿|亿元|亿|万元|万|%)")
CHINESE_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
ENGLISH_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]{1,}")
PUBLISH_YEAR_RE = re.compile(
    r"(?:(?:发布|出品|编制|刊发|出版)[^。；，]{0,12}?|"
    r"(?:19|20)\d{2}年[^。；，]{0,12}?(?:发布|出品|编制|刊发|出版))"
)


@dataclass(frozen=True)
class SearchRejection:
    title: str
    url: str | None
    reason: str


@dataclass
class MarketSearchOutcome:
    query: str
    raw_result_count: int
    evidence: list[SearchEvidence]
    rejected: list[SearchRejection]


def search_market_evidence(module_id: int, industry_context: str) -> MarketSearchOutcome:
    """Search market evidence only for the explicitly authorised BP modules."""

    if module_id not in ALLOWED_SEARCH_MODULE_IDS:
        raise PermissionError(f"BP module {module_id} is not allowed to use search")
    if not industry_context or not industry_context.strip():
        raise ValueError("industry_context is required for market search")

    current_year = datetime.now().year
    query = (
        f"{industry_context.strip()} 市场规模 {current_year - 2} {current_year} "
        "报告 发布 年份"
    )
    raw_results = bocha_web_search(query)
    evidence: list[SearchEvidence] = []
    rejected: list[SearchRejection] = []
    for item in raw_results:
        valid_evidence, reason = _validate_market_result(
            item,
            current_year,
            industry_context,
        )
        if valid_evidence is None:
            rejected.append(
                SearchRejection(
                    title=_item_title(item),
                    url=_item_url(item),
                    reason=reason,
                )
            )
        else:
            evidence.append(valid_evidence)
    return MarketSearchOutcome(
        query=query,
        raw_result_count=len(raw_results),
        evidence=evidence,
        rejected=rejected,
    )


def _validate_market_result(
    item: dict[str, Any],
    current_year: int,
    industry_context: str,
) -> tuple[SearchEvidence | None, str]:
    content = _item_content(item)
    source_name = _extract_source_name(item)
    url = _item_url(item)
    data_point = _extract_data_point(content)
    reasons: list[str] = []
    if not source_name:
        reasons.append("缺少可识别的数据发布方、机构名或报告名")
    if not _is_usable_source_url(url):
        reasons.append("来源 URL 不可用或属于内容聚合/低质站点")
    if not data_point:
        reasons.append("缺少带单位或百分比的具体市场数据")
    relevance_reason = _relevance_failure_reason(content, industry_context)
    if relevance_reason:
        reasons.append(relevance_reason)

    forecast = any(term.lower() in content.lower() for term in FORECAST_TERMS)
    year = _extract_publication_year(item, content) if forecast else _extract_data_year(data_point)
    if year is None:
        if forecast:
            reasons.append("无法识别市场预测报告发布年份")
        else:
            reasons.append("无法识别市场规模统计基准年份")
    elif year < current_year - 2:
        label = "预测报告发布年份" if forecast else "市场规模统计基准年份"
        reasons.append(f"时效性不足：{label} {year} 早于 {current_year - 2}")

    if reasons:
        return None, "；".join(reasons)
    return (
        SearchEvidence(
            data_point=data_point,
            year=year,
            source_type=SourceType.SEARCH_VALIDATION,
            source_ref=SourceReference(
                source_name=source_name,
                source_url=url,
                needs_verification=True,
            ),
        ),
        "",
    )


def _relevance_failure_reason(content: str, industry_context: str) -> str | None:
    business_terms = _extract_business_terms(industry_context)
    if not business_terms:
        return "相关性不足：行业上下文未提取到业务特征词"

    normalized_content = content.lower()
    matched = [term for term in business_terms if term.lower() in normalized_content]
    missing = [term for term in business_terms if term not in matched]
    match_ratio = len(matched) / len(business_terms)
    matched_business_objects = [
        term
        for term in matched
        if term.lower() not in GENERAL_TECHNICAL_TERMS
    ]
    if (
        match_ratio >= RELEVANCE_MATCH_RATIO_THRESHOLD
        and matched_business_objects
    ):
        return None

    detail = (
        f"相关性不足：命中词[{', '.join(matched) or '无'}]；"
        f"缺少词[{', '.join(missing) or '无'}]；"
        f"业务特征词命中比例 {match_ratio:.0%}"
    )
    if not matched_business_objects:
        detail += "；未命中具体业务对象词"
    return detail


def _extract_business_terms(industry_context: str) -> list[str]:
    terms: list[str] = []
    generic_pattern = "|".join(
        re.escape(term) for term in sorted(GENERIC_CONTEXT_TERMS, key=len, reverse=True)
    )
    for run in CHINESE_RUN_RE.findall(industry_context):
        for fragment in re.split(generic_pattern, run):
            fragment = fragment.strip()
            if 2 <= len(fragment) <= 12:
                _append_unique(terms, fragment)
        for compound in CONTEXT_COMPOUND_TERMS:
            if compound in run:
                _append_unique(terms, compound)
        if "制造" in run:
            _append_unique(terms, "制造")
        if "联网" in run:
            _append_unique(terms, "联网")
    for term in ENGLISH_TERM_RE.findall(industry_context):
        _append_unique(terms, term)
    return [term for term in terms if term not in GENERIC_CONTEXT_TERMS]


def _append_unique(terms: list[str], term: str) -> None:
    if term not in terms:
        terms.append(term)


def _item_content(item: dict[str, Any]) -> str:
    return "\n".join(
        str(item[key]).strip()
        for key in CONTENT_KEYS
        if isinstance(item.get(key), str) and item[key].strip()
    )


def _item_title(item: dict[str, Any]) -> str:
    for key in ("name", "title"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "未命名搜索结果"


def _item_url(item: dict[str, Any]) -> str | None:
    for key in ("url", "link"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_source_name(item: dict[str, Any]) -> str | None:
    for key in SOURCE_NAME_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    title = _item_title(item)
    if any(term in title for term in SOURCE_NAME_TERMS):
        return title
    return None


def _is_usable_source_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return (
        parsed.scheme in {"http", "https"}
        and bool(hostname)
        and not any(marker in hostname.lower() for marker in LOW_QUALITY_DOMAIN_MARKERS)
    )


def _extract_data_point(content: str) -> str | None:
    for sentence in re.split(r"[。；\n]", content):
        if "市场" in sentence and MARKET_VALUE_RE.search(sentence):
            return sentence.strip()
    return None


def _extract_data_year(data_point: str | None) -> int | None:
    if not data_point:
        return None
    years = [int(year) for year in YEAR_RE.findall(data_point)]
    return max(years) if years else None


def _extract_publication_year(item: dict[str, Any], content: str) -> int | None:
    for key in ("datePublished", "publishedDate", "publishTime"):
        value = item.get(key)
        if isinstance(value, str):
            years = YEAR_RE.findall(value)
            if years:
                return int(years[-1])
    for match in PUBLISH_YEAR_RE.finditer(content):
        years = YEAR_RE.findall(match.group())
        if years:
            return int(years[-1])
    return None
