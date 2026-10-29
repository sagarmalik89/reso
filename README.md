# 🖨 Printer Agent


![CI](https://github.com/sagarmalik89/reso/actions/workflows/ci.yml/badge.svg)

Fully automatic **Python-based Print Job Manager** for Windows.  

---

## ✨ Features

| Feature | Details |
|---|---|
| **Folder Watcher** | Drop PDF/DOCX/TXT into `watch_folder/` and it prints automatically |
| **Priority Queue** | Jobs processed in priority order (1 = highest, 10 = lowest) |
| **Retry Logic** | Failed jobs retried up to 3× with configurable delay |
| **Scheduler** | Print files at a specific time every day (`08:00`, `17:30`, etc.) |
| **On-Demand CLI** | Print any file instantly from the terminal |
| **Live Dashboard** | Real-time terminal dashboard showing queue health |
| **File Lifecycle** | Printed files → `processed/`, failed files → `failed/` |
| **Logging** | Colour-coded console + rotating file log in `logs/` |

---

## 📁 Project Structure

```
sa/
├── main.py                     ← CLI entry-point
├── requirements.txt
├── printer_agent/
│   ├── config.py               ← All settings (printer, paths, retries, schedules)
│   ├── print_engine.py         ← Low-level Windows printing (win32print + Shell)
│   ├── queue_manager.py        ← Priority queue + retry logic
│   ├── folder_watcher.py       ← watchdog file-system watcher
│   ├── scheduler.py            ← Daily scheduled jobs
│   └── logger.py               ← Colour console + rotating file log
├── watch_folder/               ← DROP FILES HERE (auto-created)
├── processed/                  ← Successfully printed files (auto-created)
├── failed/                     ← Files that failed all retries (auto-created)
└── logs/                       ← printer_agent.log (auto-created)
```

---

## 🚀 Quick Start

### 1. Install dependencies

```powershell
pip install -r requirements.txt
```

> **Note:** Requires Python 3.10+ on Windows (uses `win32print`).

### 2. (Optional) Set your printer

Edit `printer_agent/config.py`:

```python
DEFAULT_PRINTER = "Your Printer Name Here"   # or leave "" for system default
```

### 3. Start the full agent

```powershell
python main.py start
```

Then drop any `.pdf`, `.docx`, `.doc`, or `.txt` file into the `watch_folder/` directory — it will be automatically printed!

---

## 🔧 CLI Commands

### Start the full agent
```powershell
python main.py start
```

### Print a file on-demand
```powershell
python main.py print report.pdf
python main.py print report.pdf --priority 1 --copies 3
python main.py print report.pdf --now          # skip queue, print immediately
```

### List all printers
```powershell
python main.py printers
```

### View queue status
```powershell
python main.py status
```

### Schedule a daily print job
```powershell
python main.py schedule daily_report.pdf --time 08:00 --priority 2
```

### Live dashboard
```powershell
python main.py dashboard
```

---

## ⚙️ Configuration (`printer_agent/config.py`)

| Setting | Default | Description |
|---|---|---|
| `DEFAULT_PRINTER` | `""` (system default) | Printer name |
| `COPIES` | `1` | Number of copies |
| `MAX_RETRIES` | `3` | Retry attempts on failure |
| `RETRY_DELAY_SEC` | `30` | Seconds between retries |
| `QUEUE_POLL_SEC` | `2` | Queue check interval |
| `SUPPORTED_EXTENSIONS` | `.pdf .docx .doc .txt` | File types to watch |
| `SCHEDULED_JOBS` | `[]` | List of daily scheduled jobs |

### Example scheduled job in `config.py`
```python
SCHEDULED_JOBS = [
    {"file": "C:/reports/daily.pdf", "time": "08:00", "priority": 2},
    {"file": "C:/invoices/week.pdf", "time": "17:30", "priority": 4},
]
```

---

## 📋 Requirements

- Windows 10/11
- Python 3.10+
- `pywin32` (Windows print APIs)
- (Optional) LibreOffice – for better DOCX → PDF conversion
