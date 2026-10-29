"""
printer_agent/shop_client.py
----------------------------
Lightweight Local PC Agent for Shop Owners.
Runs on the shop's local Windows computer that is physically connected
to the printer via USB or local Wi-Fi.

Responsibilities:
1. Detects all local Windows printers installed on this PC.
2. Sends heartbeats to the central server so the dashboard shows
   🟢 Printer Online & Ready.
3. Listens for incoming print jobs for this shop, fetches the files,
   and prints directly to the physical printer.
4. Provides 1-click test printing to verify paper & ink output.
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
except ImportError:
    import urllib.request as _url_request
    import urllib.parse as _url_parse
    import json as _json

    class SimpleRequests:
        @staticmethod
        def get(url, params=None, headers=None, timeout=10):
            if params:
                query = _url_parse.urlencode(params)
                url = f"{url}?{query}"
            req = _url_request.Request(url, headers=headers or {})
            with _url_request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return SimpleResponse(resp.getcode(), data)

        @staticmethod
        def post(url, data=None, json=None, headers=None, timeout=10):
            headers = headers or {}
            body = None
            if json is not None:
                body = _json.dumps(json).encode("utf-8")
                headers["Content-Type"] = "application/json"
            elif data is not None:
                body = _url_parse.urlencode(data).encode("utf-8")
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            req = _url_request.Request(url, data=body, headers=headers, method="POST")
            with _url_request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                return SimpleResponse(resp.getcode(), data)

    class SimpleResponse:
        def __init__(self, status_code, content):
            self.status_code = status_code
            self.content = content

        @property
        def ok(self):
            return 200 <= self.status_code < 300

        def json(self):
            import json
            return json.loads(self.content.decode("utf-8"))

        @property
        def text(self):
            return self.content.decode("utf-8", errors="replace")

    requests = SimpleRequests()

from printer_agent.logger import get_logger
from printer_agent.print_engine import get_default_printer, list_printers, print_file

logger = get_logger("shop_client")


def create_test_page_file(shop_name: str, printer_name: str) -> Path:
    """Generate a clean formatted test page to verify hardware connection."""
    tmp = Path(tempfile.gettempdir()) / f"test_page_{int(time.time())}.txt"
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    content = (
        "====================================================================\n"
        "             PRINTER AGENT - HARDWARE TEST PAGE                     \n"
        "====================================================================\n\n"
        f"  SHOP NAME      : {shop_name}\n"
        f"  PRINTER MODEL  : {printer_name}\n"
        f"  TEST DATE/TIME : {timestamp}\n"
        "  STATUS         : CONNECTION ACTIVE & PRINTING VERIFIED OK\n\n"
        "--------------------------------------------------------------------\n"
        "  Congratulations! Your physical printer is properly connected and   \n"
        "  ready to receive customer print orders via QR code scan.           \n"
        "--------------------------------------------------------------------\n\n"
        "  Steps for Daily Operation:\n"
        "  1. Keep this shop agent window running in the background.\n"
        "  2. Place the laminated Counter QR Flyer on your desk.\n"
        "  3. When customers scan and upload, documents will print directly!  \n\n"
        "====================================================================\n"
        "               POWERED BY PRINTER AGENT SYSTEM                     \n"
        "====================================================================\n"
    )
    tmp.write_text(content, encoding="utf-8")
    return tmp


class ShopPrinterClient:
    def __init__(
        self,
        server_url: str,
        shop_id: str,
        api_key: str,
        printer_name: str = "",
        auto_print: bool = True,
        poll_interval: float = 3.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.shop_id = shop_id
        self.api_key = api_key
        self.printer_name = printer_name or get_default_printer()
        self.auto_print = auto_print
        self.poll_interval = poll_interval
        self._last_heartbeat = 0.0

    def print_test_page(self) -> bool:
        """Send immediate test page to physical printer."""
        chosen = self.printer_name or get_default_printer()
        print(f"\n📄 Generating test page for printer '{chosen}'...")
        test_file = create_test_page_file(self.shop_id, chosen)
        try:
            print_file(test_file, printer_name=chosen, copies=1)
            print("✅ Test print sent successfully! Check paper in your printer.\n")
            return True
        except Exception as exc:
            print(f"❌ Test print failed: {exc}\n")
            return False
        finally:
            try:
                test_file.unlink()
            except Exception:
                pass

    def send_heartbeat(self) -> bool:
        """Send status update to portal so dashboard shows 🟢 Online."""
        url = f"{self.server_url}/api/agent/heartbeat"
        try:
            printers = [p["name"] for p in list_printers()]
        except Exception:
            printers = [self.printer_name]

        payload = {
            "shop_id": self.shop_id,
            "api_key": self.api_key,
            "printer_name": self.printer_name,
            "status": "online",
            "printers": printers,
        }
        try:
            res = requests.post(url, json=payload, timeout=5)
            if res.ok:
                self._last_heartbeat = time.time()
                return True
        except Exception as exc:
            logger.debug("Heartbeat failed: %s", exc)
        return False

    def fetch_and_process_jobs(self):
        """Poll server for pending orders for this shop."""
        url = f"{self.server_url}/api/agent/pending-jobs"
        params = {"shop_id": self.shop_id, "api_key": self.api_key}
        try:
            res = requests.get(url, params=params, timeout=8)
            if not res.ok:
                return
            data = res.json()
            orders = data.get("orders", [])
            for order in orders:
                self._process_single_order(order)
        except Exception as exc:
            logger.debug("Error checking jobs: %s", exc)

    def _process_single_order(self, order: dict):
        order_id = order["order_id"]
        filename = order.get("filename", "document")
        copies = int(order.get("copies", 1))

        print(f"\n🔔 NEW PRINT ORDER RECEIVED: {order_id} ({filename}, {copies} copies)")

        # Download file
        download_url = f"{self.server_url}/api/agent/download-file/{order_id}?shop_id={self.shop_id}&api_key={self.api_key}"
        ext = Path(filename).suffix or ".txt"
        temp_dest = Path(tempfile.gettempdir()) / f"print_{order_id}{ext}"

        try:
            print(f"   Downloading '{filename}'...")
            res = requests.get(download_url, timeout=30)
            if not res.ok:
                raise RuntimeError(f"Download failed with status {res.status_code}")

            temp_dest.write_bytes(res.content)
            print(f"   🖨️ Printing to '{self.printer_name}'...")

            print_file(temp_dest, printer_name=self.printer_name, copies=copies)
            print("   ✅ Print completed successfully!")

            # Notify server completed
            self._report_status(order_id, "completed")
        except Exception as exc:
            err = str(exc)
            print(f"   ❌ Print failed: {err}")
            self._report_status(order_id, "failed", error_msg=err)
        finally:
            try:
                temp_dest.unlink()
            except Exception:
                pass

    def _report_status(self, order_id: str, status: str, error_msg: str = ""):
        url = f"{self.server_url}/api/agent/job-status"
        payload = {
            "order_id": order_id,
            "shop_id": self.shop_id,
            "api_key": self.api_key,
            "status": status,
            "printer_used": self.printer_name,
            "error_msg": error_msg,
        }
        try:
            requests.post(url, json=payload, timeout=5)
        except Exception as e:
            logger.debug("Report status failed: %s", e)

    def run(self):
        """Main client loop."""
        print("=" * 65)
        print("   🖨️  PRINTER AGENT - LOCAL SHOP CONNECTOR")
        print("=" * 65)
        print(f"   Shop ID       : {self.shop_id}")
        print(f"   Server Portal : {self.server_url}")
        print(f"   Active Printer: {self.printer_name or '(System Default)'}")
        print(f"   Auto-Print    : {'ENABLED (Instant Print)' if self.auto_print else 'DISABLED'}")
        print("=" * 65)

        # Show detected printers
        try:
            ps = list_printers()
            if ps:
                print("\n   Detected Installed Printers on this PC:")
                for idx, p in enumerate(ps, 1):
                    prefix = " ⭐ " if p["name"] == self.printer_name else "    "
                    print(f"   {prefix}{idx}. {p['name']} ({p.get('driver', 'Driver')})")
        except Exception:
            pass

        print("\n🚀 Connecting to central server...")
        if self.send_heartbeat():
            print("🟢 Connected! Server status updated: Printer Online & Ready.")
        else:
            print("⚠️ Initial heartbeat sent (waiting for server to respond).")

        print("👂 Listening for incoming customer print jobs... (Press Ctrl+C to stop)\n")

        try:
            while True:
                # 1. Heartbeat every 15 seconds
                if time.time() - self._last_heartbeat > 15:
                    self.send_heartbeat()

                # 2. Check for jobs
                if self.auto_print:
                    self.fetch_and_process_jobs()

                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            print("\n🛑 Shop agent stopped.")


def main():
    parser = argparse.ArgumentParser(description="Printer Agent Local Shop Connector")
    parser.add_argument("--server", default="http://localhost:8000", help="Portal Server URL")
    parser.add_argument("--shop", default="counter-1", help="Shop ID / Counter Slug")
    parser.add_argument("--key", default="", help="Shop Secret API Key")
    parser.add_argument("--printer", default="", help="Specific Printer Name")
    parser.add_argument("--auto-print", action="store_true", default=True, help="Auto print jobs")
    parser.add_argument("--test-print", action="store_true", help="Send test page and exit")
    args = parser.parse_args()

    client = ShopPrinterClient(
        server_url=args.server,
        shop_id=args.shop,
        api_key=args.key,
        printer_name=args.printer,
        auto_print=args.auto_print,
    )

    if args.test_print:
        success = client.print_test_page()
        sys.exit(0 if success else 1)

    client.run()


if __name__ == "__main__":
    main()
