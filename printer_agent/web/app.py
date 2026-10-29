"""
printer_agent/web/app.py
------------------------
FastAPI Web Application:
- Customer QR scanning & document upload portal
- Operator authenticated dashboard with real-time SSE alerts
- Direct Windows printing engine integration
"""

import asyncio
import json
import os
import shutil
import time
from pathlib import Path
from typing import AsyncGenerator

# pyrefly: ignore[missing-import]
from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
# pyrefly: ignore[missing-import]
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
# pyrefly: ignore[missing-import]
from fastapi.staticfiles import StaticFiles
# pyrefly: ignore[missing-import]
from fastapi.templating import Jinja2Templates

from printer_agent.config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    BASE_DIR,
    DEFAULT_PRINTER,
    SECRET_KEY,
    SUPPORTED_EXTENSIONS,
    UPLOADS_DIR,
    UPI_DEFAULT_VPA,
    UPI_MERCHANT_NAME,
    WEB_HOST,
    WEB_PORT,
)
from printer_agent.logger import get_logger
from printer_agent.print_engine import get_default_printer, list_printers, print_file
from printer_agent.queue_manager import queue_manager

from printer_agent.web.models import order_store, shop_store, Shop
from printer_agent.web.utils import (
    detect_document_page_count,
    generate_qr_png_bytes,
    generate_upi_qr_bytes,
    generate_upi_uri,
    get_local_ip,
    get_upload_url,
)

logger = get_logger("web_app")

app = FastAPI(title="Printer Agent Portal", version="1.0.0")

# Setup templates and static files
WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# In-memory SSE subscriber queues for real-time notifications
_subscribers: set[asyncio.Queue] = set()

# Session management
_ACTIVE_SESSIONS: set[str] = set()
_SESSION_DATA: dict[str, dict] = {}


def create_session_token(email: str, shop_id: str = "counter-1", is_admin: bool = False) -> str:
    import hashlib
    token = hashlib.sha256(f"{email}:{shop_id}:{SECRET_KEY}:{time.time()}".encode()).hexdigest()
    _ACTIVE_SESSIONS.add(token)
    _SESSION_DATA[token] = {
        "email": email,
        "shop_id": shop_id,
        "is_admin": is_admin,
        "created_at": time.time(),
    }
    return token


def get_session_user(token: str | None) -> dict:
    if not token or token not in _SESSION_DATA:
        return {"email": ADMIN_EMAIL, "shop_id": "counter-1", "is_admin": True}
    return _SESSION_DATA[token]


def is_authenticated(session_token: str | None = Cookie(None)) -> bool:
    if not session_token or session_token not in _ACTIVE_SESSIONS:
        return False
    return True


def require_auth(session_token: str | None = Cookie(None)) -> str:
    if not session_token or session_token not in _ACTIVE_SESSIONS:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )
    return session_token


async def broadcast_event(event_type: str, data: dict):
    """Broadcast real-time event to all connected operator dashboards."""
    payload = json.dumps({"event": event_type, "data": data, "timestamp": time.time()})
    dead_queues = []
    for q in _subscribers:
        try:
            await q.put(payload)
        except Exception:
            dead_queues.append(q)
    for q in dead_queues:
        _subscribers.discard(q)


# ──────────────────────────────────────────────
# Authentication & Shop Sign-Up Routes
# ──────────────────────────────────────────────

@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, session_token: str | None = Cookie(None)):
    if session_token and session_token in _ACTIVE_SESSIONS:
        user = get_session_user(session_token)
        return RedirectResponse(url=f"/?shop={user.get('shop_id', 'counter-1')}", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="signup.html", context={"error": None})


