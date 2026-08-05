from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeAlias


class SourceType(str, Enum):
    """Origin labels required by the BP content redlines."""

    CLIENT_PROVIDED = "client_provided"
    ENGINE_REWRITE = "engine_rewrite"
    SEARCH_VALIDATION = "search_validation"
    PENDING_CUSTOMER = "pending_customer"


@dataclass
class SourceReference:
    """A named source; required when source_type is SEARCH_VALIDATION."""

    source_name: str
    source_url: str | None = None
    needs_verification: bool = True


@dataclass
class FieldOutput:
    """One BP output field together with its fact origin."""

    value: Any
    source_type: SourceType
    source_ref: SourceReference | None = None
    message: str | None = None


@dataclass
class SearchEvidence:
    """One accepted search-only data point, kept separate from customer facts."""

    data_point: str
    year: int
    source_type: SourceType
    source_ref: SourceReference


@dataclass
class TextLengthRange:
    """Recommended character range for a rendered text field."""

    min_chars: int
    max_chars: int


# Input schema: all raw values are strings so customer-provided numbers are
# preserved exactly. Only website and market basis are optional by specification.
@dataclass
class ProjectOverviewIntake:
    bp_title: str
    company_name: str
    founded: str
    # C 类品牌字段：承载客户品牌资产，必须原样保留，绝不改写。
    one_liner: str
    business_summary: str
    team_scale: str
    slogan: str
    website: str | None = None
    mission: str | None = None
    vision: str | None = None


@dataclass
class PainPointIntake:
    description: str
    why_rigid_demand: str


@dataclass
class DemandIntake:
    target_customer: str
    pain_points: tuple[PainPointIntake, PainPointIntake, PainPointIntake]


@dataclass
class SolutionIntake:
    pain_point: str
    solution: str


@dataclass
class RevenueSourceIntake:
    source: str
    share: str


@dataclass
class ProductModelIntake:
    solutions: list[SolutionIntake]
    core_values: tuple[str, str, str]
    revenue_sources: list[RevenueSourceIntake]
    gross_margin: str
    net_margin: str
    sales_model: str


@dataclass
class MarketSizeIntake:
    tam: str
    sam: str
    som: str


@dataclass
class GrowthForecastIntake:
    year: str
    market_size: str
    growth_rate: str


@dataclass
class MarketIntake:
    market_size: MarketSizeIntake
    growth_forecast: list[GrowthForecastIntake]
    basis: str | None = None
    industry_context: str | None = None


@dataclass
class CompetitorIntake:
    name: str
    dimensions: dict[str, str]


@dataclass
class CompetitionIntake:
    competitors: list[CompetitorIntake]
    differentiations: tuple[str, str, str]


@dataclass
class CurrentStateIntake:
    product_status: str
    customer_count: str
    device_count: str
    coverage: str
    financials: dict[str, str]
    team_size: str
    endorsements: str


@dataclass
class RoadmapStageIntake:
    period: str
    objective: str
    deliverables: str


@dataclass
class FinancialProjectionIntake:
    year: str
    revenue: str
    net_profit: str


@dataclass
class PlanIntake:
    roadmap: list[RoadmapStageIntake]
    financial_projection: list[FinancialProjectionIntake]


@dataclass
class UseOfFundsIntake:
    purpose: str
    percentage: str
    description: str | None = None


@dataclass
class FundingIntake:
    funding_amount: str
    dilution_range: str
    use_of_funds: list[UseOfFundsIntake]


@dataclass
class TeamMemberIntake:
    name: str
    role: str
    background: str


@dataclass
class TeamIntake:
    members: list[TeamMemberIntake]


@dataclass
class BPIntake:
    """Complete customer collection for BP modules 0 through 8."""

    project_overview: ProjectOverviewIntake
    demand: DemandIntake
    product_model: ProductModelIntake
    market: MarketIntake
    competition: CompetitionIntake
    current_state: CurrentStateIntake
    plan: PlanIntake
    funding: FundingIntake
    team: TeamIntake


# Chart data schema. FieldOutput keeps chart values subject to the same source
# tracing rules as narrative output.
@dataclass
class KeyMetricCard:
    label: str
    value: FieldOutput


@dataclass
class ExecutiveSummaryChartData:
    key_metrics: tuple[KeyMetricCard, KeyMetricCard, KeyMetricCard, KeyMetricCard]


@dataclass
class DepartmentHeadcount:
    department: str
    headcount: FieldOutput


@dataclass
class TeamCompositionChartData:
    departments: list[DepartmentHeadcount]


@dataclass
class ProductArchitectureNode:
    node_id: str
    label: FieldOutput


@dataclass
class ProductArchitectureEdge:
    from_node_id: str
    to_node_id: str
    relation: FieldOutput


@dataclass
class RevenueCompositionSlice:
    label: str
    proportion: FieldOutput


@dataclass
class ProductModelChartData:
    architecture_nodes: list[ProductArchitectureNode]
    architecture_edges: list[ProductArchitectureEdge]
    revenue_composition: list[RevenueCompositionSlice]


@dataclass
class MarketLayer:
    label: str
    value: FieldOutput


@dataclass
class MarketTrendPoint:
    year: str
    market_size: FieldOutput
    growth_rate: FieldOutput


@dataclass
class MarketChartData:
    tam_sam_som: tuple[MarketLayer, MarketLayer, MarketLayer]
    five_year_trend: list[MarketTrendPoint]


@dataclass
class CompetitorScoreRow:
    competitor: str
    dimension_scores: dict[str, FieldOutput]


