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
    # 買掛に請求書の日付(YYYY-MM-DD)を持たせる(#12)。旧DBは自動でカラム追加。
    pay_cols = {r[1] for r in conn.execute("PRAGMA table_info(payables)")}
    if "date" not in pay_cols:
        conn.execute("ALTER TABLE payables ADD COLUMN date TEXT")
    # 取引先をAI読み取りの自由入力名で持たせる(マスタ非依存)。旧DBは自動でカラム追加。
    if "vendor_name" not in pay_cols:
        conn.execute("ALTER TABLE payables ADD COLUMN vendor_name TEXT")
    # 号別明細の手入力コストに配布作業日を持たせる。旧DBは自動でカラム追加。
    imc_cols = {r[1] for r in conn.execute("PRAGMA table_info(issue_manual_costs)")}
    if "work_date" not in imc_cols:
        conn.execute("ALTER TABLE issue_manual_costs ADD COLUMN work_date TEXT")
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
def add_payable(month, vendor_id, amount, *, date=None, vendor_name=None,
                original_status=None, note=None, project_id=None, source="manual",
                db_path=None, now=None):
    # 請求書の日付(date)があれば月度(month)はそこから導出する(#12)
    if date and not month:
        month = str(date)[:7]
    return _add("payables",
                ["month", "date", "vendor_id", "vendor_name", "amount", "original_status",
                 "note", "project_id", "source", "created_at"],
                [month, date, _int_or_none(vendor_id), vendor_name, int(amount),
                 original_status, note, _int_or_none(project_id), source, _now(now)], db_path)


def find_duplicate_petty(date, category_id, amount, *, db_path=None):
    """同じ 日付・費目・金額 の小口があれば返す(#11 重複警告用)。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM petty_cash WHERE IFNULL(date,'')=IFNULL(?,'')"
            " AND IFNULL(category_id,-1)=IFNULL(?,-1) AND amount=?",
            (date, _int_or_none(category_id), int(amount))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_duplicate_payable(date, vendor_id, amount, *, vendor_name=None, db_path=None):
    """同じ 請求書日付・取引先・金額 の買掛があれば返す(#11)。
    vendor_name を渡した場合は取引先名(自由入力)で突合、無ければ vendor_id で突合。"""
    conn = _connect(db_path)
    try:
        if vendor_name is not None:
            rows = conn.execute(
                "SELECT * FROM payables WHERE IFNULL(date,'')=IFNULL(?,'')"
                " AND IFNULL(vendor_name,'')=IFNULL(?,'') AND amount=?",
                (date, vendor_name, int(amount))).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM payables WHERE IFNULL(date,'')=IFNULL(?,'')"
                " AND IFNULL(vendor_id,-1)=IFNULL(?,-1) AND amount=?",
                (date, _int_or_none(vendor_id), int(amount))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def find_duplicate_receivable(month, client_id, amount, *, db_path=None):
    """同じ 月度・売掛先・金額 の売掛があれば返す(#11)。"""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM receivables WHERE IFNULL(month,'')=IFNULL(?,'')"
            " AND IFNULL(client_id,-1)=IFNULL(?,-1) AND amount=?",
            (month, _int_or_none(client_id), int(amount))).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


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


# --- contract_invoices ---
def add_contract_invoice(distributor_id, issue_date, period_from, period_to, lines,
                         *, db_path=None, now=None):
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO contract_invoices"
            " (distributor_id, issue_date, period_from, period_to, created_at)"
            " VALUES (?,?,?,?,?)",
            (_int_or_none(distributor_id), issue_date, period_from, period_to, _now(now)))
        invoice_id = int(cur.lastrowid)
        for ln in lines:
            qty = float(ln.get("report_qty") or 0)
            price = float(ln.get("unit_price") or 0)
            conn.execute(
                "INSERT INTO contract_invoice_lines"
                " (invoice_id, project_id, report_qty, unit_price, amount, remark)"
                " VALUES (?,?,?,?,?,?)",
                (invoice_id, _int_or_none(ln.get("project_id")), qty, price,
                 qty * price, ln.get("remark")))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)
    return invoice_id


def get_contract_invoice(invoice_id, *, db_path=None):
    conn = _connect(db_path)
    try:
        head = conn.execute("SELECT * FROM contract_invoices WHERE id=?",
                            (int(invoice_id),)).fetchone()
        if head is None:
            return None
        lines = conn.execute(
            "SELECT * FROM contract_invoice_lines WHERE invoice_id=? ORDER BY id",
            (int(invoice_id),)).fetchall()
        return {"invoice": dict(head), "lines": [dict(r) for r in lines]}
    finally:
        conn.close()


def list_contract_invoices(*, db_path=None):
    conn = _connect(db_path)
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM contract_invoices ORDER BY id DESC").fetchall()]
    finally:
        conn.close()


def delete_contract_invoice(invoice_id, *, db_path=None):
    conn = _connect(db_path)
    try:
        conn.execute("DELETE FROM contract_invoice_lines WHERE invoice_id=?",
                     (int(invoice_id),))
        conn.execute("DELETE FROM contract_invoices WHERE id=?", (int(invoice_id),))
        conn.commit()
    finally:
        conn.close()
    _push_remote(db_path)


# --- issue_manual_costs ---
def add_issue_manual_cost(project_id, content, amount, *, work_date=None, db_path=None, now=None):
    return _add("issue_manual_costs",
                ["project_id", "content", "amount", "work_date", "created_at"],
                [_int_or_none(project_id), content, int(amount), work_date or None, _now(now)],
                db_path)


def list_issue_manual_costs(*, project_id=None, db_path=None):
    conn = _connect(db_path)
    try:
        order = "ORDER BY work_date IS NULL, work_date, id"
        if project_id is None:
            rows = conn.execute(f"SELECT * FROM issue_manual_costs {order}").fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM issue_manual_costs WHERE project_id=? {order}",
                (int(project_id),)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_issue_manual_cost(row_id, *, work_date=_UNSET, content=_UNSET, amount=_UNSET, db_path=None):
    fields = {"work_date": work_date, "content": content,
              "amount": (int(amount) if amount is not _UNSET else _UNSET)}
    _update("issue_manual_costs", row_id, fields, db_path)


def delete_issue_manual_cost(row_id, *, db_path=None):
    _delete("issue_manual_costs", row_id, db_path)
