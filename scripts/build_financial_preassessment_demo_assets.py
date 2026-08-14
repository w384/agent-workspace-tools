"""Build fictional financial-preassessment demo assets and rule fixtures."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_ROOT = PROJECT_ROOT / "work" / "demo" / "financial-preassessment"
SOURCE_ROOT = DEMO_ROOT / "source"
RULES_PATH = DEMO_ROOT / "rules" / "demo-bank-rules-v1.json"
IMPORT_MANIFEST_PATH = DEMO_ROOT / "import-manifest.json"
DISCLAIMER = "仅供资料完整度与规则匹配演示参考，不参与贷款申请、审批、授信、额度测算或金融产品销售。"

PDF_DOCUMENTS = {
    "客户模拟资料/收入情况说明.pdf": (
        "收入情况说明（模拟资料）",
        (
            "本文件为完全虚构的演示资料，不含任何真实个人、账户或银行信息。",
            "模拟申请人近十二个月收入来源稳定，月度收入区间为示例区间，仅用于资料完整度演示。",
            "资料状态：已提供收入情况说明，可作为演示规则的材料依据。",
            DISCLAIMER,
        ),
    ),
    "客户模拟资料/资金流摘要.pdf": (
        "资金流摘要（模拟资料）",
        (
            "本文件为模拟资金流摘要，不是银行流水，不含真实账户、交易对手或交易明细。",
            "示例结论：资金流呈现连续记录，具体金额均为虚构占位数据。",
            "资料状态：已提供资金流摘要，可作为演示规则的材料依据。",
            DISCLAIMER,
        ),
    ),
    "客户模拟资料/补充材料清单.pdf": (
        "补充材料清单（模拟资料）",
        (
            "本文件用于说明当前演示资料范围，不构成金融产品申请材料。",
            "当前已提交：收入情况说明、资金流摘要、资产负债说明、经营情况说明。",
            "当前未提交：连续两年经营证明、可核验的外部资质说明。",
            DISCLAIMER,
        ),
    ),
    "规则依据/演示规则适用说明.pdf": (
        "演示规则适用说明",
        (
            "此文件仅说明演示规则的使用边界；规则正文以 demo-bank-rules-v1.json 的版本指纹为准。",
            "所有银行名称、规则条件和结果等级均为虚构示例，不代表任何真实银行或金融机构要求。",
            DISCLAIMER,
        ),
    ),
}

DOCX_DOCUMENTS = {
    "客户模拟资料/资料概览与授权说明.docx": (
        "资料概览与授权说明（模拟）",
        (
            "本演示资料全部为虚构或脱敏样例，禁止用于真实金融业务判断。",
            "资料用途：展示企业资料资产化、版本化、权限检索和确定性规则匹配。",
            DISCLAIMER,
        ),
    ),
    "客户模拟资料/资产负债说明.docx": (
        "资产负债说明（模拟资料）",
        (
            "资产与负债信息均为虚构示例，不包含真实财产、债务、身份或征信数据。",
            "资料状态：已提供资产负债说明，可用于演示材料完整度核验。",
            DISCLAIMER,
        ),
    ),
    "客户模拟资料/经营情况说明.docx": (
        "经营情况说明（模拟资料）",
        (
            "本文件描述虚构主体的经营连续性和资料准备情况，不构成经营证明。",
            "当前只提供一份经营情况说明，未提供连续两年经营证明。",
            DISCLAIMER,
        ),
    ),
    "敏感资料/内部资料核验说明.docx": (
        "内部资料核验说明（模拟敏感资料）",
        (
            "本文件是虚构的内部核验说明，仅用于演示权限负向控制。",
            "项目普通成员不应查询本文件；只有被显式授予权限的负责人可引用。",
            DISCLAIMER,
        ),
    ),
}


def main() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    for relative_path, (title, paragraphs) in PDF_DOCUMENTS.items():
        _build_pdf(SOURCE_ROOT / relative_path, title, paragraphs)
    for relative_path, (title, paragraphs) in DOCX_DOCUMENTS.items():
        _build_docx(SOURCE_ROOT / relative_path, title, paragraphs)
    _write_rule_fixture()
    _write_import_manifest()


def _write_rule_fixture() -> None:
    payload = {
        "source_type": "demo_fixture",
        "scenario": "finance_profile_matching",
        "rule_set_name": "演示银行规则样例",
        "assessment_rule_id": "demo-bank-a-complete",
        "version_label": "demo-2026-08-14",
        "disclaimer": DISCLAIMER,
        "rules": [
            {
                "rule_id": "demo-bank-a-complete",
                "bank_label": "示例银行A",
                "result_level": "MATCH",
                "requirements": [
                    {
                        "rule_id": "demo-bank-a-income",
                        "material_key": "income_statement",
                        "label": "收入情况说明",
                    },
                    {
                        "rule_id": "demo-bank-a-cashflow",
                        "material_key": "cashflow_summary",
                        "label": "资金流摘要",
                    },
                    {
                        "rule_id": "demo-bank-a-assets",
                        "material_key": "asset_liability_statement",
                        "label": "资产负债说明",
                    },
                ],
            },
            {
                "rule_id": "demo-bank-b-supplement",
                "bank_label": "示例银行B",
                "result_level": "POSSIBLE",
                "requirements": [
                    {
                        "rule_id": "demo-bank-b-income",
                        "material_key": "income_statement",
                        "label": "收入情况说明",
                    },
                    {
                        "rule_id": "demo-bank-b-business",
                        "material_key": "business_profile",
                        "label": "经营情况说明",
                    },
                    {
                        "rule_id": "demo-bank-b-supplement",
                        "material_key": "supplement_material_list",
                        "label": "补充材料清单",
                    },
                ],
            },
            {
                "rule_id": "demo-bank-c-history",
                "bank_label": "示例银行C",
                "result_level": "NOT_MATCH",
                "requirements": [
                    {
                        "rule_id": "demo-bank-c-history",
                        "material_key": "two_year_business_history",
                        "label": "连续两年经营证明",
                    },
                    {
                        "rule_id": "demo-bank-c-license",
                        "material_key": "external_qualification",
                        "label": "可核验的外部资质说明",
                    },
                ],
            },
        ],
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["content_fingerprint"] = "sha256:" + hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _write_import_manifest() -> None:
    payload = {
        "source_type": "demo_fixture",
        "scenario": "finance_profile_matching",
        "assets": [
            {
                "relative_path": "客户模拟资料/资料概览与授权说明.docx",
                "material_key": "customer_profile",
            },
            {
                "relative_path": "客户模拟资料/收入情况说明.pdf",
                "material_key": "income_statement",
            },
            {
                "relative_path": "客户模拟资料/资金流摘要.pdf",
                "material_key": "cashflow_summary",
            },
            {
                "relative_path": "客户模拟资料/资产负债说明.docx",
                "material_key": "asset_liability_statement",
            },
            {
                "relative_path": "客户模拟资料/经营情况说明.docx",
                "material_key": "business_profile",
            },
            {
                "relative_path": "客户模拟资料/补充材料清单.pdf",
                "material_key": "supplement_material_list",
            },
        ],
    }
    IMPORT_MANIFEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _build_pdf(path: Path, title: str, paragraphs: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    title_style = styles["Title"].clone("FinancialDemoTitle")
    title_style.fontName = "STSong-Light"
    title_style.fontSize = 18
    body_style = styles["BodyText"].clone("FinancialDemoBody")
    body_style.fontName = "STSong-Light"
    body_style.fontSize = 11
    body_style.leading = 18
    document = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=24 * mm,
        rightMargin=24 * mm,
        topMargin=24 * mm,
        bottomMargin=24 * mm,
        title=title,
        author="企业资料资产化与场景知识库 DEMO",
    )
    story = [Paragraph(title, title_style), Spacer(1, 8 * mm)]
    story.extend(Paragraph(paragraph, body_style) for paragraph in paragraphs)
    document.build(story)


def _build_docx(path: Path, title: str, paragraphs: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    document.core_properties.title = title
    document.core_properties.author = "企业资料资产化与场景知识库 DEMO"
    heading = document.add_heading(title, level=1)
    _apply_chinese_font(heading, 18)
    for paragraph_text in paragraphs:
        paragraph = document.add_paragraph(paragraph_text)
        _apply_chinese_font(paragraph, 11)
    document.save(path)


def _apply_chinese_font(paragraph, point_size: int) -> None:
    for run in paragraph.runs:
        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        run.font.size = Pt(point_size)


if __name__ == "__main__":
    main()
