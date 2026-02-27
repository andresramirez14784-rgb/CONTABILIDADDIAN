"""
Conciliador DIAN y Bancario — SQLite database manager.
Handles companies, users, roles, permissions, and uploaded file metadata.
Desarrollado por ANDRES FELIPE RAMIREZ GONZALES.
"""
import sqlite3
import os
import hashlib
import pickle
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "contadash.db"
UPLOADS_PATH = Path(__file__).parent / "uploads"

# ─── Roles ────────────────────────────────────────────────────────────────────
ROLES = ["admin", "contador_senior", "contador", "auditor", "viewer"]
ROLE_LABELS = {
    "admin":           "Administrador",
    "contador_senior": "Contador Senior",
    "contador":        "Contador",
    "auditor":         "Auditor",
    "viewer":          "Solo Lectura",
}

# ─── Permissions matrix ───────────────────────────────────────────────────────
# module → minimum role index required (lower = more access)
# 0=admin, 1=contador_senior, 2=contador, 3=auditor, 4=viewer
PERMISSIONS = {
    "dashboard":  4,  # all roles
    "ventas":     4,
    "compras":    4,
    "iva":        4,
    "nomina":     2,  # contador and above
    "exogena":    1,  # contador_senior and above (viewer via read-only for auditor)
    "hallazgos":    4,
    "datos":        4,
    "exportar":     2,
    "cargar":       2,  # contador and above (can upload files)
    "clientes":     4,  # todos los roles (reporte global clientes)
    "proveedores":  4,  # todos los roles (reporte global proveedores)
    "extractos":    4,  # todos los roles (análisis extractos bancarios)
    "empresas":     0,  # admin only
    "usuarios":     0,  # admin only
}

# All available modules (for checklist UI)
ALL_MODULES = list(PERMISSIONS.keys())
MODULE_LABELS = {
    "dashboard": "🏠 Dashboard",
    "ventas": "📄 Ventas",
    "compras": "📦 Compras",
    "iva": "💰 IVA",
    "nomina": "👥 Nómina",
    "exogena": "🔗 Exógena",
    "hallazgos": "🔍 Hallazgos",
    "datos": "📋 Datos",
    "exportar": "📥 Exportar",
    "cargar": "📂 Cargar Datos",
    "clientes": "👤 Clientes",
    "proveedores": "🏪 Proveedores",
    "extractos": "🏦 Extractos",
    "empresas": "🏢 Empresas",
    "usuarios": "👤 Usuarios",
}

# Auditor has read access to exogena despite index
AUDITOR_READ_ONLY = {"exogena", "nomina", "ventas", "compras", "iva", "datos"}


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database schema and seed demo data if empty."""
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nit         TEXT UNIQUE NOT NULL,
        razon_social TEXT NOT NULL,
        actividad   TEXT DEFAULT '',
        regimen     TEXT DEFAULT 'Simplificado',
        activa      INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS users (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        email        TEXT UNIQUE NOT NULL,
        nombre       TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        activo       INTEGER DEFAULT 1,
        created_at   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS user_company_roles (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        role        TEXT NOT NULL,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(user_id, company_id)
    );

    CREATE TABLE IF NOT EXISTS uploaded_files (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id   INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        user_id      INTEGER NOT NULL REFERENCES users(id),
        report_type  TEXT NOT NULL,
        filename     TEXT NOT NULL,
        filepath     TEXT NOT NULL,
        periodo      TEXT DEFAULT '',
        rows         INTEGER DEFAULT 0,
        uploaded_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS activity_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER REFERENCES users(id),
        company_id  INTEGER REFERENCES companies(id),
        action      TEXT NOT NULL,
        detail      TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS user_permissions (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        module      TEXT NOT NULL,
        allowed     INTEGER DEFAULT 1,
        UNIQUE(user_id, company_id, module)
    );

    CREATE TABLE IF NOT EXISTS bank_reports (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id  INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        filename    TEXT NOT NULL,
        data_blob   BLOB NOT NULL,
        created_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(company_id, filename)
    );
    """)
    conn.commit()

    # Seed demo data only if empty
    if c.execute("SELECT COUNT(*) FROM companies").fetchone()[0] == 0:
        _seed_demo(conn)

    conn.close()


