"""
Conciliador DIAN y Bancario — Authentication & RBAC.
Uses bcrypt for password hashing, Streamlit session_state for sessions.
Desarrollado por ANDRES FELIPE RAMIREZ GONZALES.
"""
import streamlit as st
import bcrypt
import base64
import os
from database import (
    get_connection, get_companies, can_access,
    ROLE_LABELS, log_action,
)

# ─── App Branding ─────────────────────────────────────────────────────────────
APP_NAME = "Conciliador DIAN y Bancario"
APP_SUBTITLE = "Sistema de Auditoría y Conciliación Tributaria"
APP_AUTHOR = "ANDRES FELIPE RAMIREZ GONZALES"

def _get_logo_b64():
    """Load logo as base64 from file if present."""
    logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.path.dirname(__file__), "logo.jpg")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    return None


# ─── Login / Logout ───────────────────────────────────────────────────────────
def authenticate(email: str, password: str) -> dict | None:
    """Return user dict on success, None on failure."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM users WHERE email=? AND activo=1", (email.strip(),)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    user = dict(row)
    try:
        ok = bcrypt.checkpw(password.encode(), user["password_hash"].encode())
    except Exception:
        ok = False
    if not ok:
        return None
    return user


def login(email: str, password: str) -> bool:
    """Authenticate and set session state. Returns True on success."""
    user = authenticate(email, password)
    if user is None:
        return False
    st.session_state["authenticated"] = True
    st.session_state["user_id"]       = user["id"]
    st.session_state["user_email"]    = user["email"]
    st.session_state["user_nombre"]   = user["nombre"]
    # Load accessible companies
    companies = get_companies(user["id"])
    st.session_state["companies"]     = companies
    # Default to first company
    if companies:
        _set_company(companies[0])
    return True


def logout():
    for key in ["authenticated", "user_id", "user_email", "user_nombre",
                "companies", "current_company", "current_role"]:
        st.session_state.pop(key, None)


def require_auth():
    """Stop rendering if not authenticated."""
    if not st.session_state.get("authenticated"):
        _render_login()
        st.stop()


def _render_login():
    """Render login page."""
    logo_b64 = _get_logo_b64()
    logo_html = ""
    if logo_b64:
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:160px;height:160px;object-fit:contain;border-radius:20px;margin-bottom:24px;box-shadow:0 4px 24px rgba(0,0,0,0.3);" />'
    else:
        logo_html = '<div style="font-size:5rem;margin-bottom:16px;">📊</div>'

    st.markdown("""
    <style>
    /* Remove top padding for a cleaner look */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 2rem !important;
    }
    /* Style the form to look modern */
    [data-testid="stForm"] {
        background: #152238;
        border: 1px solid #2A3F5F;
        border-radius: 12px;
        padding: 30px 20px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1.1, 1], gap="large")

    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #1a8bd1 0%, #0a4f8a 50%, #062d5a 100%);
                    padding: 40px; border-radius: 16px; text-align: center; height: 100%; min-height: 70vh;
                    display: flex; flex-direction: column; justify-content: center; align-items: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
            {logo_html}
            <h1 style="color:white; font-size: 2.2rem; margin-bottom: 12px; font-weight:800; text-shadow: 0 2px 8px rgba(0,0,0,0.3);">{APP_NAME}</h1>
            <p style="color:rgba(255,255,255,0.85); font-size:1.05rem; max-width: 360px; margin: 0 auto; line-height:1.5;">{APP_SUBTITLE}</p>
            <div style="margin-top: 60px; padding-top: 20px; color:rgba(255,255,255,0.6); font-size:0.8rem; border-top: 1px solid rgba(255,255,255,0.1);">
                <b>DESARROLLADO POR {APP_AUTHOR}</b><br>Software de gestión contable
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown('<div style="display:flex; flex-direction:column; justify-content:center; height:100%; min-height:70vh; padding: 20px 10px;">'
                    '<h2 style="color:white;text-align:center;margin-bottom:8px;font-size:1.8rem;">Bienvenido</h2>'
                    '<p style="color:#7A90AB;text-align:center;margin-bottom:32px;font-size:0.95rem;">Inicia sesión en tu cuenta para continuar</p>', 
                    unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            email    = st.text_input("Correo electrónico", placeholder="usuario@ejemplo.co")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("INICIAR SESIÓN", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("Ingresa correo y contraseña.")
            elif login(email, password):
                st.success(f"Bienvenido, {st.session_state['user_nombre']}!")
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos.")

        st.markdown("""
        <div style="text-align:center;margin-top:24px;font-size:.8rem;color:#4A6080; background:rgba(255,255,255,0.03); padding:12px; border-radius:8px;">
          <b style="color:#7A90AB;">Accesos de Demo:</b><br>
          <span style="color:#9DC3E6">admin@contadash.co</span> / Admin2026!<br>
          <span style="color:#9DC3E6">contador@contadash.co</span> / Contador2026!
        </div>
        </div>
        """, unsafe_allow_html=True)


# ─── Company switching ────────────────────────────────────────────────────────
def _set_company(company: dict):
    st.session_state["current_company"] = company
    st.session_state["current_role"]    = company.get("role", "viewer")


def set_active_company(company_id: int):
    companies = st.session_state.get("companies", [])
    for c in companies:
        if c["id"] == company_id:
            _set_company(c)
            return


def get_current_company() -> dict:
    return st.session_state.get("current_company", {})


def get_current_role() -> str:
    return st.session_state.get("current_role", "viewer")


def get_current_user_id() -> int:
    return st.session_state.get("user_id", 0)


def allowed(module: str) -> bool:
    """Check if the current user's role allows access to a module."""
    user_id = get_current_user_id()
    company = get_current_company()
    company_id = company.get("id") if company else None
    return can_access(get_current_role(), module, user_id, company_id)


def require_permission(module: str):
    """Stop rendering if user lacks permission for module."""
    if not allowed(module):
        st.warning(f"No tienes permiso para acceder a este módulo ({module}).")
        st.stop()


def role_badge(role: str) -> str:
    colors = {
        "admin":           ("#C00000", "#FCE4D6"),
        "contador_senior": ("#2E75B6", "#DBEAFE"),
        "contador":        ("#70AD47", "#DCFCE7"),
        "auditor":         ("#ED7D31", "#FFF0E0"),
        "viewer":          ("#6A7D90", "#F3F3F3"),
    }
    c, bg = colors.get(role, ("#888", "#EEE"))
    label = ROLE_LABELS.get(role, role)
    return f'<span style="background:{bg};color:{c};padding:2px 10px;border-radius:10px;font-size:.75rem;font-weight:700">{label}</span>'


# ─── Sidebar company selector ─────────────────────────────────────────────────
def render_company_selector():
    """Render company dropdown in sidebar. Call inside `with st.sidebar:`."""
    companies = st.session_state.get("companies", [])
    if not companies:
        st.sidebar.warning("Sin empresas asignadas.")
        return

    options   = {c["id"]: f"{c['razon_social']} ({c['nit']})" for c in companies}
    current   = get_current_company()
    current_id = current.get("id", list(options.keys())[0])

    selected_id = st.selectbox(
        "Empresa activa",
        options=list(options.keys()),
        format_func=lambda x: options[x],
        index=list(options.keys()).index(current_id) if current_id in options else 0,
        key="company_selector",
    )

    if selected_id != current_id:
        set_active_company(selected_id)
        st.rerun()

    company = get_current_company()
    role    = get_current_role()
    st.markdown(
        f'<div style="margin-top:4px">{role_badge(role)}</div>',
        unsafe_allow_html=True,
    )
    return company
