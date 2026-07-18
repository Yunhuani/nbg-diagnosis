const fs = require("fs");
const path = require("path");
const PptxGenJS = require("pptxgenjs");

const cliInputIndex = process.argv.indexOf("--input");
const cliOutIndex = process.argv.indexOf("--out");
const REVIEWED = process.argv.includes("--reviewed");
const OUT_DIR = path.join(__dirname, "output");

if (cliInputIndex < 0 || !process.argv[cliInputIndex + 1]) {
  throw new Error("Missing required --input solution report JSON.");
}

const INPUT_FILE = path.resolve(process.argv[cliInputIndex + 1]);
const RAW = JSON.parse(fs.readFileSync(INPUT_FILE, "utf8"));
const COMPANY = RAW.company || RAW.fact_base?.diagnosis_intake?.company?.name || "客户企业";
const OUT_FILE = cliOutIndex >= 0 && process.argv[cliOutIndex + 1]
  ? path.resolve(process.argv[cliOutIndex + 1])
  : path.join(OUT_DIR, `${safeName(COMPANY)}_增长方案报告.pptx`);

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
  green: "77C7A3",
};
const CATEGORY_ORDER = ["战略方向", "战术方向", "管理方向", "风险财务"];
const CATEGORY_LABELS = {
  战略方向: "战略",
  战术方向: "战术",
  管理方向: "管理",
  风险财务: "风险财务",
};
const LEVEL_SCORE = { 高: 3, 中: 2, 低: 1 };

function safeName(value) {
  return String(value || "客户企业").replace(/[\\/:*?"<>|]/g, "_");
}

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
  return content.length <= maxChars ? content : `${content.slice(0, maxChars - 1)}…`;
}

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
}

function assertArray(value, label) {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`${label} must be a non-empty array`);
  }
}

function validateInput(raw) {
  assertObject(raw.strategic_thesis, "strategic_thesis");
  assertObject(raw.strategic_thesis.from_to, "strategic_thesis.from_to");
  assertObject(raw.lever_matrix, "lever_matrix");
  assertArray(raw.lever_matrix.levers, "lever_matrix.levers");
  assertArray(raw.lever_matrix.selected, "lever_matrix.selected");
  assertObject(raw.action_map, "action_map");
  assertArray(raw.action_map.actions, "action_map.actions");
  assertObject(raw.roadmap, "roadmap");
  assertArray(raw.roadmap.phases, "roadmap.phases");
  if (raw.roadmap.phases.length !== 3) throw new Error("roadmap.phases must contain exactly 3 phases");
  assertObject(raw.ninety_day_plan, "ninety_day_plan");
  assertArray(raw.ninety_day_plan.plan, "ninety_day_plan.plan");
}

validateInput(RAW);

const DATA = {
  company: COMPANY,
  synthesis: RAW.synthesis_output || {},
  dimensions: RAW.dimension_outputs || [],
  thesis: RAW.strategic_thesis,
  levers: RAW.lever_matrix,
  actions: RAW.action_map,
  roadmap: RAW.roadmap,
  plan: RAW.ninety_day_plan,
};

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "NBG Solution";
pptx.subject = `NBG增长方案 · ${DATA.company}`;
pptx.title = `${DATA.company}_增长方案报告`;
pptx.company = DATA.company;
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: W, height: H });

function checkBounds(x, y, w, h, label) {
  if ([x, y, w, h].some((value) => typeof value !== "number" || Number.isNaN(value))) {
    throw new Error(`Invalid geometry for ${label}`);
  }
  if (x < 0 || y < 0 || w < 0 || h < 0 || x + w > W + 0.001 || y + h > H + 0.001) {
    throw new Error(`Out of bounds: ${label} (${x}, ${y}, ${w}, ${h})`);
  }
}

