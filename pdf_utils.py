"""Render exactly one selected PDF page; never extract its text."""

import pymupdf as fitz


class PdfError(ValueError):
    pass


def _open_pdf(data: bytes) -> fitz.Document:
    try:
        document = fitz.open(stream=data, filetype="pdf")
        if document.needs_pass:
            document.close()
            raise PdfError("PDF защищён паролем. Загрузите файл без защиты.")
        if document.page_count < 1:
            document.close()
            raise PdfError("В PDF нет страниц.")
        return document
    except PdfError:
        raise
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError) as exc:
        raise PdfError("Не удалось открыть PDF. Возможно, файл повреждён.") from exc


def page_count(data: bytes) -> int:
    with _open_pdf(data) as document:
        return document.page_count


def render_page(data: bytes, page_number: int, dpi: int = 200) -> bytes:
    with _open_pdf(data) as document:
        if not 1 <= page_number <= document.page_count:
            raise PdfError("Выбранной страницы нет в PDF.")
        try:
            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            return pixmap.tobytes("png")
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise PdfError("Не удалось преобразовать выбранную страницу PDF в изображение.") from exc
