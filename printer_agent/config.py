"""
printer_agent/config.py
-----------------------
Central configuration for the Printer Agent.
Edit the values here or override via environment variables.
"""

import os
from pathlib import Path

# ──────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
WATCH_FOLDER    = BASE_DIR / "watch_folder"      # Drop files here to auto-print
PROCESSED_FOLDER= BASE_DIR / "processed"         # Successfully printed files land here
FAILED_FOLDER   = BASE_DIR / "failed"            # Files that failed all retries
UPLOADS_DIR     = BASE_DIR / "uploads"           # Uploads received from customer QR scan
LOGS_DIR        = BASE_DIR / "logs"

# Auto-create folders
for _dir in (WATCH_FOLDER, PROCESSED_FOLDER, FAILED_FOLDER, UPLOADS_DIR, LOGS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# PRINTER SETTINGS
# ──────────────────────────────────────────────
DEFAULT_PRINTER = os.environ.get("PRINTER_NAME", "")   # "" = system default printer
COPIES          = int(os.environ.get("PRINTER_COPIES", 1))

# ──────────────────────────────────────────────
# QUEUE / RETRY SETTINGS
# ──────────────────────────────────────────────
MAX_RETRIES      = 3          # How many times to retry a failed job
RETRY_DELAY_SEC  = 30         # Seconds between retries
QUEUE_POLL_SEC   = 2          # How often the queue worker checks for new jobs (seconds)

# ──────────────────────────────────────────────
# SUPPORTED FILE TYPES
# ──────────────────────────────────────────────
SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".txt",
    ".png", ".jpg", ".jpeg", ".bmp", ".webp"
}

# ──────────────────────────────────────────────
# WEB & AUTHENTICATION SETTINGS
# ──────────────────────────────────────────────
WEB_HOST        = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT        = int(os.environ.get("WEB_PORT", 8000))
ADMIN_EMAIL     = os.environ.get("ADMIN_EMAIL", "admin@printagent.com")
ADMIN_PASSWORD  = os.environ.get("ADMIN_PASSWORD", "admin123")
SECRET_KEY      = os.environ.get("SECRET_KEY", "print-agent-secret-key-2026")

# ──────────────────────────────────────────────
# PRICING & PAYMENT SETTINGS (INR ₹)
# ──────────────────────────────────────────────
PRICE_PER_PAGE_BW       = float(os.environ.get("PRICE_PER_PAGE_BW", 5.0))        # ₹5 per page B&W
PRICE_PER_PAGE_COLOR    = float(os.environ.get("PRICE_PER_PAGE_COLOR", 10.0))    # ₹10 per page Color
SHOP_SUBSCRIPTION_MONTH = float(os.environ.get("SHOP_SUBSCRIPTION_MONTH", 50.0)) # ₹50 per month
UPI_DEFAULT_VPA         = os.environ.get("UPI_DEFAULT_VPA", "malikprint@upi")
UPI_MERCHANT_NAME       = os.environ.get("UPI_MERCHANT_NAME", "Printer Agent")

# ──────────────────────────────────────────────
# SCHEDULED JOBS  (add as many as you like)
# ──────────────────────────────────────────────
# Format: {"file": <path or glob>, "time": "HH:MM", "priority": 1-10}
SCHEDULED_JOBS = [
    # Example: print a daily report every morning
    # {"file": str(BASE_DIR / "reports" / "daily_report.pdf"), "time": "08:00", "priority": 5},
]