function addText(slide, content, x, y, w, h, opts = {}) {
  checkBounds(x, y, w, h, `text:${clampText(content, 20)}`);
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

function addShape(slide, type, options, label = "shape") {
  checkBounds(options.x, options.y, options.w, options.h, label);
  slide.addShape(type, options);
}

function addBackground(slide) {
  slide.background = { color: C.bg };
  addShape(slide, pptx.ShapeType.rect, {
    x: 0, y: 0, w: W, h: H,
    fill: { color: C.bg },
    line: { color: C.bg },
  }, "background");
}

function addFooter(slide, section) {
  addText(slide, `NBG增长方案 · ${section}`, 0.65, 7.08, 5.5, 0.18, {
    fontSize: 7.5, color: C.muted,
  });
  addText(slide, `${DATA.company} · ${REVIEWED ? "顾问审核版" : "草稿版"}`, 8.6, 7.08, 3.95, 0.18, {
    fontSize: 7.5, color: C.muted, align: "right",
  });
}

function addSlideTitle(slide, title, section) {
  addText(slide, title, 0.62, 0.55, 11.8, 0.62, {
    fontSize: 25, bold: true,
  });
  addText(slide, section, 0.64, 1.24, 2.2, 0.2, {
    fontSize: 8.5, color: C.gold, bold: true,
  });
}

function addPanel(slide, x, y, w, h, highlight = false) {
  addShape(slide, pptx.ShapeType.rect, {
    x, y, w, h,
    fill: { color: highlight ? C.panelGold : C.panel },
    line: { color: highlight ? C.gold : C.line, transparency: 15, width: 0.8 },
  }, "panel");
}

function paginate(items, size) {
  const pages = [];
  for (let index = 0; index < items.length; index += size) {
    pages.push(items.slice(index, index + size));
  }
  return pages.length ? pages : [[]];
}

function selectedLeverNames() {
  return new Set((DATA.levers.selected || []).map((item) => item.name));
}

function addCover() {
  const slide = pptx.addSlide();
  addBackground(slide);
  addText(slide, "NBG增长解码", 0.72, 0.62, 4.1, 0.42, {
    fontSize: 18, bold: true, color: C.gold, charSpacing: 1.2,
  });
  addText(slide, "增长方案报告", 0.72, 1.04, 2.55, 0.2, {
    fontSize: 8.5, color: C.gray,
  });
  addText(slide, DATA.thesis.strategic_thesis, 0.72, 1.72, 10.8, 1.05, {
    fontSize: 30, bold: true,
  });
  addText(slide, cleanLine(DATA.thesis.reasoning?.[0], "从诊断结论出发，形成有取舍的增长路径。"), 0.76, 3.04, 7.3, 0.62, {
    fontSize: 11, color: C.gray,
  });
  addPanel(slide, 8.55, 3.78, 3.35, 1.35, true);
  addText(slide, "方案对象", 8.88, 4.08, 0.9, 0.18, { fontSize: 8, color: C.gold });
  addText(slide, DATA.company, 8.88, 4.43, 2.45, 0.34, { fontSize: 18, bold: true });
  addText(slide, "五层方案", 0.78, 5.56, 0.9, 0.18, { fontSize: 8, color: C.gold });
  ["战略主张", "杠杆矩阵", "行动地图", "三阶段路线图", "90天计划"].forEach((label, index) => {
    const x = 0.78 + index * 2.15;
    addText(slide, `0${index + 1}`, x, 5.94, 0.35, 0.18, { fontSize: 8, bold: true, color: C.gold });
    addText(slide, label, x + 0.42, 5.9, 1.55, 0.28, { fontSize: 10.5, bold: true });
  });
  addFooter(slide, "方案总览");
}

function addStrategicThesis() {
  const slide = pptx.addSlide();
  addBackground(slide);
  addSlideTitle(slide, "先做取舍，再配置资源", "01 · 战略主张");

  addPanel(slide, 0.78, 1.86, 5.55, 1.62);
  addText(slide, "放弃 / 收缩", 1.08, 2.15, 1.2, 0.18, { fontSize: 8, color: C.muted, bold: true });
  addText(slide, DATA.thesis.from_to?.from, 1.08, 2.58, 4.8, 0.54, { fontSize: 15, bold: true });

  addPanel(slide, 6.78, 1.86, 5.55, 1.62, true);
  addText(slide, "转向 / 聚焦", 7.08, 2.15, 1.2, 0.18, { fontSize: 8, color: C.gold, bold: true });
  addText(slide, DATA.thesis.from_to?.to, 7.08, 2.58, 4.8, 0.54, { fontSize: 15, bold: true });

  const reasoning = DATA.thesis.reasoning || [];
  const assumptions = DATA.thesis.key_assumptions || [];
  addText(slide, "核心理由", 0.82, 4.05, 1.1, 0.2, { fontSize: 9, color: C.gold, bold: true });
  reasoning.slice(0, 4).forEach((item, index) => {
    const y = 4.44 + index * 0.52;
    addText(slide, String(index + 1).padStart(2, "0"), 0.84, y, 0.34, 0.18, {
      fontSize: 7.5, color: C.gold, bold: true,
    });
    addText(slide, item, 1.25, y - 0.03, 5.15, 0.34, { fontSize: 9.5 });
  });
  addText(slide, "关键前提假设", 7.0, 4.05, 1.4, 0.2, { fontSize: 9, color: C.gold, bold: true });
  const assumptionList = assumptions.length ? assumptions : ["无额外待确认前提"];
  assumptionList.slice(0, 4).forEach((item, index) => {
    const y = 4.44 + index * 0.52;
    addShape(slide, pptx.ShapeType.ellipse, {
      x: 7.02, y: y + 0.02, w: 0.17, h: 0.17,
      fill: { color: C.panelGold },
      line: { color: C.gold, width: 0.7 },
    }, "assumption dot");
    addText(slide, item, 7.35, y - 0.03, 4.65, 0.34, { fontSize: 9.5, color: C.gray });
  });
  addFooter(slide, "战略主张");
}

function addLeverMatrix() {
  const pages = paginate(DATA.levers.levers || [], 6);
  const selected = selectedLeverNames();
  pages.forEach((levers, pageIndex) => {
    const slide = pptx.addSlide();
    addBackground(slide);
    addSlideTitle(slide, pageIndex === 0 ? "只选择少数真正能推动战略的增长杠杆" : "候选杠杆续页", `02 · 杠杆选择矩阵 ${pageIndex + 1}/${pages.length}`);

    const chartX = 0.82;
    const chartY = 1.82;
    const chartW = 5.18;
    const chartH = 4.75;
    addPanel(slide, chartX, chartY, chartW, chartH);
    addText(slide, "影响力", chartX + 0.12, chartY + 0.08, 0.7, 0.18, { fontSize: 7.5, color: C.gray });
    addText(slide, "可行性", chartX + chartW - 0.7, chartY + chartH - 0.3, 0.55, 0.18, { fontSize: 7.5, color: C.gray, align: "right" });
    addShape(slide, pptx.ShapeType.line, {
      x: chartX + 0.58, y: chartY + chartH - 0.55, w: chartW - 0.92, h: 0,
      line: { color: C.line, width: 1 },
    }, "matrix x axis");
    addShape(slide, pptx.ShapeType.line, {
      x: chartX + 0.58, y: chartY + 0.42, w: 0, h: chartH - 0.97,
      line: { color: C.line, width: 1 },
    }, "matrix y axis");
    [1, 2, 3].forEach((level) => {
      const x = chartX + 0.65 + (level - 1) * 1.42;
      const y = chartY + chartH - 0.68 - (level - 1) * 1.32;
      addText(slide, ["低", "中", "高"][level - 1], x, chartY + chartH - 0.34, 0.3, 0.16, {
        fontSize: 7, color: C.muted, align: "center",
      });
      addText(slide, ["低", "中", "高"][level - 1], chartX + 0.18, y, 0.3, 0.16, {
        fontSize: 7, color: C.muted, align: "center",
      });
    });
    levers.forEach((lever, index) => {
      const feasibility = LEVEL_SCORE[lever.feasibility?.level] || 1;
      const impact = LEVEL_SCORE[lever.impact?.level] || 1;
      const jitter = (index % 3) * 0.11;
      const x = chartX + 0.76 + (feasibility - 1) * 1.42 + jitter;
      const y = chartY + chartH - 1.02 - (impact - 1) * 1.32 - jitter;
      const active = selected.has(lever.name);
      addShape(slide, pptx.ShapeType.ellipse, {
        x, y, w: active ? 0.34 : 0.26, h: active ? 0.34 : 0.26,
        fill: { color: active ? C.goldBright : C.gray },
        line: { color: active ? C.gold : C.gray, width: 0.7 },
      }, "lever point");
      addText(slide, String(lever.priority || index + 1), x + 0.08, y + 0.08, 0.18, 0.12, {
        fontSize: 5.8, bold: true, color: C.bg, align: "center",
      });
    });

    const rowH = Math.min(0.78, 4.65 / Math.max(1, levers.length));
    levers.forEach((lever, index) => {
      const y = 1.88 + index * rowH;
      const active = selected.has(lever.name);
      addPanel(slide, 6.42, y, 5.9, rowH - 0.08, active);
      addText(slide, String(lever.priority || index + 1).padStart(2, "0"), 6.66, y + 0.13, 0.34, 0.14, {
        fontSize: 7, color: active ? C.gold : C.muted, bold: true,
      });
      addText(slide, clampText(lever.name, 30), 7.12, y + 0.1, 3.3, 0.23, {
        fontSize: 10, bold: true,
      });
      addText(slide, `${lever.impact?.level || "-"}影响 × ${lever.feasibility?.level || "-"}可行`, 10.58, y + 0.11, 1.38, 0.18, {
        fontSize: 7.5, color: active ? C.goldBright : C.gray, align: "right",
      });
      addText(slide, clampText(lever.description, 72), 7.12, y + 0.38, 4.75, Math.max(0.2, rowH - 0.5), {
        fontSize: 7.8, color: C.gray,
      });
    });
    addFooter(slide, "杠杆选择矩阵");
  });
}

function addActionMap() {
  const groups = CATEGORY_ORDER.map((category) => ({
    category,
    actions: (DATA.actions.actions || []).filter((item) => item.category === category),
  }));
  const maxCount = Math.max(...groups.map((group) => group.actions.length), 1);
  const pages = maxCount > 4 ? 2 : 1;
  for (let pageIndex = 0; pageIndex < pages; pageIndex += 1) {
    const slide = pptx.addSlide();
    addBackground(slide);
    addSlideTitle(slide, pageIndex === 0 ? "把选中杠杆转成四类可执行动作" : "行动地图续页", `03 · 四类行动地图 ${pageIndex + 1}/${pages}`);
    const colW = 2.88;
    groups.forEach((group, groupIndex) => {
      const x = 0.64 + groupIndex * 3.12;
      addText(slide, CATEGORY_LABELS[group.category], x, 1.62, 1.15, 0.26, {
        fontSize: 12, bold: true, color: groupIndex === 0 ? C.goldBright : C.white,
      });
      addText(slide, group.category, x + 1.14, 1.67, 1.45, 0.18, {
        fontSize: 7.2, color: C.muted, align: "right",
      });
      const pageActions = group.actions.slice(pageIndex * 4, pageIndex * 4 + 4);
      const list = pageActions.length ? pageActions : [];
      const rowH = 1.04;
      list.forEach((item, index) => {
        const y = 2.08 + index * 1.18;
        addPanel(slide, x, y, colW, rowH, groupIndex === 0 && index === 0 && pageIndex === 0);
        addText(slide, clampText(item.action, 42), x + 0.2, y + 0.17, colW - 0.4, 0.42, {
          fontSize: 8.8, bold: true,
        });
        addText(slide, `${cleanLine(item.owner, "待定")} · ${clampText(item.expected_output, 24)}`, x + 0.2, y + 0.72, colW - 0.4, 0.16, {
          fontSize: 6.8, color: C.gray,
        });
      });
      if (!list.length) {
        addText(slide, "本案例该类暂无行动", x, 2.24, colW, 0.28, {
          fontSize: 8.5, color: C.muted, align: "center",
        });
      }
    });
    addFooter(slide, "四类行动地图");
  }
}

function addRoadmap() {
  const slide = pptx.addSlide();
  addBackground(slide);
  addSlideTitle(slide, "按依赖顺序推进，而不是同时铺开", "04 · 三阶段路线图");
  const phases = DATA.roadmap.phases || [];
  phases.forEach((phase, index) => {
    const x = 0.72 + index * 4.16;
    const highlight = index === 0;
    addPanel(slide, x, 1.82, 3.75, 4.88, highlight);
    addText(slide, `阶段 ${String(index + 1).padStart(2, "0")}`, x + 0.28, 2.08, 0.8, 0.18, {
      fontSize: 7.5, color: highlight ? C.gold : C.muted, bold: true,
    });
    addText(slide, clampText(phase.phase_name, 18), x + 0.28, 2.43, 3.15, 0.42, {
      fontSize: 15, bold: true,
    });
    addText(slide, "目标", x + 0.28, 3.08, 0.5, 0.16, { fontSize: 7.5, color: C.gold });
    addText(slide, clampText(phase.goal, 58), x + 0.28, 3.37, 3.12, 0.58, {
      fontSize: 9.2, bold: true,
    });
    addText(slide, "关键行动", x + 0.28, 4.18, 0.72, 0.16, { fontSize: 7.5, color: C.gold });
    (phase.actions || []).slice(0, 4).forEach((item, actionIndex) => {
      addText(slide, `${actionIndex + 1}. ${clampText(item.action || item, 34)}`, x + 0.28, 4.5 + actionIndex * 0.36, 3.12, 0.24, {
        fontSize: 7.9, color: C.gray,
      });
    });
    addText(slide, "里程碑", x + 0.28, 5.98, 0.65, 0.16, { fontSize: 7.5, color: C.gold });
    addText(slide, clampText(phase.milestone, 48), x + 0.28, 6.22, 3.12, 0.3, {
      fontSize: 8.5, bold: true,
    });
    if (index < phases.length - 1) {
      addText(slide, "→", x + 3.82, 4.03, 0.28, 0.3, {
        fontSize: 18, bold: true, color: C.gold, align: "center",
      });
    }
  });
  addFooter(slide, "三阶段路线图");
}

function timeframeOrder(value) {
  const match = cleanLine(value).match(/\d+/);
  return match ? Number(match[0]) : 999;
}

function addNinetyDayPlan() {
  const sorted = (DATA.plan.plan || []).slice().sort((a, b) => timeframeOrder(a.timeframe) - timeframeOrder(b.timeframe));
  const pages = paginate(sorted, 6);
  pages.forEach((items, pageIndex) => {
    const slide = pptx.addSlide();
    addBackground(slide);
    addSlideTitle(slide, pageIndex === 0 ? "把最紧急阶段压实到未来 90 天" : "90 天行动计划续页", `05 · 90天行动计划 ${pageIndex + 1}/${pages.length}`);
    const rowH = Math.min(0.78, 4.8 / Math.max(1, items.length));
    addText(slide, "时间", 0.78, 1.63, 1.05, 0.18, { fontSize: 7.5, color: C.gold, bold: true });
    addText(slide, "任务", 1.92, 1.63, 3.85, 0.18, { fontSize: 7.5, color: C.gold, bold: true });
    addText(slide, "负责人", 6.02, 1.63, 1.05, 0.18, { fontSize: 7.5, color: C.gold, bold: true });
    addText(slide, "产出物", 7.28, 1.63, 2.25, 0.18, { fontSize: 7.5, color: C.gold, bold: true });
    addText(slide, "衡量标准", 9.78, 1.63, 2.35, 0.18, { fontSize: 7.5, color: C.gold, bold: true });
    items.forEach((item, index) => {
      const y = 1.98 + index * (rowH + 0.1);
      addPanel(slide, 0.72, y, 11.65, rowH, index === 0 && pageIndex === 0);
      addText(slide, item.timeframe, 0.92, y + 0.18, 0.85, rowH - 0.28, {
        fontSize: 8.3, bold: true, color: index === 0 && pageIndex === 0 ? C.goldBright : C.white,
      });
      addText(slide, clampText(item.task, 62), 1.92, y + 0.14, 3.75, rowH - 0.24, {
        fontSize: 8.6, bold: true,
      });
      addText(slide, item.owner, 6.02, y + 0.18, 1.02, rowH - 0.28, { fontSize: 7.8, color: C.gray });
      addText(slide, clampText(item.deliverable, 30), 7.28, y + 0.16, 2.18, rowH - 0.26, { fontSize: 7.8 });
      addText(slide, clampText(item.metric, 38), 9.78, y + 0.16, 2.15, rowH - 0.26, { fontSize: 7.6, color: C.gray });
    });
    addFooter(slide, "90天行动计划");
  });
}

function humanChecks() {
  const checks = [];
  (DATA.synthesis.confirmed_reversals || []).forEach((item) => {
    if (item.status === "needs_human_falsifier_check") {
      checks.push({
        title: item.reframe || item.naive_reading || item.finding_id,
        detail: `证伪条件：${text(item.falsifier, "证伪条件将在方案深化阶段校准")}；依赖：${text(item.depends_on, "关键依赖将在方案阶段确认")}`,
      });
    }
  });
  DATA.dimensions.forEach((dimension) => {
    const item = dimension.reversal_candidate;
    if (item && item.status === "needs_human_falsifier_check") {
      checks.push({
        title: item.reframe || item.naive_reading || `${dimension.dimension}反转假设`,
        detail: `证伪条件：${text(item.falsifier, "证伪条件将在方案深化阶段校准")}`,
      });
    }
  });
  (DATA.thesis.key_assumptions || []).forEach((assumption) => {
    checks.push({ title: assumption, detail: "请顾问结合访谈、客户信息或经营数据确认。" });
  });
  return checks;
}

function addConsultantChecklist() {
  const slide = pptx.addSlide();
  addBackground(slide);
  addSlideTitle(slide, "方案进入执行前，先确认这些关键假设", "顾问确认清单");
  const checks = humanChecks();
  const list = checks.length ? checks.slice(0, 6) : [{
    title: "当前没有标记为 needs_human_falsifier_check 的待确认项",
    detail: "顾问仍需对战略取舍、资源承诺和 90 天责任人进行最终确认。",
  }];
  const rowH = Math.min(0.78, 4.8 / list.length);
  list.forEach((item, index) => {
    const y = 1.9 + index * (rowH + 0.14);
    addPanel(slide, 0.82, y, 11.45, rowH, index === 0);
    addShape(slide, pptx.ShapeType.rect, {
      x: 1.08, y: y + 0.22, w: 0.24, h: 0.24,
      fill: { color: C.bg },
      line: { color: C.gold, width: 0.9 },
    }, "check box");
    addText(slide, clampText(item.title, 52), 1.58, y + 0.15, 4.75, rowH - 0.24, {
      fontSize: 9.4, bold: true,
    });
    addText(slide, clampText(item.detail, 92), 6.72, y + 0.15, 4.95, rowH - 0.24, {
      fontSize: 8.3, color: C.gray,
    });
  });
  addText(slide, "确认后再进入项目排期与资源锁定", 0.84, 6.56, 4.2, 0.24, {
    fontSize: 10.5, bold: true, color: C.goldBright,
  });
  addFooter(slide, "顾问确认清单");
}

addCover();
addStrategicThesis();
addLeverMatrix();
addActionMap();
addRoadmap();
addNinetyDayPlan();
addConsultantChecklist();

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
