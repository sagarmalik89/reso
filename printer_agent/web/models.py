"""
printer_agent/web/models.py
---------------------------
Data models and persistent SQLite store for customer print orders
with multi-shop / multi-counter support.
"""

import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from printer_agent.config import BASE_DIR


from printer_agent.config import (
    BASE_DIR,
    PRICE_PER_PAGE_BW,
    PRICE_PER_PAGE_COLOR,
    SHOP_SUBSCRIPTION_MONTH,
    UPI_DEFAULT_VPA,
    UPI_MERCHANT_NAME,
)


DB_PATH = BASE_DIR / "orders.db"


@dataclass
class PrintOrder:
    order_id: str
    customer_name: str
    phone: str
    filename: str
    file_path: str
    file_size_bytes: int
    file_ext: str
    copies: int
    color_mode: str  # "bw" or "color"
    notes: str
    status: str      # "pending", "printing", "completed", "failed"
    created_at: float
    shop_id: str = "counter-1"
    page_count: int = 1
    unit_price: float = 5.0
    total_amount: float = 5.0
    payment_status: str = "pending"  # "pending", "paid", "cash_at_counter"
    payment_method: str = "upi"      # "upi", "cash"
    payment_ref: str = ""
    paid_at: float | None = None
    printed_at: float | None = None
    printer_used: str = ""
    error_msg: str = ""
    page_range: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OrderStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    shop_id TEXT DEFAULT 'counter-1',
                    customer_name TEXT,
                    phone TEXT,
                    filename TEXT,
                    file_path TEXT,
                    file_size_bytes INTEGER,
                    file_ext TEXT,
                    copies INTEGER,
                    color_mode TEXT,
                    notes TEXT,
                    status TEXT,
                    created_at REAL,
                    page_count INTEGER DEFAULT 1,
                    unit_price REAL DEFAULT 5.0,
                    total_amount REAL DEFAULT 5.0,
                    payment_status TEXT DEFAULT 'pending',
                    payment_method TEXT DEFAULT 'upi',
                    payment_ref TEXT DEFAULT '',
                    paid_at REAL,
                    printed_at REAL,
                    printer_used TEXT,
                    error_msg TEXT,
                    page_range TEXT DEFAULT ''
                )
                """
            )
            # Automatic column migrations for existing databases
            migrations = [
                "ALTER TABLE orders ADD COLUMN shop_id TEXT DEFAULT 'counter-1'",
                "ALTER TABLE orders ADD COLUMN page_count INTEGER DEFAULT 1",
                "ALTER TABLE orders ADD COLUMN unit_price REAL DEFAULT 5.0",
                "ALTER TABLE orders ADD COLUMN total_amount REAL DEFAULT 5.0",
                "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'pending'",
                "ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'upi'",
                "ALTER TABLE orders ADD COLUMN payment_ref TEXT DEFAULT ''",
                "ALTER TABLE orders ADD COLUMN paid_at REAL",
                "ALTER TABLE orders ADD COLUMN page_range TEXT DEFAULT ''",
            ]
            for mig in migrations:
                try:
                    conn.execute(mig)
                except sqlite3.OperationalError:
                    pass
            conn.commit()

    def create_order(
        self,
        customer_name: str,
        phone: str,
        filename: str,
        file_path: Path,
        copies: int = 1,
        color_mode: str = "bw",
        notes: str = "",
        shop_id: str = "counter-1",
        page_count: int = 1,
        unit_price: float | None = None,
        payment_method: str = "upi",
        page_range: str = "",
    ) -> PrintOrder:
        order_id = "ORD-" + uuid.uuid4().hex[:8].upper()
        # Default pricing: ₹5 for B&W, ₹10 for Color per page
        if unit_price is None or unit_price <= 0:
            unit_price = PRICE_PER_PAGE_COLOR if color_mode == "color" else PRICE_PER_PAGE_BW
        
        pages = max(1, page_count)
        if page_range and page_range.strip():
            try:
                from printer_agent.print_engine import parse_page_range
                parsed = parse_page_range(page_range)
                if parsed:
                    pages = len(parsed)
            except Exception:
                pass

        num_copies = max(1, copies)
        total_amount = round(pages * num_copies * unit_price, 2)

        order = PrintOrder(
            order_id=order_id,
            shop_id=shop_id or "counter-1",
            customer_name=customer_name or "Counter Customer",
            phone=phone or "",
            filename=filename,
            file_path=str(file_path.resolve()),
            file_size_bytes=file_path.stat().st_size if file_path.exists() else 0,
            file_ext=file_path.suffix.lower(),
            copies=num_copies,
            color_mode=color_mode,
            notes=notes or "",
            status="pending",
            created_at=time.time(),
            page_count=pages,
            unit_price=unit_price,
            total_amount=total_amount,
            payment_status="pending",
            payment_method=payment_method,
            payment_ref="",
            paid_at=None,
            page_range=page_range.strip(),
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO orders (
                    order_id, shop_id, customer_name, phone, filename, file_path,
                    file_size_bytes, file_ext, copies, color_mode, notes,
                    status, created_at, page_count, unit_price, total_amount,
                    payment_status, payment_method, payment_ref, paid_at,
                    printed_at, printer_used, error_msg, page_range
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.order_id,
                    order.shop_id,
                    order.customer_name,
                    order.phone,
                    order.filename,
                    order.file_path,
                    order.file_size_bytes,
                    order.file_ext,
                    order.copies,
                    order.color_mode,
                    order.notes,
                    order.status,
                    order.created_at,
                    order.page_count,
                    order.unit_price,
                    order.total_amount,
                    order.payment_status,
                    order.payment_method,
                    order.payment_ref,
                    order.paid_at,
                    order.printed_at,
                    order.printer_used,
                    order.error_msg,
                    order.page_range,
                ),
            )
            conn.commit()

        return order

    def mark_order_paid(
        self,
        order_id: str,
        payment_ref: str = "",
        payment_method: str = "upi",
        amount: float | None = None,
    ) -> bool:
        """Mark order payment as received with live agreed amount."""
        with self._get_connection() as conn:
            if amount is not None and amount >= 0:
                cur = conn.execute(
                    """
                    UPDATE orders
                    SET payment_status = 'paid', payment_ref = ?, payment_method = ?, paid_at = ?, total_amount = ?
                    WHERE order_id = ?
                    """,
                    (payment_ref, payment_method, time.time(), round(amount, 2), order_id),
                )
            else:
                cur = conn.execute(
                    """
                    UPDATE orders
                    SET payment_status = 'paid', payment_ref = ?, payment_method = ?, paid_at = ?
                    WHERE order_id = ?
                    """,
                    (payment_ref, payment_method, time.time(), order_id),
                )
            conn.commit()
            return cur.rowcount > 0

    def list_orders(self, shop_id: str | None = None, limit: int = 100) -> list[PrintOrder]:
        with self._get_connection() as conn:
            if shop_id and shop_id != "all":
                rows = conn.execute(
                    "SELECT * FROM orders WHERE shop_id = ? ORDER BY created_at DESC LIMIT ?",
                    (shop_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [PrintOrder(**dict(r)) for r in rows]

    def get_order(self, order_id: str) -> PrintOrder | None:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
            if not row:
                return None
            return PrintOrder(**dict(row))

    def update_status(
        self,
        order_id: str,
        status: str,
        printer_used: str = "",
        error_msg: str = "",
    ) -> bool:
        printed_at = time.time() if status == "completed" else None
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE orders
                SET status = ?, printer_used = COALESCE(NULLIF(?, ''), printer_used),
                    error_msg = ?, printed_at = COALESCE(?, printed_at)
                WHERE order_id = ?
                """,
                (status, printer_used, error_msg, printed_at, order_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_order(self, order_id: str) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
            conn.commit()
            return cur.rowcount > 0

    def update_amount(self, order_id: str, total_amount: float) -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE orders SET total_amount = ? WHERE order_id = ?",
                (round(total_amount, 2), order_id),
            )
            conn.commit()
            return cur.rowcount > 0


