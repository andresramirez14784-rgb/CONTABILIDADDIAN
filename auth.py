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
    """Render full viewport split-screen login page."""
    logo_b64 = _get_logo_b64()
    logo_html = ""
    if logo_b64:
        # Hacer logo circular estilo CELUMANIA
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:170px;height:170px;object-fit:contain;border-radius:50%;margin-bottom:20px;box-shadow:0 8px 30px rgba(0,0,0,0.15); background:white; padding:15px;" />'
    else:
        logo_html = '<div style="font-size:5rem;margin-bottom:16px;">📊</div>'

    st.markdown("""
    <style>
    /* 1. Fondo global pantalla dividida exacta 50/50 */
    .stApp {
        background: linear-gradient(90deg, 
            #58A0D6 0%,  /* Azul claro (izquierdo) simulando la imagen */
            #2C74B3 50%, /* Gradiente suave en el azul */
            #E2E8F0 50%, /* Blanco/Gris claro (derecho) */
            #E2E8F0 100%
        ) !important;
    }
    
    /* 2. Ocultar menús y header nav */
    header[data-testid="stHeader"], [data-testid="collapsedControl"], [data-testid="stSidebar"] {
        display: none !important;
    }
    
    /* 3. Limpiar paddings nativos y centrar altura completa */
    .block-container {
        padding: 0 !important;
        max-width: 100% !important;
        height: 100vh;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    
    /* 4. Alinear columnas de streamlit verticalmente al centro */
    [data-testid="stHorizontalBlock"] {
        align-items: center;
        margin: 0;
        padding: 0;
        width: 100%;
        max-width: 1200px;
        margin-left: auto;
        margin-right: auto;
    }
    
    /* 5. Título y panel izquierdo (Texto) */
    .login-left-content {
        color: white;
        text-align: center;
        padding: 2rem;
    }
    .login-left-content h1 {
        font-size: 2.8rem;
        font-weight: 800;
        margin-top: 10px;
        margin-bottom: 5px;
        text-transform: uppercase;
        letter-spacing: 1px;
        text-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .login-left-content p {
        font-size: 1rem;
        font-weight: 500;
        color: rgba(255,255,255,0.9);
    }
    .login-left-content .author {
        margin-top: 50px;
        font-size: 0.75rem;
        color: rgba(255,255,255,0.7);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* 6. Tarjeta Formulario Derecha (Blanca flotante estilo CELUMANIA) */
    [data-testid="stForm"] {
        background: #FFFFFF !important;
        border-radius: 20px !important;
        padding: 40px 30px 30px !important;
        box-shadow: 0 15px 40px rgba(0,0,0,0.06) !important;
        border: none !important;
        width: 100%;
        max-width: 380px;
        margin: 0 auto;
    }
    [data-testid="stForm"] p, [data-testid="stForm"] label, [data-testid="stForm"] div {
        color: #4A5568 !important;
    }
    [data-testid="stForm"] input {
        background: #F7FAFC !important;
        border: 1px solid #CBD5E0 !important;
        color: #2D3748 !important;
        border-radius: 8px !important;
        padding: 12px 16px !important;
        font-size: 0.95rem !important;
    }
    [data-testid="stFormSubmitButton"] button {
        background: #3498DB !important; /* Azul botón Celumania */
        color: white !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        padding: 0.6rem 1rem !important;
        border: none !important;
        width: 100% !important;
        text-transform: uppercase;
        font-size: 0.9rem !important;
        letter-spacing: 0.5px;
        margin-top: 10px;
    }
    [data-testid="stFormSubmitButton"] button:hover {
        background: #2980B9 !important;
        box-shadow: 0 4px 12px rgba(52,152,219,0.3) !important;
    }
    
    .login-right-header {
        text-align: center;
        margin-bottom: 24px;
    }
    .login-right-header h2 {
        color: #2D3748;
        font-size: 1.8rem;
        font-weight: 800;
        margin-bottom: 4px;
    }
    .login-right-header p {
        color: #718096;
        font-size: 0.9rem;
    }

    /* 7. Responsivo para celulares (Apilar) */
    @media (max-width: 768px) {
        .stApp {
            background: #E2E8F0 !important; /* Fondo gris completo */
        }
        [data-testid="stHorizontalBlock"] {
            flex-direction: column;
            gap: 20px;
            padding: 20px !important;
        }
        .block-container {
            height: auto;
            justify-content: flex-start;
        }
        .login-left-content {
            background: linear-gradient(135deg, #58A0D6 0%, #2C74B3 100%);
            border-radius: 20px;
            margin-bottom: 10px;
            padding: 40px 20px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
        }
        [data-testid="stForm"] {
            padding: 30px 20px 20px !important;
        }
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown(f"""
        <div class="login-left-content">
            {logo_html}
            <h1>{APP_NAME}</h1>
            <p>{APP_SUBTITLE}</p>
            <div class="author">
                <b>DESARROLLADO POR {APP_AUTHOR}</b><br>Software de gestión contable
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        # El st.form abarca también el encabezado para mantenerlo todo dentro de la tarjeta blanca
        with st.form("login_form", clear_on_submit=False):
            st.markdown("""
            <div class="login-right-header">
                <h2>Bienvenido</h2>
                <p>Inicia sesión en tu cuenta para continuar</p>
            </div>
            """, unsafe_allow_html=True)
            
            email    = st.text_input("Usuario / Correo", placeholder="usuario@ejemplo.co")
            password = st.text_input("Contraseña", type="password", placeholder="••••••••")
            st.markdown("<div style='text-align:right; font-size:0.75rem; color:#A0AEC0; margin-bottom:10px;'>¿Olvidaste tu contraseña?</div>", unsafe_allow_html=True)
            submitted = st.form_submit_button("INICIAR SESIÓN", use_container_width=True)

        if submitted:
            if not email or not password:
                st.error("Ingresa correo y contraseña.")
            elif login(email, password):
                st.success(f"Bienvenido, {st.session_state['user_nombre']}!")
                st.rerun()
            else:
                st.error("Correo o contraseña incorrectos.")

        st.markdown("""
        <div style="text-align:center;margin-top:20px;font-size:0.8rem;color:#718096;">
          <b style="color:#4A5568;">Accesos de Demo:</b><br>
          <span style="color:#3498DB">admin@contadash.co</span> / Admin2026!<br>
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
