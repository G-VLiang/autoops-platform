"""巡检报告导出：PDF（fpdf2）与 Excel（openpyxl）。

中文字体按平台自动探测；找不到可用字体时抛 RuntimeError，由接口层给出可读提示
（Excel 导出不依赖字体，任何环境都能用）。
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from sqlalchemy.orm import Session

from app.models import InspectionReport, TaskLog

# PDF 中文字体候选（按优先级）
_FONT_CANDIDATES = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/msyh.ttf",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

STATUS_LABEL = {"success": "成功", "partial": "部分失败", "failed": "失败"}
EVENT_LABEL = {"ok": "成功", "changed": "变更", "failed": "失败",
               "unreachable": "不可达", "info": "信息"}


def _tmp(suffix: str) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix="autoops_export_")
    os.close(fd)
    return path


def _find_font() -> str | None:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            return p
    # 兜底：扫描常见目录里的 ttf/otf
    for root in ("/usr/share/fonts", "/usr/local/share/fonts"):
        base = Path(root)
        if not base.exists():
            continue
        for pattern in ("**/*DroidSansFallback*.ttf", "**/wqy*.tt[cf]", "**/*NotoSansCJK*.tt[cf]"):
            found = list(base.glob(pattern))
            if found:
                return str(found[0])
    return None


def _clean(text: object, limit: int = 2000) -> str:
    """裁剪超长文本并去掉控制字符（PDF 排版和 Excel 单元格都需要）。"""
    s = "" if text is None else str(text)
    s = "".join(ch for ch in s if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    return s[:limit]


def _host_rows(db: Session, task_id: str | None) -> List[dict]:
    if not task_id:
        return []
    logs = db.query(TaskLog).filter(TaskLog.task_id == task_id).order_by(
        TaskLog.created_at.asc()).all()
    rows = []
    for l in logs:
        rows.append({
            "host": l.host or "-",
            "event": EVENT_LABEL.get(l.event, l.event),
            "message": _clean(l.message, 300),
            "stdout": _clean(l.stdout, 500),
        })
    return rows


# ---------------------------------------------------------------- PDF
def build_report_pdf(db: Session, report: InspectionReport) -> str:
    try:
        from fpdf import FPDF
    except ImportError as e:
        raise RuntimeError("服务端未安装 fpdf2，无法导出 PDF（pip install fpdf2）") from e

    font = _find_font()
    if not font:
        raise RuntimeError(
            "服务端缺少中文字体，无法生成 PDF。请安装 fonts-droid-fallback（Debian/Ubuntu）"
            "或改用 Excel 导出。")

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    try:
        pdf.add_font("cn", "", font)
    except Exception as e:
        raise RuntimeError(
            f"中文字体加载失败（{font}），请安装 fonts-droid-fallback 或改用 Excel 导出") from e
    pdf.set_font("cn", size=11)

    summary = report.summary or {}
    created = report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else "-"

    # 标题
    pdf.set_font("cn", size=18)
    pdf.cell(0, 12, "巡检报告", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("cn", size=10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, f"AutoOps 自动化运维平台 · 生成于 {datetime.now():%Y-%m-%d %H:%M}",
             new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # 基本信息
    pdf.set_font("cn", size=12)
    pdf.cell(0, 8, "一、基本信息", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("cn", size=10)
    info = [
        ("巡检计划", report.plan_name or "-"),
        ("巡检模板", report.template_name or "-"),
        ("执行状态", STATUS_LABEL.get(report.status, report.status or "-")),
        ("执行时间", created),
        ("报告编号", report.id),
        ("关联任务", report.task_id or "-"),
    ]
    for k, v in info:
        pdf.cell(35, 7, k, border=1)
        pdf.cell(0, 7, _clean(v, 80), border=1, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # 执行结果
    pdf.set_font("cn", size=12)
    pdf.cell(0, 8, "二、执行结果", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("cn", size=10)
    stats = [("成功", summary.get("ok", 0)), ("变更", summary.get("changed", 0)),
             ("失败", summary.get("failed", 0)), ("不可达", summary.get("unreachable", 0))]
    col_w = 190 / len(stats)
    for label, _ in stats:
        pdf.cell(col_w, 8, label, border=1, align="C")
    pdf.ln()
    for _, value in stats:
        pdf.cell(col_w, 8, str(value), border=1, align="C")
    pdf.ln(6)

    # 报告正文
    if report.content:
        pdf.set_font("cn", size=12)
        pdf.cell(0, 8, "三、报告内容", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("cn", size=10)
        pdf.multi_cell(0, 6, _clean(report.content, 4000))
        pdf.ln(3)

    # 主机明细
    rows = _host_rows(db, report.task_id)
    if rows:
        pdf.set_font("cn", size=12)
        pdf.cell(0, 8, "四、主机明细", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("cn", size=9)
        widths = (38, 22, 130)
        for title, w in zip(("主机", "结果", "说明"), widths):
            pdf.cell(w, 7, title, border=1, align="C")
        pdf.ln()
        for r in rows:
            pdf.cell(widths[0], 6, _clean(r["host"], 30), border=1)
            pdf.cell(widths[1], 6, r["event"], border=1, align="C")
            pdf.cell(widths[2], 6, _clean(r["message"], 90), border=1, new_x="LMARGIN", new_y="NEXT")

    path = _tmp(".pdf")
    pdf.output(path)
    return path


# ---------------------------------------------------------------- Excel
def _style_header(ws, row: int = 1) -> None:
    from openpyxl.styles import Alignment, Font, PatternFill

    for cell in ws[row]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1677FF")
        cell.alignment = Alignment(horizontal="center", vertical="center")


def _autofit(ws, widths: Sequence[int]) -> None:
    from openpyxl.utils import get_column_letter

    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def build_report_xlsx(db: Session, report: InspectionReport) -> str:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment
    except ImportError as e:
        raise RuntimeError("服务端未安装 openpyxl，无法导出 Excel（pip install openpyxl）") from e

    wb = Workbook()
    summary = report.summary or {}
    created = report.created_at.strftime("%Y-%m-%d %H:%M:%S") if report.created_at else "-"

    ws = wb.active
    ws.title = "报告概览"
    ws.append(["项目", "内容"])
    for k, v in [
        ("巡检计划", report.plan_name or "-"),
        ("巡检模板", report.template_name or "-"),
        ("执行状态", STATUS_LABEL.get(report.status, report.status or "-")),
        ("执行时间", created),
        ("报告编号", report.id),
        ("关联任务", report.task_id or "-"),
        ("成功数", summary.get("ok", 0)),
        ("变更数", summary.get("changed", 0)),
        ("失败数", summary.get("failed", 0)),
        ("不可达数", summary.get("unreachable", 0)),
        ("报告正文", _clean(report.content, 3000)),
    ]:
        ws.append([k, v])
    _style_header(ws)
    _autofit(ws, (16, 90))
    for row in ws.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")

    rows = _host_rows(db, report.task_id)
    if rows:
        ws2 = wb.create_sheet("主机明细")
        ws2.append(["主机", "结果", "说明", "详细输出"])
        for r in rows:
            ws2.append([r["host"], r["event"], r["message"], r["stdout"]])
        _style_header(ws2)
        _autofit(ws2, (22, 12, 50, 70))
        ws2.freeze_panes = "A2"

    path = _tmp(".xlsx")
    wb.save(path)
    return path


def build_reports_xlsx(reports: Iterable[InspectionReport]) -> str:
    """近 N 天报告汇总表。"""
    try:
        from openpyxl import Workbook
    except ImportError as e:
        raise RuntimeError("服务端未安装 openpyxl，无法导出 Excel（pip install openpyxl）") from e

    wb = Workbook()
    ws = wb.active
    ws.title = "巡检报告汇总"
    ws.append(["执行时间", "巡检计划", "模板", "状态", "成功", "变更", "失败", "不可达", "报告编号"])
    for r in reports:
        s = r.summary or {}
        ws.append([
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            r.plan_name or "-", r.template_name or "-",
            STATUS_LABEL.get(r.status, r.status or "-"),
            s.get("ok", 0), s.get("changed", 0), s.get("failed", 0), s.get("unreachable", 0),
            r.id,
        ])
    _style_header(ws)
    _autofit(ws, (20, 24, 20, 12, 8, 8, 8, 10, 34))
    ws.freeze_panes = "A2"
    path = _tmp(".xlsx")
    wb.save(path)
    return path
