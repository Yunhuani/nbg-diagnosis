const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const cliInputIndex = process.argv.indexOf("--input");
const cliOutIndex = process.argv.indexOf("--out");
const REVIEWED = process.argv.includes("--reviewed");
const OUT_DIR = path.join(__dirname, "output");
const INPUT_FILE = cliInputIndex >= 0 ? path.resolve(process.argv[cliInputIndex + 1]) : findLatestInput();
const OUT_FILE = cliOutIndex >= 0
  ? path.resolve(process.argv[cliOutIndex + 1])
  : path.join(OUT_DIR, `${safeName(loadInput(INPUT_FILE).company)}_完整诊断报告_12页.pptx`);

const W = 13.333;
const H = 7.5;
const C = {
  bg: "121317",
  panel: "1A1B20",
  panelGold: "231F16",
  line: "3A3C44",
  gold: "E8B84B",
  goldBright: "FFD166",
  white: "EAEDF3",
  gray: "9DA4B3",
  muted: "6E7180",
};

const DIMENSION_ORDER = ["market", "competition", "business_model", "capability", "finance"];
const DIMENSION_LABELS = {
  market: "市场",
  competition: "竞争",
  business_model: "商业模式",
  capability: "内部能力",
  finance: "财务",
};

function findLatestInput() {
  if (!fs.existsSync(OUT_DIR)) {
    throw new Error("Missing --input and report/output does not exist.");
  }
  const candidates = fs.readdirSync(OUT_DIR)
    .filter((name) => name.endsWith("_report_input.json"))
    .map((name) => path.join(OUT_DIR, name))
    .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  if (!candidates.length) {
    throw new Error("Missing --input and no *_report_input.json found in report/output.");
  }
  return candidates[0];
}

function loadInput(file) {
  const raw = JSON.parse(fs.readFileSync(file, "utf8"));
  const factBase = raw.fact_base || {};
  const intake = factBase.diagnosis_intake || {};
  const synthesis = raw.synthesis_output || {};
  const dimensions = (raw.dimension_outputs || []).slice().sort(
    (a, b) => DIMENSION_ORDER.indexOf(a.dimension) - DIMENSION_ORDER.indexOf(b.dimension)
  );
  const company = intake.company?.name || raw.company || "客户企业";
  return {
    raw,
    caseName: raw.case || "",
    company,
    factBase,
    financialFacts: raw.financial_facts || factBase.financial_facts || {},
    dimensions,
    synthesis,
    scoreSummary: raw.score_summary || {},
  };
}

function safeName(value) {
  return String(value || "客户企业").replace(/[\\/:*?"<>|]/g, "_");
}

const DATA = loadInput(INPUT_FILE);

function text(value, fallback = "") {
  if (value === null || value === undefined) return fallback;
  if (Array.isArray(value)) return value.filter(Boolean).join(" / ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function cleanLine(value, fallback = "") {
  return text(value, fallback).replace(/\s+/g, " ").trim();
}

function clampText(value, maxChars, fallback = "") {
  const content = cleanLine(value, fallback);
  if (content.length <= maxChars) return content;
  return `${content.slice(0, Math.max(0, maxChars - 1))}…`;
}

function reportHeadline() {
  return clampText(
    DATA.synthesis.headline || DATA.synthesis.overall_judgment,
    30,
    "诊断结论待生成"
  );
}

function scoreLabel(score) {
  if (score >= 8) return "健康";
  if (score >= 5) return "亚健康";
  return "警告";
}

function dimensionScores() {
  const scores = {};
  DATA.dimensions.forEach((dim) => {
    scores[dim.dimension] = dim.score?.value || 0;
  });
  return scores;
}

function sourceTypeLabel(item) {
  if (item.source_type === "computed") return "计算值";
  if (item.source_type === "client_provided") return "客户提供";
  if (item.source_type === "verified") return "外部验证";
  if (item.source_type === "inferred") return "方向线索";
  return "来源未标";
}

function displaySource(item) {
  if (item.source_type === "verified" || item.source_type === "inferred") {
    return text(item.source);
  }
  return "";
}

function splitTransition(value) {
  if (value && typeof value === "object") {
    return {
      risk: text(value.risk, "关键风险将在方案阶段进一步校准"),
      opportunity: text(value.opportunity, "关键机会将在方案阶段进一步细化"),
      next: text(value.next_step || value.next, "下一步聚焦可执行方案拆解"),
    };
  }
  const body = text(value, "转向解决方案将在方案阶段进一步细化");
  return { risk: body, opportunity: body, next: body };
}

function addText(slide, content, x, y, w, h, opts = {}) {
  slide.addText(text(content), {
    x, y, w, h,
    margin: 0,
    breakLine: false,
    fontFace: "Microsoft YaHei",
    fit: "shrink",
    color: C.white,
    ...opts,
  });
}

function addBackground(slide) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: H,
    fill: { color: C.bg },
    line: { color: C.bg },
  });
}

