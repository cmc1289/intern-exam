"""评估报告 PDF V2 生成（展示层，结构化评估报告）。

原则：
- 不重算分数、不修改评分逻辑、不重新调用 AI —— 全部复用 exam_records.result_json。
- 渲染：ReportLab（纯 pip，无系统字体/GTK 依赖），中文用内置 CID 字体 STSong-Light。
- 雷达图为服务端向量绘制，与网页报告使用同一份统计数据。

报告结构（V2）：
  P1 候选人评估摘要（管理者视角：总分/评级/岗位匹配/一句话 AI 总结）
  P2 能力画像（雷达图 + 维度得分评价表）
  P3 AI 综合分析（优势能力 / 待提升方向 / 面试建议）
  P4+ 答题记录附录（客观题按维度汇总 + 错题号；主观题详细展示）
"""
import html
import math
import re
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

FONT_NAME = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

TYPE_LABELS = {
    "single_choice": "单选",
    "multi_choice": "多选",
    "true_false": "判断",
    "subjective": "主观题",
}

GRADE_BANDS = [
    # (min, label, stars, recommend)
    (90, "卓越", "★★★★★", "强烈推荐进入技术面试"),
    (80, "优秀", "★★★★☆", "推荐进入技术面试"),
    (70, "良好", "★★★☆☆", "可进入技术面试，重点考察薄弱方向"),
    (60, "基础", "★★☆☆☆", "建议补充基础后再次评估"),
    (0, "待提升", "★☆☆☆☆", "暂不推荐进入下一轮"),
]

# 岗位匹配：方向 key -> 岗位名（可扩展）
ROLE_MAP = {
    "Agent岗位": "AI Agent开发实习生",
    "前端开发": "前端开发工程师",
    "后端开发": "后端开发工程师",
    "测试": "测试开发工程师",
    "运维": "运维开发工程师",
    "算法数据": "算法与数据工程师",
}


def _style(**kw):
    base = dict(fontName=FONT_NAME, wordWrap="CJK", allowWidows=0, allowOrphans=0)
    base.update(kw)
    return ParagraphStyle(name=base.pop("name", "s"), **base)


ST_TITLE = _style(name="t", fontName=FONT_NAME, fontSize=19, leading=27, alignment=TA_CENTER, textColor=colors.HexColor("#0F172A"), spaceAfter=2)
ST_SUBTITLE = _style(name="st", fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#64748B"), spaceAfter=16)
ST_H1 = _style(name="h1", fontSize=14, leading=20, textColor=colors.HexColor("#1E293B"), spaceBefore=6, spaceAfter=10)
ST_H2 = _style(name="h2", fontSize=11.5, leading=17, textColor=colors.HexColor("#1E293B"), spaceBefore=8, spaceAfter=5)
ST_BODY = _style(name="b", fontSize=10, leading=15.5, textColor=colors.HexColor("#0F172A"))
ST_META_KEY = _style(name="mk", fontSize=10, leading=15, textColor=colors.HexColor("#64748B"))
ST_META_VAL = _style(name="mv", fontSize=10.5, leading=15.5, textColor=colors.HexColor("#0F172A"))
ST_QUESTION = _style(name="q", fontSize=10.5, leading=16, textColor=colors.HexColor("#0F172A"), spaceAfter=4)
ST_DETAIL = _style(name="d", fontSize=9.5, leading=14, textColor=colors.HexColor("#334155"))
ST_AI_TEXT = _style(name="ai", fontSize=11.5, leading=18, textColor=colors.HexColor("#1E293B"))
ST_SMALL = _style(name="sm", fontSize=8, leading=11, textColor=colors.HexColor("#94A3B8"))


def _fmt_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10]


def _fmt_answer(ans) -> str:
    if isinstance(ans, list):
        return "、".join(str(a) for a in ans) or "（未作答）"
    return str(ans).strip() or "（未作答）"


