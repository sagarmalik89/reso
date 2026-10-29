"""
main.py / CLI entry-point for the Printer Agent
================================================

Usage examples
--------------
  # Start the full agent (folder watcher + scheduler + queue worker):
  python main.py start

  # Print a specific file on-demand:
  python main.py print path/to/file.pdf

  # Print with priority and copies:
  python main.py print report.pdf --priority 1 --copies 2

  # List available printers:
  python main.py printers

  # Show current queue status:
  python main.py status

  # Add a one-time scheduled job:
  python main.py schedule path/to/file.pdf --time 09:30 --priority 3

  # Interactive dashboard (refreshes every 3 s):
  python main.py dashboard
"""

import signal
import sys
import time

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# pyrefly: ignore[missing-import]
import click
from tabulate import tabulate

from printer_agent.config import LOGS_DIR, WATCH_FOLDER, WEB_HOST, WEB_PORT
from printer_agent.folder_watcher import folder_watcher
from printer_agent.logger import get_logger
from printer_agent.print_engine import get_default_printer, list_printers, print_file
from printer_agent.queue_manager import queue_manager
from printer_agent.scheduler import print_scheduler

logger = get_logger("main", LOGS_DIR)


# ──────────────────────────────────────────────
# CLI group
# ──────────────────────────────────────────────

@click.group()
def cli():
    """🖨  Printer Agent – automatic print job management."""
    pass


# ──────────────────────────────────────────────
# start
# ──────────────────────────────────────────────

@cli.command()
def start():
    """Start the full printer agent (watcher + scheduler + queue)."""
    logger.info("=" * 60)
    logger.info("  🖨  PRINTER AGENT starting up …")
    logger.info("=" * 60)
    logger.info("  Watch folder : %s", WATCH_FOLDER)
    logger.info("  Default printer: %s", get_default_printer())
    logger.info("=" * 60)

    queue_manager.start()
    folder_watcher.start()
    print_scheduler.start()

    # Graceful shutdown on Ctrl+C or SIGTERM
    def _shutdown(sig, frame):
        logger.info("\n🛑 Shutting down printer agent …")
        print_scheduler.stop()
        folder_watcher.stop()
        queue_manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT,  _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    logger.info("✅ Printer Agent is running. Drop files into:\n   %s", WATCH_FOLDER)
    logger.info("   Press Ctrl+C to stop.\n")

    # Keep the main thread alive
    while True:
        time.sleep(1)


# ──────────────────────────────────────────────
# print (on-demand)
# ──────────────────────────────────────────────

@cli.command(name="print")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--printer", "-p", default="", help="Printer name (default: system default)")
@click.option("--priority", "-P", default=5, show_default=True,
              help="Priority 1 (highest) – 10 (lowest)")
@click.option("--copies",   "-c", default=1, show_default=True, help="Number of copies")
@click.option("--now",      is_flag=True, default=False,
              help="Print immediately (skip queue)")
def print_cmd(file_path, printer, priority, copies, now):
    """Print FILE_PATH immediately or via the queue."""
    from pathlib import Path
    path = Path(file_path)

    if now:
        logger.info("🖨  Printing '%s' immediately …", path.name)
        queue_manager.start()   # ensure worker is up
        print_file(path, printer_name=printer, copies=copies)
    else:
        queue_manager.start()
        jid = queue_manager.enqueue(path, priority=priority,
                                    printer_name=printer, copies=copies)
        click.echo(f"✅ Job {jid!r} added to queue (priority={priority}).")

        # Wait until the job is processed
        click.echo("⏳ Waiting for job to complete …")
        timeout = 120
        start   = time.monotonic()
        while time.monotonic() - start < timeout:
            if jid in queue_manager._completed or jid in queue_manager._failed:
                break
            time.sleep(1)

        if jid in queue_manager._completed:
            click.echo("✅ Job completed successfully.")
        elif jid in queue_manager._failed:
            click.echo("❌ Job failed after all retries. Check logs and failed/ folder.")
        else:
            click.echo("⚠️  Job still in queue (timed out waiting). Agent continues in background.")

        queue_manager.stop()


# ──────────────────────────────────────────────
# printers
# ──────────────────────────────────────────────

@cli.command()
def printers():
    """List all installed printers."""
    ps = list_printers()
    if not ps:
        click.echo("No printers found.")
        return
    rows = [(p["name"], p["driver"], p["port"]) for p in ps]
    click.echo(tabulate(rows, headers=["Name", "Driver", "Port"], tablefmt="rounded_outline"))
    click.echo(f"\n  Default: {get_default_printer()}")


