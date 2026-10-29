"""
tests/test_web.py
-----------------
Unit tests for the Web Application:
- Customer QR code upload
- Operator authentication & session
- Order management & SQLite persistence
- Printing API trigger
"""

import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starlette.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from printer_agent.config import ADMIN_EMAIL, ADMIN_PASSWORD
from printer_agent.web.app import app, create_session_token
from printer_agent.web.models import order_store, shop_store


class TestWebApp(unittest.TestCase):
    _TEST_SHOP_IDS = ["delhi-cafe", "new-delhi-cyber-cafe"]

    def setUp(self):
        self.client = TestClient(app)
        self.valid_token = create_session_token(ADMIN_EMAIL)
        # Remove any leftover test shops from prior runs to keep tests idempotent
        self._cleanup_test_shops()

    def tearDown(self):
        self._cleanup_test_shops()

    def _cleanup_test_shops(self):
        """Delete test shops created by signup tests so tests can re-run cleanly."""
        import sqlite3
        from printer_agent.web.models import DB_PATH
        with sqlite3.connect(str(DB_PATH)) as conn:
            for sid in self._TEST_SHOP_IDS:
                conn.execute("DELETE FROM shops WHERE shop_id = ?", (sid,))
            conn.execute(
                "DELETE FROM shops WHERE email = ?",
                ("rohan@delhicafe.com",),
            )
            conn.commit()

    def test_login_flow(self):
        # 1. Accessing dashboard without auth redirects to /login
        res = self.client.get("/", follow_redirects=False)
        self.assertEqual(res.status_code, 303)
        self.assertEqual(res.headers.get("Location"), "/login")

        # 2. Invalid login returns 401
        res = self.client.post("/login", data={"email": "wrong@test.com", "password": "bad"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("Invalid email or password", res.text)

        # 3. Valid login sets session_token and redirects
        res = self.client.post(
            "/login",
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            follow_redirects=False,
        )
        self.assertEqual(res.status_code, 302)
        self.assertIn("session_token", res.headers.get("set-cookie", ""))

    def test_qr_code_endpoint(self):
        res = self.client.get("/api/qr.png?shop=counter-1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "image/png")
        self.assertTrue(len(res.content) > 100)

    def test_customer_upload_endpoint(self):
        file_content = b"Sample invoice content to print"
        files = {"file": ("invoice.txt", io.BytesIO(file_content), "text/plain")}
        data = {
            "customer_name": "Test Customer",
            "phone": "9999999999",
            "copies": "2",
            "color_mode": "bw",
            "notes": "Print asap",
        }

        res = self.client.post("/api/upload", data=data, files=files)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["order_id"].startswith("ORD-"))

        # Verify it exists in order_store
        order = order_store.get_order(body["order_id"])
        self.assertIsNotNone(order)
        self.assertEqual(order.customer_name, "Test Customer")
        self.assertEqual(order.copies, 2)
        self.assertEqual(order.status, "pending")

    def test_authenticated_dashboard(self):
        self.client.cookies.set("session_token", self.valid_token)
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Printer Agent", res.text)
        self.assertIn("Customer Print Orders", res.text)

    @patch("printer_agent.web.app.print_file")
    def test_operator_print_order(self, mock_print):
        # Create an order
        file_content = b"Document to print"
        files = {"file": ("doc.txt", io.BytesIO(file_content), "text/plain")}
        res = self.client.post("/api/upload", data={"customer_name": "Aman"}, files=files)
        order_id = res.json()["order_id"]

        # Trigger print as operator
        self.client.cookies.set("session_token", self.valid_token)
        print_res = self.client.post(f"/api/orders/{order_id}/print", data={"printer_name": "TestPrinter"})
        self.assertEqual(print_res.status_code, 200)
        self.assertEqual(print_res.json()["status"], "completed")

        mock_print.assert_called_once()

        # Check DB status updated to completed
        order = order_store.get_order(order_id)
        self.assertEqual(order.status, "completed")

    @patch("printer_agent.web.app.print_file")
    def test_operator_print_with_page_range(self, mock_print):
        from printer_agent.print_engine import parse_page_range
        self.assertEqual(parse_page_range("1-3, 5, 8"), [1, 2, 3, 5, 8])
        self.assertEqual(parse_page_range(""), [])
        self.assertEqual(parse_page_range("4-2"), [2, 3, 4])

        files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")}
        res = self.client.post("/api/upload", data={"customer_name": "Priya", "page_range": "1-3, 5"}, files=files)
        order_id = res.json()["order_id"]

        order = order_store.get_order(order_id)
        self.assertEqual(order.page_range, "1-3, 5")

        self.client.cookies.set("session_token", self.valid_token)
        print_res = self.client.post(
            f"/api/orders/{order_id}/print",
            data={"printer_name": "TestLaser", "page_range": "1-2"}
        )
        self.assertEqual(print_res.status_code, 200)
        self.assertEqual(print_res.json()["page_range"], "1-2")
        mock_print.assert_called_once()
        _, kwargs = mock_print.call_args
        self.assertEqual(kwargs.get("page_range"), "1-2")

    def test_inspect_file_and_page_count_detection(self):
        # 1. Test inspection API with a simple text file
        files = {"file": ("notes.txt", io.BytesIO(b"Hello world!\nLine 2"), "text/plain")}
        res = self.client.post("/api/inspect-file", files=files, data={"color_mode": "bw", "copies": "2"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["page_count"], 1)
        self.assertEqual(data["copies"], 2)
        self.assertEqual(data["total_amount"], 10.0)

        # 2. Test inspection API with color mode
        files2 = {"file": ("photo.jpg", io.BytesIO(b"binaryimgdata"), "image/jpeg")}
        res2 = self.client.post("/api/inspect-file", files=files2, data={"color_mode": "color", "copies": "1"})
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["unit_price"], 10.0)
        self.assertEqual(res2.json()["total_amount"], 10.0)

    def test_delete_order(self):
        files = {"file": ("temp.txt", io.BytesIO(b"data"), "text/plain")}
        res = self.client.post("/api/upload", data={"customer_name": "Delete Me"}, files=files)
        order_id = res.json()["order_id"]

        self.client.cookies.set("session_token", self.valid_token)
        del_res = self.client.delete(f"/api/orders/{order_id}")
        self.assertEqual(del_res.status_code, 200)

        # Confirm deleted
        self.assertIsNone(order_store.get_order(order_id))

    def test_shop_signup_and_login_flow(self):
        # 1. Sign up a new shop
        data = {
            "shop_name": "New Delhi Cyber Cafe",
            "owner_name": "Rohan Kumar",
            "email": "rohan@delhicafe.com",
            "phone": "9811223344",
            "password": "secretpassword123",
            "confirm_password": "secretpassword123",
            "city": "New Delhi",
            "custom_slug": "delhi-cafe",
        }
        res = self.client.post("/signup", data=data, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/setup-guide?shop=delhi-cafe", res.headers.get("Location", ""))

        # 2. Login with newly registered shopkeeper credentials
        login_res = self.client.post(
            "/login",
            data={"email": "rohan@delhicafe.com", "password": "secretpassword123"},
            follow_redirects=False,
        )
        self.assertEqual(login_res.status_code, 302)
        self.assertIn("shop=delhi-cafe", login_res.headers.get("Location", ""))

    def test_setup_guide_and_download_launcher(self):
        self.client.cookies.set("session_token", self.valid_token)
        guide_res = self.client.get("/setup-guide?shop=counter-1")
        self.assertEqual(guide_res.status_code, 200)
        self.assertIn("Physical Printer Setup", guide_res.text)

        # Download launcher script
        launcher_res = self.client.get("/api/agent/download-launcher?shop=counter-1")
        self.assertEqual(launcher_res.status_code, 200)
        self.assertIn("PRINTER AGENT - LOCAL SHOP CONNECTOR", launcher_res.text)

    def test_agent_heartbeat(self):
        payload = {
            "shop_id": "counter-1",
            "printer_name": "HP LaserJet Test",
            "status": "online",
        }
        res = self.client.post("/api/agent/heartbeat", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_upi_qr_and_payment_flow(self):
        # 1. Create order
        files = {"file": ("test_doc.txt", io.BytesIO(b"Hello UPI"), "text/plain")}
        res = self.client.post("/api/upload", data={"customer_name": "UPI Test User", "copies": "2"}, files=files)
        self.assertEqual(res.status_code, 200)
        order_id = res.json()["order_id"]

        # 2. Test UPI QR image endpoint
        qr_res = self.client.get(f"/api/orders/{order_id}/upi-qr.png")
        self.assertEqual(qr_res.status_code, 200)
        self.assertEqual(qr_res.headers["content-type"], "image/png")
        self.assertTrue(len(qr_res.content) > 100)

        # 3. Test Payment info endpoint
        info_res = self.client.get(f"/api/orders/{order_id}/payment")
        self.assertEqual(info_res.status_code, 200)
        data = info_res.json()
        self.assertEqual(data["order_id"], order_id)
        self.assertIn("upi://pay", data["upi_uri"])
        self.assertTrue(data["total_amount"] > 0)

        # 4. Test Customer submit UTR
        utr_res = self.client.post(
            f"/api/orders/{order_id}/submit-utr",
            data={"utr": "UTR123456789"},
        )
        self.assertEqual(utr_res.status_code, 200)
        self.assertEqual(utr_res.json()["payment_status"], "paid")

        # 5. Verify order is paid
        order = order_store.get_order(order_id)
        self.assertEqual(order.payment_status, "paid")
        self.assertEqual(order.payment_ref, "UTR123456789")

    def test_update_shop_upi_settings(self):
        self.client.cookies.set("session_token", self.valid_token)
        res = self.client.post(
            "/api/shops/counter-1/upi",
            data={"upi_vpa": "testshop@upi", "upi_merchant_name": "Test Shop"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["upi_vpa"], "testshop@upi")

        # Verify shop store updated
        shop = shop_store.get_shop("counter-1")
        self.assertEqual(shop.upi_vpa, "testshop@upi")


if __name__ == "__main__":
    unittest.main(verbosity=2)
