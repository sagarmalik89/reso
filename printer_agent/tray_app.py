"""
printer_agent/tray_app.py
-------------------------
Windows System Tray Application for the Printer Agent Shop Connector.
Runs silently in the Windows Taskbar / Notification Area (system tray),
listening for customer print orders and printing automatically.

Features:
- Windows Notification Area tray icon with real-time status (🟢 Online / 🔴 Offline)
- Native Windows balloon/toast notifications on incoming jobs, completions, and errors
- 1-Click Hardware Test Print directly from tray menu
- 1-Click shortcut to open the web operator dashboard
- Reads settings from 'shop_config.json' (auto-created if missing)
- Graceful background worker thread management
"""

import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from printer_agent.logger import get_logger
from printer_agent.print_engine import get_default_printer, list_printers
from printer_agent.shop_client import ShopPrinterClient

logger = get_logger("tray_app")

CONFIG_FILE = BASE_DIR / "shop_config.json"

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8000",
    "shop_id": "counter-1",
    "api_key": "shop-secret-key-1",
    "printer_name": "",
    "auto_print": True,
    "poll_interval": 3.0,
    "desktop_notifications": True,
}


def load_config() -> dict:
    """Load configuration from shop_config.json or generate defaults."""
    if not CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info("Created default shop_config.json at %s", CONFIG_FILE)
        except Exception as exc:
            logger.warning("Could not create default config: %s", exc)
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # Merge missing defaults
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as exc:
        logger.error("Failed to parse shop_config.json: %s. Using defaults.", exc)
        return DEFAULT_CONFIG.copy()


def save_config(cfg: dict):
    """Save updated config dictionary to file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except Exception as exc:
        logger.error("Failed to save shop_config.json: %s", exc)


def create_tray_icon_image(online: bool = True):
    """
    Generate a dynamic 64x64 printer icon with an online/offline LED badge.
    Uses Pillow (PIL) to generate the icon without requiring external image files.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None

    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Top Paper Feed Sheet (White paper coming from top slot)
    paper_fill = (248, 250, 252, 255)
    paper_border = (148, 163, 184, 255)
    draw.rounded_rectangle([18, 4, 46, 26], radius=2, fill=paper_fill, outline=paper_border, width=2)
    # Faux text lines on top paper
    draw.line([22, 11, 42, 11], fill=(203, 213, 225, 255), width=2)
    draw.line([22, 16, 38, 16], fill=(203, 213, 225, 255), width=2)
    draw.line([22, 21, 34, 21], fill=(203, 213, 225, 255), width=2)

    # 2. Main Printer Body (Modern Dark Navy / Blue-Gray Chassis)
    body_fill = (30, 41, 59, 255)       # Slate 800
    body_border = (71, 85, 105, 255)    # Slate 600
    draw.rounded_rectangle([8, 20, 56, 54], radius=6, fill=body_fill, outline=body_border, width=2)

    # Top paper intake slit
    draw.rectangle([16, 21, 48, 24], fill=(15, 23, 42, 255))

    # 3. Output Paper Tray Slot
    draw.rectangle([14, 38, 50, 42], fill=(15, 23, 42, 255))

    # 4. Printed Output Sheet (peeking out from bottom slot)
    draw.rounded_rectangle([18, 40, 46, 60], radius=2, fill=paper_fill, outline=paper_border, width=2)
    draw.line([22, 46, 42, 46], fill=(100, 116, 139, 255), width=2)
    draw.line([22, 51, 36, 51], fill=(100, 116, 139, 255), width=2)

    # 5. Status LED Badge (Bottom-Right Corner)
    # Green (Connected & Ready) vs Amber/Red (Disconnected)
    if online:
        led_color = (16, 185, 129, 255)   # Emerald 500
        led_border = (255, 255, 255, 255)
    else:
        led_color = (239, 68, 68, 255)    # Red 500
        led_border = (255, 255, 255, 255)

    draw.ellipse([46, 46, 60, 60], fill=led_color, outline=led_border, width=2)

    return img


