from pathlib import Path

from app.core.enums import SourceType


class UnsupportedSourceError(ValueError):
    pass


def infer_source_type(file_name: str) -> SourceType:
    extension = Path(file_name).suffix.lower()
    mapping = {
        ".txt": SourceType.TXT,
        ".md": SourceType.MARKDOWN,
        ".markdown": SourceType.MARKDOWN,
        ".pdf": SourceType.PDF,
        ".docx": SourceType.DOCX,
    }
    try:
        return mapping[extension]
    except KeyError as exc:
        raise UnsupportedSourceError("Поддерживаются TXT, Markdown, PDF и DOCX.") from exc


def extract_file_text(path: Path, file_name: str) -> tuple[SourceType, str]:
    source_type = infer_source_type(file_name)
    if source_type in {SourceType.TXT, SourceType.MARKDOWN}:
        return source_type, path.read_text(encoding="utf-8")
    if source_type is SourceType.PDF:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    else:
        from docx import Document

        text = "\n".join(paragraph.text for paragraph in Document(path).paragraphs)
    if not text.strip():
        raise ValueError("Не удалось извлечь текст из файла.")
    return source_type, text