# ──────────────────────────────────────────────
# status
# ──────────────────────────────────────────────

@cli.command()
def status():
    """Show current queue statistics."""
    s = queue_manager.status()
    rows = [
        ["Queued jobs",    s["queued"]],
        ["Retrying",       s["retrying"]],
        ["Completed",      s["completed"]],
        ["Permanently failed", s["failed"]],
    ]
    click.echo(tabulate(rows, headers=["Metric", "Count"], tablefmt="rounded_outline"))


# ──────────────────────────────────────────────
# schedule
# ──────────────────────────────────────────────

@cli.command(name="schedule")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--time",     "-t", "run_time", required=True, help="Time in HH:MM format")
@click.option("--priority", "-P", default=5, show_default=True, help="Priority 1–10")
def schedule_cmd(file_path, run_time, priority):
    """Schedule FILE_PATH to print daily at --time HH:MM."""
    from pathlib import Path
    queue_manager.start()
    print_scheduler.start()
    print_scheduler.add_job(str(Path(file_path).resolve()), run_time, priority)

    click.echo(f"🗓  Scheduled '{file_path}' to print daily at {run_time} (priority={priority}).")
    click.echo("   The scheduler is running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print_scheduler.stop()
        queue_manager.stop()
        click.echo("\n🛑 Scheduler stopped.")


# ──────────────────────────────────────────────
# dashboard (live terminal UI)
# ──────────────────────────────────────────────

@cli.command()
def dashboard():
    """Show a live-refreshing dashboard (press Ctrl+C to exit)."""
    import os

    queue_manager.start()
    folder_watcher.start()
    print_scheduler.start()

    try:
        while True:
            os.system("cls" if sys.platform == "win32" else "clear")
            s = queue_manager.status()

            click.echo("╔══════════════════════════════════════════╗")
            click.echo("║     🖨  PRINTER AGENT  –  DASHBOARD      ║")
            click.echo("╠══════════════════════════════════════════╣")
            click.echo(f"║  Printer  : {get_default_printer():<30}║")
            click.echo(f"║  Watch folder: {str(WATCH_FOLDER):<27}║")
            click.echo("╠══════════════════════════════════════════╣")
            click.echo(f"║  Queued       : {s['queued']:<26}║")
            click.echo(f"║  Retrying     : {s['retrying']:<26}║")
            click.echo(f"║  Completed ✅  : {s['completed']:<26}║")
            click.echo(f"║  Failed ❌     : {s['failed']:<26}║")
            click.echo("╠══════════════════════════════════════════╣")
            click.echo("║  Drop files into watch_folder to print  ║")
            click.echo("║  Press Ctrl+C to exit                   ║")
            click.echo("╚══════════════════════════════════════════╝")

            time.sleep(3)
    except KeyboardInterrupt:
        click.echo("\n🛑 Stopping agent …")
        print_scheduler.stop()
        folder_watcher.stop()
        queue_manager.stop()


# ──────────────────────────────────────────────
# web (Customer QR Portal & Operator Dashboard)
# ──────────────────────────────────────────────

@cli.command()
@click.option("--host", default=WEB_HOST, help="Host interface to bind (default: 0.0.0.0)")
@click.option("--port", "-p", default=WEB_PORT, help="Port to listen on (default: 8000)")
@click.option("--shop", default="counter-1", help="Shop or counter ID")
def web(host, port, shop):
    """Start the web server for customer QR scan & operator dashboard."""
    import uvicorn
    from printer_agent.web.utils import get_local_ip, get_upload_url

    local_ip = get_local_ip()
    upload_url = get_upload_url(local_ip, port, shop)

    click.echo("=" * 65)
    click.echo("  🌐 PRINTER AGENT WEB PORTAL STARTED")
    click.echo("=" * 65)
    click.echo(f"  Operator Dashboard : http://localhost:{port}")
    click.echo(f"  Customer Upload URL: {upload_url}")
    click.echo(f"  Print Counter Flyer: http://localhost:{port}/qr?shop={shop}")
    click.echo(f"  Admin Login Email  : admin@printagent.com (password: admin123)")
    click.echo("=" * 65)
    click.echo("  Press Ctrl+C to stop.\n")

    # Start queue manager worker
    queue_manager.start()

    try:
        uvicorn.run("printer_agent.web.app:app", host=host, port=port, reload=False, log_level="info")
    finally:
        queue_manager.stop()


# ──────────────────────────────────────────────
# Entry-point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    cli()
