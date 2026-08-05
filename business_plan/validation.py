from __future__ import annotations

import difflib
import re


KEYWORD_CHARACTER_COVERAGE_THRESHOLD = 0.6
REWRITE_SIMILARITY_THRESHOLD = 0.9
PREFIX_COPY_SIMILARITY_THRESHOLD = 0.9
HOLLOW_PHRASES = (
    "构成刚需",
    "导致经营后果",
    "存在问题",
    "需要解决",
)
HOLLOW_PHRASES += (
    "公司当前",
    "核心目标是",
    "意味着",
    "从而",
    "这一举措",
    "旨在",
    "以此",
    "进而",
    "本字段",
    "该方案",
)
MIN_SUBSTANTIVE_CHARS = 20
HOLLOW_PHRASE_RATIO_THRESHOLD = 0.25
INDICATOR_TERMS = (
    "利用率",
    "良率",
    "能耗",
    "成本",
    "收入",
    "利润",
    "交付率",
    "投诉率",
    "市场份额",
    "客户数",
)

_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_ASCII_TERM_RE = re.compile(r"[A-Za-z]{2,}")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?(?:[%％]|[万亿千百十])?")
_QUANTITY_RE = re.compile(r"(?:数|几|多|[一二三四五六七八九十]+)(?:万|亿|千|百)?(?:元|台|家|年|月|日|个|%)")
_PERCENTAGE_RE = re.compile(r"(?:\d+(?:\.\d+)?[%％]|百分之[一二三四五六七八九十\d]+)")
_ORGANIZATION_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]{2,}(?:公司|集团|股份)")
_SPLIT_RE = re.compile(
    r"(?:的|是|而且|全靠|看不到|不知道|哪台|多少|在哪|才|了|无从|"
    r"主要|这些|这类|基本|坏了|一次|动辄|影响|导致|造成|并|且|后|采取|被动|即|单次)"
)
_STOPWORDS = {"现在", "管理者", "决策", "经验", "企业", "主要", "这些", "这类", "基本", "没有", "而且"}


def validate_rewrite(
    original_text: str,
    rewritten_text: str,
    *,
    min_chars: int | None = None,
    max_chars: int | None = None,
    require_keyword_coverage: bool = True,
    require_quantity_preservation: bool = True,
    check_rewrite_distance: bool = True,
) -> tuple[bool, list[str]]:
    """Check that a rewrite retains core terms and adds no new numeric facts."""

    issues: list[str] = []
    if min_chars is not None and len(rewritten_text.strip()) < min_chars:
        issues.append("输出低于字数下限，必须形成完整观点")
    if max_chars is not None and len(rewritten_text.strip()) > max_chars:
        issues.append("输出超出字数上限，必须精简")
    original_keywords = _extract_keywords(original_text)
    core_characters = {
        character.lower()
        for keyword in original_keywords
        for character in keyword
    }
    rewritten_characters = set(rewritten_text.lower())
    if require_keyword_coverage and core_characters:
        coverage = len(core_characters & rewritten_characters) / len(core_characters)
        if coverage < KEYWORD_CHARACTER_COVERAGE_THRESHOLD:
            issues.append(f"核心关键词字符覆盖率不足: {coverage:.0%}")

    original_numbers = set(_NUMBER_RE.findall(original_text))
    rewritten_numbers = set(_NUMBER_RE.findall(rewritten_text))
    issues.extend(
        f"新增数字或数量表述: {number}"
        for number in sorted(rewritten_numbers - original_numbers)
    )

    original_quantities = set(_QUANTITY_RE.findall(original_text))
    rewritten_quantities = set(_QUANTITY_RE.findall(rewritten_text))
    if require_quantity_preservation:
        issues.extend(
            f"丢失数量表述: {quantity}"
            for quantity in sorted(original_quantities - rewritten_quantities)
        )

    original_percentages = set(_PERCENTAGE_RE.findall(original_text))
    rewritten_percentages = set(_PERCENTAGE_RE.findall(rewritten_text))
    issues.extend(
        f"新增百分比: {percentage}"
        for percentage in sorted(rewritten_percentages - original_percentages)
    )

    original_organizations = set(_ORGANIZATION_RE.findall(original_text))
    rewritten_organizations = set(_ORGANIZATION_RE.findall(rewritten_text))
    issues.extend(
        f"新增公司或机构名称: {organization}"
        for organization in sorted(rewritten_organizations - original_organizations)
    )

    issues.extend(
        f"新增指标: {indicator}"
        for indicator in INDICATOR_TERMS
        if indicator in rewritten_text and indicator not in original_text
    )

    normalized_original = _normalize_for_similarity(original_text)
    normalized_rewritten = _normalize_for_similarity(rewritten_text)
    if check_rewrite_distance:
        similarity = difflib.SequenceMatcher(
            None,
            normalized_original,
            normalized_rewritten,
        ).ratio()
        if normalized_original == normalized_rewritten or similarity >= REWRITE_SIMILARITY_THRESHOLD:
            issues.append("改写与原文过于接近,未做专业化重述")

        if _has_copied_prefix(normalized_original, normalized_rewritten):
            issues.append("照抄原文后续写")

    remaining_text = rewritten_text
    found_hollow_phrases = [
        phrase for phrase in HOLLOW_PHRASES if phrase in rewritten_text
    ]
    for phrase in found_hollow_phrases:
        remaining_text = remaining_text.replace(phrase, "")
    normalized_rewritten_length = max(len(normalized_rewritten), 1)
    hollow_phrase_length = sum(
        len(_normalize_for_similarity(phrase))
        for phrase in found_hollow_phrases
    )
    starts_with_hollow_phrase = any(
        normalized_rewritten.startswith(_normalize_for_similarity(phrase))
        for phrase in found_hollow_phrases
    )
    if found_hollow_phrases and (
        len(_normalize_for_similarity(remaining_text)) < MIN_SUBSTANTIVE_CHARS
        or hollow_phrase_length / normalized_rewritten_length >= HOLLOW_PHRASE_RATIO_THRESHOLD
        or starts_with_hollow_phrase
    ):
        issues.append("输出为空洞套话,缺乏实质论证")
    return not issues, issues


def _extract_keywords(text: str) -> list[str]:
    keywords: list[str] = []
    for chunk in _CJK_RUN_RE.findall(text):
        for term in _SPLIT_RE.split(chunk):
            term = term.strip()
            if (
                2 <= len(term) <= 6
                and term not in _STOPWORDS
                and term not in keywords
            ):
                keywords.append(term)
    for term in _ASCII_TERM_RE.findall(text):
        if term not in keywords:
            keywords.append(term)
    return keywords


def _normalize_for_similarity(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE)


def _has_copied_prefix(normalized_original: str, normalized_rewritten: str) -> bool:
    if len(normalized_original) < 6:
        return False
    prefix_length = max(6, round(len(normalized_original) * 0.6))
    if len(normalized_rewritten) < prefix_length:
        return False
    similarity = difflib.SequenceMatcher(
        None,
        normalized_original[:prefix_length],
        normalized_rewritten[:prefix_length],
    ).ratio()
    return similarity >= PREFIX_COPY_SIMILARITY_THRESHOLD