def _seed_demo(conn: sqlite3.Connection):
    """Insert demo companies and users."""
    import bcrypt

    c = conn.cursor()

    # Companies
    companies = [
        ("1070951754",  "FAMIFAR,A VARIEDADES",           "Comercio al por menor", "Simplificado"),
        ("900123456-1", "DISTRIBUCIONES ABC S.A.S",        "Distribución mayorista", "Ordinario"),
        ("800987654-2", "SERVICIOS CONTABLES XYZ LTDA",    "Servicios profesionales", "Ordinario"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO companies (nit, razon_social, actividad, regimen) VALUES (?,?,?,?)",
        companies
    )

    # Users (admin + contador)
    users = [
        ("admin@contadash.co",     "Administrador Sistema",  "Admin2026!"),
        ("contador@contadash.co",  "Contador Senior Demo",   "Contador2026!"),
        ("auditor@contadash.co",   "Auditor Demo",           "Auditor2026!"),
        ("viewer@contadash.co",    "Solo Lectura Demo",      "Viewer2026!"),
    ]
    user_ids = []
    for email, nombre, pwd in users:
        ph = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()).decode()
        c.execute(
            "INSERT OR IGNORE INTO users (email, nombre, password_hash) VALUES (?,?,?)",
            (email, nombre, ph)
        )
        uid = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
        user_ids.append(uid)

    conn.commit()

    # Assign roles: admin gets admin on all companies, rest get roles on company 1
    comp_ids = [r["id"] for r in c.execute("SELECT id FROM companies ORDER BY id").fetchall()]
    role_map = [
        (user_ids[0], comp_ids[0], "admin"),
        (user_ids[0], comp_ids[1], "admin"),
        (user_ids[0], comp_ids[2], "admin"),
        (user_ids[1], comp_ids[0], "contador_senior"),
        (user_ids[1], comp_ids[1], "contador"),
        (user_ids[2], comp_ids[0], "auditor"),
        (user_ids[3], comp_ids[0], "viewer"),
    ]
    c.executemany(
        "INSERT OR IGNORE INTO user_company_roles (user_id, company_id, role) VALUES (?,?,?)",
        role_map
    )
    conn.commit()


# ─── Company CRUD ──────────────────────────────────────────────────────────────
def get_companies(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.id, c.nit, c.razon_social, c.actividad, c.regimen, c.activa,
               ucr.role
        FROM companies c
        JOIN user_company_roles ucr ON ucr.company_id = c.id
        WHERE ucr.user_id = ? AND c.activa = 1
        ORDER BY c.id
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_companies() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM companies ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_company(nit: str, razon_social: str, actividad: str = "", regimen: str = "Simplificado") -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO companies (nit, razon_social, actividad, regimen) VALUES (?,?,?,?)",
        (nit, razon_social, actividad, regimen)
    )
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def update_company(company_id: int, nit: str, razon_social: str, actividad: str, regimen: str):
    conn = get_connection()
    conn.execute(
        "UPDATE companies SET nit=?, razon_social=?, actividad=?, regimen=? WHERE id=?",
        (nit, razon_social, actividad, regimen, company_id)
    )
    conn.commit()
    conn.close()


def toggle_company(company_id: int, activa: bool):
    conn = get_connection()
    conn.execute("UPDATE companies SET activa=? WHERE id=?", (int(activa), company_id))
    conn.commit()
    conn.close()


# ─── User CRUD ────────────────────────────────────────────────────────────────
def get_all_users() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, email, nombre, activo, created_at FROM users ORDER BY nombre"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_roles(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT c.razon_social, c.nit, ucr.role, ucr.company_id
        FROM user_company_roles ucr
        JOIN companies c ON c.id = ucr.company_id
        WHERE ucr.user_id = ?
    """, (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(email: str, nombre: str, password: str) -> int:
    import bcrypt
    ph = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO users (email, nombre, password_hash) VALUES (?,?,?)",
        (email, nombre, ph)
    )
    conn.commit()
    new_id = c.lastrowid
    conn.close()
    return new_id


def update_user_role(user_id: int, company_id: int, role: str):
    conn = get_connection()
    conn.execute("""
        INSERT INTO user_company_roles (user_id, company_id, role)
        VALUES (?,?,?)
        ON CONFLICT(user_id, company_id) DO UPDATE SET role=excluded.role
    """, (user_id, company_id, role))
    conn.commit()
    conn.close()


def remove_user_from_company(user_id: int, company_id: int):
    conn = get_connection()
    conn.execute(
        "DELETE FROM user_company_roles WHERE user_id=? AND company_id=?",
        (user_id, company_id)
    )
    conn.commit()
    conn.close()


def toggle_user(user_id: int, activo: bool):
    conn = get_connection()
    conn.execute("UPDATE users SET activo=? WHERE id=?", (int(activo), user_id))
    conn.commit()
    conn.close()


def reset_password(user_id: int, new_password: str):
    import bcrypt
    ph = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (ph, user_id))
    conn.commit()
    conn.close()


def update_user_profile(user_id: int, nombre: str, email: str):
    """Update user name and email."""
    conn = get_connection()
    conn.execute("UPDATE users SET nombre=?, email=? WHERE id=?", (nombre, email, user_id))
    conn.commit()
    conn.close()


# ─── User Permissions (checklist) ────────────────────────────────────────────────
def get_user_permissions(user_id: int, company_id: int) -> dict:
    """Get per-user permission overrides for a company. Returns {module: bool}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT module, allowed FROM user_permissions WHERE user_id=? AND company_id=?",
        (user_id, company_id)
    ).fetchall()
    conn.close()
    return {r["module"]: bool(r["allowed"]) for r in rows}


