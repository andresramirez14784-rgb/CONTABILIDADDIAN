"""
ContaDash — Authentication & RBAC.
Uses bcrypt for password hashing, Streamlit session_state for sessions.
"""
import streamlit as st
import bcrypt
from database import (
    get_connection, get_companies, can_access,
    ROLE_LABELS, log_action,
)


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
    """Render the login page inline."""
    st.markdown("""
    <style>
    .login-box {
        max-width: 420px; margin: 80px auto 0 auto;
        background: #152238; border: 1px solid #2A3F5F;
        border-radius: 16px; padding: 40px 36px;
        box-shadow: 0 8px 40px rgba(0,0,0,0.5);
    }
    </style>
    """, unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown("""
        <div class="login-box">
          <div style="text-align:center;margin-bottom:28px">
            <div style="font-size:3rem">📊</div>
            <div style="font-size:1.5rem;font-weight:700;color:white;letter-spacing:1px">ContaDash</div>
            <div style="color:#7A90AB;font-size:.85rem">Plataforma de Auditoría Tributaria</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            email    = st.text_input("Correo electrónico", placeholder="usuario@ejemplo.co")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Iniciar Sesión", use_container_width=True, type="primary")

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
