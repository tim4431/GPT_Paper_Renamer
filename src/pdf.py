"""PDF utilities backed by PyMuPDF (no external poppler dependency)."""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"


def is_valid_pdf(path: Path) -> bool:
    """Return True if *path* looks like a complete PDF file on disk."""
    try:
        if path.stat().st_size < 1024:
            return False
        with path.open("rb") as f:
            return f.read(5) == PDF_MAGIC
    except OSError:
        return False


def render_first_page(pdf_path: Path, out_path: Path, *, dpi: int = 150) -> Path:
    """Render the first page of *pdf_path* as a PNG at *out_path*."""
    with pymupdf.open(pdf_path) as doc:
        if doc.page_count == 0:
            raise ValueError(f"PDF has no pages: {pdf_path}")
        page = doc.load_page(0)
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        pixmap.save(out_path)
    return out_path