def set_user_permissions(user_id: int, company_id: int, permissions: dict):
    """Set per-user permissions. permissions = {module: True/False}."""
    conn = get_connection()
    for module, allowed in permissions.items():
        conn.execute("""
            INSERT INTO user_permissions (user_id, company_id, module, allowed)
            VALUES (?,?,?,?)
            ON CONFLICT(user_id, company_id, module) DO UPDATE SET allowed=excluded.allowed
        """, (user_id, company_id, module, int(allowed)))
    conn.commit()
    conn.close()


def has_custom_permissions(user_id: int, company_id: int) -> bool:
    """Check if user has any custom per-module permissions set."""
    conn = get_connection()
    count = conn.execute(
        "SELECT COUNT(*) FROM user_permissions WHERE user_id=? AND company_id=?",
        (user_id, company_id)
    ).fetchone()[0]
    conn.close()
    return count > 0


# ─── Uploaded files ───────────────────────────────────────────────────────────
def save_upload_meta(company_id: int, user_id: int, report_type: str,
                     filename: str, filepath: str, periodo: str = "", rows: int = 0):
    conn = get_connection()
    conn.execute("""
        INSERT INTO uploaded_files (company_id, user_id, report_type, filename, filepath, periodo, rows)
        VALUES (?,?,?,?,?,?,?)
    """, (company_id, user_id, report_type, filename, filepath, periodo, rows))
    conn.commit()
    conn.close()


def get_uploads(company_id: int, report_type: str = None) -> list[dict]:
    conn = get_connection()
    if report_type:
        rows = conn.execute("""
            SELECT uf.*, u.nombre as uploaded_by
            FROM uploaded_files uf
            JOIN users u ON u.id = uf.user_id
            WHERE uf.company_id=? AND uf.report_type=?
            ORDER BY uf.uploaded_at DESC
        """, (company_id, report_type)).fetchall()
    else:
        rows = conn.execute("""
            SELECT uf.*, u.nombre as uploaded_by
            FROM uploaded_files uf
            JOIN users u ON u.id = uf.user_id
            WHERE uf.company_id=?
            ORDER BY uf.uploaded_at DESC
        """, (company_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_upload(company_id: int, report_type: str) -> dict | None:
    uploads = get_uploads(company_id, report_type)
    return uploads[0] if uploads else None


# ─── Activity log ─────────────────────────────────────────────────────────────
def log_action(user_id: int, company_id: int, action: str, detail: str = ""):
    conn = get_connection()
    conn.execute(
        "INSERT INTO activity_log (user_id, company_id, action, detail) VALUES (?,?,?,?)",
        (user_id, company_id, action, detail)
    )
    conn.commit()
    conn.close()


def get_recent_activity(company_id: int = None, limit: int = 50) -> list[dict]:
    conn = get_connection()
    if company_id:
        rows = conn.execute("""
            SELECT al.*, u.nombre, u.email
            FROM activity_log al
            LEFT JOIN users u ON u.id = al.user_id
            WHERE al.company_id = ?
            ORDER BY al.created_at DESC LIMIT ?
        """, (company_id, limit)).fetchall()
    else:
        rows = conn.execute("""
            SELECT al.*, u.nombre, u.email, c.razon_social
            FROM activity_log al
            LEFT JOIN users u ON u.id = al.user_id
            LEFT JOIN companies c ON c.id = al.company_id
            ORDER BY al.created_at DESC LIMIT ?
        """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Permission check ─────────────────────────────────────────────────────────
def can_access(role: str, module: str, user_id: int = None, company_id: int = None) -> bool:
    """Check if a role can access a module. Per-user overrides take priority."""
    if not role:
        return False
    # Check per-user permission overrides first
    if user_id and company_id:
        perms = get_user_permissions(user_id, company_id)
        if module in perms:
            return perms[module]
    # Fall back to role-based defaults
    role_index = ROLES.index(role) if role in ROLES else 99
    required = PERMISSIONS.get(module, 99)
    # Auditor gets read-only on select modules
    if role == "auditor" and module in AUDITOR_READ_ONLY:
        return True
    return role_index <= required


# ─── Upload path helpers ──────────────────────────────────────────────────────
def get_upload_dir(nit: str, report_type: str) -> Path:
    d = UPLOADS_PATH / nit / report_type
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_uploaded_file(nit: str, report_type: str, filename: str, data: bytes) -> str:
    """Save uploaded file bytes to disk. Returns full path string."""
    d = get_upload_dir(nit, report_type)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = f"{ts}_{filename}"
    path = d / safe_name
    path.write_bytes(data)
    return str(path)
