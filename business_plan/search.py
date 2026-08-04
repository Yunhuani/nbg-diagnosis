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
EVALUATIVE_TERMS = (
    "体验差",
    "口碑不佳",
    "优势",
    "劣势",
    "领先",
    "最好",
    "第一",
    "最强",
    "首选",
    "大型",
    "知名",
    "领军",
)
MARKETING_TERMS = ("赋能", "一站式", "卓越", "全方位", "致力于")
SELF_PUBLISHED_PAGE_TERMS = ("关于我们", "投资者关系", "公司介绍", "about", "investor")
COMPETITOR_LOW_QUALITY_DOMAIN_MARKERS = ("databanker.cn", "xueqiu.com")
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
COMPETITOR_VALUE_RE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:万亿|亿元|亿|万元|万|元|美元|%)"
)
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


@dataclass
class CompetitorSearchOutcome:
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


def search_competitor_evidence(
    module_id: int,
    competitor_name: str,
) -> CompetitorSearchOutcome:
    """Search objective public facts for one customer-specified competitor only."""

    if module_id not in ALLOWED_SEARCH_MODULE_IDS:
        raise PermissionError(f"BP module {module_id} is not allowed to use search")
    if not competitor_name or not competitor_name.strip():
        raise ValueError("competitor_name is required for competitor search")

    current_year = datetime.now().year
    competitor_name = competitor_name.strip()
    query = f"{competitor_name} 成立时间 产品线 公开定价 融资"
    raw_results = bocha_web_search(query)
    evidence: list[SearchEvidence] = []
    rejected: list[SearchRejection] = []
    for item in raw_results:
        valid_evidence, reason = _validate_competitor_result(
            item,
            current_year,
            competitor_name,
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
    return CompetitorSearchOutcome(
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


def _validate_competitor_result(
    item: dict[str, Any],
    current_year: int,
    competitor_name: str,
) -> tuple[SearchEvidence | None, str]:
    content = _item_content(item)
    source_name = _extract_source_name(item)
    url = _item_url(item)
    data_point, fact_type = _extract_competitor_fact(content)
    reasons: list[str] = []
    if competitor_name.lower() not in content.lower():
        reasons.append(f"相关性不足：搜索结果未明确指向竞品 {competitor_name}")
    if not source_name:
        reasons.append("缺少可识别的数据发布方、机构名或报告名")
    if not _is_usable_competitor_source_url(url):
        reasons.append("来源 URL 不可用或属于内容聚合/低质站点")
    if _is_self_published_source(
        source_name,
        url,
        _item_title(item),
        competitor_name,
    ):
        reasons.append("来源属于竞品自身材料，不收录营销性表述")
    if any(term in content for term in EVALUATIVE_TERMS + MARKETING_TERMS):
        reasons.append("包含评价性、比较性或宣传性表述")
    if data_point is None or fact_type is None:
        reasons.append("未找到成立时间、产品线、公开定价或公开融资等客观事实")
    else:
        evidence_year = _competitor_fact_year(item, content, data_point, fact_type)
        if evidence_year is None:
            reasons.append("无法识别客观事实的年份口径")
        elif fact_type != "founded" and evidence_year < current_year - 2:
            reasons.append(
                f"时效性不足：公开信息年份 {evidence_year} 早于 {current_year - 2}"
            )

    if reasons:
        return None, "；".join(reasons)
    return (
        SearchEvidence(
            data_point=data_point,
            year=evidence_year,
            source_type=SourceType.SEARCH_VALIDATION,
            source_ref=SourceReference(
                source_name=source_name,
                source_url=url,
                needs_verification=True,
            ),
        ),
        "",
    )


def _extract_competitor_fact(content: str) -> tuple[str | None, str | None]:
    for sentence in re.split(r"[。；\n]", content):
        sentence = sentence.strip()
        if not sentence:
            continue
        if ("成立" in sentence or "创立" in sentence) and YEAR_RE.search(sentence):
            return sentence, "founded"
        if any(term in sentence for term in ("价格", "定价", "售价", "订阅费")) and COMPETITOR_VALUE_RE.search(sentence):
            return sentence, "pricing"
        if any(term in sentence for term in ("融资", "获投", "融资轮")) and COMPETITOR_VALUE_RE.search(sentence):
            return sentence, "funding"
        if any(term in sentence for term in ("产品线", "产品包括", "旗下产品", "产品包含")):
            return sentence, "product_line"
    return None, None


def _competitor_fact_year(
    item: dict[str, Any],
    content: str,
    data_point: str,
    fact_type: str,
) -> int | None:
    if fact_type == "founded":
        return _extract_data_year(data_point)
    return _extract_publication_year(item, content) or _extract_data_year(data_point)


def _is_self_published_source(
    source_name: str | None,
    url: str | None,
    title: str,
    competitor_name: str,
) -> bool:
    source_text = " ".join(part for part in (source_name, url, title) if part).lower()
    return (
        competitor_name.lower() in source_text
        and bool(source_name and competitor_name.lower() in source_name.lower())
    ) or any(term in source_text for term in SELF_PUBLISHED_PAGE_TERMS)


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


def _is_usable_competitor_source_url(url: str | None) -> bool:
    if not _is_usable_source_url(url):
        return False
    hostname = urlparse(url).hostname or ""
    return not any(
        marker in hostname.lower()
        for marker in COMPETITOR_LOW_QUALITY_DOMAIN_MARKERS
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