def _esc(text) -> str:
    return html.escape(str(text), quote=False)


def _sanitize_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", "_", name).strip("._ ")
    return name or "技术能力评估报告"


def _spec_keys(specialty_raw: str) -> list[str]:
    return [k for k in (specialty_raw or "").split(",") if k]


def _spec_label_text(specialty_raw: str, specialties_map: dict) -> str:
    labels = [
        (specialties_map.get(k) or {}).get("label", k)
        for k in _spec_keys(specialty_raw)
    ]
    return " / ".join(labels) or "通用基础"


def _role_name(specialty_raw: str, specialties_map: dict) -> str:
    for k in _spec_keys(specialty_raw):
        if k in ROLE_MAP:
            return ROLE_MAP[k]
    return f"{_spec_label_text(specialty_raw, specialties_map)}实习生"


def _grade_of(score: float | None) -> dict:
    if score is None:
        return {"label": "—", "stars": "—", "recommend": "—"}
    for lo, label, stars, rec in GRADE_BANDS:
        if score >= lo:
            return {"label": label, "stars": stars, "recommend": rec}
    return {"label": "待提升", "stars": "★☆☆☆☆", "recommend": "暂不推荐进入下一轮"}


def _dim_comment(acc: float) -> str:
    """维度得分 -> 一句话评价（阈值规则措辞）。"""
    if acc >= 90:
        return "掌握扎实，理解到位"
    if acc >= 75:
        return "理解良好，应用较熟练"
    if acc >= 60:
        return "基础了解，仍需深化"
    return "掌握不足，需加强学习"


def _capability_entries(result: dict) -> list[tuple[str, dict]]:
    """与网页同一口径：assessment_category（历史回退 category），>8 top8。"""
    stat_source = result.get("assessment_stats") or result.get("category_stats") or {}
    entries = list(stat_source.items())
    if len(entries) > 8:
        entries = sorted(entries, key=lambda kv: kv[1]["total_count"], reverse=True)[:8]
    return entries


# ---------------- 页眉页脚（含 Page X/Y） ----------------
class _NumberedCanvas:
    """包装 reportlab canvas 以便 Page X/Y 两遍输出。

    使用方式：doc.build(story, canvasmaker=_NumberedCanvas)。
    """

    def __init__(self, doc):
        self.doc = doc

    def __call__(self, *args, **kw):
        from reportlab.pdfgen import canvas as _pdfcanvas
        _doc = self.doc

        class NumberedCanvas(_pdfcanvas.Canvas):
            def __init__(self2, *a, **k):
                super().__init__(*a, **k)
                self2._saved_page_states = []

            def showPage(self2):
                self2._saved_page_states.append(dict(self2.__dict__))
                self2._startPage()

            def save(self2):
                num_pages = len(self2._saved_page_states)
                for state in self2._saved_page_states:
                    self2.__dict__.update(state)
                    self2.draw_header_footer(num_pages)
                    super().showPage()
                super().save()

            def draw_header_footer(self2, num_pages):
                self2.saveState()
                w, h = A4
                self2.setFont(FONT_NAME, 7.5)
                self2.setFillColor(colors.HexColor("#94A3B8"))
                # 页眉
                self2.drawString(18 * mm, h - 11 * mm, "智能技术能力评估平台 · Assessment Report")
                if _doc._report_id:
                    self2.drawRightString(w - 18 * mm, h - 11 * mm, _doc._report_id)
                self2.setStrokeColor(colors.HexColor("#E2E8F0"))
                self2.setLineWidth(0.5)
                self2.line(18 * mm, h - 13 * mm, w - 18 * mm, h - 13 * mm)
                # 页脚
                self2.setStrokeColor(colors.HexColor("#E2E8F0"))
                self2.line(18 * mm, 14 * mm, w - 18 * mm, 14 * mm)
                self2.setFillColor(colors.HexColor("#94A3B8"))
                self2.drawString(18 * mm, 10.5 * mm, "AI Technical Assessment Platform · Confidential Candidate Report")
                self2.drawRightString(w - 18 * mm, 10.5 * mm, f"Page {self2._pageNumber}/{num_pages}")
                self2.restoreState()

        return NumberedCanvas(*args, **kw)