@dataclass
class CompetitionChartData:
    dimensions: list[str]
    score_matrix: list[CompetitorScoreRow]


@dataclass
class MonthlyMetricPoint:
    month: str
    value: FieldOutput


@dataclass
class RegionalShare:
    region: str
    proportion: FieldOutput


@dataclass
class CurrentStateChartData:
    twelve_month_series: list[MonthlyMetricPoint]
    regional_distribution: list[RegionalShare]


@dataclass
class RoadmapMilestone:
    period: FieldOutput
    milestone: FieldOutput


@dataclass
class FinancialProjectionPoint:
    year: str
    revenue: FieldOutput
    net_profit: FieldOutput


@dataclass
class PlanChartData:
    milestones: list[RoadmapMilestone]
    five_year_financials: list[FinancialProjectionPoint]


@dataclass
class FundingUseSlice:
    purpose: str
    proportion: FieldOutput


@dataclass
class FundingChartData:
    use_of_funds: list[FundingUseSlice]


@dataclass
class TeamMemberCard:
    name: FieldOutput
    role: FieldOutput
    background: FieldOutput


@dataclass
class TeamChartData:
    member_cards: list[TeamMemberCard]


ChartData: TypeAlias = (
    ExecutiveSummaryChartData
    | TeamCompositionChartData
    | ProductModelChartData
    | MarketChartData
    | CompetitionChartData
    | CurrentStateChartData
    | PlanChartData
    | FundingChartData
    | TeamChartData
)


@dataclass
class ModuleOutput:
    """Source-marked output for one BP module; module 1 may have no chart."""

    module_id: int
    headline: FieldOutput
    fields: dict[str, FieldOutput]
    chart_data: list[ChartData]
    text_length_constraints: dict[str, TextLengthRange]


@dataclass
class ExecutiveSummaryOutput:
    core_claim: FieldOutput
    key_metrics: tuple[KeyMetricCard, KeyMetricCard, KeyMetricCard, KeyMetricCard]
    problem: FieldOutput
    solution: FieldOutput
    traction: FieldOutput
    funding: FieldOutput
    chart_data: list[ExecutiveSummaryChartData]


@dataclass
class PendingItem:
    module_id: int
    field_name: str
    message: str


@dataclass
class ModuleGenerationStatus:
    """Execution state for one independently generated BP module."""

    module_id: int
    status: str
    duration_seconds: float
    error_message: str | None = None
    headline_attempts: int = 0


@dataclass
class DegradedField:
    """A rewrite field that fell back to the customer-provided original."""

    module_id: int
    field_name: str


@dataclass
class GenerationStats:
    """Per-run observability data for BP cost and quality analysis."""

    llm_call_count: int
    headline_call_count: int
    search_call_count: int
    minimum_llm_call_count: int
    retry_llm_call_count: int
    total_duration_seconds: float
    module_durations: dict[int, float]
    degraded_fields: list[DegradedField]


@dataclass
class BPResult:
    """The completed BP, preserving the specification's module 0-8 numbering."""

    bp_title: str
    executive_summary: ExecutiveSummaryOutput | None
    project_overview: ModuleOutput | None
    demand: ModuleOutput | None
    product_model: ModuleOutput | None
    market: ModuleOutput | None
    competition: ModuleOutput | None
    current_state: ModuleOutput | None
    plan: ModuleOutput | None
    funding: ModuleOutput | None
    team: ModuleOutput | None
    pending_items: list[PendingItem]
    module_statuses: dict[int, ModuleGenerationStatus]
    generation_stats: GenerationStats


# Recommended character ranges for all narrative text output fields. Structured
# values and chart labels are intentionally excluded from these render limits.
TEXT_LENGTH_CONSTRAINTS: dict[str, TextLengthRange] = {
    "module.headline": TextLengthRange(20, 40),
    "executive_summary.core_claim": TextLengthRange(40, 120),
    "executive_summary.problem": TextLengthRange(80, 220),
    "executive_summary.solution": TextLengthRange(80, 220),
    "executive_summary.traction": TextLengthRange(80, 220),
    "executive_summary.funding": TextLengthRange(80, 180),
    "module_0.bp_title": TextLengthRange(2, 40),
    "module_0.company_name": TextLengthRange(2, 50),
    "module_0.founded": TextLengthRange(4, 30),
    "module_0.one_liner": TextLengthRange(12, 40),
    "module_0.business_summary": TextLengthRange(120, 360),
    "module_0.team_scale": TextLengthRange(2, 80),
    "module_0.slogan": TextLengthRange(8, 30),
    "module_1.target_customer": TextLengthRange(80, 220),
    "module_1.pain_points": TextLengthRange(180, 480),
    "module_1.why_now": TextLengthRange(80, 220),
    "module_2.solution": TextLengthRange(120, 360),
    "module_2.core_value": TextLengthRange(15, 50),
    "module_2.business_model": TextLengthRange(150, 420),
    "module_2.sales_model": TextLengthRange(100, 300),
    "module_3.market_size": TextLengthRange(80, 220),
    "module_3.market_narrative": TextLengthRange(180, 500),
    "module_3.market_validation": TextLengthRange(80, 240),
    "module_4.competitors": TextLengthRange(120, 360),
    "module_4.differentiation": TextLengthRange(180, 450),
    "module_5.traction": TextLengthRange(180, 480),
    "module_6.roadmap": TextLengthRange(180, 420),
    "module_6.financial_projection": TextLengthRange(100, 260),
    "module_7.funding_ask": TextLengthRange(80, 180),
    "module_7.use_of_funds": TextLengthRange(100, 260),
    "module_8.team": TextLengthRange(120, 360),
}
