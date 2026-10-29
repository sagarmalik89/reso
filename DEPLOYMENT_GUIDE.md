# 🖨️ Printer Agent & Multi-Shop QR Web Portal
## Complete Setup, Deployment & Handover Guide

---

### 🌟 Overview & Workflow
This application replaces the traditional, messy process of asking customers to send files on WhatsApp before printing.

```
+------------------+         +----------------------------+         +--------------------------+
|  Customer Phone  |  Scan   |   Mobile Upload Portal     | Upload  |    Shop Operator Screen  |
|  (Camera/Safari) | ------> |  (Select PDF/Image/Word,   | ------> |  (Live Audio/Visual Alert|
|                  |         |   Copies, B&W or Color)    |         |   1-Click Direct Print)  |
+------------------+         +----------------------------+         +--------------------------+
                                                                                 |
                                                                                 v
                                                                    [ Physical Local Printer ]
```

1. **Customer scans the Counter QR Code** with their phone camera.
2. A fast, mobile-friendly upload page opens on their phone.
3. Customer selects their document/photo, specifies copies, and taps **Send**.
4. The **Operator Dashboard rings an instant chime** and shows the customer's document.
5. The operator clicks **"🖨️ Print Now"** to directly print to the connected printer.

---

### 🚀 Quick Start (Running Locally in a Shop)

#### Option 1: One-Click Launcher (Recommended for Shop Staff)
Simply double-click:
```
start_printer_agent.bat
```
This automatically verifies dependencies and launches the portal on port `8000`.

#### Option 2: Command Line
Open PowerShell or Terminal in the project folder and run:
```powershell
python main.py web --port 8000 --shop "Shop-1"
```

Once running:
- **Operator Dashboard**: `http://localhost:8000`
- **Default Login Email**: `admin@printagent.com`
- **Default Password**: `admin123`
- **Printable Counter Flyer**: `http://localhost:8000/qr`

---

### 🏪 How to Sell & Onboard Multiple Shops (SaaS Model)

When a new shopkeeper wants to use this service with you:

#### Step 1: Shopkeeper Signs Up
1. Send the shopkeeper to your portal registration link:
   ```text
   http://your-server-ip:8000/signup
   ```
2. The shopkeeper enters:
   - **Shop Name** (e.g., *Malik Cyber Cafe & Prints*)
   - **Owner Name & Phone Number**
   - **Email & Password**
   - **City / Market Location**
3. Upon registration, their unique Shop Counter ID (e.g. `malik-cafe`) and dedicated QR code are automatically generated!

---

### 🖨️ How the Shopkeeper Connects Their Physical Printer

Once logged in, the shopkeeper opens their **Setup Guide**:
```text
http://your-server-ip:8000/setup-guide?shop=malik-cafe
```

#### 1. Hardware Connection (Physical Printer to PC)
- Connect printer to the shop PC via **USB cable** or connect both to the **same Wi-Fi router**.
- Ensure the printer has paper and power is ON.
- Works with **HP, Canon, Epson, Brother, TVS**, or any Windows-compatible printer.

#### 2. Installing the Shop Agent on the Shop PC
The shopkeeper needs to run the lightweight Shop Agent on the PC connected to the printer:
- **Option A (Standalone System Tray .exe - Recommended)**:
  Run `build_tray_app.bat` to compile `release/PrinterAgent.exe`. Give the shopkeeper the `release/` folder. They edit their shop ID in `shop_config.json` and double-click `PrinterAgent.exe`. It runs silently in their Windows taskbar tray with desktop notifications and 1-click test printing!
- **Option B (1-Click Download)**: On their Setup Guide, they click **"⬇️ Download Launcher"** which downloads `start_malik-cafe_agent.bat` pre-configured with their Shop ID and API key.
- **Option C (Batch Menu)**: Double-click **`run_shop_agent.bat`** in the project folder and choose `[1] Start Live Print Agent`.

#### 3. Live Status & Hardware Test Print
- As soon as the agent starts, the server updates the shop's status to **🟢 Printer Online & Ready**.
- In the dashboard or system tray menu, click **"🖨️ Send Test Print"** to verify that paper feeds and ink prints correctly.

#### 4. Place Counter QR Flyer
- Print the flyer from `http://your-server-ip:8000/qr?shop=malik-cafe`.
- Place the laminated flyer on the shop desk. Customers scan and print!

---

### 🖥️ Windows System Tray Executable (.exe)

For non-technical shopkeepers who do not want command prompt windows on their screens:

```text
build_tray_app.bat   -->   Compiles release\PrinterAgent.exe
```

1. Run **`build_tray_app.bat`** (or `python build_exe.py`).
2. The compilation produces a single portable **`release\PrinterAgent.exe`** with:
   - Modern Windows System Tray icon with live connection indicator (🟢 Online / 🔴 Offline).
   - Windows Desktop Balloon / Toast notifications on incoming orders and completed prints.
   - Right-click tray menu with 1-click **Hardware Test Print**, **Open Dashboard**, **Open Counter Flyer**, and **Edit Configuration**.
   - No black console window (`--noconsole`).
3. To start automatically on Windows boot:
   - Press `Win + R`, type `shell:startup`, and drop a shortcut to `PrinterAgent.exe`.


---

### 👑 Super Admin Dashboard (For Platform Owner)
As the owner, log in with `admin@printagent.com` and open:
```text
http://localhost:8000/admin/shops
```
Here you can:
- View all registered shops and contact details (phone, email, city).
- See real-time online/offline status of each shop's printer.
- Monitor total print jobs completed.
- Manage subscriptions and access any shop's dashboard directly.

---

### ⚙️ Configuration & Customization (`printer_agent/config.py`)

You can customize credentials or default settings via environment variables or directly in `printer_agent/config.py`:

| Variable | Default Value | Description |
|---|---|---|
| `ADMIN_EMAIL` | `admin@printagent.com` | Login email for the operator dashboard |
| `ADMIN_PASSWORD` | `admin123` | Password for the operator dashboard |
| `WEB_PORT` | `8000` | Port for the web portal |
| `WEB_HOST` | `0.0.0.0` | Bind host (all interfaces for LAN access) |
| `PRINTER_NAME` | `""` | Empty string means system default printer |

---

### 🧪 Verifying & Testing
All automated tests are pre-configured. To verify anytime:
```powershell
python -m pytest -v
```
All 21 unit tests (print engine, queue management, multi-shop registration, hardware test printing, order store, and QR generation) pass with 100% success.