# ---------------- 雷达图（向量绘制 Flowable） ----------------
class RadarChart(Flowable):
    """按维度列表绘制雷达图，直接嵌入 PDF 向量层。"""

    def __init__(self, labels: list[str], values: list[float], width=116 * mm, height=92 * mm):
        super().__init__()
        if len(labels) != len(values) or not labels:
            raise ValueError("radar labels/values 长度不一致或为空")
        self.labels = labels
        self.values = [max(0.0, min(100.0, float(v))) for v in values]
        self.width = width
        self.height = height
        self.hAlign = "CENTER"

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        canv = self.canv
        n = len(self.labels)
        cx, cy = self.width / 2, self.height / 2
        radius = min(self.width, self.height) / 2 - 22
        base_angle = math.pi / 2

        def point(angle, r):
            return (cx + r * math.cos(angle), cy + r * math.sin(angle))

        for level in (25, 50, 75, 100):
            pts = []
            for i in range(n):
                a = base_angle - 2 * math.pi * i / n
                px, py = point(a, radius * level / 100)
                pts.extend([px, py])
            canv.setLineWidth(0.6 if level < 100 else 1.0)
            canv.setStrokeColor(colors.HexColor("#CBD5E1" if level < 100 else "#94A3B8"))
            p = canv.beginPath()
            p.moveTo(pts[0], pts[1])
            for j in range(2, len(pts), 2):
                p.lineTo(pts[j], pts[j + 1])
            p.close()
            canv.drawPath(p)

        canv.setLineWidth(0.6)
        canv.setStrokeColor(colors.HexColor("#CBD5E1"))
        for i in range(n):
            a = base_angle - 2 * math.pi * i / n
            px, py = point(a, radius)
            canv.line(cx, cy, px, py)

        data_pts = []
        for i in range(n):
            a = base_angle - 2 * math.pi * i / n
            px, py = point(a, radius * self.values[i] / 100)
            data_pts.append((px, py))
        p = canv.beginPath()
        p.moveTo(data_pts[0][0], data_pts[0][1])
        for px, py in data_pts[1:]:
            p.lineTo(px, py)
        p.close()
        canv.saveState()
        canv.setFillColor(colors.HexColor("#6366F1"))
        canv.setFillAlpha(0.22)
        canv.drawPath(p, fill=1, stroke=0)
        canv.restoreState()
        canv.setStrokeColor(colors.HexColor("#4F46E5"))
        canv.setLineWidth(1.8)
        canv.drawPath(p, fill=0, stroke=1)

        canv.setFillColor(colors.HexColor("#4F46E5"))
        for px, py in data_pts:
            canv.circle(px, py, 2.2, fill=1, stroke=0)

        canv.setFont(FONT_NAME, 8.5)
        canv.setFillColor(colors.HexColor("#1E293B"))
        for i in range(n):
            a = base_angle - 2 * math.pi * i / n
            ex, ey = point(a, radius + 14)
            cosv = math.cos(a)
            sinv = math.sin(a)
            if abs(cosv) < 0.25:
                if sinv > 0:
                    canv.drawCentredString(cx, ey, self.labels[i])
                else:
                    canv.drawCentredString(cx, ey - 10, self.labels[i])
            elif cosv > 0:
                canv.drawString(ex, ey - 5, self.labels[i])
            else:
                canv.drawRightString(ex, ey - 5, self.labels[i])


def _make_table(rows, col_widths, header_bg="#EEF2FF", zebra=True):
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    if zebra:
        style.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]))
    t.setStyle(TableStyle(style))
    return t


