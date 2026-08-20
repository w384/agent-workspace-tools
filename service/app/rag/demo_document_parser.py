"""Demo-only PDF/DOCX parser for the controlled sample source directory."""

import io
from pathlib import Path, PurePosixPath

from docx import Document
from pypdf import PdfReader

from service.app.rag.contracts import Chunk
from service.app.rag.ingestion import IngestionRequest
from service.app.rag.parser_worker import DOCX_MIME_TYPE, PDF_MIME_TYPE


class DemoDocumentParser:
    """Read PDF/DOCX fixtures only from one explicit demo source root."""

    def __init__(self, source_root: Path) -> None:
        self._source_root = source_root.resolve()

    def parse(self, request: IngestionRequest) -> tuple[Chunk, ...]:
        source_path = self._resolve_source(request.source_ref)
        if request.mime_type == PDF_MIME_TYPE:
            return _parse_pdf(source_path, request)
        if request.mime_type == DOCX_MIME_TYPE:
            return _parse_docx(source_path, request)
        raise ValueError("demo parser does not support this MIME type")

    def parse_bytes(
        self,
        request: IngestionRequest,
        content: bytes,
    ) -> tuple[Chunk, ...]:
        """Parse an in-memory PDF/DOCX payload (real uploaded material).

        Used by the demo upload pipeline: the BFF never writes uploaded bytes
        to disk, so the parser consumes a BytesIO stream instead of a file on
        the controlled source root.
        """
        if not content:
            raise ValueError("demo parser received empty content")
        stream = io.BytesIO(content)
        if request.mime_type == PDF_MIME_TYPE:
            return _parse_pdf(stream, request)
        if request.mime_type == DOCX_MIME_TYPE:
            return _parse_docx(stream, request)
        raise ValueError("demo parser does not support this MIME type")

    def _resolve_source(self, source_ref: str) -> Path:
        relative = PurePosixPath(source_ref)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("demo source reference must be relative")
        source_path = (self._source_root / Path(*relative.parts)).resolve()
        try:
            source_path.relative_to(self._source_root)
        except ValueError as error:
            raise ValueError("demo source is outside the controlled root") from error
        if not source_path.is_file():
            raise ValueError("demo source file does not exist")
        return source_path


def _parse_pdf(source, request: IngestionRequest) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for page_number, page in enumerate(PdfReader(source).pages, start=1):
        text = (page.extract_text() or "").strip()
        if not text:
            continue
        chunks.append(
            _chunk(
                request,
                ordinal=len(chunks),
                text=text,
                page_number=page_number,
                paragraph_index=None,
            )
        )
    return tuple(chunks)


def _parse_docx(source, request: IngestionRequest) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    for paragraph_index, paragraph in enumerate(Document(source).paragraphs):
        text = paragraph.text.strip()
        if not text:
            continue
        chunks.append(
            _chunk(
                request,
                ordinal=len(chunks),
                text=text,
                page_number=None,
                paragraph_index=paragraph_index,
            )
        )
    return tuple(chunks)


def _chunk(
    request: IngestionRequest,
    *,
    ordinal: int,
    text: str,
    page_number: int | None,
    paragraph_index: int | None,
) -> Chunk:
    return Chunk(
        tenant_id=request.tenant_id,
        asset_id=request.target_version.asset_id,
        asset_version_id=request.target_version.asset_version_id,
        chunk_id=(
            f"{request.target_version.asset_version_id}:"
            f"{ordinal}"
        ),
        ordinal=ordinal,
        text=text,
        page_number=page_number,
        paragraph_index=paragraph_index,
        parser_version="demo-pdf-docx-parser-v1",
        embedding_version="demo-lexical-v1",
        index_version="demo-in-memory-v1",
    )
