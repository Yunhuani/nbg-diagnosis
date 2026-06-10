const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const PptxGenJS = require("pptxgenjs");

const OUT_DIR = path.join(__dirname, "output");
const OUT_FILE = path.join(OUT_DIR, "甬辉_样板_雷达修正版.pptx");
const RADAR_FILE = path.join(OUT_DIR, "dimension_radar.png");
const REVIEWED = process.argv.includes("--reviewed");

const W = 13.333;
const H = 7.5;

const C = {
  bg: "121317",
  bgDeep: "0E0F13",
  panel: "1A1B20",
  panelGold: "231F16",
  line: "3A3C44",
  gold: "E8B84B",
  goldBright: "FFD166",
  white: "EAEDF3",
  gray: "9DA4B3",
  muted: "6E7180",
  amber: "E0A05A",
};

const synthesis = {
  company: "甬辉",
  product: "NBG增长解码",
  rating: "警告",
  score: "3.8",
  dimension_scores: {
    market: 4,
    competition: 4,
    business_model: 4,
    capability: 4,
    finance: 3,
  },
  overall_judgment:
    "现有能力足以维持现状、但无法驱动增长，财务压力迫使短期内做艰难取舍：先止住现金与利润失血，再把认证和交付壁垒转化为高值增长入口。",
  three_key_findings: [
    {
      title: "现金跑道仅1.6个月，流动性危机一触即发",
      why_surprising:
        "订单不少不等于现金安全；真正限制转身速度的，不是市场机会，而是账上现金承受不了试错。",
    },
    {
      title: "法兰/排水配件年亏410万，全品类代工正在吞噬利润",
      why_surprising:
        "看似补齐品类、稳住客户，实际是在用赚钱产品给亏损线输血；收入规模掩盖了利润黑洞。",
    },
    {
      title: "65%客户集中不是单纯软肋，认证和适配把依赖变成壁垒候选",
      why_surprising:
        "大客户依赖既是风险，也可能是别人进不来的门槛；关键在于认证、合作年限和定制适配是否真的形成切换成本。",
    },
  ],
};

const dimensionLabels = [
  ["market", "市场"],
  ["competition", "竞争"],
  ["business_model", "商业模式"],
  ["capability", "内部能力"],
  ["finance", "财务"],
];

function addText(slide, text, x, y, w, h, opts = {}) {
  slide.addText(text, {
    x,
    y,
    w,
    h,
    margin: 0,
    breakLine: false,
    fontFace: "Microsoft YaHei",
    fit: "shrink",
    color: C.white,
    ...opts,
  });
}

function addFooter(slide, framework = "NBG五维增长诊断") {
  addText(slide, `分析框架：${framework}`, 0.65, 7.08, 4.2, 0.18, {
    fontSize: 7.5,
    color: C.muted,
  });
  const statusText = REVIEWED ? "顾问审核版" : "草稿版";
  addText(slide, `甬辉 · ${statusText}`, 8.6, 7.08, 3.95, 0.18, {
    fontSize: 7.5,
    color: C.muted,
    align: "right",
  });
}

function addBackground(slide) {
  slide.background = { color: C.bg };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: W,
    h: H,
    fill: { color: C.bg },
    line: { color: C.bg },
  });
}

