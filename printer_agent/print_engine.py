"""
printer_agent/print_engine.py
------------------------------
Low-level print functions for PDF, DOCX, and TXT files on Windows.
Uses the Windows Shell / win32print APIs so no extra drivers are needed.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

import win32api
import win32con
import win32print

from .config import DEFAULT_PRINTER, COPIES
from .logger import get_logger, Path as _P  # noqa: re-export for type hints

logger = get_logger("print_engine")


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def get_default_printer() -> str:
    """Return the currently configured printer (from config or OS default)."""
    if DEFAULT_PRINTER:
        return DEFAULT_PRINTER
    return win32print.GetDefaultPrinter()


def list_printers() -> list[dict]:
    """Return a list of all installed printers with basic info."""
    printers = []
    for flags in (
        win32print.PRINTER_ENUM_LOCAL,
        win32print.PRINTER_ENUM_CONNECTIONS,
    ):
        for p in win32print.EnumPrinters(flags, None, 2):
            printers.append(
                {
                    "name":   p["pPrinterName"],
                    "driver": p["pDriverName"],
                    "port":   p["pPortName"],
                    "status": p["Status"],
                }
            )
    return printers


# ──────────────────────────────────────────────────────────────────
# File-type dispatchers
# ──────────────────────────────────────────────────────────────────

def _print_via_shell(file_path: Path, printer_name: str) -> None:
    """
    Use the Windows Shell 'print' verb.
    Works for any file type that has a registered print handler
    (PDF via Acrobat/Edge, DOCX via Word, TXT via Notepad, etc.).
    """
    logger.debug("Shell-print '%s' → printer '%s'", file_path.name, printer_name)
    win32api.ShellExecute(
        0,              # hwnd
        "print",        # verb
        str(file_path), # file
        f'/d:"{printer_name}"',  # parameters
        ".",            # working dir
        win32con.SW_HIDE,
    )


def _print_txt_raw(file_path: Path, printer_name: str) -> None:
    """Send a plain-text file directly to the printer as raw bytes."""
    logger.debug("RAW-print TXT '%s'", file_path.name)
    hprinter = win32print.OpenPrinter(printer_name)
    try:
        win32print.StartDocPrinter(hprinter, 1, (file_path.name, None, "RAW"))
        win32print.StartPagePrinter(hprinter)
        data = file_path.read_bytes()
        win32print.WritePrinter(hprinter, data)
        win32print.EndPagePrinter(hprinter)
        win32print.EndDocPrinter(hprinter)
    finally:
        win32print.ClosePrinter(hprinter)


def parse_page_range(range_str: str, max_pages: int | None = None) -> list[int]:
    """
    Parse a page range string like '1-3, 5, 8' into a sorted list of unique 1-based page numbers.
    """
    if not range_str or not range_str.strip():
        return []

    pages: set[int] = set()
    parts = range_str.replace(" ", "").split(",")
    for part in parts:
        if not part:
            continue
        if "-" in part:
            sub = part.split("-")
            if len(sub) == 2 and sub[0].isdigit() and sub[1].isdigit():
                start, end = int(sub[0]), int(sub[1])
                s, e = min(start, end), max(start, end)
                for p in range(s, e + 1):
                    pages.add(p)
        elif part.isdigit():
            pages.add(int(part))

    sorted_pages = sorted(p for p in pages if p > 0)
    if max_pages is not None:
        sorted_pages = [p for p in sorted_pages if p <= max_pages]
    return sorted_pages


def slice_pdf_pages(input_path: Path, page_numbers: list[int]) -> Path | None:
    """
    Create a temporary PDF containing only the requested 1-based page numbers.
    Returns the path to the temporary sliced PDF file, or None if slicing was skipped/failed.
    """
    if not page_numbers:
        return None

    try:
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            from PyPDF2 import PdfReader, PdfWriter
    except ImportError:
        logger.warning("pypdf/PyPDF2 not installed; cannot slice pages.")
        return None

    try:
        reader = PdfReader(str(input_path))
        total_pages = len(reader.pages)
        valid_pages = [p for p in page_numbers if 1 <= p <= total_pages]
        if not valid_pages:
            logger.warning("Requested pages %s out of bounds (total pages: %d)", page_numbers, total_pages)
            return None

        writer = PdfWriter()
        for p in valid_pages:
            writer.add_page(reader.pages[p - 1])

        temp_f = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        temp_path = Path(temp_f.name)
        temp_f.close()

        with open(temp_path, "wb") as f:
            writer.write(f)

        logger.info("Sliced PDF '%s' to %d pages (%s) → '%s'",
                    input_path.name, len(valid_pages), valid_pages, temp_path.name)
        return temp_path
    except Exception as exc:
        logger.error("Failed slicing PDF '%s': %s", input_path.name, exc)
        return None


def _print_docx(file_path: Path, printer_name: str, page_range: str = "") -> None:
    """
    Convert DOCX → PDF via LibreOffice (if available), then print the PDF.
    Falls back to Shell-print if LibreOffice is not installed.
    """
    soffice = shutil.which("soffice") or shutil.which("soffice.exe")
    if soffice:
        with tempfile.TemporaryDirectory() as tmp:
            logger.debug("Converting DOCX → PDF via LibreOffice")
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", tmp, str(file_path)],
                check=True,
                capture_output=True,
            )
            pdf_path = Path(tmp) / (file_path.stem + ".pdf")
            if pdf_path.exists():
                sliced_path = None
                target_pdf = pdf_path
                if page_range:
                    page_nums = parse_page_range(page_range)
                    if page_nums:
                        sliced_path = slice_pdf_pages(pdf_path, page_nums)
                        if sliced_path:
                            target_pdf = sliced_path
                try:
                    _print_via_shell(target_pdf, printer_name)
                finally:
                    if sliced_path and sliced_path.exists():
                        try:
                            import time
                            time.sleep(2)
                            sliced_path.unlink(missing_ok=True)
                        except Exception:
                            pass
                return
    # fallback
    logger.warning("LibreOffice not found – falling back to Shell print for DOCX")
    _print_via_shell(file_path, printer_name)


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────

def print_file(
    file_path: Path,
    printer_name: str = "",
    copies: int = COPIES,
    page_range: str = "",
) -> None:
    """
    Print *file_path* to *printer_name* (defaults to system default).

    Supported extensions: .pdf, .docx, .doc, .txt
    Supports page_range filtering for PDFs (e.g. '1-3, 5').
    Raises FileNotFoundError or RuntimeError on failure.
    """
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    printer = printer_name or get_default_printer()
    ext = file_path.suffix.lower()

    logger.info("🖨  Printing '%s' (%s) → '%s' [copies=%d, page_range='%s']",
                file_path.name, ext, printer, copies, page_range or "all")

    target_to_print = file_path
    sliced_temp_path = None

    if page_range and ext == ".pdf":
        page_nums = parse_page_range(page_range)
        if page_nums:
            sliced_temp_path = slice_pdf_pages(file_path, page_nums)
            if sliced_temp_path and sliced_temp_path.exists():
                target_to_print = sliced_temp_path

    try:
        for copy_num in range(copies):
            if copies > 1:
                logger.debug("  Copy %d/%d", copy_num + 1, copies)

            if ext == ".txt":
                _print_txt_raw(target_to_print, printer)
            elif ext in (".docx", ".doc"):
                _print_docx(target_to_print, printer, page_range=page_range)
            else:
                # .pdf and anything else with a registered shell handler
                _print_via_shell(target_to_print, printer)
    finally:
        if sliced_temp_path and sliced_temp_path.exists():
            try:
                import time
                time.sleep(2)
                sliced_temp_path.unlink(missing_ok=True)
            except Exception:
                pass

    logger.info("✅  Print job submitted for '%s'", file_path.name)