function addFooter(slide, section = "NBG五维增长诊断") {
  addText(slide, `分析框架：${section}`, 0.65, 7.08, 4.6, 0.18, {
    fontSize: 7.5, color: C.muted,
  });
  addText(slide, `${DATA.company} · ${REVIEWED ? "顾问审核版" : "草稿版"}`, 8.6, 7.08, 3.95, 0.18, {
    fontSize: 7.5, color: C.muted, align: "right",
  });
}

function addScoreBadge(slide, score, x, y, w = 1.8) {
  const value = score?.value ?? DATA.synthesis.overall_score ?? DATA.scoreSummary.overall_score ?? "";
  const label = score?.label || DATA.synthesis.score_label || DATA.scoreSummary.score_label || scoreLabel(value);
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h: 0.68,
    rectRadius: 0.03,
    fill: { color: C.panelGold },
    line: { color: C.gold, width: 1 },
  });
  addText(slide, `${label} · ${value}分`, x + 0.18, y + 0.2, w - 0.36, 0.2, {
    fontSize: 12.5, bold: true, color: C.goldBright, align: "center",
  });
}

function radarPoint(cx, cy, r, index, valueScale = 1) {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / DIMENSION_ORDER.length;
  return { x: cx + Math.cos(angle) * r * valueScale, y: cy + Math.sin(angle) * r * valueScale };
}