function buildRadarPng() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const script = `
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

labels = ["市场", "竞争", "商业模式", "内部能力", "财务"]
values = [4, 4, 4, 4, 3]
angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
angles_closed = np.concatenate([angles, angles[:1]])
values_closed = values + values[:1]

fig = plt.figure(figsize=(4.2, 4.2), dpi=220)
fig.patch.set_alpha(0)
ax = plt.subplot(111, polar=True)
ax.set_facecolor((0, 0, 0, 0))
ax.set_theta_offset(np.pi / 2)
ax.set_theta_direction(-1)
ax.set_ylim(0, 5)
ax.spines["polar"].set_visible(False)
ax.grid(False)
ax.set_yticks([1, 2, 3, 4, 5])
ax.set_yticklabels([])
ax.set_xticks(angles)
ax.set_xticklabels(labels, color="#EAEDF3", fontsize=8)

for radius in [1, 2, 3, 4, 5]:
    ring = [radius] * (len(labels) + 1)
    ax.plot(angles_closed, ring, color="#3A3C44", linewidth=0.55, alpha=0.42)
for angle in angles:
    ax.plot([angle, angle], [0, 5], color="#3A3C44", linewidth=0.45, alpha=0.28)

ax.plot(angles_closed, values_closed, color="#E8B84B", linewidth=1.35)
ax.fill(angles_closed, values_closed, color="#E8B84B", alpha=0.15)
ax.scatter(angles, values, s=10, color="#FFD166", zorder=3)
plt.tight_layout(pad=0.45)
plt.savefig(r"${RADAR_FILE.replace(/\\/g, "\\\\")}", transparent=True)
`;
  const result = spawnSync("py", ["-c", script], { encoding: "utf8" });
  return result.status === 0 && fs.existsSync(RADAR_FILE);
}

function radarPoint(cx, cy, r, index, valueScale = 1) {
  const angle = -Math.PI / 2 + (index * 2 * Math.PI) / dimensionLabels.length;
  return {
    x: cx + Math.cos(angle) * r * valueScale,
    y: cy + Math.sin(angle) * r * valueScale,
  };
}

