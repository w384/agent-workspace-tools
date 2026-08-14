from pathlib import Path
from zipfile import ZipFile


DEMO_SOURCE = (
    Path(__file__).parents[2]
    / "work"
    / "demo"
    / "public-drive-ai-organizing"
    / "source"
)


def test_demo_sample_assets_are_minimal_pdf_docx_first_and_self_contained():
    expected_files = {
        "客户资料/星河食品品牌资料.pdf",
        "项目策划/2026春季新品整合传播方案.docx",
        "报价合同/星河食品春季新品项目报价单.pdf",
        "原始素材/星河食品新品KV参考.jpg",
        "工程文件/春季新品主视觉工程.aep",
        "输出稿/星河食品春季新品主视觉KV.pdf",
        "输出稿/星河食品春季新品视频脚本.docx",
        "修改反馈/客户第三轮修改意见.docx",
        "验收交付/2026春季新品项目验收清单.pdf",
        "版权授权证明/内部法务评审意见.docx",
    }

    actual_files = {
        path.relative_to(DEMO_SOURCE).as_posix()
        for path in DEMO_SOURCE.rglob("*")
        if path.is_file()
    }

    assert actual_files == expected_files
    assert len(actual_files) == 10

    for relative_path in actual_files:
        path = DEMO_SOURCE / relative_path
        if path.suffix.lower() == ".pdf":
            assert path.read_bytes().startswith(b"%PDF-")
        if path.suffix.lower() == ".docx":
            with ZipFile(path) as archive:
                assert "word/document.xml" in archive.namelist()