@app.post("/signup")
async def signup_submit(
    request: Request,
    shop_name: str = Form(...),
    owner_name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    city: str = Form(""),
    custom_slug: str = Form(""),
):
    if len(password) < 6:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"error": "Password must be at least 6 characters long."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if password != confirm_password:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"error": "Passwords do not match. Please verify."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing = shop_store.get_shop_by_email(email)
    if existing:
        return templates.TemplateResponse(
            request=request,
            name="signup.html",
            context={"error": f"An account with email '{email}' already exists. Please sign in."},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Register new shop in database
    shop = shop_store.register_shop(
        shop_name=shop_name,
        owner_name=owner_name,
        email=email,
        phone=phone,
        password=password,
        city=city,
        custom_slug=custom_slug,
    )

    token = create_session_token(shop.email, shop_id=shop.shop_id, is_admin=False)
    response = RedirectResponse(
        url=f"/setup-guide?shop={shop.shop_id}&welcome=1",
        status_code=status.HTTP_302_FOUND,
    )
    response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400 * 7)
    return response


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, session_token: str | None = Cookie(None)):
    if session_token and session_token in _ACTIVE_SESSIONS:
        user = get_session_user(session_token)
        return RedirectResponse(url=f"/?shop={user.get('shop_id', 'counter-1')}", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request=request, name="login.html", context={"error": None})


@app.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    # 1. Master Admin Login
    if email.strip().lower() == ADMIN_EMAIL.strip().lower() and password == ADMIN_PASSWORD:
        token = create_session_token(email, shop_id="counter-1", is_admin=True)
        response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400 * 7)
        return response

    # 2. Shopkeeper Authenticate
    shop = shop_store.authenticate(email, password)
    if shop:
        token = create_session_token(shop.email, shop_id=shop.shop_id, is_admin=False)
        response = RedirectResponse(url=f"/?shop={shop.shop_id}", status_code=status.HTTP_302_FOUND)
        response.set_cookie(key="session_token", value=token, httponly=True, max_age=86400 * 7)
        return response

    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": "Invalid email or password. Please try again or register your shop."},
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@app.get("/logout")
async def logout(session_token: str | None = Cookie(None)):
    if session_token in _ACTIVE_SESSIONS:
        _ACTIVE_SESSIONS.discard(session_token)
        _SESSION_DATA.pop(session_token, None)
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("session_token")
    return response


# ──────────────────────────────────────────────
# Setup & Printer Hardware Installation Guide
# ──────────────────────────────────────────────

@app.get("/setup-guide", response_class=HTMLResponse)
async def setup_guide_page(
    request: Request,
    token: str = Depends(require_auth),
    shop: str | None = None,
):
    user = get_session_user(token)
    active_shop_id = shop or user.get("shop_id") or "counter-1"
    shop_obj = shop_store.get_shop(active_shop_id)
    if not shop_obj:
        shop_obj = shop_store.get_shop("counter-1")

    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:{WEB_PORT}"

    return templates.TemplateResponse(
        request=request,
        name="setup_guide.html",
        context={
            "shop": shop_obj,
            "server_url": server_url,
            "local_ip": local_ip,
            "port": WEB_PORT,
        },
    )


# ──────────────────────────────────────────────
# Master Admin All Shops Overview
# ──────────────────────────────────────────────

@app.get("/admin/shops", response_class=HTMLResponse)
async def admin_all_shops_page(
    request: Request,
    token: str = Depends(require_auth),
):
    user = get_session_user(token)
    if not user.get("is_admin"):
        return RedirectResponse(url=f"/?shop={user.get('shop_id', 'counter-1')}", status_code=status.HTTP_302_FOUND)

    shops = shop_store.list_shops()
    all_orders = order_store.list_orders(limit=1000)
    online_count = sum(1 for s in shops if s.is_online())

    return templates.TemplateResponse(
        request=request,
        name="shops_admin.html",
        context={
            "shops": shops,
            "online_count": online_count,
            "total_orders": len(all_orders),
        },
    )


