from pathlib import Path

from service.app.rag.contracts import ActiveAssetVersion
from service.app.rag.ingestion import IngestionRequest


DEMO_SOURCE = (
    Path(__file__).parents[3]
    / "work"
    / "demo"
    / "financial-preassessment"
    / "source"
)


def _request(source_ref: str, mime_type: str) -> IngestionRequest:
    return IngestionRequest(
        tenant_id="workspace-demo",
        target_version=ActiveAssetVersion("asset-demo", "version-demo-v1"),
        source_ref=source_ref,
        content_fingerprint="sha256:" + "d" * 64,
        mime_type=mime_type,
        size_bytes=(DEMO_SOURCE / source_ref).stat().st_size,
    )


def test_demo_parser_extracts_pdf_into_page_bound_chunks():
    from service.app.rag.demo_document_parser import DemoDocumentParser

    chunks = DemoDocumentParser(DEMO_SOURCE).parse(
        _request(
            "客户模拟资料/收入情况说明.pdf",
            "application/pdf",
        )
    )

    assert len(chunks) == 1
    assert chunks[0].page_number == 1
    assert chunks[0].paragraph_index is None
    assert "4,860万元" in chunks[0].text
    assert "营业收入" in chunks[0].text
    assert chunks[0].asset_id == "asset-demo"
    assert chunks[0].asset_version_id == "version-demo-v1"


def test_demo_parser_extracts_docx_into_paragraph_bound_chunks():
    from service.app.rag.demo_document_parser import DemoDocumentParser

    chunks = DemoDocumentParser(DEMO_SOURCE).parse(
        _request(
            "敏感资料/内部资料核验说明.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    )

    assert [chunk.paragraph_index for chunk in chunks] == [0, 1, 2, 3]
    assert all(chunk.page_number is None for chunk in chunks)
    assert "虚构的内部核验说明" in chunks[1].text
    assert chunks[-1].ordinal == 3
