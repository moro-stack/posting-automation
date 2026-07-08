import csv
import io
import os
import sqlite3
from datetime import datetime

from common import db_sync

DEFAULT_DB_PATH = os.path.join("data", "posting.db")
_UNSET = object()


def _resolve_db_path(db_path=None) -> str:
    return db_path or os.environ.get("POSTING_DB_PATH") or DEFAULT_DB_PATH


def _push_remote(db_path=None) -> None:
    db_sync.push_db(_resolve_db_path(db_path))


def sync_from_remote(*, db_path=None) -> bool:
    return db_sync.pull_db(_resolve_db_path(db_path))


def _connect(db_path=None) -> sqlite3.Connection:
    path = _resolve_db_path(db_path)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _now(now):
    return now if now is not None else datetime.now().isoformat(timespec="seconds")


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS payables_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, default_category TEXT, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS receivables_clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS distributors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '業務委託',
            active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS petty_cash (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT, category_id INTEGER, amount INTEGER NOT NULL,
            project_id INTEGER, memo TEXT, source TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS payables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT, vendor_id INTEGER, amount INTEGER NOT NULL,
            original_status TEXT, note TEXT, project_id INTEGER,
            source TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS receivables (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT, client_id INTEGER, amount INTEGER NOT NULL,
            note TEXT, project_id INTEGER, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contract_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            distributor_id INTEGER, issue_date TEXT,
            period_from TEXT, period_to TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS contract_invoice_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL, project_id INTEGER,
            report_qty INTEGER NOT NULL DEFAULT 0, unit_price INTEGER NOT NULL DEFAULT 0,
            amount INTEGER NOT NULL DEFAULT 0, remark TEXT);
        CREATE TABLE IF NOT EXISTS issue_manual_costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER, content TEXT, amount INTEGER NOT NULL,
            created_at TEXT NOT NULL);
        """
    )
    conn.commit()


def init_db(db_path=None) -> None:
    _connect(db_path).close()