# ──────────────────────────────────────────────
# Operator Dashboard Routes (Protected)
# ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard_page(
    request: Request,
    token: str = Depends(require_auth),
    shop: str | None = None,
):
    user = get_session_user(token)
    active_shop_id = shop or user.get("shop_id") or "counter-1"
    shop_obj = shop_store.get_shop(active_shop_id)
    shop_name = shop_obj.shop_name if shop_obj else active_shop_id

    orders = order_store.list_orders(shop_id=active_shop_id, limit=100)
    try:
        printers = list_printers()
    except Exception:
        printers = []

    try:
        current_default = (shop_obj.printer_name if shop_obj and shop_obj.printer_name else None) or get_default_printer()
    except Exception:
        current_default = "Default Printer"

    local_ip = get_local_ip()
    upload_url = get_upload_url(local_ip, WEB_PORT, active_shop_id)
    all_shops = shop_store.list_shops()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "orders": orders,
            "printers": printers,
            "default_printer": current_default,
            "local_ip": local_ip,
            "port": WEB_PORT,
            "upload_url": upload_url,
            "admin_email": user.get("email", ADMIN_EMAIL),
            "shop_id": active_shop_id,
            "shop_name": shop_name,
            "is_admin": user.get("is_admin", False),
            "total_shops": len(all_shops),
        },
    )


@app.get("/qr", response_class=HTMLResponse)
async def qr_page(request: Request, shop: str = "counter-1"):
    """Public printable flyer with QR code for the counter."""
    local_ip = get_local_ip()
    upload_url = get_upload_url(local_ip, WEB_PORT, shop)
    return templates.TemplateResponse(
        request=request,
        name="qr.html",
        context={
            "upload_url": upload_url,
            "shop_id": shop,
            "local_ip": local_ip,
            "port": WEB_PORT,
        },
    )


@app.get("/api/qr.png")
async def get_qr_image(shop: str = "counter-1"):
    """Returns dynamic QR code PNG."""
    local_ip = get_local_ip()
    url = get_upload_url(local_ip, WEB_PORT, shop)
    qr_bytes = generate_qr_png_bytes(url)
    return Response(content=qr_bytes, media_type="image/png")


# ──────────────────────────────────────────────
# Shop Agent Connector & Hardware Control APIs
# ──────────────────────────────────────────────

@app.get("/api/agent/download-launcher")
async def download_agent_launcher(shop: str = "counter-1"):
    """Generate and return a pre-configured 1-click .bat launcher for the shop."""
    shop_obj = shop_store.get_shop(shop)
    if not shop_obj:
        raise HTTPException(status_code=404, detail="Shop not found.")

    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:{WEB_PORT}"

    bat_content = f"""@echo off
TITLE Printer Agent - {shop_obj.shop_name}
COLOR 0A
cd /d "%~dp0"

echo ================================================================
echo      PRINTER AGENT - LOCAL SHOP CONNECTOR
echo      Shop: {shop_obj.shop_name} ({shop_obj.shop_id})
echo ================================================================
echo.

:: Detect Python
set "PYTHON_EXE="
if exist "C:\\Python314\\python.exe" set "PYTHON_EXE=C:\\Python314\\python.exe"
if not defined PYTHON_EXE (
    python --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    py -3 --version >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_EXE=py -3"
)
if not defined PYTHON_EXE (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please install Python from https://www.python.org/
    pause
    exit /b 1
)

echo [1/2] Connecting to Portal at {server_url}...
echo [2/2] Starting Printer Agent for Shop {shop_obj.shop_id}...
echo.
%PYTHON_EXE% -m printer_agent.shop_client --server "{server_url}" --shop "{shop_obj.shop_id}" --key "{shop_obj.api_key}"

pause
"""
    return Response(
        content=bat_content.encode("utf-8"),
        media_type="application/x-bat",
        headers={"Content-Disposition": f'attachment; filename="start_{shop_obj.shop_id}_agent.bat"'},
    )


