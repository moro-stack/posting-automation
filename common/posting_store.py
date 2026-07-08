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


def _int_or_none(value):
    return None if value is None else int(value)


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


def _add(table, columns, values, db_path):
    conn = _connect(db_path)
    try:
        cols = ", ".join(columns)
        ph = ", ".join("?" for _ in columns)
        cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({ph})", values)
        conn.commit()
        new_id = int(cur.lastrowid)
    finally:
        conn.close()
    _push_remote(db_path)
    return new_id


def _list(table, only_active, db_path):
    conn = _connect(db_path)
    try:
        sql = f"SELECT * FROM {table}"
        if only_active:
            sql += " WHERE active=1"
        sql += " ORDER BY id"
        return [dict(r) for r in conn.execute(sql).fetchall()]
    finally:
        conn.close()


def _update(table, row_id, fields, db_path):
    sets = {k: v for k, v in fields.items() if v is not _UNSET}
    if not sets:
        return
    assignments = ", ".join(f"{k}=?" for k in sets)
    conn = _connect(db_path)
    try:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id=?",
                     (*sets.values(), int(row_id)))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)


def _delete(table, row_id, db_path):
    conn = _connect(db_path)
    try:
        conn.execute(f"DELETE FROM {table} WHERE id=?", (int(row_id),))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)


# --- projects ---
def add_project(name, *, active=1, db_path=None):
    return _add("projects", ["name", "active"], [name, int(active)], db_path)


def list_projects(*, only_active=False, db_path=None):
    return _list("projects", only_active, db_path)