order_store = OrderStore()


# ──────────────────────────────────────────────────────────────────
# Multi-Shop / Shopkeeper SaaS Models & Store
# ──────────────────────────────────────────────────────────────────

import hashlib
import re
import secrets


def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def slugify_shop_name(name: str) -> str:
    """Generate a clean URL-friendly slug from shop name."""
    clean = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip().lower()
    slug = re.sub(r"[\s-]+", "-", clean)
    return slug[:24] if slug else "shop"


@dataclass
class Shop:
    shop_id: str
    shop_name: str
    owner_name: str
    email: str
    phone: str
    password_hash: str
    api_key: str
    city: str = ""
    status: str = "active"             # "active", "trial", "suspended"
    subscription_plan: str = "pro"     # "free_trial", "basic", "pro"
    printer_name: str = ""
    printer_status: str = "offline"    # "online", "offline"
    last_heartbeat: float = 0.0
    auto_print: int = 0                # 0 = manual click to print, 1 = instant zero-click print
    created_at: float = 0.0
    upi_vpa: str = UPI_DEFAULT_VPA
    upi_merchant_name: str = UPI_MERCHANT_NAME

    def is_online(self, max_idle_sec: float = 45.0) -> bool:
        """Consider printer online if heartbeat received within last 45 seconds."""
        if self.printer_status != "online":
            return False
        return (time.time() - self.last_heartbeat) <= max_idle_sec

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("password_hash", None)
        d["is_online"] = self.is_online()
        return d


class ShopStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shops (
                    shop_id TEXT PRIMARY KEY,
                    shop_name TEXT NOT NULL,
                    owner_name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    phone TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    api_key TEXT UNIQUE NOT NULL,
                    city TEXT DEFAULT '',
                    status TEXT DEFAULT 'active',
                    subscription_plan TEXT DEFAULT 'pro',
                    printer_name TEXT DEFAULT '',
                    printer_status TEXT DEFAULT 'offline',
                    last_heartbeat REAL DEFAULT 0,
                    auto_print INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    upi_vpa TEXT DEFAULT 'malikprint@upi',
                    upi_merchant_name TEXT DEFAULT 'Printer Agent'
                )
                """
            )
            # Automatic migrations for existing databases
            shop_migrations = [
                f"ALTER TABLE shops ADD COLUMN upi_vpa TEXT DEFAULT '{UPI_DEFAULT_VPA}'",
                f"ALTER TABLE shops ADD COLUMN upi_merchant_name TEXT DEFAULT '{UPI_MERCHANT_NAME}'",
            ]
            for mig in shop_migrations:
                try:
                    conn.execute(mig)
                except sqlite3.OperationalError:
                    pass
            conn.commit()

        # Seed default counter-1 shop if not exists
        if not self.get_shop("counter-1"):
            from printer_agent.config import ADMIN_EMAIL, ADMIN_PASSWORD
            self._insert_shop(
                Shop(
                    shop_id="counter-1",
                    shop_name="Counter 1 - Main Station",
                    owner_name="Primary Operator",
                    email=ADMIN_EMAIL,
                    phone="+91 98765 43210",
                    password_hash=hash_password(ADMIN_PASSWORD),
                    api_key="key-counter-1-" + secrets.token_hex(8),
                    city="Headquarters",
                    status="active",
                    subscription_plan="pro",
                    printer_name="",
                    printer_status="online",
                    last_heartbeat=time.time(),
                    auto_print=0,
                    created_at=time.time(),
                    upi_vpa=UPI_DEFAULT_VPA,
                    upi_merchant_name=UPI_MERCHANT_NAME,
                )
            )

    def _insert_shop(self, shop: Shop) -> Shop:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO shops (
                    shop_id, shop_name, owner_name, email, phone, password_hash,
                    api_key, city, status, subscription_plan, printer_name,
                    printer_status, last_heartbeat, auto_print, created_at,
                    upi_vpa, upi_merchant_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shop.shop_id,
                    shop.shop_name,
                    shop.owner_name,
                    shop.email,
                    shop.phone,
                    shop.password_hash,
                    shop.api_key,
                    shop.city,
                    shop.status,
                    shop.subscription_plan,
                    shop.printer_name,
                    shop.printer_status,
                    shop.last_heartbeat,
                    shop.auto_print,
                    shop.created_at,
                    shop.upi_vpa or UPI_DEFAULT_VPA,
                    shop.upi_merchant_name or UPI_MERCHANT_NAME,
                ),
            )
            conn.commit()
        return shop

    def update_shop_upi(self, shop_id: str, upi_vpa: str, upi_merchant_name: str) -> bool:
        """Update UPI payment details for a shop."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "UPDATE shops SET upi_vpa = ?, upi_merchant_name = ? WHERE shop_id = ?",
                (upi_vpa.strip(), upi_merchant_name.strip(), shop_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def register_shop(
        self,
        shop_name: str,
        owner_name: str,
        email: str,
        phone: str,
        password: str,
        city: str = "",
        custom_slug: str = "",
        upi_vpa: str = "",
        upi_merchant_name: str = "",
    ) -> Shop:
        """Register a new shop with unique slug and API key."""
        base_slug = slugify_shop_name(custom_slug) if custom_slug else slugify_shop_name(shop_name)
        shop_id = base_slug
        counter = 2
        while self.get_shop(shop_id):
            shop_id = f"{base_slug}-{counter}"
            counter += 1

        api_key = f"key-{shop_id}-{secrets.token_hex(12)}"
        shop = Shop(
            shop_id=shop_id,
            shop_name=shop_name.strip(),
            owner_name=owner_name.strip(),
            email=email.strip().lower(),
            phone=phone.strip(),
            password_hash=hash_password(password),
            api_key=api_key,
            city=city.strip(),
            status="active",
            subscription_plan="pro",
            printer_name="",
            printer_status="offline",
            last_heartbeat=0.0,
            auto_print=0,
            created_at=time.time(),
            upi_vpa=upi_vpa.strip() or UPI_DEFAULT_VPA,
            upi_merchant_name=upi_merchant_name.strip() or (shop_name.strip() or UPI_MERCHANT_NAME),
        )
        return self._insert_shop(shop)

    def authenticate(self, email: str, password: str) -> Shop | None:
        """Verify shopkeeper credentials."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM shops WHERE lower(email) = ?", (email.strip().lower(),)
            ).fetchone()
            if not row:
                return None
            shop = Shop(**dict(row))
            if shop.password_hash == hash_password(password):
                return shop
            return None

    def get_shop(self, shop_id: str) -> Shop | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM shops WHERE shop_id = ?", (shop_id,)).fetchone()
            if not row:
                return None
            return Shop(**dict(row))

    def get_shop_by_email(self, email: str) -> Shop | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM shops WHERE lower(email) = ?", (email.strip().lower(),)).fetchone()
            if not row:
                return None
            return Shop(**dict(row))

    def get_shop_by_api_key(self, api_key: str) -> Shop | None:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM shops WHERE api_key = ?", (api_key.strip(),)).fetchone()
            if not row:
                return None
            return Shop(**dict(row))

    def list_shops(self) -> list[Shop]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM shops ORDER BY created_at ASC").fetchall()
            return [Shop(**dict(r)) for r in rows]

    def update_heartbeat(self, shop_id: str, printer_name: str, status: str = "online") -> bool:
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE shops
                SET last_heartbeat = ?, printer_status = ?,
                    printer_name = COALESCE(NULLIF(?, ''), printer_name)
                WHERE shop_id = ?
                """,
                (time.time(), status, printer_name, shop_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def update_settings(
        self,
        shop_id: str,
        printer_name: str | None = None,
        auto_print: int | None = None,
        status: str | None = None,
        subscription_plan: str | None = None,
    ) -> bool:
        shop = self.get_shop(shop_id)
        if not shop:
            return False

        new_printer = shop.printer_name if printer_name is None else printer_name
        new_auto = shop.auto_print if auto_print is None else auto_print
        new_status = shop.status if status is None else status
        new_plan = shop.subscription_plan if subscription_plan is None else subscription_plan

        with self._get_connection() as conn:
            cur = conn.execute(
                """
                UPDATE shops
                SET printer_name = ?, auto_print = ?, status = ?, subscription_plan = ?
                WHERE shop_id = ?
                """,
                (new_printer, new_auto, new_status, new_plan, shop_id),
            )
            conn.commit()
            return cur.rowcount > 0


shop_store = ShopStore()