@app.post("/api/agent/heartbeat")
async def agent_heartbeat_api(request: Request):
    """Receive periodic heartbeat from local PC shop agent."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    shop_id = data.get("shop_id", "counter-1")
    printer_name = data.get("printer_name", "")
    status_str = data.get("status", "online")
    shop_store.update_heartbeat(shop_id, printer_name, status_str)
    return {"success": True, "shop_id": shop_id, "status": "online"}


@app.post("/api/agent/test-print")
async def agent_test_print_api(shop: str = "counter-1"):
    """Trigger physical hardware test page."""
    shop_obj = shop_store.get_shop(shop)
    shop_name = shop_obj.shop_name if shop_obj else shop
    chosen_printer = (shop_obj.printer_name if shop_obj else "") or get_default_printer()

    from printer_agent.shop_client import create_test_page_file
    test_file = create_test_page_file(shop_name, chosen_printer)
    try:
        print_file(test_file, printer_name=chosen_printer, copies=1)
        return {
            "success": True,
            "message": f"Test print dispatched to '{chosen_printer}'. Check your printer tray!",
            "shop_id": shop,
            "printer": chosen_printer,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Physical print failed: {exc}")
    finally:
        try:
            test_file.unlink()
        except Exception:
            pass


@app.get("/api/agent/pending-jobs")
async def agent_pending_jobs(shop_id: str = "counter-1", api_key: str = ""):
    """Return pending print jobs for local shop agent to execute."""
    orders = order_store.list_orders(shop_id=shop_id, limit=50)
    pending = [o.to_dict() for o in orders if o.status == "pending"]
    return {"orders": pending}


@app.get("/api/agent/download-file/{order_id}")
async def agent_download_file(order_id: str, shop_id: str = "", api_key: str = ""):
    """Allow shop agent to fetch original file to print locally."""
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    target_file = Path(order.file_path)
    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    from fastapi.responses import FileResponse
    return FileResponse(target_file, filename=order.filename)


@app.post("/api/agent/job-status")
async def agent_job_status_update(request: Request):
    """Allow shop agent to update order status upon physical printing."""
    try:
        data = await request.json()
    except Exception:
        data = {}
    order_id = data.get("order_id")
    status_str = data.get("status", "completed")
    printer_used = data.get("printer_used", "")
    error_msg = data.get("error_msg", "")
    if order_id:
        order_store.update_status(order_id, status_str, printer_used=printer_used, error_msg=error_msg)
        await broadcast_event("order_updated", {"order_id": order_id, "status": status_str})
    return {"success": True}


@app.get("/api/shops/{shop_id}/status")
async def get_shop_status_api(shop_id: str):
    """Check live status of a shop's printer connection."""
    shop = shop_store.get_shop(shop_id)
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop.to_dict()


# ──────────────────────────────────────────────
# Customer Upload Portal (Public)
# ──────────────────────────────────────────────

@app.get("/upload", response_class=HTMLResponse)
async def customer_upload_page(request: Request, shop: str = "counter-1"):
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={
            "shop_id": shop,
            "supported_extensions": sorted(list(SUPPORTED_EXTENSIONS)),
        },
    )


@app.post("/api/inspect-file")
async def inspect_file_api(
    file: UploadFile = File(...),
    color_mode: str = Form("bw"),
    copies: int = Form(1),
    page_range: str = Form(""),
):
    """Fast pre-upload inspector to detect document page count and estimate pricing."""
    content = await file.read()
    ext = Path(file.filename or "").suffix.lower()

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        detected_pages = detect_document_page_count(tmp_path)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    from printer_agent.config import PRICE_PER_PAGE_BW, PRICE_PER_PAGE_COLOR
    from printer_agent.print_engine import parse_page_range

    unit_price = PRICE_PER_PAGE_COLOR if color_mode == "color" else PRICE_PER_PAGE_BW
    effective_pages = detected_pages
    if page_range and page_range.strip():
        parsed = parse_page_range(page_range.strip(), max_pages=detected_pages)
        if parsed:
            effective_pages = len(parsed)

    num_copies = max(1, copies)
    est_total = round(effective_pages * num_copies * unit_price, 2)

    return {
        "filename": file.filename,
        "extension": ext,
        "page_count": detected_pages,
        "effective_pages": effective_pages,
        "unit_price": unit_price,
        "copies": num_copies,
        "total_amount": est_total,
    }


