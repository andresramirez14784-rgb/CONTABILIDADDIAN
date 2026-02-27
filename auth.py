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
    """Render split-screen login page with logo panel and form panel."""
    logo_b64 = _get_logo_b64()
    logo_html = ""
    if logo_b64:
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:180px;height:180px;object-fit:contain;border-radius:20px;margin-bottom:24px;box-shadow:0 4px 24px rgba(0,0,0,0.3);" />'
    else:
        logo_html = '<div style="font-size:5rem;margin-bottom:16px;">📊</div>'

    st.markdown(f"""
    <style>
    .login-split {{
        display: flex;
        min-height: 92vh;
        margin: -1rem -1rem 0 -1rem;
        border-radius: 0;
    }}
    .login-left {{
        flex: 1;
        background: linear-gradient(135deg, #1a8bd1 0%, #0a4f8a 40%, #062d5a 100%);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 40px;
        position: relative;
    }}
    .login-left h1 {{
        color: white;
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: 1px;
        margin: 0 0 8px 0;
        text-align: center;
        text-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }}
    .login-left .subtitle {{
        color: rgba(255,255,255,0.8);
        font-size: 0.95rem;
        text-align: center;
        max-width: 320px;
        line-height: 1.5;
    }}
    .login-left .author {{
        position: absolute;
        bottom: 30px;
        color: rgba(255,255,255,0.6);
        font-size: 0.75rem;
        text-align: center;
        letter-spacing: 0.5px;
    }}
    .login-left .author b {{
        color: rgba(255,255,255,0.85);
    }}
    .login-right {{
        flex: 1;
        background: #0F1C33;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 40px;
    }}
    .login-right-inner {{
        max-width: 400px;
        width: 100%;
    }}
    .login-right-inner h2 {{
        color: white;
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0 0 6px 0;
        text-align: center;
    }}
    .login-right-inner .hint {{
        color: #7A90AB;
        font-size: 0.85rem;
        text-align: center;
        margin-bottom: 28px;
    }}
    @media(max-width:768px) {{
        .login-split {{ flex-direction: column; }}
        .login-left {{ min-height: 30vh; padding: 24px; }}
        .login-left h1 {{ font-size: 1.4rem; }}
        .login-right {{ padding: 24px; }}
    }}
    </style>
    <div class="login-split">
      <div class="login-left">
        {logo_html}
        <h1>{APP_NAME}</h1>
        <div class="subtitle">{APP_SUBTITLE}</div>
        <div class="author"><b>DESARROLLADO POR {APP_AUTHOR}</b><br>Software de gestión contable</div>
      </div>
      <div class="login-right">
        <div class="login-right-inner">
          <h2>Bienvenido</h2>
          <div class="hint">Inicia sesión en tu cuenta para continuar</div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1.2, 2, 1.2])
    with col_c:
        with st.form("login_form", clear_on_submit=False):
            email    = st.text_input("Correo electrónico", placeholder="usuario@ejemplo.co")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
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
        <div style="text-align:center;margin-top:20px;font-size:.78rem;color:#4A6080">
          <b>Demo:</b> admin@contadash.co / Admin2026!<br>
          Contador: contador@contadash.co / Contador2026!
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


# ─── Permission helpers ───────────────────────────────────────────────────────
def allowed(module: str) -> bool:
    """Check if the current user's role allows access to a module."""
    return can_access(get_current_role(), module)


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