class PrinterAgentTrayApp:
    def __init__(self):
        self.config = load_config()
        self.client: ShopPrinterClient | None = None
        self.client_thread: threading.Thread | None = None
        self.tray_icon = None
        self.is_connected = False
        self.total_printed = 0

        self._init_client()

    def _init_client(self):
        """Instantiate ShopPrinterClient with notification callbacks."""
        self.client = ShopPrinterClient(
            server_url=self.config.get("server_url", "http://localhost:8000"),
            shop_id=self.config.get("shop_id", "counter-1"),
            api_key=self.config.get("api_key", ""),
            printer_name=self.config.get("printer_name", ""),
            auto_print=self.config.get("auto_print", True),
            poll_interval=float(self.config.get("poll_interval", 3.0)),
            on_order_received=self._on_order_received,
            on_order_completed=self._on_order_completed,
            on_order_failed=self._on_order_failed,
            on_heartbeat=self._on_heartbeat,
        )

    # ─────────────────────────────────────────────────────────────
    # Notification Callbacks
    # ─────────────────────────────────────────────────────────────

    def _on_heartbeat(self, connected: bool):
        prev = self.is_connected
        self.is_connected = connected
        if prev != connected:
            self._update_tray_state()

    def _on_order_received(self, order: dict):
        order_id = order.get("order_id", "New Order")
        filename = order.get("filename", "Document")
        copies = order.get("copies", 1)
        self._notify(
            title=f"🔔 Print Job Received: {order_id}",
            message=f"Document: {filename}\nCopies: {copies}\nPrinting to {self.client.printer_name}...",
        )

    def _on_order_completed(self, order: dict):
        self.total_printed += 1
        order_id = order.get("order_id", "Order")
        filename = order.get("filename", "Document")
        self._notify(
            title="✅ Print Finished",
            message=f"{filename} ({order_id}) was printed successfully.",
        )
        self._update_tray_state()

    def _on_order_failed(self, order: dict, err: str):
        order_id = order.get("order_id", "Order")
        self._notify(
            title="❌ Print Failed",
            message=f"Order {order_id} failed: {err}",
        )

    def _notify(self, title: str, message: str):
        """Deliver native Windows Desktop Notification via pystray."""
        if not self.config.get("desktop_notifications", True):
            return
        if self.tray_icon and hasattr(self.tray_icon, "notify"):
            try:
                self.tray_icon.notify(message, title)
            except Exception as exc:
                logger.debug("Failed to send tray notification: %s", exc)

    def _update_tray_state(self):
        """Update the icon image and tooltip with current state."""
        if not self.tray_icon:
            return

        status_text = "🟢 Online & Ready" if self.is_connected else "🔴 Offline / Connecting..."
        printer_str = self.client.printer_name or get_default_printer() or "Default Printer"
        self.tray_icon.title = (
            f"Printer Agent: {self.config.get('shop_id', 'counter-1')}\n"
            f"Status: {status_text}\n"
            f"Printer: {printer_str}\n"
            f"Printed Today: {self.total_printed}"
        )

        new_img = create_tray_icon_image(online=self.is_connected)
        if new_img:
            self.tray_icon.icon = new_img

    # ─────────────────────────────────────────────────────────────
    # Menu Actions
    # ─────────────────────────────────────────────────────────────

    def action_print_test_page(self, icon=None, item=None):
        """Trigger instant hardware test print."""
        threading.Thread(target=self._run_test_print, daemon=True).start()

    def _run_test_print(self):
        self._notify("📄 Test Print", "Sending hardware alignment test page to printer...")
        success = self.client.print_test_page()
        if success:
            self._notify("✅ Test Page Sent", "Check your printer tray for the test sheet.")
        else:
            self._notify("❌ Test Print Failed", "Check printer power, cable connection, and paper.")

    def action_open_portal(self, icon=None, item=None):
        """Open web operator dashboard in default browser."""
        url = self.config.get("server_url", "http://localhost:8000")
        webbrowser.open(url)

    def action_open_flyer(self, icon=None, item=None):
        """Open printable counter flyer QR page."""
        base = self.config.get("server_url", "http://localhost:8000").rstrip("/")
        shop = self.config.get("shop_id", "counter-1")
        webbrowser.open(f"{base}/qr?shop={shop}")

    def action_edit_config(self, icon=None, item=None):
        """Open shop_config.json in notepad or default text editor."""
        if sys.platform == "win32":
            os.system(f'notepad.exe "{CONFIG_FILE}"')
        else:
            webbrowser.open(str(CONFIG_FILE))

    def action_reconnect(self, icon=None, item=None):
        """Reload configuration and reconnect."""
        self._notify("🔄 Reconnecting", "Reloading configuration and reconnecting to portal...")
        self.config = load_config()
        if self.client:
            self.client.stop()
        self._init_client()
        self._start_worker_thread()

    def action_exit(self, icon=None, item=None):
        """Clean shutdown of background client and tray icon."""
        logger.info("Exiting Printer Agent System Tray...")
        if self.client:
            self.client.stop()
        if self.tray_icon:
            self.tray_icon.stop()

    # ─────────────────────────────────────────────────────────────
    # Tray Menu Setup
    # ─────────────────────────────────────────────────────────────

    def _build_menu(self):
        try:
            import pystray
        except ImportError:
            return None

        def format_shop_label(item):
            return f"🏪 Shop: {self.config.get('shop_id', 'counter-1')}"

        def format_status_label(item):
            return "🟢 Status: Connected & Ready" if self.is_connected else "🔴 Status: Connecting..."

        def format_printer_label(item):
            pr = self.client.printer_name or get_default_printer() or "System Default"
            return f"🖨️ Printer: {pr}"

        def format_count_label(item):
            return f"📊 Jobs Processed: {self.total_printed}"

        return pystray.Menu(
            pystray.MenuItem(format_shop_label, lambda icon, item: None, enabled=False),
            pystray.MenuItem(format_status_label, lambda icon, item: None, enabled=False),
            pystray.MenuItem(format_printer_label, lambda icon, item: None, enabled=False),
            pystray.MenuItem(format_count_label, lambda icon, item: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("🖨️ Print Hardware Test Page", self.action_print_test_page),
            pystray.MenuItem("🌐 Open Web Dashboard", self.action_open_portal),
            pystray.MenuItem("📱 View Counter QR Flyer", self.action_open_flyer),
            pystray.MenuItem("⚙️ Edit Settings (shop_config.json)", self.action_edit_config),
            pystray.MenuItem("🔄 Reconnect / Reload Config", self.action_reconnect),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("❌ Exit Printer Agent", self.action_exit),
        )

    def _start_worker_thread(self):
        """Start ShopPrinterClient loop in background thread."""
        self.client_thread = threading.Thread(target=self.client.run, daemon=True)
        self.client_thread.start()

    def run(self):
        """Launch the system tray application."""
        try:
            import pystray
        except ImportError:
            logger.error(
                "pystray is not installed. Run: pip install pystray pillow\n"
                "Falling back to console mode..."
            )
            self.client.run()
            return

        icon_image = create_tray_icon_image(online=False)
        menu = self._build_menu()

        self.tray_icon = pystray.Icon(
            name="PrinterAgent",
            icon=icon_image,
            title=f"Printer Agent: {self.config.get('shop_id', 'counter-1')} (Starting...)",
            menu=menu,
        )

        # Start the background polling and printing client
        self._start_worker_thread()

        # Show initial launch toast
        def _initial_toast():
            time.sleep(1.5)
            self._notify(
                title="🖨️ Printer Agent Active",
                message=f"Listening for orders for '{self.config.get('shop_id', 'counter-1')}'. Icon is in your system tray.",
            )

        threading.Thread(target=_initial_toast, daemon=True).start()

        # Run tray main loop (blocks until exit)
        self.tray_icon.run()


def main():
    app = PrinterAgentTrayApp()
    app.run()


if __name__ == "__main__":
    main()