@app.post("/api/upload")
async def customer_upload_api(
    file: UploadFile = File(...),
    customer_name: str = Form("Counter Customer"),
    phone: str = Form(""),
    copies: int = Form(1),
    color_mode: str = Form("bw"),
    notes: str = Form(""),
    shop_id: str = Form("counter-1"),
    page_range: str = Form(""),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # Generate unique stored filename
    timestamp = int(time.time())
    safe_name = f"{timestamp}_{Path(file.filename).name}"
    target_path = UPLOADS_DIR / safe_name

    with target_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Detect actual page count of uploaded document
    detected_pages = detect_document_page_count(target_path)

    # Save to SQLite order store
    order = order_store.create_order(
        customer_name=customer_name.strip(),
        phone=phone.strip(),
        filename=file.filename,
        file_path=target_path,
        copies=max(1, copies),
        color_mode=color_mode,
        notes=notes.strip(),
        shop_id=shop_id.strip() or "counter-1",
        page_range=page_range.strip(),
        page_count=detected_pages,
    )

    logger.info("📥 New customer upload: %s (%s, %d copies, shop=%s) -> Order %s",
                order.filename, order.customer_name, order.copies, order.shop_id, order.order_id)

    # Broadcast live alert to operator dashboard
    await broadcast_event("new_order", order.to_dict())

    return {
        "success": True,
        "message": "Document uploaded successfully! Operator notified.",
        "order_id": order.order_id,
        "filename": order.filename,
        "copies": order.copies,
        "color_mode": order.color_mode,
        "page_count": order.page_count,
        "unit_price": order.unit_price,
        "total_amount": order.total_amount,
        "shop_id": order.shop_id,
    }


# ──────────────────────────────────────────────
# Operator Actions & Printing API (Protected)
# ──────────────────────────────────────────────

@app.get("/api/orders")
async def list_orders_api(shop: str | None = None, token: str = Depends(require_auth)):
    orders = order_store.list_orders(shop_id=shop, limit=100)
    return {"orders": [o.to_dict() for o in orders]}


@app.post("/api/orders/{order_id}/print")
async def print_order_api(
    order_id: str,
    printer_name: str = Form(""),
    copies: int | None = Form(None),
    page_range: str = Form(""),
    token: str = Depends(require_auth),
):
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    target_file = Path(order.file_path)
    if not target_file.exists():
        raise HTTPException(status_code=404, detail="Original uploaded file missing on disk.")

    chosen_printer = printer_name.strip() or get_default_printer()
    chosen_copies = copies if (copies and copies > 0) else order.copies
    chosen_range = page_range.strip() or getattr(order, "page_range", "")

    order_store.update_status(order_id, "printing", printer_used=chosen_printer)
    await broadcast_event("order_updated", {"order_id": order_id, "status": "printing"})

    try:
        # Trigger real Windows print engine with page range
        print_file(
            target_file,
            printer_name=chosen_printer,
            copies=chosen_copies,
            page_range=chosen_range,
        )
        order_store.update_status(order_id, "completed", printer_used=chosen_printer)
        await broadcast_event("order_updated", {"order_id": order_id, "status": "completed"})
        range_suffix = f" (pages: {chosen_range})" if chosen_range else ""
        return {
            "success": True,
            "message": f"Printed '{order.filename}' to '{chosen_printer}' ({chosen_copies} copies{range_suffix}).",
            "order_id": order_id,
            "status": "completed",
            "page_range": chosen_range,
        }
    except Exception as exc:
        err = str(exc)
        logger.error("Failed printing order %s: %s", order_id, err)
        order_store.update_status(order_id, "failed", printer_used=chosen_printer, error_msg=err)
        await broadcast_event("order_updated", {"order_id": order_id, "status": "failed", "error": err})
        raise HTTPException(status_code=500, detail=f"Print failed: {err}")


@app.post("/api/orders/{order_id}/status")
async def update_order_status_api(
    order_id: str,
    status: str = Form(...),
    token: str = Depends(require_auth),
):
    valid_statuses = {"pending", "printing", "completed", "failed", "cancelled"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    ok = order_store.update_status(order_id, status)
    if not ok:
        raise HTTPException(status_code=404, detail="Order not found.")

    await broadcast_event("order_updated", {"order_id": order_id, "status": status})
    return {"success": True, "order_id": order_id, "status": status}


@app.delete("/api/orders/{order_id}")
async def delete_order_api(order_id: str, token: str = Depends(require_auth)):
    ok = order_store.delete_order(order_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Order not found.")
    await broadcast_event("order_deleted", {"order_id": order_id})
    return {"success": True, "order_id": order_id}


@app.post("/api/orders/{order_id}/amount")
async def update_order_amount_api(
    order_id: str,
    amount: float = Form(...),
    token: str = Depends(require_auth),
):
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    new_amount = max(0.0, round(float(amount), 2))
    ok = order_store.update_amount(order_id, new_amount)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update order amount.")

    await broadcast_event("order_updated", {"order_id": order_id, "total_amount": new_amount})
    return {"success": True, "order_id": order_id, "total_amount": new_amount}


@app.post("/api/orders/{order_id}/pay")
async def mark_order_paid_api(
    order_id: str,
    payment_method: str = Form("cash"),
    payment_ref: str = Form(""),
    amount: float | None = Form(None),
    token: str = Depends(require_auth),
):
    """Operator marks an order as paid (cash or UPI) with live determined amount."""
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    chosen_amount = amount if (amount is not None and amount >= 0) else order.total_amount

    ok = order_store.mark_order_paid(
        order_id=order_id,
        payment_ref=payment_ref.strip(),
        payment_method=payment_method.strip(),
        amount=chosen_amount,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to update payment.")

    await broadcast_event("order_updated", {"order_id": order_id, "payment_status": "paid", "total_amount": chosen_amount})
    return {
        "success": True,
        "order_id": order_id,
        "payment_status": "paid",
        "payment_method": payment_method,
        "total_amount": chosen_amount,
    }


@app.get("/api/orders/{order_id}/upi-qr.png")
async def get_order_upi_qr(order_id: str):
    """Generate dynamic UPI QR Code PNG for scanning with PhonePe / GPay / Paytm / BHIM."""
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shop = shop_store.get_shop(order.shop_id)
    vpa = (shop.upi_vpa if shop and shop.upi_vpa else "") or UPI_DEFAULT_VPA
    merchant_name = (shop.upi_merchant_name if shop and shop.upi_merchant_name else "") or (shop.shop_name if shop else "") or UPI_MERCHANT_NAME

    qr_bytes = generate_upi_qr_bytes(
        vpa=vpa,
        merchant_name=merchant_name,
        amount=order.total_amount,
        order_id=order.order_id,
        note=f"Print {order.filename[:18]}",
    )
    return Response(content=qr_bytes, media_type="image/png")


@app.get("/api/orders/{order_id}/payment")
async def get_order_payment_info(order_id: str):
    """Retrieve full payment details, amount breakdown, and UPI intent URI."""
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    shop = shop_store.get_shop(order.shop_id)
    vpa = (shop.upi_vpa if shop and shop.upi_vpa else "") or UPI_DEFAULT_VPA
    merchant_name = (shop.upi_merchant_name if shop and shop.upi_merchant_name else "") or (shop.shop_name if shop else "") or UPI_MERCHANT_NAME

    upi_uri = generate_upi_uri(
        vpa=vpa,
        merchant_name=merchant_name,
        amount=order.total_amount,
        order_id=order.order_id,
        note=f"Print {order.filename[:18]}",
    )

    return {
        "order_id": order.order_id,
        "customer_name": order.customer_name,
        "filename": order.filename,
        "total_amount": order.total_amount,
        "copies": order.copies,
        "color_mode": order.color_mode,
        "page_count": order.page_count,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "payment_ref": order.payment_ref,
        "paid_at": order.paid_at,
        "vpa": vpa,
        "merchant_name": merchant_name,
        "upi_uri": upi_uri,
    }


@app.post("/api/orders/{order_id}/submit-utr")
async def customer_submit_utr(order_id: str, utr: str = Form(""), method: str = Form("upi")):
    """Allow customer or counter staff to record UPI transaction reference / UTR number."""
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    clean_utr = utr.strip()
    ok = order_store.mark_order_paid(
        order_id=order_id,
        payment_ref=clean_utr,
        payment_method=method.strip() or "upi",
        amount=order.total_amount,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to record payment reference")

    await broadcast_event("order_updated", {
        "order_id": order_id,
        "payment_status": "paid",
        "payment_ref": clean_utr,
        "payment_method": method.strip() or "upi",
        "total_amount": order.total_amount,
    })
    return {
        "success": True,
        "order_id": order_id,
        "message": "Payment recorded successfully! Operator notified.",
        "payment_status": "paid",
        "payment_ref": clean_utr,
    }


@app.post("/api/shops/{shop_id}/upi")
async def update_shop_upi_api(
    shop_id: str,
    upi_vpa: str = Form(...),
    upi_merchant_name: str = Form(""),
    token: str = Depends(require_auth),
):
    """Update shop's UPI ID and Merchant Name for direct customer payments."""
    user = get_session_user(token)
    if not user.get("is_admin") and user.get("shop_id") != shop_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this shop.")

    ok = shop_store.update_shop_upi(shop_id, upi_vpa, upi_merchant_name)
    if not ok:
        raise HTTPException(status_code=404, detail="Shop not found or update failed")
    return {
        "success": True,
        "shop_id": shop_id,
        "upi_vpa": upi_vpa.strip(),
        "upi_merchant_name": upi_merchant_name.strip(),
    }


@app.get("/api/analytics")
async def get_analytics_api(shop: str | None = None, token: str = Depends(require_auth)):
    """Revenue & order analytics for the dashboard stat cards."""
    import time as _time
    orders = order_store.list_orders(shop_id=shop, limit=1000)

    today_start = _time.mktime(_time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
    total_revenue = 0.0
    today_revenue = 0.0
    paid_count = 0
    unpaid_count = 0
    pending_count = 0
    completed_count = 0
    today_orders = 0

    for o in orders:
        if o.payment_status == "paid":
            total_revenue += o.total_amount
            paid_count += 1
            if o.paid_at and o.paid_at >= today_start:
                today_revenue += o.total_amount
        else:
            unpaid_count += 1

        if o.status == "pending":
            pending_count += 1
        elif o.status == "completed":
            completed_count += 1

        if o.created_at >= today_start:
            today_orders += 1

    return {
        "total_orders": len(orders),
        "today_orders": today_orders,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "total_revenue": round(total_revenue, 2),
        "today_revenue": round(today_revenue, 2),
    }


@app.get("/api/files/{order_id}")
async def view_order_file(order_id: str, token: str = Depends(require_auth)):
    order = order_store.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    path = Path(order.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing.")

    import mimetypes
    media_type, _ = mimetypes.guess_type(order.filename)
    if not media_type:
        media_type = "application/octet-stream"

    # pyrefly: ignore[missing-import]
    from fastapi.responses import FileResponse
    return FileResponse(
        path,
        media_type=media_type,
        content_disposition_type="inline",
        filename=order.filename,
    )


@app.get("/api/printers")
async def get_printers_api(token: str = Depends(require_auth)):
    try:
        printers = list_printers()
        default_p = get_default_printer()
    except Exception:
        printers = []
        default_p = ""
    return {"printers": printers, "default": default_p}


# ──────────────────────────────────────────────
# Real-time Server-Sent Events (SSE)
# ──────────────────────────────────────────────

@app.get("/api/events")
async def events_sse(token: str = Depends(require_auth)):
    """Server-Sent Events stream for instant dashboard updates & sound alerts."""
    queue: asyncio.Queue = asyncio.Queue()
    _subscribers.add(queue)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            # Send initial keepalive/connected message
            yield f"data: {json.dumps({'event': 'connected', 'timestamp': time.time()})}\n\n"
            while True:
                data = await queue.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _subscribers.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
