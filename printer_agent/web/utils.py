"""
printer_agent/web/utils.py
--------------------------
Networking and QR code generation helpers.
"""

import io
import socket
from pathlib import Path
import qrcode
from PIL import Image

from printer_agent.config import WEB_PORT


def get_local_ip() -> str:
    """Return the LAN IP address of this machine to allow phone connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_upload_url(host: str | None = None, port: int = WEB_PORT, shop_id: str = "counter-1") -> str:
    """Return full URL that customers scan to upload files."""
    ip = host or get_local_ip()
    return f"http://{ip}:{port}/upload?shop={shop_id}"


def generate_qr_png_bytes(url: str) -> bytes:
    """Generate a high-quality QR code image with high error correction."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="#FFFFFF")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def detect_document_page_count(file_path: Path) -> int:
    """Detect the number of pages in a document (PDF, DOCX, images, TXT)."""
    file_path = Path(file_path)
    if not file_path.exists():
        return 1

    ext = file_path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            return max(1, len(reader.pages))
        except Exception:
            try:
                from PyPDF2 import PdfReader
                reader = PdfReader(str(file_path))
                return max(1, len(reader.pages))
            except Exception:
                try:
                    import re
                    content = file_path.read_bytes()
                    m = re.search(rb"/Type\s*/Pages.*?/Count\s+(\d+)", content)
                    if m:
                        return max(1, int(m.group(1)))
                    pages = re.findall(rb"/Type\s*/Page\b", content)
                    if pages:
                        return max(1, len(pages))
                except Exception:
                    pass
        return 1

    if ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"):
        return 1

    if ext in (".docx", ".doc"):
        try:
            import docx
            doc = docx.Document(str(file_path))
            total_words = sum(len(p.text.split()) for p in doc.paragraphs)
            return max(1, (total_words + 349) // 350)
        except Exception:
            return 1

    if ext in (".txt", ".log", ".csv", ".json"):
        try:
            lines = len(file_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            return max(1, (lines + 49) // 50)
        except Exception:
            return 1

    return 1


def generate_upi_uri(
    vpa: str,
    merchant_name: str,
    amount: float,
    order_id: str = "",
    note: str = "",
) -> str:
    """
    Generate standard NPCI-compliant UPI payment intent URI.
    Supported by PhonePe, Google Pay, Paytm, BHIM, Cred, and all UPI apps.
    """
    import urllib.parse
    clean_vpa = (vpa or "malikprint@upi").strip()
    clean_name = (merchant_name or "Printer Agent").strip()
    clean_note = note.strip() or (f"Print Order {order_id}" if order_id else "Printer Agent Service")
    
    params = {
        "pa": clean_vpa,
        "pn": clean_name,
        "am": f"{max(0.0, float(amount)):.2f}",
        "cu": "INR",
        "tn": clean_note,
    }
    if order_id:
        params["tr"] = order_id
    return f"upi://pay?{urllib.parse.urlencode(params)}"


def generate_upi_qr_bytes(
    vpa: str,
    merchant_name: str,
    amount: float,
    order_id: str = "",
    note: str = "",
) -> bytes:
    """Generate high-contrast QR PNG for UPI payment with exact amount."""
    upi_uri = generate_upi_uri(vpa, merchant_name, amount, order_id, note)
    return generate_qr_png_bytes(upi_uri)