def build_report_pdf(
    record: dict,
    exam: dict | None,
    specialties_map: dict,
    report_id: str = "",
) -> bytes:
    """生成 V2 结构化评估报告 PDF。report_id 如 ASSESS-20260904-001。"""
    result = record.get("result") or {}
    details = result.get("details") or []
    final_score = result.get("final_score")
    if final_score is None:
        final_score = record.get("final_score")
    passed = result.get("passed")
    if passed is None:
        passed = record.get("passed")

    exam_title = (exam or {}).get("title") or "—"
    spec_text = _spec_label_text(record.get("specialty"), specialties_map)
    role_name = _role_name(record.get("specialty"), specialties_map)
    grade = _grade_of(final_score)
    ai_summary = (result.get("ai_summary") or "").strip()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"{spec_text or exam_title} 技术能力评估报告",
        author="智能技术能力评估平台",
    )
    doc._report_id = report_id

    W = A4[0] - 36 * mm  # 内容宽
    story = []

    # ============ P1 候选人评估摘要 ============
    story.append(Paragraph(f"{_esc(spec_text or exam_title)}技术能力评估报告", ST_TITLE))
    story.append(Paragraph(f"候选人：{_esc(record.get('candidate_name') or '未署名')}　|　报告编号：{_esc(report_id or '—')}", ST_SUBTITLE))

    # 评分 + 评级
    score_show = f"{final_score}" if final_score is not None else "—"
    story.append(Paragraph(score_show, _style(fontSize=44, leading=52, alignment=TA_CENTER, textColor=colors.HexColor("#4F46E5"), spaceBefore=6)))
    verdict = "通过" if passed else "未通过"
    story.append(Paragraph(
        f"评级：<font color='#4F46E5'><b>{grade['label']}</b></font>（及格线 {result.get('pass_score', 60)} 分 · {verdict}）　{grade['stars']}",
        _style(fontSize=12, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#0F172A")),
    ))

    # 基础信息
    meta_rows = [
        ["考试名称", exam_title, "专业方向", spec_text],
        ["岗位匹配", role_name, "评估时间", _fmt_time(record.get("submitted_at"))],
    ]
    meta_cells = []
    for r in meta_rows:
        meta_cells.append([
            Paragraph(r[0], ST_META_KEY), Paragraph(_esc(r[1]), ST_META_VAL),
            Paragraph(r[2], ST_META_KEY), Paragraph(_esc(r[3]), ST_META_VAL),
        ])
    meta_table = Table(meta_cells, colWidths=[20 * mm, W * 0.5 - 20 * mm, 20 * mm, W * 0.5 - 20 * mm])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(meta_table)

    # 岗位匹配度 + 推荐
    match_row = Table(
        [[Paragraph("岗位匹配度", ST_META_KEY), Paragraph(f"{grade['stars']}", _style(fontSize=13, leading=18)),
          Paragraph("推荐结论", ST_META_KEY), Paragraph(_esc(grade["recommend"]), ST_META_VAL)]],
        colWidths=[24 * mm, W - 48 * mm - (W * 0.62), 24 * mm, W * 0.62],
    )
    match_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EEF2FF")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C7D2FE")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(Spacer(1, 4 * mm))
    story.append(match_row)

    # 一句话 AI 总结
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("评估摘要", ST_H2))
    summary_box = Table(
        [[Paragraph(_esc(ai_summary) if ai_summary else "未生成 AI 总结。", ST_AI_TEXT)]],
        colWidths=[W],
    )
    summary_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF4FF")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E9D5FF")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary_box)

    # ============ P2 能力画像 ============
    story.append(PageBreak())
    story.append(Paragraph("二、能力画像", ST_H1))
    entries = _capability_entries(result)
    if entries:
        if len(entries) >= 3:
            story.append(RadarChart([kv[0] for kv in entries], [kv[1].get("accuracy", 0) for kv in entries]))
            story.append(Spacer(1, 6 * mm))
        head = [Paragraph("能力维度", ST_META_KEY), Paragraph("得分", ST_META_KEY), Paragraph("评价", ST_META_KEY)]
        rows = [head]
        for k, v in entries:
            acc = v.get("accuracy", 0)
            rows.append([
                Paragraph(_esc(k), ST_META_VAL),
                Paragraph(f"{acc}", _style(fontSize=12, leading=16, alignment=TA_CENTER, textColor=colors.HexColor("#4F46E5"))),
                Paragraph(_esc(_dim_comment(acc)), ST_DETAIL),
            ])
        story.append(_make_table(rows, [W * 0.34, W * 0.13, W * 0.53]))
    else:
        story.append(Paragraph("本次作答暂无能力维度统计。", ST_BODY))

    # ============ P3 AI 综合分析（规则生成） ============
    story.append(PageBreak())
    story.append(Paragraph("三、AI 综合分析", ST_H1))

    # 依据维度正确率做规则分层
    dims = sorted(
        ((k, v.get("accuracy", 0), v.get("correct_count", 0), v.get("total_count", 0)) for k, v in dict(entries).items()),
        key=lambda x: x[1],
    )
    strong = [d for d in dims if d[1] >= 75]
    weak = [d for d in dims if d[1] < 75]

    # 3.1 优势能力
    story.append(Paragraph("优势能力", ST_H2))
    if strong:
        s_rows = []
        for k, acc, c, t in strong:
            comment = _dim_comment(acc)
            s_rows.append([Paragraph("✓", _style(fontSize=10, leading=14, textColor=colors.HexColor("#16A34A"))),
                           Paragraph(f"{_esc(k)} — {comment}（{c}/{t}，正确率 {acc}%）", ST_BODY)])
        story.append(_make_table(s_rows, [8 * mm, W - 8 * mm], header_bg="#F0FDF4", zebra=False))
    else:
        story.append(Paragraph("本次考核无明显优势维度，建议系统性补强基础。", ST_BODY))

    # 3.2 待提升方向
    story.append(Paragraph("待提升方向", ST_H2))
    if weak:
        w_rows = []
        for k, acc, c, t in weak:
            comment = _dim_comment(acc)
            w_rows.append([Paragraph("△", _style(fontSize=10, leading=14, textColor=colors.HexColor("#F59E0B"))),
                           Paragraph(f"{_esc(k)} — {comment}（{c}/{t}，正确率 {acc}%）", ST_BODY)])
        story.append(_make_table(w_rows, [8 * mm, W - 8 * mm], header_bg="#FFFBEB", zebra=False))
    else:
        story.append(Paragraph("各维度表现均衡且良好，暂无明确短板。", ST_BODY))

    # 3.3 面试建议
    story.append(Paragraph("面试建议", ST_H2))
    adv_lines = [f"• {grade['recommend']}（综合得分 {final_score} 分，评级：{grade['label']}）。"]
    if weak:
        focus = [k for k, _, _, _ in weak[:3]]
        if focus:
            adv_lines.append(f"• 面试重点考察：{('、'.join(focus))} 方向的实际掌握程度。")
    if ai_summary:
        adv_lines.append(f"• 参考 AI 点评：{ai_summary}")
    for line in adv_lines:
        story.append(Paragraph(_esc(line), ST_BODY))

    # ============ P4 答题记录附录 ============
    story.append(PageBreak())
    story.append(Paragraph("四、答题记录（附录）", ST_H1))

    # 客观题：按 assessment_category 汇总
    obj_details = [d for d in details if d.get("type") != "subjective"]
    subj_details = [d for d in details if d.get("type") == "subjective"]
    if obj_details:
        story.append(Paragraph("客观题 · 知识点覆盖", ST_H2))
        group: dict[str, dict] = {}
        for idx, d in enumerate(obj_details):
            ac = d.get("assessment_category") or d.get("category") or "未分类"
            g = group.setdefault(ac, {"correct": 0, "total": 0, "wrong": []})
            g["total"] += 1
            if d.get("is_correct"):
                g["correct"] += 1
            else:
                g["wrong"].append(idx + 1)  # 附录内题号（客观题计数）
        o_rows = [[Paragraph("知识点", ST_META_KEY), Paragraph("答对/题量", ST_META_KEY), Paragraph("错题号", ST_META_KEY)]]
        for k, g in sorted(group.items(), key=lambda kv: kv[1]["correct"] / kv[1]["total"] if kv[1]["total"] else 0):
            wrong_txt = "、".join(str(i) for i in g["wrong"]) if g["wrong"] else "无"
            o_rows.append([
                Paragraph(_esc(k), ST_META_VAL),
                Paragraph(f"{g['correct']}/{g['total']}", _style(fontSize=11, leading=15, alignment=TA_CENTER)),
                Paragraph(_esc(wrong_txt), ST_DETAIL),
            ])
        story.append(_make_table(o_rows, [W * 0.3, W * 0.15, W * 0.55]))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph("（附录客观题仅做知识点覆盖汇总；主观题见下，含 AI 点评与得分。）", ST_SMALL))
    else:
        story.append(Paragraph("本次作答无客观题。", ST_BODY))

    # 主观题：逐题详细
    if subj_details:
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("主观题作答详情", ST_H2))
        for idx, d in enumerate(subj_details, start=1):
            color = "#16A34A" if d.get("is_correct") else "#DC2626"
            title = f"主观题 {idx}. [{_esc(d.get('assessment_category') or d.get('category') or '未分类')}] {d.get('difficulty') or ''} ×{d.get('weight') or 0}"
            score_txt = f"{d.get('score', 0)} / {d.get('max_score', 0)}"
            q_rows_extra = []
            if d.get("ai_comment"):
                q_rows_extra.append([Paragraph("AI 点评", ST_META_KEY), Paragraph(_esc(d["ai_comment"]), ST_DETAIL)])
            if d.get("explanation"):
                q_rows_extra.append([Paragraph("参考要点", ST_META_KEY), Paragraph(_esc(d["explanation"]), ST_DETAIL)])
            q_table = Table(
                [
                    [Paragraph(_esc(title), ST_META_KEY), Paragraph(score_txt, _style(fontSize=12, leading=16, alignment=TA_RIGHT, textColor=colors.HexColor(color)))],
                    [Paragraph(_esc(d.get("question") or ""), ST_QUESTION), ""],
                    [Paragraph("考生回答", ST_META_KEY), Paragraph(_esc(_fmt_answer(d.get("user_answer"))), ST_DETAIL)],
                    [Paragraph("AI 评分", ST_META_KEY),
                     Paragraph(f"{d.get('ai_score', 0)} 分（{'AI 评判' if d.get('ai_used') else '关键词评判'}）", ST_DETAIL)],
                ]
                + q_rows_extra,
                colWidths=[30 * mm, W - 30 * mm],
            )
            q_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F1F5F9")),
                ("SPAN", (0, 1), (1, 1)),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(KeepTogether(q_table))
            story.append(Spacer(1, 3 * mm))

    doc.build(story, canvasmaker=_NumberedCanvas(doc))
    return buf.getvalue()


def make_pdf_filename(record: dict, exam: dict | None, specialties_map: dict) -> str:
    """按文档规范生成文件名：<方向>技术能力评估报告_<候选人>_<年份>.pdf"""
    spec = _spec_label_text(record.get("specialty"), specialties_map).replace(" / ", "_")
    title = (exam or {}).get("title") or ""
    base = _sanitize_filename(spec or title or "技术能力")
    name = _sanitize_filename(record.get("candidate_name") or "未署名")
    submitted = record.get("submitted_at") or ""
    year = submitted[:4] if submitted[:4].isdigit() else str(datetime.now().year)
    return f"{base}技术能力评估报告_{name}_{year}.pdf"