def update_project(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("projects", row_id, {"name": name, "active": active}, db_path)


def delete_project(row_id, *, db_path=None):
    _delete("projects", row_id, db_path)


# --- expense_categories ---
def add_expense_category(name, *, active=1, db_path=None):
    return _add("expense_categories", ["name", "active"], [name, int(active)], db_path)


def list_expense_categories(*, only_active=False, db_path=None):
    return _list("expense_categories", only_active, db_path)


def update_expense_category(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("expense_categories", row_id, {"name": name, "active": active}, db_path)


def delete_expense_category(row_id, *, db_path=None):
    _delete("expense_categories", row_id, db_path)


# --- payables_vendors ---
def add_payables_vendor(name, *, default_category=None, active=1, db_path=None):
    return _add("payables_vendors", ["name", "default_category", "active"],
                [name, default_category, int(active)], db_path)


def list_payables_vendors(*, only_active=False, db_path=None):
    return _list("payables_vendors", only_active, db_path)


def update_payables_vendor(row_id, *, name=_UNSET, default_category=_UNSET, active=_UNSET, db_path=None):
    _update("payables_vendors", row_id,
            {"name": name, "default_category": default_category, "active": active}, db_path)


def delete_payables_vendor(row_id, *, db_path=None):
    _delete("payables_vendors", row_id, db_path)


# --- receivables_clients ---
def add_receivables_client(name, *, active=1, db_path=None):
    return _add("receivables_clients", ["name", "active"], [name, int(active)], db_path)


def list_receivables_clients(*, only_active=False, db_path=None):
    return _list("receivables_clients", only_active, db_path)


def update_receivables_client(row_id, *, name=_UNSET, active=_UNSET, db_path=None):
    _update("receivables_clients", row_id, {"name": name, "active": active}, db_path)


def delete_receivables_client(row_id, *, db_path=None):
    _delete("receivables_clients", row_id, db_path)


# --- distributors ---
def add_distributor(name, *, kind="業務委託", active=1, db_path=None):
    return _add("distributors", ["name", "kind", "active"], [name, kind, int(active)], db_path)


def list_distributors(*, only_active=False, db_path=None):
    return _list("distributors", only_active, db_path)


def update_distributor(row_id, *, name=_UNSET, kind=_UNSET, active=_UNSET, db_path=None):
    _update("distributors", row_id, {"name": name, "kind": kind, "active": active}, db_path)


def delete_distributor(row_id, *, db_path=None):
    _delete("distributors", row_id, db_path)


_PRESET_PROJECTS = ["関西ぱど：京阪北版", "関西ぱど：京阪南版", "アドバリュー",
                    "リビングプロシード", "その他"]
_PRESET_CATEGORIES = ["駐車場代", "飲み物代", "その他"]
_PRESET_VENDORS = [
    ("京阪総合サービス株式会社", "ゴミ収集"),
    ("大東建託パートナーズ株式会社", "家賃"),
    ("NTTファイナンス株式会社", "電話"),
    ("NTTコミュニケーション株式会社", "プロバイダ"),
    ("関西電力株式会社", "電気"),
    ("株式会社スペースリーダー", "機械警備"),
    ("株式会社トヨタレンタリース大阪", "リース"),
    ("株式会社ネクストレベル", "派遣"),
    ("キャノンマーケティングジャパン株式会社", "コピー代"),
    ("株式会社 CLOVER JAPAN", "配布"),
    ("配夢株式会社", "配布"),
]
_PRESET_CLIENTS = ["株式会社関西ぱど　北大阪営業部", "株式会社進和プロモーション 大阪支社",
                   "株式会社アド・バリュー", "株式会社リビングプロシード"]


def seed_masters(*, db_path=None) -> None:
    if not list_projects(db_path=db_path):
        for n in _PRESET_PROJECTS:
            add_project(n, db_path=db_path)
    if not list_expense_categories(db_path=db_path):
        for n in _PRESET_CATEGORIES:
            add_expense_category(n, db_path=db_path)
    if not list_payables_vendors(db_path=db_path):
        for n, c in _PRESET_VENDORS:
            add_payables_vendor(n, default_category=c, db_path=db_path)
    if not list_receivables_clients(db_path=db_path):
        for n in _PRESET_CLIENTS:
            add_receivables_client(n, db_path=db_path)


# --- petty_cash ---
def add_petty_cash(date, category_id, amount, *, project_id=None, memo=None,
                   source="manual", db_path=None, now=None):
    return _add("petty_cash",
                ["date", "category_id", "amount", "project_id", "memo", "source", "created_at"],
                [date, _int_or_none(category_id), int(amount), _int_or_none(project_id),
                 memo, source, _now(now)], db_path)


def list_petty_cash(*, project_id=None, date_from=None, date_to=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM petty_cash WHERE 1=1"
        args = []
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        if date_from is not None:
            sql += " AND date>=?"; args.append(date_from)
        if date_to is not None:
            sql += " AND date<=?"; args.append(date_to)
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_petty_cash(row_id, *, db_path=None):
    _delete("petty_cash", row_id, db_path)


# --- payables ---
def add_payable(month, vendor_id, amount, *, original_status=None, note=None,
                project_id=None, source="manual", db_path=None, now=None):
    return _add("payables",
                ["month", "vendor_id", "amount", "original_status", "note",
                 "project_id", "source", "created_at"],
                [month, _int_or_none(vendor_id), int(amount), original_status, note,
                 _int_or_none(project_id), source, _now(now)], db_path)


def list_payables(*, month=None, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM payables WHERE 1=1"
        args = []
        if month is not None:
            sql += " AND month=?"; args.append(month)
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_payable(row_id, *, db_path=None):
    _delete("payables", row_id, db_path)


# --- receivables ---
def add_receivable(month, client_id, amount, *, note=None, project_id=None,
                   db_path=None, now=None):
    return _add("receivables",
                ["month", "client_id", "amount", "note", "project_id", "created_at"],
                [month, _int_or_none(client_id), int(amount), note,
                 _int_or_none(project_id), _now(now)], db_path)


def list_receivables(*, month=None, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM receivables WHERE 1=1"
        args = []
        if month is not None:
            sql += " AND month=?"; args.append(month)
        if project_id is not None:
            sql += " AND project_id=?"; args.append(int(project_id))
        sql += " ORDER BY id DESC"
        return [dict(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def delete_receivable(row_id, *, db_path=None):
    _delete("receivables", row_id, db_path)