function svgPoints(points) {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

function buildRadarSvgData() {
  const size = 700;
  const cx = size / 2;
  const cy = size / 2;
  const r = 230;
  const ringPolygons = [1, 2, 3, 4, 5]
    .map((tick) => {
      const points = dimensionLabels.map((_, i) => radarPoint(cx, cy, r, i, tick / 5));
      return `<polygon points="${svgPoints(points)}" fill="none" stroke="#3A3C44" stroke-opacity="0.42" stroke-width="1.1"/>`;
    })
    .join("");
  const axes = dimensionLabels
    .map((_, i) => {
      const p = radarPoint(cx, cy, r, i, 1);
      return `<line x1="${cx}" y1="${cy}" x2="${p.x.toFixed(1)}" y2="${p.y.toFixed(1)}" stroke="#3A3C44" stroke-opacity="0.28" stroke-width="0.9"/>`;
    })
    .join("");
  const scorePoints = dimensionLabels.map(([key], i) => radarPoint(cx, cy, r, i, synthesis.dimension_scores[key] / 5));
  const labels = dimensionLabels
    .map(([, label], i) => {
      const p = radarPoint(cx, cy, r + 48, i, 1);
      return `<text x="${p.x.toFixed(1)}" y="${(p.y + 4).toFixed(1)}" fill="#EAEDF3" font-size="22" font-family="Microsoft YaHei, Arial, sans-serif" text-anchor="middle">${label}</text>`;
    })
    .join("");
  const dots = scorePoints
    .map((p) => `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4.4" fill="#FFD166"/>`)
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <rect width="${size}" height="${size}" fill="none"/>
  ${ringPolygons}
  ${axes}
  <polygon points="${svgPoints(scorePoints)}" fill="#E8B84B" fill-opacity="0.15" stroke="#E8B84B" stroke-width="3" stroke-linejoin="round"/>
  ${dots}
  ${labels}
</svg>`;
  return `data:image/svg+xml;base64,${Buffer.from(svg).toString("base64")}`;
}

function addRadar(slide, x, y, w, h) {
  if (buildRadarPng()) {
    slide.addImage({ path: RADAR_FILE, x, y, w, h });
    return;
  }
  slide.addImage({ data: buildRadarSvgData(), x, y, w, h });
}

function addCover(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);
  slide.background = { color: C.bgDeep };

  addText(slide, synthesis.product, 0.72, 0.62, 4.1, 0.42, {
    fontSize: 18,
    bold: true,
    color: C.gold,
    charSpace: 1.2,
  });
  addText(slide, "增长诊断报告 · 样板草稿", 0.72, 1.04, 2.55, 0.2, {
    fontSize: 8.5,
    color: C.gray,
  });

  addText(slide, "现有能力守得住今天，但撑不起下一轮增长", 0.72, 1.84, 7.55, 0.86, {
    fontSize: 27,
    bold: true,
    color: C.white,
    fit: "shrink",
  });

  addText(slide, synthesis.overall_judgment, 0.74, 3.04, 6.65, 0.8, {
    fontSize: 12.1,
    color: C.gray,
    fit: "shrink",
  });

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.76,
    y: 4.36,
    w: 2.12,
    h: 0.92,
    rectRadius: 0.04,
    fill: { color: C.panelGold },
    line: { color: C.gold, transparency: 12, width: 1 },
  });
  addText(slide, `${synthesis.rating} · ${synthesis.score}分`, 0.98, 4.6, 1.68, 0.3, {
    fontSize: 15.5,
    bold: true,
    color: C.goldBright,
    align: "center",
  });

  addText(slide, "诊断对象", 0.78, 5.78, 0.95, 0.18, { fontSize: 8, color: C.muted });
  addText(slide, synthesis.company, 0.78, 6.02, 1.4, 0.34, {
    fontSize: 17,
    bold: true,
    color: C.white,
  });
  addText(slide, "保密 · 仅供客户决策层阅读", 0.78, 6.43, 2.2, 0.18, {
    fontSize: 7.5,
    color: C.muted,
  });

  addText(slide, "五维评分", 9.28, 1.16, 1.5, 0.22, {
    fontSize: 9,
    color: C.gold,
    bold: true,
  });
  addRadar(slide, 8.12, 1.56, 3.82, 3.82);
  addText(slide, "market / competition / model / capability / finance", 8.12, 5.68, 3.82, 0.16, {
    fontSize: 6.5,
    color: C.muted,
    align: "center",
  });
  addFooter(slide);
}

function addFindingCard(slide, item, index, x) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y: 2.04,
    w: 3.78,
    h: 3.95,
    rectRadius: 0.03,
    fill: { color: index === 1 ? C.panelGold : C.panel },
    line: { color: index === 1 ? C.gold : C.line, transparency: 12, width: 0.9 },
  });
  addText(slide, `0${index + 1}`, x + 0.26, 2.31, 0.48, 0.26, {
    fontSize: 12,
    bold: true,
    color: C.gold,
  });
  addText(slide, item.title, x + 0.26, 2.82, 3.14, 0.92, {
    fontSize: 15,
    bold: true,
    color: C.white,
    fit: "shrink",
  });
  slide.addShape(pptx.ShapeType.line, {
    x: x + 0.26,
    y: 4.02,
    w: 0.82,
    h: 0,
    line: { color: C.gold, width: 1.2 },
  });
  addText(slide, item.why_surprising, x + 0.26, 4.32, 3.18, 1.14, {
    fontSize: 10.6,
    color: C.gray,
    fit: "shrink",
  });
}

function addThreeFindings(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);

  addText(slide, "真正限制甬辉增长的，不是机会不足，而是现金、利润和壁垒三件事", 0.62, 0.62, 11.6, 0.5, {
    fontSize: 25,
    bold: true,
    color: C.white,
    fit: "shrink",
  });
  addText(slide, "三个关键发现", 0.64, 1.24, 1.4, 0.2, {
    fontSize: 8.5,
    color: C.gold,
  });
  addText(slide, "读完这三条，就能理解为什么诊断先谈止血，再谈增长。", 0.64, 1.49, 4.35, 0.25, {
    fontSize: 10,
    color: C.gray,
  });

  [0.72, 4.78, 8.84].forEach((x, index) => addFindingCard(slide, synthesis.three_key_findings[index], index, x));
  addFooter(slide, "NBG五维综合验证 · 三个关键发现");
}

function addScorePill(slide, label, value, x, y) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w: 1.42,
    h: 0.62,
    rectRadius: 0.03,
    fill: { color: C.panel },
    line: { color: C.line, transparency: 10, width: 0.8 },
  });
  addText(slide, label, x + 0.14, y + 0.12, 0.82, 0.14, {
    fontSize: 7.2,
    color: C.gray,
  });
  addText(slide, `${value}/10`, x + 0.14, y + 0.31, 0.72, 0.18, {
    fontSize: 10.5,
    bold: true,
    color: C.goldBright,
  });
}

function addOverallJudgment(pptx) {
  const slide = pptx.addSlide();
  addBackground(slide);

  addText(slide, "现有能力足以维持现状，但无法驱动增长", 0.62, 0.62, 8.7, 0.5, {
    fontSize: 26,
    bold: true,
    color: C.white,
    fit: "shrink",
  });
  addText(slide, "总体判断", 0.64, 1.24, 1.05, 0.2, {
    fontSize: 8.5,
    color: C.gold,
  });
  addText(slide, "财务压力迫使甬辉短期内做艰难取舍：先止住失血，再选择能转化壁垒的增长入口。", 0.64, 1.52, 6.6, 0.36, {
    fontSize: 12,
    color: C.gray,
    fit: "shrink",
  });

  slide.addShape(pptx.ShapeType.line, {
    x: 0.68,
    y: 2.42,
    w: 0,
    h: 2.68,
    line: { color: C.gold, width: 1.2 },
  });
  addText(slide, synthesis.overall_judgment, 1.02, 2.34, 6.18, 1.4, {
    fontSize: 19,
    bold: true,
    color: C.white,
    fit: "shrink",
  });
  addText(slide, "这不是单点经营问题，而是增长窗口、竞争壁垒、能力短板与财务约束同时交汇后的结构性取舍。", 1.04, 4.05, 5.9, 0.56, {
    fontSize: 11.2,
    color: C.gray,
    fit: "shrink",
  });

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 8.02,
    y: 1.12,
    w: 3.88,
    h: 4.68,
    rectRadius: 0.03,
    fill: { color: C.bg, transparency: 100 },
    line: { color: C.line, transparency: 45, width: 0.7 },
  });
  addText(slide, "五维评级一览", 8.34, 1.45, 1.55, 0.2, {
    fontSize: 9,
    color: C.gold,
    bold: true,
  });
  addRadar(slide, 8.38, 1.78, 3.1, 3.1);
  const pillY = 5.24;
  addScorePill(slide, "市场", synthesis.dimension_scores.market, 1.04, 5.58);
  addScorePill(slide, "竞争", synthesis.dimension_scores.competition, 2.68, 5.58);
  addScorePill(slide, "商业模式", synthesis.dimension_scores.business_model, 4.32, 5.58);
  addScorePill(slide, "内部能力", synthesis.dimension_scores.capability, 5.96, 5.58);
  addScorePill(slide, "财务", synthesis.dimension_scores.finance, 7.6, 5.58);
  addText(slide, `总体评级：${synthesis.rating} · ${synthesis.score}分`, 9.2, pillY, 1.8, 0.2, {
    fontSize: 9,
    color: C.goldBright,
    bold: true,
    align: "center",
  });
  addFooter(slide, "NBG五维综合验证 · 总体判断");
}

const pptx = new PptxGenJS();
pptx.layout = "LAYOUT_WIDE";
pptx.author = "NBG Diagnosis";
pptx.subject = "NBG增长解码 · 甬辉样板";
pptx.title = "甬辉_样板";
pptx.company = "甬辉";
pptx.lang = "zh-CN";
pptx.theme = {
  headFontFace: "Microsoft YaHei",
  bodyFontFace: "Microsoft YaHei",
  lang: "zh-CN",
};
pptx.defineLayout({ name: "LAYOUT_WIDE", width: W, height: H });

addCover(pptx);
addThreeFindings(pptx);
addOverallJudgment(pptx);

fs.mkdirSync(OUT_DIR, { recursive: true });
pptx.writeFile({ fileName: OUT_FILE }).then(() => {
  console.log(`Generated: ${OUT_FILE}`);
  console.log(`Reviewed: ${REVIEWED}`);
  console.log(`Radar PNG: ${fs.existsSync(RADAR_FILE) ? RADAR_FILE : "matplotlib unavailable; used SVG fallback"}`);
});