function svgPoints(points) {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function radarSvgData() {
  const size = 700;
  const cx = size / 2;
  const cy = size / 2;
  const r = 230;
  const scores = dimensionScores();
  const rings = [1, 2, 3, 4, 5].map((tick) => {
    const pts = DIMENSION_ORDER.map((_, i) => radarPoint(cx, cy, r, i, tick / 5));
    return `<polygon points="${svgPoints(pts)}" fill="none" stroke="#3A3C44" stroke-opacity="0.42" stroke-width="1.1"/>`;
  }).join("");
  const axes = DIMENSION_ORDER.map((_, i) => {
    const p = radarPoint(cx, cy, r, i, 1);
    return `<line x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="#3A3C44" stroke-opacity="0.28" stroke-width="0.9"/>`;
  }).join("");
  const scorePoints = DIMENSION_ORDER.map((key, i) => radarPoint(cx, cy, r, i, (scores[key] || 0) / 5));
  const labels = DIMENSION_ORDER.map((key, i) => {
    const p = radarPoint(cx, cy, r + 58, i, 1);
    return `<text x="${p.x.toFixed(1)}" y="${p.y.toFixed(1)}" text-anchor="middle" dominant-baseline="middle" fill="#EAEDF3" font-size="30" font-family="Microsoft YaHei">${DIMENSION_LABELS[key]}</text>`;
  }).join("");
  const dots = scorePoints.map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="6" fill="#FFD166"/>`).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
    ${rings}${axes}
    <polygon points="${svgPoints(scorePoints)}" fill="#E8B84B" fill-opacity="0.15" stroke="#E8B84B" stroke-width="4"/>
    ${dots}${labels}
  </svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

function addRadar(slide, x, y, w, h) {
  slide.addImage({ data: radarSvgData(), x, y, w, h });
}

function addCover(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "NBG增长解码", 0.72, 0.62, 4.1, 0.42, {
    fontSize: 18, bold: true, color: C.gold, charSpace: 1.2,
  });
  addText(slide, "增长诊断报告", 0.72, 1.04, 2.55, 0.2, {
    fontSize: 8.5, color: C.gray,
  });
  addText(slide, reportHeadline(), 0.72, 1.72, 7.25, 0.9, {
    fontSize: 27, bold: true, color: C.white, fit: "shrink",
  });
  addText(slide, DATA.synthesis.overall_judgment || "诊断结论待生成", 0.76, 2.88, 6.55, 0.7, {
    fontSize: 10.5, color: C.gray, fit: "shrink",
  });
  addScoreBadge(slide, { value: DATA.synthesis.overall_score, label: DATA.synthesis.score_label }, 0.76, 4.36, 2.12);
  addText(slide, "诊断对象", 0.78, 5.78, 0.95, 0.18, { fontSize: 8, color: C.muted });
  addText(slide, DATA.company, 0.78, 6.02, 2.6, 0.34, { fontSize: 17, bold: true });
  addText(slide, "五维评分", 9.28, 1.16, 1.5, 0.22, { fontSize: 9, color: C.gold, bold: true });
  addRadar(slide, 8.12, 1.56, 3.82, 3.82);
  addFooter(slide);
}

function addOverallJudgment(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, reportHeadline(), 0.62, 0.6, 9.2, 0.72, {
    fontSize: 26, bold: true, fit: "shrink",
  });
  addText(slide, "总体判断", 0.64, 1.54, 1.05, 0.2, { fontSize: 8.5, color: C.gold });
  slide.addShape(pptx.ShapeType.line, {
    x: 0.68, y: 2.25, w: 0, h: 2.8, line: { color: C.gold, width: 1.2 },
  });
  addText(slide, DATA.synthesis.overall_judgment || "本次诊断已形成初步结构性判断，完整结论以各维度分析为准", 1.02, 2.22, 6.42, 1.18, {
    fontSize: 15, bold: true, fit: "shrink",
  });
  addText(slide, "这页承接五维结论，展示当前最需要管理层判断的结构性处境。", 1.04, 4.12, 5.9, 0.42, {
    fontSize: 10.8, color: C.gray,
  });
  addText(slide, "五维评级一览", 8.34, 1.45, 1.55, 0.2, { fontSize: 9, color: C.gold, bold: true });
  addRadar(slide, 8.38, 1.78, 3.1, 3.1);
  DIMENSION_ORDER.forEach((key, index) => {
    const x = 1.04 + index * 1.64;
    addScorePill(slide, DIMENSION_LABELS[key], dimensionScores()[key] || 0, x, 5.58);
  });
  addFooter(slide, "NBG五维综合验证 · 总体判断");
}

function addScorePill(slide, label, value, x, y) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w: 1.42, h: 0.62, rectRadius: 0.03,
    fill: { color: C.panel }, line: { color: C.line, transparency: 10, width: 0.8 },
  });
  addText(slide, label, x + 0.14, y + 0.12, 0.82, 0.14, { fontSize: 7.2, color: C.gray });
  addText(slide, `${value}/10`, x + 0.14, y + 0.31, 0.72, 0.18, {
    fontSize: 10.5, bold: true, color: C.goldBright,
  });
}

function addDynamicCards(slide, items, options) {
  const list = items.length ? items : [{ title: options.emptyTitle || "暂无数据", body: options.emptyBody || "该部分暂无可渲染内容。" }];
  const count = list.length;
  const top = options.top || 2.0;
  const bottom = options.bottom || 6.35;
  const gap = options.gap || 0.24;
  const h = Math.max(0.76, (bottom - top - gap * (count - 1)) / count);
  list.forEach((item, index) => {
    const y = top + index * (h + gap);
    const x = options.x || 0.82;
    const w = options.w || 11.2;
    const highlight = index === 0 && options.highlightFirst;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y, w, h, rectRadius: 0.03,
      fill: { color: highlight ? C.panelGold : C.panel },
      line: { color: highlight ? C.gold : C.line, transparency: 16, width: 0.8 },
    });
    addText(slide, options.indexLabel ? `${options.indexLabel} ${String(index + 1).padStart(2, "0")}` : `0${index + 1}`, x + 0.3, y + 0.18, 1.0, 0.14, {
      fontSize: 7.2, color: highlight ? C.gold : C.muted, bold: true,
    });
    addText(slide, clampText(item.title || item.fact || item.naive_reading || item.tension || item.flag || "该项将在方案阶段进一步细化", 42), x + 0.3, y + 0.46, w * 0.4, Math.max(0.26, h * 0.36), {
      fontSize: options.titleSize || 11.4, bold: true, color: C.white, fit: "shrink",
    });
    addText(slide, item.body || item.why_surprising || item.detail || item.reframe || item.decision || item.meaning || "", x + w * 0.52, y + 0.38, w * 0.4, Math.max(0.34, h * 0.52), {
      fontSize: options.bodySize || 9.2, color: C.gray, fit: "shrink",
    });
  });
}

function addThreeFindings(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "真正值得优先看的，是能改变经营判断的关键发现", 0.62, 0.62, 11.6, 0.5, {
    fontSize: 25, bold: true, fit: "shrink",
  });
  addText(slide, "关键发现", 0.64, 1.24, 1.4, 0.2, { fontSize: 8.5, color: C.gold });
  const items = (DATA.synthesis.three_key_findings || []).map((item) => ({
    title: item.title || item.finding_id,
    body: item.why_surprising || item.statement || "",
  }));
  addDynamicCards(slide, items, { top: 2.02, bottom: 6.25, highlightFirst: true, indexLabel: "发现" });
  addFooter(slide, "NBG五维综合验证 · 关键发现");
}

function addReasoningChain(slide, chain) {
  const items = chain && chain.length ? chain : ["暂无推理链。"];
  addText(slide, "推理链", 0.76, 2.42, 0.8, 0.18, { fontSize: 8.5, bold: true, color: C.gold });
  const h = Math.min(0.72, 2.9 / items.length);
  items.forEach((item, index) => {
    const y = 2.82 + index * h;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 0.8, y: y + 0.02, w: 0.22, h: 0.22,
      fill: { color: index === 0 ? C.gold : C.panelGold },
      line: { color: C.gold, transparency: 15, width: 0.6 },
    });
    addText(slide, String(index + 1), 0.86, y + 0.06, 0.1, 0.09, {
      fontSize: 5.6, bold: true, color: index === 0 ? C.bg : C.goldBright, align: "center",
    });
    addText(slide, item, 1.18, y, 5.0, Math.max(0.34, h - 0.08), {
      fontSize: 9.8, fit: "shrink",
    });
  });
}

function addEvidenceList(slide, evidenceList) {
  const list = evidenceList && evidenceList.length ? evidenceList : [{ claim: "本维以已确认信息形成结构性判断", value: "定性判断", source_type: "", source: "" }];
  addText(slide, "关键证据", 7.24, 2.42, 0.95, 0.18, { fontSize: 8.5, bold: true, color: C.gold });
  const h = Math.min(0.92, 3.35 / list.length);
  list.forEach((evidence, index) => {
    const y = 2.82 + index * (h + 0.14);
    const isSoft = evidence.source_type === "inferred";
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 7.24, y, w: 4.86, h, rectRadius: 0.025,
      fill: { color: isSoft ? C.bg : C.panel, transparency: isSoft ? 8 : 0 },
      line: { color: C.line, transparency: isSoft ? 45 : 18, width: 0.7 },
    });
    addText(slide, evidence.claim, 7.48, y + 0.15, 2.7, h * 0.34, {
      fontSize: 8.2, bold: true, color: isSoft ? C.gray : C.white, fit: "shrink",
    });
    addText(slide, evidence.value, 10.22, y + 0.15, 1.6, h * 0.34, {
      fontSize: 8.8, bold: true, color: isSoft ? C.gray : C.goldBright, align: "right", fit: "shrink",
    });
    addText(slide, sourceTypeLabel(evidence), 7.48, y + h - 0.28, 1.7, 0.14, {
      fontSize: 6.5, color: isSoft ? C.muted : C.gray,
    });
    addText(slide, displaySource(evidence), 9.0, y + h - 0.28, 2.82, 0.14, {
      fontSize: 6.5, color: C.muted, align: "right", fit: "shrink",
    });
  });
}

function addDimensionPage(pptx, dimension) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, clampText(dimension.core_judgment || "该维度采用结构性判断口径", 46), 0.62, 0.56, 8.95, 0.82, {
    fontSize: 21.5, bold: true, fit: "shrink",
  });
  addText(slide, DIMENSION_LABELS[dimension.dimension] || dimension.dimension, 0.64, 1.5, 1.6, 0.2, {
    fontSize: 8.5, color: C.gold,
  });
  addText(slide, (dimension.framework || []).join(" + "), 0.64, 1.76, 4.4, 0.2, {
    fontSize: 8.3, color: C.muted, fit: "shrink",
  });
  addScoreBadge(slide, dimension.score, 10.35, 0.66, 1.72);
  slide.addShape(pptx.ShapeType.line, {
    x: 6.72, y: 2.36, w: 0, h: 3.86, line: { color: C.line, transparency: 20, width: 0.8 },
  });
  addReasoningChain(slide, dimension.reasoning_chain || []);
  addEvidenceList(slide, dimension.evidence || []);
  if (dimension.degradation?.degraded) {
    addText(slide, `本维采用结构性判断口径：${text(dimension.degradation.upgrade_hook)}`, 7.24, 6.25, 4.85, 0.26, {
      fontSize: 7.2, color: C.muted, align: "right", fit: "shrink",
    });
  }
  addFooter(slide, `NBG五维分析 · ${DIMENSION_LABELS[dimension.dimension] || dimension.dimension}`);
}

function addCrossResonances(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "同一个事实在不同维度里，可能意味着完全不同的经营动作", 0.62, 0.6, 9.8, 0.52, {
    fontSize: 25, bold: true, fit: "shrink",
  });
  addText(slide, "交叉呼应", 0.64, 1.24, 1.0, 0.2, { fontSize: 8.5, color: C.gold });
  const items = (DATA.synthesis.cross_resonances || []).map((item) => ({
    title: item.fact,
    body: `${DIMENSION_LABELS[item.dim_a] || item.dim_a || "维度A"}：${text(item.meaning_a)}\n${DIMENSION_LABELS[item.dim_b] || item.dim_b || "维度B"}：${text(item.meaning_b)}`,
  }));
  addDynamicCards(slide, items, { top: 2.02, bottom: 6.25, highlightFirst: true, indexLabel: "呼应" });
  addFooter(slide, "NBG五维综合验证 · 交叉呼应");
}

function addConfirmedReversals(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "反转不是结论，而是最值得人工核验的决策假设", 0.62, 0.6, 9.0, 0.52, {
    fontSize: 25, bold: true, fit: "shrink",
  });
  addText(slide, "反转与待核验", 0.64, 1.24, 1.25, 0.2, { fontSize: 8.5, color: C.gold });
  const items = (DATA.synthesis.confirmed_reversals || []).map((item) => ({
    title: text(item.naive_reading),
    body: `${text(item.reframe)}\n状态：${text(item.status)}；依赖：${text(item.depends_on)}`,
  }));
  addDynamicCards(slide, items, { top: 2.02, bottom: 6.25, highlightFirst: true, indexLabel: "反转", titleSize: 10.5, bodySize: 8.6 });
  addFooter(slide, "NBG五维综合验证 · 反转与待核验");
}

function addConsistencyFlags(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "最难的不是看见机会，而是在约束下做取舍", 0.62, 0.6, 9.2, 0.52, {
    fontSize: 25, bold: true, fit: "shrink",
  });
  addText(slide, "一致性张力", 0.64, 1.24, 1.1, 0.2, { fontSize: 8.5, color: C.gold });
  const items = (DATA.synthesis.consistency_flags || []).map((item) => ({
    title: text(item.tension || item.flag || item.issue || item.dimensions || "需人工判断的张力"),
    body: text(item.decision || item.recommendation || item.human_check || item.severity || "需顾问结合访谈和经营数据继续判断。"),
  }));
  addDynamicCards(slide, items, { top: 2.02, bottom: 6.1, highlightFirst: true, indexLabel: "张力" });
  addFooter(slide, "NBG五维综合验证 · 一致性张力");
}

function addTransitionToSolution(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  const transition = splitTransition(DATA.synthesis.transition_to_solution);
  addText(slide, "下一步不是盲目增长，而是把风险和机会拆成可验证动作", 0.62, 0.62, 10.4, 0.62, {
    fontSize: 25, bold: true, fit: "shrink",
  });
  addText(slide, "转向解决方案", 0.64, 1.34, 1.25, 0.2, { fontSize: 8.5, color: C.gold });
  const cards = [
    { label: "最大风险", text: transition.risk },
    { label: "最大机会", text: transition.opportunity },
  ];
  cards.forEach((card, index) => {
    const x = index === 0 ? 0.84 : 6.72;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 2.22, w: 5.1, h: 1.7, rectRadius: 0.03,
      fill: { color: index === 0 ? C.panel : C.panelGold },
      line: { color: index === 0 ? C.line : C.gold, transparency: 14, width: 0.8 },
    });
    addText(slide, card.label, x + 0.28, 2.48, 0.9, 0.16, { fontSize: 8, color: C.gold, bold: true });
    addText(slide, card.text, x + 0.28, 2.86, 4.36, 0.56, {
      fontSize: 13.2, bold: true, fit: "shrink",
    });
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 1.0, y: 4.75, w: 10.82, h: 0, line: { color: C.gold, transparency: 12, width: 1.2 },
  });
  addText(slide, "建议进入下一阶段", 1.0, 5.1, 1.55, 0.18, { fontSize: 8.5, color: C.gold, bold: true });
  addText(slide, transition.next, 1.0, 5.48, 9.85, 0.58, {
    fontSize: 15, bold: true, fit: "shrink",
  });
  addFooter(slide, "NBG五维综合验证 · 转向解决方案");
}

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "NBG Diagnosis";
pptx.subject = `NBG增长解码 · ${DATA.company}`;
pptx.title = `${DATA.company}_完整诊断报告`;
pptx.company = DATA.company;
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: W, height: H });

addCover(pptx);
addOverallJudgment(pptx);
addThreeFindings(pptx);
DATA.dimensions.forEach((dimension) => addDimensionPage(pptx, dimension));
addCrossResonances(pptx);
addConfirmedReversals(pptx);
addConsistencyFlags(pptx);
addTransitionToSolution(pptx);

fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
pptx.writeFile({ fileName: OUT_FILE }).then(() => {
  console.log(`Generated: ${OUT_FILE}`);
  console.log(`Slides: ${pptx._slides.length}`);
  console.log(`Reviewed: ${REVIEWED}`);
  console.log(`Input: ${INPUT_FILE}`);
}).catch((error) => {
  console.error(error);
  process.exit(1);
});
