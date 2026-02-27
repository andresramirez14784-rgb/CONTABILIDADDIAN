"""
ContaDash v2 — Ecosistema de Auditoría Tributaria
Multi-empresa | Usuarios y Roles | DIAN FE + Nómina + Exógena + Retenciones
Compatible: SIIGO, Helisa, ContaSOL, WinContab, Portal DIAN
"""
import streamlit as st
import pandas as pd
import os, sys, re
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))

from database import (init_db, get_all_companies, get_all_users, create_company, create_user,
                      update_company, toggle_company, update_user_role, toggle_user,
                      reset_password, get_user_roles, remove_user_from_company,
                      save_uploaded_file, save_upload_meta, get_uploads, get_latest_upload,
                      get_recent_activity, log_action, ROLE_LABELS, ROLES, can_access)
from auth import (require_auth, render_company_selector, get_current_company,
                  get_current_role, get_current_user_id, allowed, role_badge, logout)
from data_loader import (load_file, compute_kpis, detect_hallazgos,
                         build_iva_conciliation,
                         load_nomina, compute_nomina_kpis, detect_hallazgos_extended,
                         load_exogena, load_retenciones,
                         build_client_summary, build_supplier_summary,
                         build_entity_monthly_pivot)
from bank_analyzer import parse_bank_statement, parse_bank_statement_excel, build_bank_fiscal_report
from charts import (
    chart_ventas_vs_compras, chart_iva_waterfall, chart_top_clientes,
    chart_top_proveedores, chart_ventas_tiempo, chart_compras_tiempo,
    chart_tipo_documentos, chart_iva_bimestral, chart_riesgo_gauge,
    chart_scatter_proveedores,
    chart_nomina_mensual, chart_top_empleados, chart_nomina_composicion,
    chart_exogena_cruce, chart_retenciones_tipos,
)
from reports import generate_excel, generate_word

init_db()

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="ContaDash v2 | Auditoría DIAN",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
:root {
  --primary:#1F3864;--secondary:#2E75B6;--accent:#ED7D31;
  --success:#70AD47;--danger:#C00000;--warning:#FFD700;
  --bg-dark:#0F1C33;--bg-card:#152238;--bg-card2:#1A2B4A;
  --text:#E8EFF8;--text-muted:#7A90AB;--border:#2A3F5F;
}
.stApp{background:var(--bg-dark)!important;}
.stSidebar{background:var(--primary)!important;}
.stSidebar .stMarkdown,.stSidebar label,.stSidebar p{color:#D0DCEC!important;}
#MainMenu,footer,.stDeployButton{display:none!important;}
header[data-testid="stHeader"]{background:rgba(15,28,51,0.95)!important;}

/* ── KPI CARDS — diseño profesional ── */
.kpi-card {
  background: linear-gradient(145deg, var(--bg-card) 0%, var(--bg-card2) 100%);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 20px 16px 16px;
  text-align: center;
  margin-bottom: 10px;
  box-shadow: 0 4px 24px rgba(0,0,0,.35);
  position: relative;
  overflow: hidden;
  transition: transform .15s ease, box-shadow .15s ease;
}
.kpi-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 32px rgba(0,0,0,.5);
}
.kpi-accent-bar {
  position: absolute; top: 0; left: 0; right: 0;
  height: 3px; border-radius: 14px 14px 0 0;
}
.kpi-icon {
  font-size: 2.2rem;
  line-height: 1;
  margin-bottom: 10px;
  display: block;
  filter: drop-shadow(0 2px 6px rgba(0,0,0,.4));
}
.kpi-value {
  font-size: 1.4rem;
  font-weight: 800;
  color: #FFF;
  font-family: 'Arial Black', 'Arial', sans-serif;
  letter-spacing: -0.5px;
  line-height: 1.2;
  word-break: break-word;
}
.kpi-label {
  font-size: .68rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1.3px;
  margin-top: 7px;
  font-weight: 600;
}
.kpi-subtitle {
  font-size: .67rem;
  color: #5A7090;
  margin-top: 4px;
  line-height: 1.3;
}

/* ── SECTION HEADER ── */
.section-header {
  background: linear-gradient(90deg, var(--primary) 0%, var(--secondary) 60%, #1A3A6A 100%);
  color: white;
  padding: 9px 18px;
  border-radius: 8px;
  font-size: .9rem;
  font-weight: 700;
  margin: 16px 0 10px 0;
  border-left: 4px solid var(--accent);
  letter-spacing: .3px;
}

/* ── TABS — scroll horizontal si hay muchas ── */
.stTabs [data-baseweb="tab-list"] {
  background: var(--bg-card2);
  border-radius: 10px;
  padding: 4px;
  overflow-x: auto;
  flex-wrap: nowrap !important;
  scrollbar-width: thin;
}
.stTabs [data-baseweb="tab"] {
  color: var(--text-muted);
  border-radius: 7px;
  font-weight: 600;
  font-size: .82rem;
  white-space: nowrap;
  padding: 6px 12px !important;
}
.stTabs [aria-selected="true"] {
  background: var(--secondary) !important;
  color: white !important;
}

/* ── SCROLLBAR ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--bg-dark); }
::-webkit-scrollbar-thumb { background: var(--secondary); border-radius: 3px; }

/* ── ACCOUNT CARD (extractos) ── */
.account-card {
  background: linear-gradient(135deg, #162640 0%, #1E3550 100%);
  border: 1px solid #2A4A70;
  border-radius: 12px;
  padding: 16px 20px;
  margin-bottom: 8px;
}
.account-card-title { font-size: 1rem; font-weight: 700; color: #9DC3E6; }
.account-card-sub   { font-size: .78rem; color: #6A8AAB; margin-top: 3px; }

@media(max-width:768px) {
  .kpi-value { font-size: 1rem; }
  .kpi-icon  { font-size: 1.6rem; }
  .kpi-card  { padding: 12px 8px; }
}
</style>
""", unsafe_allow_html=True)

# ─── Auth gate ────────────────────────────────────────────────────────────────
require_auth()

uid     = get_current_user_id()
company = get_current_company()
role    = get_current_role()


# ─── Helpers ──────────────────────────────────────────────────────────────────
def fmt_cop(v, dec=0):
    try: return f"${float(v):,.{dec}f}"
    except: return str(v)

def kpi_card(icon, label, value, color="#70AD47", subtitle="", drill_key=None, drill_label="📋 Ver detalle"):
    """Tarjeta KPI profesional con barra de color, ícono grande y subtítulo."""
    sub_html = f'<div class="kpi-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(f"""<div class="kpi-card">
      <div class="kpi-accent-bar" style="background:{color}"></div>
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-value" style="color:{color}">{value}</div>
      <div class="kpi-label">{label}</div>{sub_html}
    </div>""", unsafe_allow_html=True)
    if drill_key:
        if st.button(drill_label, key=f"kpibtn_{drill_key}", use_container_width=True,
                     help=f"Ver detalle de {label}"):
            st.session_state[f"kpi_drill_{drill_key}"] = not st.session_state.get(f"kpi_drill_{drill_key}", False)
            st.rerun()

def section_header(txt):
    st.markdown(f'<div class="section-header">{txt}</div>', unsafe_allow_html=True)


# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center;padding:10px 0 18px 0">
      <div style="font-size:2.2rem">📊</div>
      <div style="font-size:1.2rem;font-weight:700;color:white;letter-spacing:1px">ContaDash v2</div>
      <div style="font-size:.72rem;color:#9DC3E6">Auditoría Tributaria DIAN</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<div style="color:#9DC3E6;font-size:.78rem;font-weight:700;letter-spacing:1px">🏢 EMPRESA ACTIVA</div>',
                unsafe_allow_html=True)
    render_company_selector()
    st.markdown("---")
    st.markdown('<div style="color:#9DC3E6;font-size:.78rem;font-weight:700;letter-spacing:1px">📅 PERÍODO</div>',
                unsafe_allow_html=True)
    periodo = st.text_input("Período", "Enero - Febrero 2026", key="periodo_input", label_visibility="collapsed")
    st.markdown("---")
    nombre = st.session_state.get("user_nombre", "")
    email_s = st.session_state.get("user_email", "")
    st.markdown(f"""<div style="background:rgba(46,117,182,.15);border-radius:8px;padding:10px;font-size:.76rem;color:#9DC3E6">
      <b style="color:white">{nombre}</b><br>{email_s}
    </div>""", unsafe_allow_html=True)
    st.markdown(f'<div style="margin-top:6px">{role_badge(role)}</div>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("""<div style="background:rgba(46,117,182,.15);border-radius:8px;padding:8px;font-size:.7rem;color:#9DC3E6">
    <b>Reportes DIAN compatibles:</b><br>
    Facturas Electrónicas · Nómina Electrónica<br>Información Exógena · Retenciones
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    if st.button("Cerrar Sesión", use_container_width=True):
        logout()
        st.rerun()
    st.markdown('<div style="color:#4A6080;font-size:.68rem;text-align:center">v2.0 · Al Día Contador 2026</div>',
                unsafe_allow_html=True)


# ─── Company context ──────────────────────────────────────────────────────────
company = get_current_company()
empresa = company.get("razon_social","Sin empresa") if company else "Sin empresa"
nit     = company.get("nit","—") if company else "—"
cid     = company.get("id",0) if company else 0


# ─── Data loading ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_all_merged(company_id: int, report_type: str) -> pd.DataFrame:
    """Carga y concatena TODOS los archivos del historial para empresa+tipo.
    Deduplica por CUFE/CUDE (ventas/compras) o por NIT+Período (nómina).
    Así los reportes se auto-alimentan al subir más meses sin repetir datos.
    """
    _loaders = {
        "ventas":      load_file,
        "compras":     load_file,
        "nomina":      load_nomina,
        "exogena":     load_exogena,
        "retenciones": load_retenciones,
    }
    uploads = get_uploads(company_id, report_type)
    if not uploads:
        return pd.DataFrame()
    frames = []
    for meta in reversed(uploads):      # más antiguo primero → concat cronológico
        p = Path(meta["filepath"])
        if not p.exists():
            continue
        try:
            df = _loaders.get(report_type, load_file)(str(p))
        except Exception:
            continue
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames, ignore_index=True)
    # Deduplicar: omitir facturas repetidas al subir el mismo mes dos veces
    if report_type in ("ventas", "compras") and "CUFE/CUDE" in merged.columns:
        merged = merged.drop_duplicates(subset=["CUFE/CUDE"], keep="first")
    elif report_type == "nomina" and "NIT Empleado" in merged.columns and "Periodo" in merged.columns:
        merged = merged.drop_duplicates(subset=["NIT Empleado", "Periodo"], keep="first")
    return merged


def _handle_upload(uploaded_file, report_type: str, label: str):
    if uploaded_file is None:
        return
    data  = uploaded_file.read()
    path  = save_uploaded_file(nit, report_type, uploaded_file.name, data)
    dftmp = load_file(path) if report_type in ("ventas","compras") else pd.DataFrame()
    rows  = len(dftmp)
    save_upload_meta(cid, uid, report_type, uploaded_file.name, path, periodo, rows)
    log_action(uid, cid, f"upload_{report_type}", f"{uploaded_file.name} ({rows} filas)")
    _load_all_merged.clear()
    _cached_analysis.clear()
    # Reset meses cache so new periods are detected
    st.session_state.pop("_meses_all_cache", None)
    st.session_state.pop("sel_meses_bar", None)
    st.success(f"✅ {label}: {uploaded_file.name} — {rows} registros")
    st.rerun()


def _import_from_dian(auth_url: str, fecha_desde, fecha_hasta, tipos_sel: list):
    """Importa facturas directamente desde el catálogo DIAN usando el link de token."""
    try:
        from dian_connector import authenticate_dian, download_invoices, diagnose_session
    except ImportError as e:
        st.error(f"❌ Módulo DIAN no disponible: {e}")
        return

    with st.spinner("🔐 Autenticando con la DIAN..."):
        session = authenticate_dian(auth_url)

    if session is None:
        st.error("❌ **Link DIAN inválido o expirado.**  \n"
                 "El link dura 60 minutos. Solicita uno nuevo desde el portal DIAN.")
        return

    st.success("✅ Sesión DIAN activa — descargando facturas...")

    _map = {"Ventas (facturas emitidas)": "ventas", "Compras (facturas recibidas)": "compras"}
    fmt_d = lambda d: d.strftime("%d/%m/%Y")
    any_ok = False

    for tipo_label in tipos_sel:
        rt = _map.get(tipo_label)
        if not rt:
            continue
        icon = "📄" if rt == "ventas" else "📦"
        with st.spinner(f"{icon} Descargando {tipo_label}..."):
            def _prog(msg):
                pass  # silencioso; podemos ampliar con st.write si se desea
            try:
                df = download_invoices(session, rt, fmt_d(fecha_desde), fmt_d(fecha_hasta), _prog)
            except PermissionError:
                st.error("❌ La sesión expiró durante la descarga. Obtén un nuevo link.")
                return
            except Exception as e:
                st.warning(f"⚠ Error descargando {tipo_label}: {e}")
                continue

        if df is None or df.empty:
            st.warning(f"⚠ No se encontraron facturas de {tipo_label} "
                       f"en el período {fmt_d(fecha_desde)} → {fmt_d(fecha_hasta)}")
            continue

        # Guardar igual que una subida manual → deduplicación automática por CUFE/CUDE
        import io as _io, tempfile as _tmp, os as _os
        fname = f"DIAN_{rt}_{fecha_desde}_{fecha_hasta}.xlsx"
        buf = _io.BytesIO()
        df.to_excel(buf, index=False)
        raw_bytes = buf.getvalue()
        path = save_uploaded_file(nit, rt, fname, raw_bytes)
        rows = len(df)
        save_upload_meta(cid, uid, rt, fname, path, str(fecha_desde), rows)
        log_action(uid, cid, f"dian_import_{rt}", f"{rows} facturas {fmt_d(fecha_desde)}→{fmt_d(fecha_hasta)}")
        st.success(f"✅ {tipo_label}: **{rows:,} facturas** importadas "
                   f"(repetidas omitidas automáticamente)")
        any_ok = True

    if any_ok:
        _load_all_merged.clear()
        _cached_analysis.clear()
        st.session_state.pop("_meses_all_cache", None)
        st.session_state.pop("sel_meses_bar", None)
        st.info("🔄 Actualizando dashboard con los nuevos datos...")
        st.rerun()
    else:
        # Diagnóstico: mostrar qué encontramos en el portal para ayudar a depurar
        with st.expander("🔍 Diagnóstico del portal DIAN"):
            try:
                from dian_connector import diagnose_session
                diag = diagnose_session(session)
                st.json(diag)
                st.caption("Comparte esta información si necesitas soporte técnico.")
            except Exception:
                pass


# Defaults for demo
DEFAULT_V = r"C:\Users\USUARIO\Downloads\reportes de dian contador\VENTAS ENERO - FEBRERO ANDRES.xlsx"
DEFAULT_C = r"C:\Users\USUARIO\Downloads\reportes de dian contador\COMPRAS ENERO - FEBRERO ANDRES.xlsx"


# ─── Análisis cacheado por empresa + períodos seleccionados ───────────────────
@st.cache_data(show_spinner=False)
def _cached_analysis(company_id: int, _nit: str, meses_tuple: tuple):
    """Cache KPIs + hallazgos + pivot IVA por empresa y selección de períodos.
    Solo recalcula cuando cambia empresa o meses; cambiar tabs = 0ms (cache hit).
    """
    v_raw = _load_all_merged(company_id, "ventas")
    c_raw = _load_all_merged(company_id, "compras")
    n_raw = _load_all_merged(company_id, "nomina")
    e_raw = _load_all_merged(company_id, "exogena")
    r_raw = _load_all_merged(company_id, "retenciones")

    # Demo fallback para empresa FAMIFAR (nit = 1070951754)
    if v_raw.empty and Path(DEFAULT_V).exists() and _nit == "1070951754":
        v_raw = load_file(DEFAULT_V)
    if c_raw.empty and Path(DEFAULT_C).exists() and _nit == "1070951754":
        c_raw = load_file(DEFAULT_C)

    # Calcular meses disponibles
    _mv = sorted(v_raw["Mes"].dropna().unique().tolist()) if "Mes" in v_raw.columns else []
    _mc = sorted(c_raw["Mes"].dropna().unique().tolist()) if "Mes" in c_raw.columns else []
    _mn = sorted(n_raw["Mes"].dropna().unique().tolist()) if "Mes" in n_raw.columns else []
    meses_all = sorted(set(_mv) | set(_mc) | set(_mn))

    # Aplicar filtro de períodos
    def _f(df):
        if not meses_tuple or df.empty or "Mes" not in df.columns:
            return df
        return df[df["Mes"].isin(meses_tuple)]

    v = _f(v_raw); c = _f(c_raw); n = _f(n_raw); e = _f(e_raw); r = _f(r_raw)

    kpis      = compute_kpis(v, c)
    kpis_nom  = compute_nomina_kpis(n) if not n.empty else {}
    h_base    = detect_hallazgos(v, c)
    h_ext     = detect_hallazgos_extended(
        v, c,
        nomina=n if not n.empty else None,
        exogena=e if not e.empty else None,
        retenciones=r if not r.empty else None,
    )
    hallazgos = h_base + h_ext
    iva_pivot = build_iva_conciliation(v, c)

    # Reportes globales clientes/proveedores (cacheados junto con el resto)
    client_summary   = build_client_summary(v)
    supplier_summary = build_supplier_summary(c)
    client_pivot     = build_entity_monthly_pivot(v, "Nombre Receptor")
    supplier_pivot   = build_entity_monthly_pivot(c, "Nombre Emisor")

    return {
        "ventas": v, "compras": c, "nomina": n, "exogena": e, "retenciones": r,
        "ventas_raw": v_raw, "compras_raw": c_raw,
        "nomina_raw": n_raw, "exogena_raw": e_raw, "retenciones_raw": r_raw,
        "kpis": kpis, "kpis_nom": kpis_nom,
        "hallazgos": hallazgos, "iva_pivot": iva_pivot,
        "meses_all": meses_all,
        "client_summary":   client_summary,
        "supplier_summary": supplier_summary,
        "client_pivot":     client_pivot,
        "supplier_pivot":   supplier_pivot,
    }


# ─── Leer selección previa de meses (widget se renderiza más adelante) ────────
_meses_all_prev = st.session_state.get("_meses_all_cache", [])
_prev_sel       = st.session_state.get("sel_meses_bar", _meses_all_prev)
_sel_tuple      = tuple(sorted(_prev_sel)) if _prev_sel else ()

# ─── Ejecutar análisis cacheado ───────────────────────────────────────────────
_an = _cached_analysis(cid, nit, _sel_tuple)

ventas_df_raw      = _an["ventas_raw"]
compras_df_raw     = _an["compras_raw"]
nomina_df_raw      = _an["nomina_raw"]
exogena_df_raw     = _an["exogena_raw"]
retenciones_df_raw = _an["retenciones_raw"]
ventas_df          = _an["ventas"]
compras_df         = _an["compras"]
nomina_df          = _an["nomina"]
exogena_df         = _an["exogena"]
retenciones_df     = _an["retenciones"]
kpis               = _an["kpis"]
kpis_nom           = _an["kpis_nom"]
hallazgos          = _an["hallazgos"]
iva_pivot          = _an["iva_pivot"]
_meses_all         = _an["meses_all"]
client_summary     = _an["client_summary"]
supplier_summary   = _an["supplier_summary"]
client_pivot       = _an["client_pivot"]
supplier_pivot     = _an["supplier_pivot"]

# sel_meses = intersección de selección previa con meses disponibles (o todos)
sel_meses = [m for m in _prev_sel if m in _meses_all] if _prev_sel else _meses_all
altos     = sum(1 for h in hallazgos if "ALTO" in h["nivel"] and "MEDIO" not in h["nivel"])
medios    = sum(1 for h in hallazgos if "MEDIO" in h["nivel"])

# Persistir meses disponibles para el siguiente rerun
st.session_state["_meses_all_cache"] = _meses_all


# ─── Header ───────────────────────────────────────────────────────────────────
c_logo, c_title, c_badge = st.columns([1,6,2])
with c_logo:
    st.markdown('<div style="font-size:3rem;text-align:center">📊</div>', unsafe_allow_html=True)
with c_title:
    _has_data = not (ventas_df_raw.empty and compras_df_raw.empty)
    _data_badge = (
        '<span style="background:#70AD47;color:white;font-size:.7rem;font-weight:700;'
        'padding:2px 10px;border-radius:20px;margin-left:8px">✓ CON DATOS</span>'
        if _has_data else
        '<span style="background:#C00000;color:white;font-size:.7rem;font-weight:700;'
        'padding:2px 10px;border-radius:20px;margin-left:8px">⚠ SIN DATOS</span>'
    )
    _periodo_hdr = ", ".join(sel_meses) if sel_meses else (", ".join(_meses_all) if _meses_all else periodo)
    _nper = len(_meses_all)
    _nper_txt = f" · {_nper} período{'s' if _nper!=1 else ''} disponible{'s' if _nper!=1 else ''}" if _nper > 1 else ""
    st.markdown(f"""
    <h1 style="margin:0;color:white;font-size:1.5rem;font-weight:700">{empresa} {_data_badge}</h1>
    <div style="color:#9DC3E6;font-size:.85rem">NIT: {nit} · {_periodo_hdr or periodo} · FE + Nómina + Exógena{_nper_txt}</div>
    """, unsafe_allow_html=True)
with c_badge:
    bc = "#C00000" if altos>0 else "#70AD47"
    st.markdown(f"""<div style="background:{bc};border-radius:10px;padding:10px 14px;text-align:center;margin-top:4px">
      <div style="color:white;font-size:1.4rem;font-weight:700">{len(hallazgos)}</div>
      <div style="color:rgba(255,255,255,.85);font-size:.72rem;text-transform:uppercase">Hallazgos</div>
    </div>""", unsafe_allow_html=True)
st.markdown("---")

# ─── Filtro de período (solo visible si hay más de 1 mes) ─────────────────────
if len(_meses_all) > 0:
    _pf1, _pf2 = st.columns([1, 7])
    with _pf1:
        st.markdown('<div style="padding-top:6px;color:#9DC3E6;font-size:.82rem;font-weight:700">📅 Período:</div>',
                    unsafe_allow_html=True)
    with _pf2:
        st.multiselect(
            "Filtrar períodos",
            options=_meses_all,
            default=sel_meses,
            key="sel_meses_bar",
            label_visibility="collapsed",
            placeholder="Seleccionar meses…"
        )
    if sel_meses and sel_meses != _meses_all:
        _tot_v = len(ventas_df); _tot_c = len(compras_df)
        st.caption(f"Mostrando {len(sel_meses)} de {len(_meses_all)} períodos · "
                   f"{_tot_v} facturas ventas · {_tot_c} facturas compras")


# ─── Dynamic tabs based on role ───────────────────────────────────────────────
tab_defs = [
    ("Dashboard",    "🏠 Dashboard"),
    ("ventas",       "📄 Ventas"),
    ("clientes",     "👤 Clientes"),
    ("compras",      "📦 Compras"),
    ("proveedores",  "🏪 Proveedores"),
    ("extractos",    "🏦 Extractos"),
    ("iva",          "💰 IVA"),
    ("nomina",       "👥 Nómina"),
    ("exogena",      "🔗 Exógena"),
    ("hallazgos",    "🔍 Hallazgos"),
    ("datos",        "📋 Datos"),
    ("exportar",     "📥 Exportar"),
    ("cargar",       "📂 Cargar Datos"),
]
if allowed("empresas"):
    tab_defs.append(("empresas", "🏢 Empresas"))
if allowed("usuarios"):
    tab_defs.append(("usuarios", "👤 Usuarios"))

vis_mods  = [m for m,_ in tab_defs if allowed(m)]
vis_labels = [l for m,l in tab_defs if allowed(m)]
tabs_ui   = st.tabs(vis_labels)

def get_tab(module: str):
    try: return tabs_ui[vis_mods.index(module)]
    except ValueError: return None


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("Dashboard")
if t:
  with t:
    section_header("📌 KPIs Consolidados")

    if ventas_df_raw.empty and compras_df_raw.empty:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,#1A2B4A,#152238);border:2px dashed #2E75B6;
          border-radius:16px;padding:40px 30px;text-align:center;margin:20px 0">
          <div style="font-size:3rem">📂</div>
          <h2 style="color:#9DC3E6;margin:12px 0 6px 0">{empresa}</h2>
          <p style="color:#7A90AB;font-size:1rem;margin:0 0 8px 0">
            Esta empresa aún no tiene archivos DIAN cargados.
          </p>
          <p style="color:#5A7090;font-size:.85rem;margin:0">
            Ve a la pestaña <b style="color:#2E75B6">📂 Cargar Datos</b> para subir los reportes DIAN.<br>
            Cada empresa maneja sus propios archivos de forma independiente.
          </p>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Resumen de períodos consolidados
        if _meses_all:
            _tots = f"{len(ventas_df_raw)} ventas · {len(compras_df_raw)} compras (total histórico)"
            _filt = f" · mostrando {len(sel_meses)}/{len(_meses_all)} períodos" if sel_meses != _meses_all else ""
            st.markdown(
                f'<div style="background:#1A2B4A;border-radius:8px;padding:8px 16px;'
                f'margin-bottom:12px;font-size:.8rem;color:#9DC3E6">'
                f'📅 <b>Datos consolidados:</b> {", ".join(_meses_all)} &nbsp;·&nbsp; {_tots}{_filt}</div>',
                unsafe_allow_html=True)

        # ── FILA 1: 4 KPIs principales ────────────────────────────────────────
        c1,c2,c3,c4 = st.columns(4)
        _ic_iva = "#C00000" if kpis["iva_neto"]>0 else "#70AD47"
        _il_iva = "IVA A PAGAR 🔴" if kpis["iva_neto"]>0 else "IVA A FAVOR ✅"
        with c1: kpi_card("💵","Total Ventas",
                           fmt_cop(kpis["total_ventas"]),"#70AD47",
                           subtitle=f"Base gravable: {fmt_cop(kpis['base_ventas'])}",
                           drill_key="d_ventas", drill_label="📄 Ver todos los clientes")
        with c2: kpi_card("🛒","Total Compras",
                           fmt_cop(kpis["total_compras"]),"#ED7D31",
                           subtitle=f"Base gravable: {fmt_cop(kpis['base_compras'])}",
                           drill_key="d_compras", drill_label="📦 Ver todos los proveedores")
        with c3: kpi_card("🏦","IVA Generado",
                           fmt_cop(kpis["iva_generado"]),"#2E75B6",
                           subtitle=f"Descontable: {fmt_cop(kpis['iva_descontable'])}")
        with c4: kpi_card("⚖️", _il_iva,
                           fmt_cop(abs(kpis["iva_neto"])), _ic_iva,
                           subtitle=f"Margen bruto: {kpis['margen_bruto']:.1f}%")

        # Drill-downs inline desde KPIs del dashboard
        if st.session_state.get("kpi_drill_d_ventas") and not client_summary.empty:
            _vis_cl = [c for c in client_summary.columns if c not in ["Resp_IVA","Ret_Renta","Ret_ICA","Gran_Contrib"]]
            with st.expander("📄 Clientes — Vista rápida (Top 30)", expanded=True):
                _fmt_cl = {c:"${:,.0f}" for c in ["Total","Base","IVA","Rete Renta"] if c in _vis_cl}
                st.dataframe(client_summary[_vis_cl].head(30).style.format(_fmt_cl),
                             use_container_width=True, height=300)
                st.caption(f"Top 30 de {len(client_summary)} clientes · Abre 👤 Clientes para el reporte completo e interactivo")

        if st.session_state.get("kpi_drill_d_compras") and not supplier_summary.empty:
            _vis_pv = [c for c in supplier_summary.columns if c not in ["Resp_IVA","Ret_Renta","Ret_ICA","Gran_Contrib"]]
            with st.expander("📦 Proveedores — Vista rápida (Top 30)", expanded=True):
                _fmt_pv = {c:"${:,.0f}" for c in ["Total","Base","IVA","Rete Renta"] if c in _vis_pv}
                st.dataframe(supplier_summary[_vis_pv].head(30).style.format(_fmt_pv),
                             use_container_width=True, height=300)
                st.caption(f"Top 30 de {len(supplier_summary)} proveedores · Abre 🏪 Proveedores para el reporte completo e interactivo")

        # ── FILA 2: 4 KPIs secundarios ────────────────────────────────────────
        c5,c6,c7,c8 = st.columns(4)
        _nom_sub = f"Nómina: {fmt_cop(kpis_nom.get('total_devengado',0))}" if kpis_nom.get('total_devengado',0) else "Sin datos nómina"
        _hall_sub = f"{altos} críticos · {medios} medios" if hallazgos else "Sin alertas activas"
        with c5: kpi_card("🧾","Facturas Ventas",
                           f"{kpis['num_facturas_ventas']:,}","#9DC3E6",
                           subtitle=f"Compras: {kpis['num_facturas_compras']:,} facturas")
        with c6: kpi_card("👥","Empleados",
                           str(kpis_nom.get("num_empleados","—")),"#9DC3E6",
                           subtitle=_nom_sub)
        with c7: kpi_card("🔍","Hallazgos",
                           str(len(hallazgos)),
                           "#C00000" if altos>0 else "#70AD47",
                           subtitle=_hall_sub)
        with c8: kpi_card("📅","Períodos Activos",
                           str(len(sel_meses)),"#ED7D31",
                           subtitle=" · ".join(sel_meses[-3:]) + (" ..." if len(sel_meses)>3 else "") if sel_meses else "—")

        # ── Gráficos — layout 2+2+2 uniforme ─────────────────────────────────
        ca, cb = st.columns(2)
        with ca: st.plotly_chart(chart_ventas_vs_compras(kpis), use_container_width=True, key="d1")
        with cb: st.plotly_chart(chart_iva_waterfall(kpis),     use_container_width=True, key="d2")

        cc, cd = st.columns(2)
        with cc: st.plotly_chart(chart_ventas_tiempo(ventas_df),  use_container_width=True, key="d3")
        with cd: st.plotly_chart(chart_compras_tiempo(compras_df), use_container_width=True, key="d4")

        cf, cg = st.columns(2)
        with cf:
            _sel_d6 = st.plotly_chart(
                chart_top_clientes(
                    client_summary.rename(columns={"Nombre Receptor":"Cliente"})[["Cliente","Total"]].head(15)
                    if not client_summary.empty else kpis["top_clientes"], n=15),
                use_container_width=True, key="d6", on_select="rerun",
            )
            if _sel_d6 and _sel_d6.selection and _sel_d6.selection.points:
                _cl_click = str(_sel_d6.selection.points[0].get("y","")).strip()
                if _cl_click:
                    st.session_state["drill_cliente"] = _cl_click
                    st.info(f"✅ **{_cl_click[:50]}** seleccionado — abre la pestaña **👤 Clientes** para ver el detalle completo")

        with cg:
            _sel_d7 = st.plotly_chart(
                chart_top_proveedores(
                    supplier_summary.rename(columns={"Nombre Emisor":"Proveedor"})[["Proveedor","Total"]].head(15)
                    if not supplier_summary.empty else kpis["top_proveedores"], n=15),
                use_container_width=True, key="d7", on_select="rerun",
            )
            if _sel_d7 and _sel_d7.selection and _sel_d7.selection.points:
                _pv_click = str(_sel_d7.selection.points[0].get("y","")).strip()
                if _pv_click:
                    st.session_state["drill_proveedor"] = _pv_click
                    st.info(f"✅ **{_pv_click[:50]}** seleccionado — abre la pestaña **🏪 Proveedores** para ver el detalle completo")

        # Gauge de riesgo solo si hay hallazgos
        if hallazgos:
            st.plotly_chart(chart_riesgo_gauge(hallazgos), use_container_width=True, key="d5")


# ══════════════════════════════════════════════════════════════════════════════
# VENTAS
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("ventas")
if t:
  with t:
    section_header("📄 Ventas — Facturas Electrónicas Emitidas")
    if ventas_df.empty:
        st.warning("Sin datos de ventas.")
    else:
        with st.expander("🔎 Filtros"):
            f1,f2,f3 = st.columns(3)
            with f1:
                tipos=["Todos"]+(ventas_df["Tipo_Label"].dropna().unique().tolist() if "Tipo_Label" in ventas_df.columns else [])
                ts=st.selectbox("Tipo",tipos,key="v_tipo2")
            with f2:
                ests=["Todos"]+(ventas_df["Estado"].dropna().unique().tolist() if "Estado" in ventas_df.columns else [])
                es=st.selectbox("Estado",ests,key="v_est2")
            with f3:
                if "Fecha Emisión" in ventas_df.columns:
                    mn=ventas_df["Fecha Emisión"].min().date(); mx=ventas_df["Fecha Emisión"].max().date()
                    dr=st.date_input("Fechas",[mn,mx],key="v_dr2")
                else: dr=None

        dv=ventas_df.copy()
        if ts!="Todos" and "Tipo_Label" in dv.columns: dv=dv[dv["Tipo_Label"]==ts]
        if es!="Todos" and "Estado" in dv.columns: dv=dv[dv["Estado"]==es]
        if dr and len(dr)==2 and "Fecha Emisión" in dv.columns:
            dv=dv[(dv["Fecha Emisión"].dt.date>=dr[0])&(dv["Fecha Emisión"].dt.date<=dr[1])]

        s1,s2,s3,s4 = st.columns(4)
        with s1: kpi_card("💵","Total",fmt_cop(dv["Total"].sum() if "Total" in dv.columns else 0),"#70AD47")
        with s2: kpi_card("🏦","IVA",fmt_cop(dv["IVA"].sum() if "IVA" in dv.columns else 0),"#2E75B6")
        with s3: kpi_card("📊","Base",fmt_cop(dv["Base"].sum() if "Base" in dv.columns else 0),"#9DC3E6")
        with s4: kpi_card("🧾","Docs",str(len(dv)),"#FFD700")

        cv1,cv2 = st.columns(2)
        with cv1: st.plotly_chart(chart_ventas_tiempo(dv),use_container_width=True,key="v1")
        with cv2: st.plotly_chart(chart_tipo_documentos(dv,"Composición"),use_container_width=True,key="v2")
        st.plotly_chart(chart_top_clientes(kpis["top_clientes"]),use_container_width=True,key="v3")
        section_header("📋 Detalle Facturas Ventas")
        dc=["Tipo_Label","Folio","Prefijo","Fecha Emisión","Nombre Receptor","Base","IVA","Total","Estado"]
        dc=[c for c in dc if c in dv.columns]
        st.dataframe(dv[dc].rename(columns={"Tipo_Label":"Tipo"})
            .style.format({c:"${:,.0f}" for c in ["Base","IVA","Total"] if c in dc}),
            use_container_width=True,height=380)


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTES — Reporte global con drill-down por cliente
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("clientes")
if t:
  with t:
    import plotly.express as _px
    section_header("👤 Reporte Global de Clientes")
    if ventas_df.empty or client_summary.empty:
        st.warning("Sin datos de ventas. Carga los archivos DIAN en 📂 Cargar Datos.")
    else:
        # ── KPIs de resumen ──────────────────────────────────────────────────
        _nc = len(client_summary)
        _ck1,_ck2,_ck3,_ck4 = st.columns(4)
        with _ck1: kpi_card("👤","Total Clientes",f"{_nc:,}","#9DC3E6")
        with _ck2: kpi_card("💵","Total Ventas",fmt_cop(client_summary["Total"].sum() if "Total" in client_summary.columns else 0),"#70AD47")
        with _ck3: kpi_card("📊","Promedio / Cliente",fmt_cop(client_summary["Total"].mean() if "Total" in client_summary.columns else 0),"#ED7D31")
        with _ck4: kpi_card("🧾","Total Facturas",f"{int(client_summary['Facturas'].sum()):,}" if "Facturas" in client_summary.columns else "—","#FFD700")

        # ── KPIs de responsabilidad fiscal ───────────────────────────────────
        _n_resp_iva  = int(client_summary["Resp_IVA"].sum())   if "Resp_IVA"    in client_summary.columns else 0
        _n_ret_renta = int(client_summary["Ret_Renta"].sum())  if "Ret_Renta"   in client_summary.columns else 0
        _n_ret_ica   = int(client_summary["Ret_ICA"].sum())    if "Ret_ICA"     in client_summary.columns else 0
        _n_gran      = int(client_summary["Gran_Contrib"].sum()) if "Gran_Contrib" in client_summary.columns else 0
        _fk1,_fk2,_fk3,_fk4 = st.columns(4)
        with _fk1: kpi_card("🧾","Resp. IVA",    str(_n_resp_iva), "#E74C3C", subtitle="Clientes con IVA")
        with _fk2: kpi_card("🔒","Agt. Ret. Renta",str(_n_ret_renta),"#8E44AD", subtitle="Retienen Retefuente")
        with _fk3: kpi_card("🏙","Agt. Ret. ICA", str(_n_ret_ica),  "#2980B9", subtitle="Retienen ICA")
        with _fk4: kpi_card("⭐","Gran Contrib.", str(_n_gran),     "#E67E22", subtitle=">$500M acumulado")

        # ── Vista de período + filtro fiscal ─────────────────────────────────
        _cl_col1, _cl_col2, _cl_col3 = st.columns([3, 4, 5])
        with _cl_col1:
            _cl_v = st.radio("Agrupar por:",["Mes","Año","Total acumulado"], horizontal=True, key="cl_vista")
        with _cl_col2:
            _cl_fiscal = st.multiselect("🏛 Filtrar obligación:", ["Resp. IVA","Ret. Renta","Ret. ICA","⭐ Gran Contrib."], key="cl_fiscal_filtro")
        with _cl_col3:
            _cl_bq = st.text_input("🔍 Buscar por nombre o NIT", key="cl_busq", placeholder="Escribe para filtrar...")

        # ── Tabla global (todos los clientes) ────────────────────────────────
        _df_cl = client_summary.copy()
        if _cl_bq:
            _mask_cl = _df_cl.apply(lambda r: _cl_bq.lower() in str(r).lower(), axis=1)
            _df_cl = _df_cl[_mask_cl]
        if "Resp. IVA"       in _cl_fiscal and "Resp_IVA"    in _df_cl.columns: _df_cl = _df_cl[_df_cl["Resp_IVA"]]
        if "Ret. Renta"      in _cl_fiscal and "Ret_Renta"   in _df_cl.columns: _df_cl = _df_cl[_df_cl["Ret_Renta"]]
        if "Ret. ICA"        in _cl_fiscal and "Ret_ICA"     in _df_cl.columns: _df_cl = _df_cl[_df_cl["Ret_ICA"]]
        if "⭐ Gran Contrib." in _cl_fiscal and "Gran_Contrib" in _df_cl.columns: _df_cl = _df_cl[_df_cl["Gran_Contrib"]]

        # Columnas visibles — incluir Obligaciones, excluir flags booleanos
        _flag_cols_cl = ["Resp_IVA","Ret_Renta","Ret_ICA","Gran_Contrib"]
        _vis_cols_cl = [c for c in _df_cl.columns if c not in _flag_cols_cl]
        _df_cl_show = _df_cl[_vis_cols_cl].copy()
        _cl_fmt = {c:"${:,.0f}" for c in ["Total","Base","IVA","Rete Renta","Rete ICA"] if c in _df_cl_show.columns}
        _cl_rename = {"Nombre Receptor":"Cliente","NIT Receptor":"NIT"}

        section_header(f"📋 Todos los Clientes ({len(_df_cl_show):,})")
        st.caption("🖱 Haz clic en una fila para ver el detalle completo del cliente")

        _evt_cl = st.dataframe(
            _df_cl_show.rename(columns=_cl_rename).style.format(_cl_fmt),
            use_container_width=True, height=350,
            on_select="rerun", selection_mode="single-row", key="tbl_cl",
        )

        # Capturar selección de fila
        if _evt_cl.selection.rows:
            _row_i = _evt_cl.selection.rows[0]
            _sel_cl_name = _df_cl.iloc[_row_i]["Nombre Receptor"]
            st.session_state["drill_cliente"] = _sel_cl_name

        # ── Panel drill-down del cliente seleccionado ────────────────────────
        _drill_cl = st.session_state.get("drill_cliente")
        if _drill_cl and "Nombre Receptor" in ventas_df.columns:
            _inv_cl = ventas_df[ventas_df["Nombre Receptor"] == _drill_cl]
            if not _inv_cl.empty:
                st.markdown("---")
                section_header(f"🔍 Detalle: {_drill_cl}")
                # Badge de obligaciones fiscales del cliente
                _cl_oblig = client_summary.loc[client_summary["Nombre Receptor"]==_drill_cl, "Obligaciones"].values if "Obligaciones" in client_summary.columns else []
                if len(_cl_oblig) and _cl_oblig[0] != "—":
                    st.markdown(f"🏛 **Obligaciones fiscales identificadas:** `{_cl_oblig[0]}`")
                _d1,_d2,_d3,_d4,_d5 = st.columns(5)
                with _d1: kpi_card("🧾","Facturas",str(len(_inv_cl)),"#9DC3E6")
                with _d2: kpi_card("💵","Total",fmt_cop(_inv_cl["Total"].sum() if "Total" in _inv_cl.columns else 0),"#70AD47")
                with _d3: kpi_card("🏦","IVA",fmt_cop(_inv_cl["IVA"].sum() if "IVA" in _inv_cl.columns else 0),"#2E75B6")
                with _d4: kpi_card("📊","Base",fmt_cop(_inv_cl["Base"].sum() if "Base" in _inv_cl.columns else 0),"#ED7D31")
                with _d5: kpi_card("📅","Períodos",str(_inv_cl["Mes"].nunique() if "Mes" in _inv_cl.columns else 0),"#FFD700")

                # Gráfico de tendencia mensual
                if not client_pivot.empty and _drill_cl in client_pivot.index:
                    _pv_row = client_pivot.loc[[_drill_cl]].T.reset_index()
                    _pv_row.columns = ["Mes","Total"]
                    _pv_row = _pv_row[_pv_row["Total"] > 0]
                    if not _pv_row.empty:
                        _fig_clt = _px.bar(
                            _pv_row, x="Mes", y="Total",
                            title=f"📈 Ventas por mes — {str(_drill_cl)[:50]}",
                            template="plotly_dark", color_discrete_sequence=["#2E75B6"],
                            labels={"Total":"Total COP","Mes":"Período"},
                        )
                        _fig_clt.update_layout(
                            plot_bgcolor="#152238", paper_bgcolor="#0F1C33",
                            font_color="#E8EFF8", showlegend=False,
                            yaxis=dict(tickformat="$,.0f"), xaxis_title="",
                            margin=dict(t=50,b=30,l=60,r=20),
                        )
                        _fig_clt.update_traces(texttemplate="%{y:$,.0f}", textposition="outside",
                                               textfont_size=10)
                        st.plotly_chart(_fig_clt, use_container_width=True, key="cl_trend_drill")

                # Tabla de todas las facturas del cliente
                _cols_inv_cl = ["Fecha Emisión","Tipo_Label","Folio","Prefijo","Base","IVA","Total","Estado"]
                _cols_inv_cl = [c for c in _cols_inv_cl if c in _inv_cl.columns]
                _sort_col = "Fecha Emisión" if "Fecha Emisión" in _inv_cl.columns else _inv_cl.columns[0]
                st.dataframe(
                    _inv_cl[_cols_inv_cl].sort_values(_sort_col, ascending=False)
                    .rename(columns={"Tipo_Label":"Tipo"})
                    .style.format({c:"${:,.0f}" for c in ["Base","IVA","Total"] if c in _cols_inv_cl}),
                    use_container_width=True, height=320,
                )
                if st.button("✖ Cerrar detalle del cliente", key="cl_close"):
                    st.session_state.pop("drill_cliente", None)
                    st.rerun()

        # ── Vista pivot por período ───────────────────────────────────────────
        if _cl_v != "Total acumulado" and not client_pivot.empty:
            st.markdown("---")
            section_header("📅 Ventas por Cliente × Período")
            _pv = client_pivot.copy()
            if _cl_v == "Año":
                _pv.columns = [str(c)[:4] for c in _pv.columns]
                _pv = _pv.T.groupby(level=0).sum().T
            # Filtrar solo clientes visibles en la búsqueda actual
            if _cl_bq and not _df_cl.empty:
                _visible = _df_cl["Nombre Receptor"].tolist()
                _pv = _pv[_pv.index.isin(_visible)]
            _pv_disp = _pv.copy()
            _pv_disp.index.name = "Cliente"
            _pv_disp = _pv_disp.reset_index()
            st.caption(f"{'Agrupado por año' if _cl_v=='Año' else 'Por mes'} · Clic en fila arriba para drill-down")
            st.dataframe(
                _pv_disp.set_index("Cliente").style
                .format("${:,.0f}")
                .background_gradient(cmap="Blues", axis=None),
                use_container_width=True, height=400,
            )


# ══════════════════════════════════════════════════════════════════════════════
# COMPRAS
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("compras")
if t:
  with t:
    section_header("📦 Compras — Facturas Electrónicas Recibidas")
    if compras_df.empty:
        st.warning("Sin datos de compras.")
    else:
        with st.expander("🔎 Filtros"):
            f1,f2=st.columns(2)
            with f1:
                tpc=["Todos"]+(compras_df["Tipo_Label"].dropna().unique().tolist() if "Tipo_Label" in compras_df.columns else [])
                tsc=st.selectbox("Tipo",tpc,key="c_tipo2")
            with f2:
                pvs=["Todos"]+sorted(compras_df["Nombre Emisor"].dropna().unique().tolist()[:50]) if "Nombre Emisor" in compras_df.columns else ["Todos"]
                psc=st.selectbox("Proveedor",pvs,key="c_prov2")

        dc2=compras_df.copy()
        if tsc!="Todos" and "Tipo_Label" in dc2.columns: dc2=dc2[dc2["Tipo_Label"]==tsc]
        if psc!="Todos" and "Nombre Emisor" in dc2.columns: dc2=dc2[dc2["Nombre Emisor"]==psc]

        s1,s2,s3,s4=st.columns(4)
        with s1: kpi_card("🛒","Total",fmt_cop(dc2["Total"].sum() if "Total" in dc2.columns else 0),"#ED7D31")
        with s2: kpi_card("✅","IVA",fmt_cop(dc2["IVA"].sum() if "IVA" in dc2.columns else 0),"#70AD47")
        with s3: kpi_card("📊","Base",fmt_cop(dc2["Base"].sum() if "Base" in dc2.columns else 0),"#9DC3E6")
        with s4: kpi_card("📋","Docs",str(len(dc2)),"#FFD700")

        cc1,cc2=st.columns(2)
        with cc1: st.plotly_chart(chart_compras_tiempo(dc2),use_container_width=True,key="c1")
        with cc2: st.plotly_chart(chart_tipo_documentos(dc2,"Composición"),use_container_width=True,key="c2")
        st.plotly_chart(chart_top_proveedores(kpis["top_proveedores"]),use_container_width=True,key="c3")
        st.plotly_chart(chart_scatter_proveedores(dc2),use_container_width=True,key="c4")
        st.plotly_chart(chart_retenciones_tipos(dc2),use_container_width=True,key="c5")
        section_header("📋 Detalle Facturas Compras")
        dc=["Tipo_Label","Folio","Prefijo","Fecha Emisión","Nombre Emisor","Base","IVA","Rete Renta","Total","Estado"]
        dc=[c for c in dc if c in dc2.columns]
        st.dataframe(dc2[dc].rename(columns={"Tipo_Label":"Tipo"})
            .style.format({c:"${:,.0f}" for c in ["Base","IVA","Rete Renta","Total"] if c in dc}),
            use_container_width=True,height=380)


# ══════════════════════════════════════════════════════════════════════════════
# PROVEEDORES — Reporte global con drill-down por proveedor
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("proveedores")
if t:
  with t:
    import plotly.express as _px
    section_header("🏪 Reporte Global de Proveedores")
    if compras_df.empty or supplier_summary.empty:
        st.warning("Sin datos de compras. Carga los archivos DIAN en 📂 Cargar Datos.")
    else:
        # ── KPIs de resumen ──────────────────────────────────────────────────
        _np = len(supplier_summary)
        _pk1,_pk2,_pk3,_pk4 = st.columns(4)
        with _pk1: kpi_card("🏪","Total Proveedores",f"{_np:,}","#9DC3E6")
        with _pk2: kpi_card("🛒","Total Compras",fmt_cop(supplier_summary["Total"].sum() if "Total" in supplier_summary.columns else 0),"#ED7D31")
        with _pk3: kpi_card("📊","Promedio / Proveedor",fmt_cop(supplier_summary["Total"].mean() if "Total" in supplier_summary.columns else 0),"#FFD700")
        with _pk4: kpi_card("🧾","Total Facturas",f"{int(supplier_summary['Facturas'].sum()):,}" if "Facturas" in supplier_summary.columns else "—","#9DC3E6")

        # ── KPIs de responsabilidad fiscal ───────────────────────────────────
        _n_pv_iva   = int(supplier_summary["Resp_IVA"].sum())    if "Resp_IVA"    in supplier_summary.columns else 0
        _n_pv_renta = int(supplier_summary["Ret_Renta"].sum())   if "Ret_Renta"   in supplier_summary.columns else 0
        _n_pv_ica   = int(supplier_summary["Ret_ICA"].sum())     if "Ret_ICA"     in supplier_summary.columns else 0
        _n_pv_gran  = int(supplier_summary["Gran_Contrib"].sum()) if "Gran_Contrib" in supplier_summary.columns else 0
        _pfk1,_pfk2,_pfk3,_pfk4 = st.columns(4)
        with _pfk1: kpi_card("🧾","Resp. IVA",      str(_n_pv_iva),   "#E74C3C", subtitle="Proveed. con IVA")
        with _pfk2: kpi_card("🔒","Agt. Ret. Renta",str(_n_pv_renta), "#8E44AD", subtitle="Retienen Retefuente")
        with _pfk3: kpi_card("🏙","Agt. Ret. ICA",  str(_n_pv_ica),   "#2980B9", subtitle="Retienen ICA")
        with _pfk4: kpi_card("⭐","Gran Contrib.",   str(_n_pv_gran),  "#E67E22", subtitle=">$500M acumulado")

        # ── Vista de período + filtro fiscal ─────────────────────────────────
        _pv_col1, _pv_col2, _pv_col3 = st.columns([3, 4, 5])
        with _pv_col1:
            _pv_v = st.radio("Agrupar por:",["Mes","Año","Total acumulado"], horizontal=True, key="pv_vista")
        with _pv_col2:
            _pv_fiscal = st.multiselect("🏛 Filtrar obligación:", ["Resp. IVA","Ret. Renta","Ret. ICA","⭐ Gran Contrib."], key="pv_fiscal_filtro")
        with _pv_col3:
            _pv_bq = st.text_input("🔍 Buscar por nombre o NIT", key="pv_busq", placeholder="Escribe para filtrar...")

        # ── Tabla global (todos los proveedores) ─────────────────────────────
        _df_pv = supplier_summary.copy()
        if _pv_bq:
            _mask_pv = _df_pv.apply(lambda r: _pv_bq.lower() in str(r).lower(), axis=1)
            _df_pv = _df_pv[_mask_pv]
        if "Resp. IVA"       in _pv_fiscal and "Resp_IVA"    in _df_pv.columns: _df_pv = _df_pv[_df_pv["Resp_IVA"]]
        if "Ret. Renta"      in _pv_fiscal and "Ret_Renta"   in _df_pv.columns: _df_pv = _df_pv[_df_pv["Ret_Renta"]]
        if "Ret. ICA"        in _pv_fiscal and "Ret_ICA"     in _df_pv.columns: _df_pv = _df_pv[_df_pv["Ret_ICA"]]
        if "⭐ Gran Contrib." in _pv_fiscal and "Gran_Contrib" in _df_pv.columns: _df_pv = _df_pv[_df_pv["Gran_Contrib"]]

        # Columnas visibles — incluir Obligaciones, excluir flags booleanos
        _flag_cols_pv = ["Resp_IVA","Ret_Renta","Ret_ICA","Gran_Contrib"]
        _vis_cols_pv  = [c for c in _df_pv.columns if c not in _flag_cols_pv]
        _df_pv_show   = _df_pv[_vis_cols_pv].copy()
        _pv_fmt = {c:"${:,.0f}" for c in ["Total","Base","IVA","Rete Renta","Rete ICA"] if c in _df_pv_show.columns}
        _pv_rename = {"Nombre Emisor":"Proveedor","NIT Emisor":"NIT"}

        section_header(f"📋 Todos los Proveedores ({len(_df_pv_show):,})")
        st.caption("🖱 Haz clic en una fila para ver el detalle completo del proveedor")

        _evt_pv = st.dataframe(
            _df_pv_show.rename(columns=_pv_rename).style.format(_pv_fmt),
            use_container_width=True, height=350,
            on_select="rerun", selection_mode="single-row", key="tbl_pv",
        )

        # Capturar selección de fila
        if _evt_pv.selection.rows:
            _row_pi = _evt_pv.selection.rows[0]
            _sel_pv_name = _df_pv.iloc[_row_pi]["Nombre Emisor"]
            st.session_state["drill_proveedor"] = _sel_pv_name

        # ── Panel drill-down del proveedor seleccionado ──────────────────────
        _drill_pv = st.session_state.get("drill_proveedor")
        if _drill_pv and "Nombre Emisor" in compras_df.columns:
            _inv_pv = compras_df[compras_df["Nombre Emisor"] == _drill_pv]
            if not _inv_pv.empty:
                st.markdown("---")
                section_header(f"🔍 Detalle: {_drill_pv}")
                # Badge de obligaciones fiscales del proveedor
                _pv_oblig = supplier_summary.loc[supplier_summary["Nombre Emisor"]==_drill_pv, "Obligaciones"].values if "Obligaciones" in supplier_summary.columns else []
                if len(_pv_oblig) and _pv_oblig[0] != "—":
                    st.markdown(f"🏛 **Obligaciones fiscales identificadas:** `{_pv_oblig[0]}`")
                _e1,_e2,_e3,_e4,_e5 = st.columns(5)
                with _e1: kpi_card("🧾","Facturas",str(len(_inv_pv)),"#9DC3E6")
                with _e2: kpi_card("🛒","Total",fmt_cop(_inv_pv["Total"].sum() if "Total" in _inv_pv.columns else 0),"#ED7D31")
                with _e3: kpi_card("🏦","IVA",fmt_cop(_inv_pv["IVA"].sum() if "IVA" in _inv_pv.columns else 0),"#2E75B6")
                with _e4: kpi_card("✂️","Rete Renta",fmt_cop(_inv_pv["Rete Renta"].sum() if "Rete Renta" in _inv_pv.columns else 0),"#C00000")
                with _e5: kpi_card("📅","Períodos",str(_inv_pv["Mes"].nunique() if "Mes" in _inv_pv.columns else 0),"#FFD700")

                # Gráfico de tendencia mensual
                if not supplier_pivot.empty and _drill_pv in supplier_pivot.index:
                    _pv_row = supplier_pivot.loc[[_drill_pv]].T.reset_index()
                    _pv_row.columns = ["Mes","Total"]
                    _pv_row = _pv_row[_pv_row["Total"] > 0]
                    if not _pv_row.empty:
                        _fig_pvt = _px.bar(
                            _pv_row, x="Mes", y="Total",
                            title=f"📈 Compras por mes — {str(_drill_pv)[:50]}",
                            template="plotly_dark", color_discrete_sequence=["#ED7D31"],
                            labels={"Total":"Total COP","Mes":"Período"},
                        )
                        _fig_pvt.update_layout(
                            plot_bgcolor="#152238", paper_bgcolor="#0F1C33",
                            font_color="#E8EFF8", showlegend=False,
                            yaxis=dict(tickformat="$,.0f"), xaxis_title="",
                            margin=dict(t=50,b=30,l=60,r=20),
                        )
                        _fig_pvt.update_traces(texttemplate="%{y:$,.0f}", textposition="outside",
                                               textfont_size=10)
                        st.plotly_chart(_fig_pvt, use_container_width=True, key="pv_trend_drill")

                # Tabla de todas las facturas del proveedor
                _cols_inv_pv = ["Fecha Emisión","Tipo_Label","Folio","Prefijo","Base","IVA","Rete Renta","Total","Estado"]
                _cols_inv_pv = [c for c in _cols_inv_pv if c in _inv_pv.columns]
                _sort_col_pv = "Fecha Emisión" if "Fecha Emisión" in _inv_pv.columns else _inv_pv.columns[0]
                st.dataframe(
                    _inv_pv[_cols_inv_pv].sort_values(_sort_col_pv, ascending=False)
                    .rename(columns={"Tipo_Label":"Tipo"})
                    .style.format({c:"${:,.0f}" for c in ["Base","IVA","Rete Renta","Total"] if c in _cols_inv_pv}),
                    use_container_width=True, height=320,
                )
                if st.button("✖ Cerrar detalle del proveedor", key="pv_close"):
                    st.session_state.pop("drill_proveedor", None)
                    st.rerun()

        # ── Vista pivot por período ───────────────────────────────────────────
        if _pv_v != "Total acumulado" and not supplier_pivot.empty:
            st.markdown("---")
            section_header("📅 Compras por Proveedor × Período")
            _spv = supplier_pivot.copy()
            if _pv_v == "Año":
                _spv.columns = [str(c)[:4] for c in _spv.columns]
                _spv = _spv.T.groupby(level=0).sum().T
            if _pv_bq and not _df_pv.empty:
                _visible_pv = _df_pv["Nombre Emisor"].tolist()
                _spv = _spv[_spv.index.isin(_visible_pv)]
            _spv_disp = _spv.copy()
            _spv_disp.index.name = "Proveedor"
            _spv_disp = _spv_disp.reset_index()
            st.caption(f"{'Agrupado por año' if _pv_v=='Año' else 'Por mes'} · Clic en fila arriba para drill-down")
            st.dataframe(
                _spv_disp.set_index("Proveedor").style
                .format("${:,.0f}")
                .background_gradient(cmap="Oranges", axis=None),
                use_container_width=True, height=400,
            )


# ══════════════════════════════════════════════════════════════════════════════
# IVA
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("iva")
if t:
  with t:
    section_header("💰 Conciliación IVA — Posición Bimestral")
    st.info("Confrontar con Formulario 300 DIAN presentado.")
    ic1,ic2,ic3,ic4=st.columns(4)
    with ic1: kpi_card("🏦","IVA Generado",fmt_cop(kpis["iva_generado"]),"#C00000")
    with ic2: kpi_card("✅","IVA Descontable",fmt_cop(kpis["iva_descontable"]),"#70AD47")
    ivc="#C00000" if kpis["iva_neto"]>0 else "#70AD47"
    ivl="A PAGAR" if kpis["iva_neto"]>0 else "A FAVOR"
    with ic3: kpi_card("⚖️",f"IVA Neto ({ivl})",fmt_cop(abs(kpis["iva_neto"])),ivc)
    with ic4:
        tasa=(kpis["iva_generado"]/kpis["base_ventas"]*100) if kpis.get("base_ventas",0)>0 else 0
        kpi_card("📊","Tasa IVA Efectiva",f"{tasa:.1f}%","#2E75B6")
    st.plotly_chart(chart_iva_waterfall(kpis),use_container_width=True,key="i1")
    if not iva_pivot.empty:
        st.plotly_chart(chart_iva_bimestral(iva_pivot),use_container_width=True,key="i2")
        section_header("📋 Tabla Conciliación Bimestral")
        st.dataframe(iva_pivot.style.format(
            {c:"${:,.0f}" for c in iva_pivot.columns if iva_pivot[c].dtype in ["float64","int64"]}),
            use_container_width=True)
    section_header("📝 Plantilla Form. 300")
    st.dataframe(pd.DataFrame({
        "Concepto":["IVA Generado FE","(-) NC emitidas","= Total Generado",
                    "IVA Descontable FE","(-) NC recibidas","= Total Descontable",
                    "IVA Neto","Retenciones IVA","= A Pagar / A Favor"],
        "DIAN (FE)":[fmt_cop(kpis["iva_generado"]),"$ —",fmt_cop(kpis["iva_generado"]),
                     fmt_cop(kpis["iva_descontable"]),"$ —",fmt_cop(kpis["iva_descontable"]),
                     fmt_cop(kpis["iva_neto"]),"$ —",fmt_cop(abs(kpis["iva_neto"]))],
        "Form. 300":[""]*9,"Diferencia":[""]*9,
    }),use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# NOMINA
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("nomina")
if t:
  with t:
    section_header("👥 Nómina Electrónica — Costo Laboral")
    if nomina_df.empty:
        st.info("Carga el archivo de Nómina Electrónica del portal DIAN.")
        st.markdown("""
        | Columna esperada | Descripción |
        |---|---|
        | Nombre Empleado | Nombre completo |
        | NIT Empleado | Cédula o NIT |
        | Período | Mes de la nómina |
        | Devengado | Salario + prestaciones |
        | Deducido | Total descuentos |
        | Rete Fuente | Retención practicada |
        | Salud / Pensión | Aportes del empleado |
        | Total Pagar | Neto a pagar |
        """)
    else:
        n1,n2,n3,n4=st.columns(4)
        with n1: kpi_card("👥","Empleados",str(kpis_nom.get("num_empleados",0)),"#9DC3E6")
        with n2: kpi_card("💵","Devengado",fmt_cop(kpis_nom.get("total_devengado",0)),"#70AD47")
        with n3: kpi_card("✂️","Deducido",fmt_cop(kpis_nom.get("total_deducido",0)),"#ED7D31")
        with n4: kpi_card("🏛️","Carga Patronal Est.",fmt_cop(kpis_nom.get("carga_patronal_est",0)),"#2E75B6","38.5% s/devengado")
        na,nb=st.columns(2)
        with na: st.plotly_chart(chart_nomina_mensual(nomina_df),use_container_width=True,key="n1")
        with nb: st.plotly_chart(chart_nomina_composicion(kpis_nom),use_container_width=True,key="n2")
        st.plotly_chart(chart_top_empleados(nomina_df),use_container_width=True,key="n3")
        section_header("📋 Detalle Nómina")
        dcn=["Nombre Empleado","NIT Empleado","Periodo","Devengado","Deducido","Rete Fuente","Total Pagar"]
        dcn=[c for c in dcn if c in nomina_df.columns]
        if dcn:
            st.dataframe(nomina_df[dcn].style.format(
                {c:"${:,.0f}" for c in ["Devengado","Deducido","Rete Fuente","Total Pagar"] if c in dcn}),
                use_container_width=True,height=380)


# ══════════════════════════════════════════════════════════════════════════════
# EXOGENA
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("exogena")
if t:
  with t:
    section_header("🔗 Información Exógena / Medios Magnéticos")
    if exogena_df.empty:
        st.info("Carga el archivo de Información Exógena del portal DIAN.")
        st.markdown("""
        | Columna | Descripción |
        |---|---|
        | NIT Tercero | NIT del cliente / proveedor |
        | Nombre Tercero | Razón social |
        | Concepto | Formato DIAN (1001, 1007…) |
        | Valor Bruto | Monto operación |
        | Retencion | Retención practicada |
        | Valor Neto | Neto de la operación |
        """)
    else:
        e1,e2,e3,e4=st.columns(4)
        texg=exogena_df["Valor Bruto"].sum() if "Valor Bruto" in exogena_df.columns else 0
        tret=exogena_df["Retencion"].sum() if "Retencion" in exogena_df.columns else 0
        tnet=exogena_df["Valor Neto"].sum() if "Valor Neto" in exogena_df.columns else 0
        terc=exogena_df["NIT Tercero"].nunique() if "NIT Tercero" in exogena_df.columns else len(exogena_df)
        with e1: kpi_card("🔗","Terceros",str(terc),"#9DC3E6")
        with e2: kpi_card("💵","Valor Bruto",fmt_cop(texg),"#70AD47")
        with e3: kpi_card("✂️","Retención",fmt_cop(tret),"#ED7D31")
        with e4: kpi_card("💰","Valor Neto",fmt_cop(tnet),"#2E75B6")
        st.plotly_chart(chart_exogena_cruce(ventas_df,exogena_df),use_container_width=True,key="ex1")
        section_header("📋 Detalle Exógena")
        dce=["NIT Tercero","Nombre Tercero","Concepto","Valor Bruto","Retencion","Valor Neto"]
        dce=[c for c in dce if c in exogena_df.columns]
        if dce:
            st.dataframe(exogena_df[dce].style.format(
                {c:"${:,.0f}" for c in ["Valor Bruto","Retencion","Valor Neto"] if c in dce}),
                use_container_width=True,height=380)

    if not retenciones_df.empty:
        st.markdown("---")
        section_header("✂️ Retenciones Practicadas")
        r1,r2=st.columns(2)
        tot_ret=retenciones_df["Valor Retenido"].sum() if "Valor Retenido" in retenciones_df.columns else 0
        age_ret=retenciones_df["Agente Retenedor"].nunique() if "Agente Retenedor" in retenciones_df.columns else 0
        with r1: kpi_card("✂️","Total Retenido",fmt_cop(tot_ret),"#C00000")
        with r2: kpi_card("🏦","Agentes Retenedores",str(age_ret),"#9DC3E6")
        dcr=["Agente Retenedor","NIT Retenedor","Concepto","Base","Tarifa","Valor Retenido","Periodo"]
        dcr=[c for c in dcr if c in retenciones_df.columns]
        st.dataframe(retenciones_df[dcr] if dcr else retenciones_df,use_container_width=True,height=300)


# ══════════════════════════════════════════════════════════════════════════════
# HALLAZGOS
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("hallazgos")
if t:
  with t:
    section_header("🔍 Hallazgos de Auditoría — H1 a H14")
    from collections import Counter
    nc=Counter(h["nivel"] for h in hallazgos)
    an=sum(v for k,v in nc.items() if "ALTO" in k and "MEDIO" not in k)
    mn2=sum(v for k,v in nc.items() if "MEDIO-ALTO" in k)
    me=sum(v for k,v in nc.items() if "MEDIO" in k and "ALTO" not in k)
    ba=sum(v for k,v in nc.items() if "BAJO" in k)

    h1,h2,h3,h4,h5=st.columns(5)
    with h1: kpi_card("🔴","Alto",str(an),"#C00000")
    with h2: kpi_card("🟠","Medio-Alto",str(mn2),"#ED7D31")
    with h3: kpi_card("🟡","Medio",str(me),"#FFD700")
    with h4: kpi_card("⚪","Bajo",str(ba),"#9DC3E6")
    with h5: kpi_card("📋","Total",str(len(hallazgos)),"#FFF")

    hg1,hg2=st.columns([1,2])
    with hg1: st.plotly_chart(chart_riesgo_gauge(hallazgos),use_container_width=True,key="hg1")
    with hg2:
        imp=sum(h.get("impacto",0) for h in hallazgos)
        kpi_card("💰","Impacto Económico Total",fmt_cop(imp),"#C00000","Suma estimada de todos los hallazgos")

    if not hallazgos:
        st.success("✅ No se detectaron hallazgos.")
    else:
        st.markdown("---")
        areas=sorted(set(h["area"] for h in hallazgos))
        af=st.selectbox("Filtrar área:",["Todas"]+areas,key="hall_af")
        filt=hallazgos if af=="Todas" else [h for h in hallazgos if h["area"]==af]

        for h in filt:
            ico="🔴" if "ALTO" in h["nivel"] and "MEDIO" not in h["nivel"] else(
               "🟠" if "MEDIO-ALTO" in h["nivel"] else(
               "🟡" if "MEDIO" in h["nivel"] else "⚪"))
            with st.expander(f"{ico} {h['codigo']} | {h['nivel']} | {h['area']} — {h['descripcion'][:80]}..."):
                cl,cr=st.columns([3,1])
                with cl:
                    st.markdown(f"**Descripción:**\n{h['descripcion']}")
                    st.markdown(f"**Procedimiento:**\n{h.get('procedimiento','—')}")
                with cr:
                    st.markdown(f"**Cuenta:** `{h.get('cuenta','')}`")
                    st.markdown(f"**Impacto:** {fmt_cop(h.get('impacto',0))}")
                    st.markdown(f"**Norma:** {h.get('norma','')}")


# ══════════════════════════════════════════════════════════════════════════════
# DATOS
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("datos")
if t:
  with t:
    section_header("📋 Explorador de Datos")
    sel=st.radio("Ver:",["Ventas","Compras","Nómina","Exógena","Retenciones","Archivos subidos"],
                 horizontal=True,key="raw_s")
    dmap={"Ventas":ventas_df,"Compras":compras_df,"Nómina":nomina_df,
          "Exógena":exogena_df,"Retenciones":retenciones_df}
    if sel=="Archivos subidos":
        ups=get_uploads(cid)
        if ups:
            st.dataframe(pd.DataFrame(ups)[["report_type","filename","rows","periodo","uploaded_by","uploaded_at"]],
                         use_container_width=True)
        else: st.info("Sin archivos subidos para esta empresa.")
    else:
        df_r=dmap.get(sel,pd.DataFrame())
        if df_r.empty: st.warning(f"Sin datos de {sel}.")
        else:
            srch=st.text_input(f"Buscar en {sel}",placeholder="Nombre, NIT, folio…")
            if srch:
                mask=df_r.astype(str).apply(lambda c:c.str.contains(srch,case=False,na=False)).any(axis=1)
                df_r=df_r[mask]; st.info(f"{len(df_r)} resultados para '{srch}'")
            st.markdown(f"**{len(df_r)} filas** | {len(df_r.columns)} columnas")
            st.dataframe(df_r,use_container_width=True,height=480)


# ══════════════════════════════════════════════════════════════════════════════
# EXPORTAR
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("exportar")
if t:
  with t:
    section_header("📥 Exportar Reportes Profesionales")
    xe1,xe2=st.columns(2)
    with xe1:
        st.markdown("""<div class="kpi-card" style="text-align:left">
          <div style="font-size:1.3rem;margin-bottom:8px">📊 Excel Completo</div>
          <div style="color:#9DC3E6;font-size:.8rem">6 hojas · KPIs · Ventas · Compras ·
          Hallazgos H1-H14 · IVA · Procedimientos</div></div>""",unsafe_allow_html=True)
        if st.button("⬇️ Generar Excel",use_container_width=True,type="primary",key="bxl"):
            with st.spinner("Generando..."):
                xb=generate_excel(ventas_df,compras_df,kpis,hallazgos,iva_pivot,empresa=empresa,nit=nit,periodo=periodo)
            st.download_button("📊 Descargar",xb,
                f"Auditoria_{empresa.replace(' ','_')}_{nit}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",key="dl_xls")
            log_action(uid,cid,"export_excel",periodo)
    with xe2:
        st.markdown("""<div class="kpi-card" style="text-align:left">
          <div style="font-size:1.3rem;margin-bottom:8px">📝 Informe Word</div>
          <div style="color:#9DC3E6;font-size:.8rem">Ejecutivo · Hallazgos detallados ·
          Normas · Conclusiones · Recomendaciones</div></div>""",unsafe_allow_html=True)
        if st.button("⬇️ Generar Word",use_container_width=True,key="bwd"):
            with st.spinner("Generando..."):
                wb=generate_word(kpis,hallazgos,empresa=empresa,nit=nit,periodo=periodo)
            if wb:
                st.download_button("📝 Descargar",wb,
                    f"Informe_{empresa.replace(' ','_')}_{nit}.docx",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",key="dl_doc")
                log_action(uid,cid,"export_word",periodo)
            else: st.error("Instala python-docx: pip install python-docx")

    st.markdown("---")
    if hallazgos:
        section_header("📋 Hallazgos a Exportar")
        st.dataframe(pd.DataFrame([{"Código":h["codigo"],"Nivel":h["nivel"],"Área":h["area"],
            "Descripción":h["descripcion"][:100]+"...","Impacto COP":h.get("impacto",0),
            "Cuenta":h.get("cuenta","")} for h in hallazgos])
            .style.format({"Impacto COP":"${:,.0f}"}),use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# CARGAR DATOS — Tab dedicada por empresa
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("cargar")
if t:
  with t:
    section_header(f"📂 Cargar Archivos DIAN — {empresa}  ·  NIT {nit}")

    st.markdown(f"""
    <div style="background:#1A2B4A;border-radius:10px;padding:10px 18px;margin-bottom:16px;font-size:.82rem;color:#9DC3E6">
      📌 Cada empresa tiene su propio historial de archivos. Los datos se <b>acumulan automáticamente</b> —
      las facturas repetidas (mismo CUFE/CUDE) se omiten. Usa el <b>Conector DIAN</b> para importar
      automáticamente, o sube el Excel manualmente abajo.
    </div>
    """, unsafe_allow_html=True)

    # ══ CONECTOR DIAN AUTOMÁTICO ══════════════════════════════════════════════
    with st.expander("🔌 Importar automáticamente desde DIAN (nuevo)", expanded=True):
        st.markdown("""
        <div style="background:linear-gradient(135deg,#0F1C33,#1A2B4A);border:1px solid #2E75B6;
          border-radius:10px;padding:14px 18px;margin-bottom:12px">
          <div style="color:white;font-weight:700;font-size:.95rem;margin-bottom:6px">
            📧 ¿Cómo obtener el link?
          </div>
          <div style="color:#9DC3E6;font-size:.82rem;line-height:1.6">
            1. Entra a <b>muisca.dian.gov.co</b> → Inicio de sesión<br>
            2. Ve a <b>Facturación Electrónica → Catálogo de documentos</b><br>
            3. La DIAN envía un link al correo del RUT → <b>cópialo y pégalo aquí</b><br>
            <span style="color:#FFD700;font-size:.76rem">⚠ El link es válido por 60 minutos</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        _d_url = st.text_input(
            "🔗 Link de acceso DIAN (del correo)",
            placeholder="https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&rk=...&token=...",
            key="dian_auth_url",
            help="Pega aquí el link completo que llegó al correo registrado en el RUT de la empresa",
        )

        _dc1, _dc2, _dc3 = st.columns([2, 2, 3])
        with _dc1:
            _d_desde = st.date_input("📅 Desde", key="dian_desde", help="Fecha inicio del período a importar")
        with _dc2:
            _d_hasta = st.date_input("📅 Hasta", key="dian_hasta", help="Fecha fin del período a importar")
        with _dc3:
            _d_tipos = st.multiselect(
                "📋 Qué importar",
                options=["Ventas (facturas emitidas)", "Compras (facturas recibidas)"],
                default=["Ventas (facturas emitidas)", "Compras (facturas recibidas)"],
                key="dian_tipos",
                help="Selecciona qué tipo de facturas traer del catálogo DIAN",
            )

        _btn_disabled = not (_d_url and _d_url.startswith("http") and "catalogo-vpfe" in _d_url)
        if st.button(
            "⬇️ Importar desde DIAN",
            use_container_width=True,
            disabled=_btn_disabled,
            type="primary",
            key="btn_dian_import",
            help="Importa las facturas directamente sin descargar Excel manualmente",
        ):
            if not _d_tipos:
                st.warning("Selecciona al menos un tipo de documento para importar.")
            elif _d_desde > _d_hasta:
                st.warning("La fecha de inicio debe ser anterior a la fecha de fin.")
            else:
                _import_from_dian(_d_url, _d_desde, _d_hasta, _d_tipos)

        if _btn_disabled and _d_url:
            st.caption("⚠ El link debe ser de catalogo-vpfe.dian.gov.co")

    st.markdown("---")
    st.markdown("""
    <div style="color:#9DC3E6;font-size:.88rem;font-weight:700;margin-bottom:10px">
      📁 También puedes subir el archivo Excel manualmente:
    </div>
    """, unsafe_allow_html=True)
    # ══ FIN CONECTOR DIAN ═════════════════════════════════════════════════════

    _tipos_info = [
        ("ventas",      "📄", "Ventas FE",           ventas_df_raw,      "Portal DIAN → Facturación Electrónica → Documentos emitidos → Exportar Excel"),
        ("compras",     "📦", "Compras FE",           compras_df_raw,     "Portal DIAN → Facturación Electrónica → Documentos recibidos → Exportar Excel"),
        ("nomina",      "👥", "Nómina Electrónica",   nomina_df_raw,      "Portal DIAN → Nómina Electrónica → Reporte de documentos → Exportar Excel"),
        ("exogena",     "🔗", "Información Exógena",  exogena_df_raw,     "Portal DIAN → Medios Magnéticos → Formatos 1001, 1007, 1008 → Exportar Excel"),
        ("retenciones", "📋", "Retenciones",          retenciones_df_raw, "Portal DIAN → Retenciones practicadas / Certificados → Exportar Excel"),
    ]

    for i in range(0, len(_tipos_info), 2):
        _cols = st.columns(2)
        for j, _col in enumerate(_cols):
            if i + j >= len(_tipos_info):
                break
            _rtype, _icon, _label, _df_raw, _hint = _tipos_info[i + j]
            _meta = get_latest_upload(cid, _rtype)
            _tiene = _meta is not None and not _df_raw.empty
            _uploads_hist = get_uploads(cid, _rtype)

            with _col:
                _bc  = "#70AD47" if _tiene else "#C00000"
                _btx = "✓ CARGADO" if _tiene else "⚠ SIN DATOS"

                if _tiene:
                    _meses_tipo = sorted(_df_raw["Mes"].dropna().unique().tolist()) if "Mes" in _df_raw.columns else []
                    _info_line = (f"{len(_df_raw):,} filas (sin duplicados) · "
                                  f"{len(_uploads_hist)} archivo{'s' if len(_uploads_hist)!=1 else ''}")
                    _periodos_str = " · ".join(_meses_tipo) if _meses_tipo else _meta.get("periodo", "—")
                else:
                    _info_line = "Ningún archivo cargado aún"
                    _periodos_str = ""

                st.markdown(f"""
                <div style="background:#152238;border:1px solid {'#70AD47' if _tiene else '#2A3F5F'};
                  border-radius:12px;padding:16px 18px 4px 18px;margin-bottom:4px">
                  <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
                    <span style="font-size:1.6rem">{_icon}</span>
                    <div>
                      <div style="color:white;font-weight:700;font-size:.98rem">{_label}</div>
                      <span style="background:{_bc};color:white;font-size:.68rem;font-weight:700;
                        padding:2px 10px;border-radius:20px">{_btx}</span>
                    </div>
                  </div>
                  <div style="color:#9DC3E6;font-size:.8rem;margin-bottom:2px">{_info_line}</div>
                  {'<div style="color:#70AD47;font-size:.75rem;margin-bottom:4px">📅 ' + _periodos_str + '</div>' if _periodos_str else ''}
                  <div style="color:#4A6080;font-size:.7rem;font-style:italic;margin-bottom:8px">ℹ️ {_hint}</div>
                </div>
                """, unsafe_allow_html=True)

                _up_label = f"{'Agregar más meses a' if _tiene else 'Subir archivo para'} {_label}"
                _uf = st.file_uploader(
                    _up_label,
                    type=["xlsx"],
                    key=f"up_car_{_rtype}",
                    help=f"Sube el reporte Excel del portal DIAN. Si ya hay datos cargados, las facturas repetidas se omiten automáticamente."
                )
                if _uf:
                    _handle_upload(_uf, _rtype, _label)
                st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

    # Historial completo de uploads
    st.markdown("---")
    section_header("📋 Historial de Archivos Subidos")
    _all_ups = get_uploads(cid)
    if _all_ups:
        _ups_df = pd.DataFrame(_all_ups)[["report_type","filename","rows","periodo","uploaded_by","uploaded_at"]]
        _ups_df.columns = ["Tipo","Archivo","Filas","Período","Subido por","Fecha"]
        st.dataframe(_ups_df, use_container_width=True, height=260)
    else:
        st.info("Esta empresa aún no tiene archivos subidos.")


# ══════════════════════════════════════════════════════════════════════════════
# EMPRESAS (Admin only)
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("empresas")
if t:
  with t:
    section_header("🏢 Gestión de Empresas")

    # ── Nueva empresa ──────────────────────────────────────────────────────────
    with st.expander("➕ Agregar Nueva Empresa", expanded=False):
        with st.form("new_co", clear_on_submit=True):
            nc1, nc2 = st.columns(2)
            with nc1:
                newnit = st.text_input("NIT *", placeholder="900123456-1")
                newact = st.text_input("Actividad económica", placeholder="Comercio al por menor")
            with nc2:
                newrs  = st.text_input("Razón Social *", placeholder="MI EMPRESA S.A.S")
                newreg = st.selectbox("Régimen", ["Simplificado","Ordinario","Gran Contribuyente"])
            if st.form_submit_button("✅ Crear Empresa", type="primary", use_container_width=True):
                if newnit and newrs:
                    try:
                        ncid = create_company(newnit.strip(), newrs.strip(), newact, newreg)
                        update_user_role(uid, ncid, "admin")
                        from database import get_companies as _gc
                        st.session_state["companies"] = _gc(uid)
                        log_action(uid, ncid, "create_company", newrs)
                        st.success(f"✅ Empresa **{newrs}** creada con NIT {newnit}.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error al crear: {ex}")
                else:
                    st.error("NIT y Razón Social son obligatorios.")

    st.markdown("---")
    cos = get_all_companies()
    st.markdown(f"**{len(cos)} empresa(s) registradas**")

    # ── Tabla de empresas ──────────────────────────────────────────────────────
    for co in cos:
        is_active = bool(co["activa"])
        badge_color = "#70AD47" if is_active else "#C00000"
        badge_txt   = "ACTIVA" if is_active else "INACTIVA"
        st.markdown(
            f'<div style="background:#152238;border:1px solid #2A3F5F;border-radius:10px;'
            f'padding:14px 18px;margin-bottom:10px">'
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px">'
            f'<span style="background:{badge_color};color:white;padding:2px 10px;border-radius:8px;'
            f'font-size:.72rem;font-weight:700">{badge_txt}</span>'
            f'<span style="color:white;font-weight:700;font-size:1rem">{co["razon_social"]}</span>'
            f'<span style="color:#7A90AB;font-size:.82rem">NIT: {co["nit"]}</span>'
            f'<span style="color:#7A90AB;font-size:.78rem;margin-left:auto">'
            f'{co["regimen"]} | {co["actividad"] or "Sin actividad"}</span>'
            f'</div></div>',
            unsafe_allow_html=True
        )
        with st.expander(f"✏️ Editar — {co['razon_social']}", expanded=False):
            with st.form(f"eco_{co['id']}", clear_on_submit=False):
                e1, e2 = st.columns(2)
                with e1:
                    enid = st.text_input("NIT",          value=co["nit"],          key=f"en_{co['id']}")
                    eac  = st.text_input("Actividad",    value=co["actividad"] or "",key=f"ea_{co['id']}")
                with e2:
                    ers  = st.text_input("Razón Social", value=co["razon_social"], key=f"er_{co['id']}")
                    REGS = ["Simplificado","Ordinario","Gran Contribuyente"]
                    erg  = st.selectbox("Régimen", REGS,
                               index=REGS.index(co["regimen"]) if co["regimen"] in REGS else 0,
                               key=f"eg_{co['id']}")

                b1, b2, b3 = st.columns([2, 1, 1])
                with b1:
                    if st.form_submit_button("💾 Guardar cambios", type="primary", use_container_width=True):
                        if enid.strip() and ers.strip():
                            update_company(co["id"], enid.strip(), ers.strip(), eac, erg)
                            st.success("✅ Empresa actualizada.")
                            st.rerun()
                        else:
                            st.error("NIT y Razón Social son obligatorios.")
                with b2:
                    lbl = "⛔ Desactivar" if is_active else "✅ Activar"
                    if st.form_submit_button(lbl, use_container_width=True):
                        toggle_company(co["id"], not is_active)
                        st.rerun()
                with b3:
                    st.markdown(f'<div style="text-align:center;color:#4A6080;font-size:.72rem;padding-top:8px">ID: {co["id"]}</div>',
                                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# USUARIOS (Admin only)
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("usuarios")
if t:
  with t:
    section_header("👤 Gestión de Usuarios y Roles")

    # ── Nuevo usuario ──────────────────────────────────────────────────────────
    with st.expander("➕ Crear Nuevo Usuario", expanded=False):
        with st.form("new_usr", clear_on_submit=True):
            u1, u2 = st.columns(2)
            with u1:
                nemail = st.text_input("Correo electrónico *", placeholder="usuario@empresa.co")
                npwd   = st.text_input("Contraseña *", type="password")
            with u2:
                nnomb  = st.text_input("Nombre completo *", placeholder="Juan Pérez")
                npwd2  = st.text_input("Confirmar contraseña *", type="password")
            if st.form_submit_button("✅ Crear Usuario", type="primary", use_container_width=True):
                if not (nemail and nnomb and npwd):
                    st.error("Todos los campos son obligatorios.")
                elif npwd != npwd2:
                    st.error("Las contraseñas no coinciden.")
                else:
                    try:
                        create_user(nemail.strip(), nnomb.strip(), npwd)
                        log_action(uid, 0, "create_user", nemail)
                        st.success(f"✅ Usuario **{nnomb}** creado exitosamente.")
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Error: {ex}")

    st.markdown("---")
    usrs = get_all_users()
    cos  = get_all_companies()
    co_opts = {c["id"]: f"{c['razon_social']} ({c['nit']})" for c in cos}
    st.markdown(f"**{len(usrs)} usuario(s) registrados**")

    # ── Tabla de usuarios ──────────────────────────────────────────────────────
    for usr in usrs:
        uroles   = get_user_roles(usr["id"])
        is_activo = bool(usr["activo"])
        badge_c  = "#70AD47" if is_activo else "#C00000"
        badge_t  = "ACTIVO" if is_activo else "INACTIVO"
        roles_str = " · ".join(
            f'{ROLE_LABELS.get(r["role"],r["role"])} @ {r["razon_social"]}' for r in uroles
        ) or "Sin empresas asignadas"

        # User card header
        st.markdown(
            f'<div style="background:#152238;border:1px solid #2A3F5F;border-radius:10px;'
            f'padding:14px 18px;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">'
            f'<span style="background:{badge_c};color:white;padding:2px 9px;border-radius:8px;'
            f'font-size:.7rem;font-weight:700">{badge_t}</span>'
            f'<span style="color:white;font-weight:700">{usr["nombre"]}</span>'
            f'<span style="color:#7A90AB;font-size:.82rem">{usr["email"]}</span>'
            f'<span style="color:#4A6080;font-size:.72rem;margin-left:auto">'
            f'Creado: {usr["created_at"][:10]}</span>'
            f'</div>'
            f'<div style="color:#7A90AB;font-size:.75rem;margin-top:6px">📋 {roles_str}</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        with st.expander(f"✏️ Editar — {usr['nombre']}", expanded=False):
            ed1, ed2 = st.columns([3, 2])

            # ── Editar nombre + toggle activo ─────────────────────────────────
            with ed1:
                with st.form(f"edit_usr_{usr['id']}", clear_on_submit=False):
                    new_nombre = st.text_input("Nombre completo", value=usr["nombre"],
                                               key=f"nm_{usr['id']}")
                    new_email  = st.text_input("Correo", value=usr["email"],
                                               key=f"em_{usr['id']}", disabled=True)
                    new_pwd    = st.text_input("Nueva contraseña (dejar vacío = sin cambios)",
                                               type="password", key=f"pw_{usr['id']}")

                    activo_val = st.checkbox("✅ Usuario activo", value=is_activo,
                                            key=f"chk_{usr['id']}")

                    if st.form_submit_button("💾 Guardar", type="primary", use_container_width=True):
                        # Update name if changed
                        if new_nombre.strip() and new_nombre.strip() != usr["nombre"]:
                            conn_tmp = get_connection()
                            conn_tmp.execute("UPDATE users SET nombre=? WHERE id=?",
                                             (new_nombre.strip(), usr["id"]))
                            conn_tmp.commit()
                            conn_tmp.close()
                        # Update password if provided
                        if new_pwd:
                            reset_password(usr["id"], new_pwd)
                        # Toggle active if changed
                        if activo_val != is_activo:
                            toggle_user(usr["id"], activo_val)
                        log_action(uid, 0, "edit_user", usr["email"])
                        st.success("✅ Usuario actualizado.")
                        st.rerun()

            # ── Asignar rol por empresa ───────────────────────────────────────
            with ed2:
                st.markdown("**Roles por empresa:**")
                for r in uroles:
                    rc1, rc2 = st.columns([3, 1])
                    with rc1:
                        st.markdown(
                            f'{role_badge(r["role"])} <span style="font-size:.8rem;color:#9DC3E6">'
                            f'{r["razon_social"]}</span>',
                            unsafe_allow_html=True
                        )
                    with rc2:
                        if st.button("✖", key=f"rm_{usr['id']}_{r['company_id']}",
                                     help="Quitar de esta empresa"):
                            remove_user_from_company(usr["id"], r["company_id"])
                            st.rerun()

                st.markdown("---")
                with st.form(f"asgn_{usr['id']}", clear_on_submit=False):
                    if co_opts:
                        aco = st.selectbox("Empresa", list(co_opts.keys()),
                                           format_func=lambda x: co_opts[x],
                                           key=f"ac_{usr['id']}")
                        arl = st.selectbox("Rol", ROLES,
                                           format_func=lambda r: ROLE_LABELS[r],
                                           key=f"ar_{usr['id']}")
                        if st.form_submit_button("➕ Asignar", use_container_width=True):
                            update_user_role(usr["id"], aco, arl)
                            st.success(f"Rol asignado.")
                            st.rerun()
                    else:
                        st.info("No hay empresas creadas.")




# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTOS BANCARIOS — Dashboard por cuenta individual (auto-generado)
# Cada cuenta cargada (PDF o Excel) genera su propio tab con KPIs, graficos,
# filtros por fecha/categoria y exportacion Excel independiente.
# ══════════════════════════════════════════════════════════════════════════════
t = get_tab("extractos")
if t:
  with t:
    import tempfile as _tmplib
    import io     as _io_bk
    import plotly.express as _px_bk

    section_header("🏦 Extractos Bancarios — Dashboard por Cuenta")

    # ── Uploader PDF + Excel hibrido ──────────────────────────────────────
    _bk_files = st.file_uploader(
        "📤 Subir extractos — PDF o Excel (Bancolombia, Nequi, Davivienda, BBVA...)",
        type=["pdf", "xlsx", "xls"],
        accept_multiple_files=True,
        key="bank_pdfs",
        help="Cada cuenta genera automaticamente su propio dashboard separado.",
    )

    if _bk_files:
        if "bank_data" not in st.session_state:
            st.session_state["bank_data"] = {}
        _bk_prog = st.progress(0)
        for _bk_i, _bk_f in enumerate(_bk_files):
            _bk_prog.progress((_bk_i + 1) / len(_bk_files))
            _bk_key = _bk_f.name
            if _bk_key not in st.session_state["bank_data"]:
                _bk_ext = os.path.splitext(_bk_f.name)[1].lower()
                _bk_suf = _bk_ext if _bk_ext in (".pdf", ".xlsx", ".xls") else ".pdf"
                with _tmplib.NamedTemporaryFile(suffix=_bk_suf, delete=False) as _tf:
                    _tf.write(_bk_f.read()); _bk_tmp = _tf.name
                try:
                    if _bk_ext in (".xlsx", ".xls"):
                        _bk_r = parse_bank_statement_excel(_bk_tmp)
                        _tipo_icon = "📊"
                    else:
                        _bk_r = parse_bank_statement(_bk_tmp)
                        _tipo_icon = "📄"
                    st.session_state["bank_data"][_bk_key] = _bk_r
                    _nmov = len(_bk_r["movimientos"])
                    st.success(
                        f"{_tipo_icon} **{_bk_f.name}** "
                        f"| 🏦 {_bk_r['banco']} "
                        f"| 💳 Cta: **{_bk_r['cuenta'] or 'N/D'}** "
                        f"| 👤 {_bk_r['titular'] or 'sin nombre'} "
                        f"| 📅 {_bk_r['periodo'] or 'N/D'} "
                        f"| **{_nmov} movimientos**"
                    )
                except Exception as _ex:
                    st.error(f"❌ **{_bk_f.name}**: {_ex}")
                finally:
                    try:
                        import os as _os_bk; _os_bk.unlink(_bk_tmp)
                    except Exception:
                        pass
        _bk_prog.empty()

    _bk_loaded = st.session_state.get("bank_data", {})

    # ── Boton limpiar ─────────────────────────────────────────────────────
    if _bk_loaded:
        _xc1, _xc2 = st.columns([9, 2])
        with _xc2:
            if st.button("🗑 Limpiar todo", key="clear_banks", use_container_width=True):
                st.session_state.pop("bank_data"); st.rerun()

    if _bk_loaded:
        # ── Agrupar por banco + cuenta ────────────────────────────────────
        _bk_accounts = {}
        for _fn, _fd in _bk_loaded.items():
            _ak = f"{_fd['banco']}||{_fd['cuenta'] or _fn}"
            if _ak not in _bk_accounts:
                _bk_accounts[_ak] = {
                    "banco":    _fd["banco"],
                    "cuenta":   _fd["cuenta"],
                    "titular":  _fd["titular"],
                    "periodos": [],
                    "frames":   [],
                    "metas":    [],
                }
            _bk_accounts[_ak]["periodos"].append(_fd.get("periodo", ""))
            if isinstance(_fd.get("movimientos"), pd.DataFrame) and not _fd["movimientos"].empty:
                _bk_accounts[_ak]["frames"].append(_fd["movimientos"])
            if _fd.get("meta"):
                _bk_accounts[_ak]["metas"].append(_fd["meta"])

        # Consolidado de todos los movimientos
        _bk_all_frames = [
            v["movimientos"] for v in _bk_loaded.values()
            if isinstance(v.get("movimientos"), pd.DataFrame) and not v["movimientos"].empty
        ]
        _bk_all = pd.concat(_bk_all_frames, ignore_index=True) if _bk_all_frames else pd.DataFrame()

        # ── Funcion auxiliar: dashboard completo por cuenta ───────────────
        def _render_bk_dashboard(df_full, aid, banco, cuenta, titular, periodos, metas):
            _CARD_BG   = "background:linear-gradient(135deg,#162640,#1E3550)"
            _per_str   = " · ".join(p for p in periodos if p) or "Periodo no detectado"
            _cta_disp  = cuenta or "N/D"
            _tit_disp  = titular or "Titular no detectado"
            st.markdown(
                '<div style="' + _CARD_BG + ';border-left:4px solid #2E75B6;'
                'border-radius:10px;padding:14px 20px;margin-bottom:14px;'
                'display:flex;justify-content:space-between;align-items:center">'
                '<div>'
                '<span style="font-size:1.5rem">🏦</span>'
                f'<strong style="color:#9DC3E6;font-size:1.1rem;margin-left:8px">{banco}</strong>'
                '<span style="color:#5A7090;margin:0 10px">|</span>'
                f'<code style="color:#70C995;font-size:1rem">Cta: {_cta_disp}</code>'
                '<span style="color:#5A7090;margin:0 10px">|</span>'
                f'<span style="color:#BDD3E8">{_tit_disp}</span>'
                '</div>'
                f'<div style="color:#5A7090;font-size:.8rem;text-align:right">{_per_str}</div>'
                '</div>',
                unsafe_allow_html=True
            )

            if df_full.empty:
                st.warning("⚠ No se encontraron movimientos para esta cuenta.")
                return

            # Filtros
            _fa, _fb, _fc, _fd_col = st.columns([3, 3, 2, 2])
            _df_w = df_full.copy()

            if "fecha" in _df_w.columns:
                _dates_s = pd.to_datetime(_df_w["fecha"], dayfirst=True, errors="coerce")
                _valid   = _dates_s.dropna()
                if not _valid.empty:
                    _mn = _valid.min().date()
                    _mx = _valid.max().date()
                    with _fa:
                        _f_d = st.date_input("📅 Desde", value=_mn,
                                             min_value=_mn, max_value=_mx,
                                             key=f"bk_fd_{aid}")
                    with _fb:
                        _f_h = st.date_input("📅 Hasta", value=_mx,
                                             min_value=_mn, max_value=_mx,
                                             key=f"bk_fh_{aid}")
                    _mask = (_dates_s >= pd.Timestamp(_f_d)) & (_dates_s <= pd.Timestamp(_f_h))
                    _df_w = _df_w[_mask.fillna(False)]
                else:
                    with _fa: st.empty()
                    with _fb: st.empty()
            else:
                with _fa: st.empty()
                with _fb: st.empty()

            with _fc:
                _cats  = sorted(_df_w["cat_label"].unique()) if "cat_label" in _df_w.columns else []
                _f_cat = st.multiselect("💡 Categoría", _cats, key=f"bk_fc_{aid}")
            with _fd_col:
                _busq = st.text_input("🔍 Buscar", key=f"bk_bq_{aid}",
                                      placeholder="DIAN, NOMINA, NEQUI...")

            if _f_cat: _df_w = _df_w[_df_w["cat_label"].isin(_f_cat)]
            if _busq:  _df_w = _df_w[_df_w["descripcion"].str.contains(_busq, case=False, na=False)]

            _fiscal = build_bank_fiscal_report(_df_w)
            _neto   = _fiscal["total_ingresos"] - _fiscal["total_egresos"]

            # KPIs fila 1: ingresos / egresos / flujo / saldo
            _k1, _k2, _k3, _k4 = st.columns(4)
            _n_ing = int((_df_w["credito"] > 0).sum()) if "credito" in _df_w.columns else 0
            _n_eg  = int((_df_w["debito"]  > 0).sum()) if "debito"  in _df_w.columns else 0
            _sal_f = (float(_df_w["saldo"].dropna().iloc[-1])
                      if "saldo" in _df_w.columns and not _df_w.empty else 0.0)
            with _k1: kpi_card("📈", "Ingresos",   fmt_cop(_fiscal["total_ingresos"]),
                                "#27AE60", subtitle=f"{_n_ing} créditos")
            with _k2: kpi_card("📉", "Egresos",    fmt_cop(_fiscal["total_egresos"]),
                                "#E74C3C", subtitle=f"{_n_eg} débitos")
            with _k3: kpi_card("⚖️", "Flujo Neto", fmt_cop(abs(_neto)),
                                "#70AD47" if _neto >= 0 else "#C00000",
                                subtitle="✅ Positivo" if _neto >= 0 else "⚠ Negativo")
            with _k4: kpi_card("💰", "Saldo Final", fmt_cop(_sal_f),
                                "#9DC3E6", subtitle=f"{len(_df_w):,} movimientos")

            # KPIs fila 2: fiscales
            _k5, _k6, _k7, _k8 = st.columns(4)
            with _k5: kpi_card("💸", "GMF / 4×1000",  fmt_cop(_fiscal["total_gmf"]),
                                "#E74C3C", subtitle="Gravamen movimiento")
            with _k6: kpi_card("🏦", "Int. Pagados",   fmt_cop(_fiscal["total_interes_pago"]),
                                "#E67E22", subtitle="Costo financiero")
            with _k7: kpi_card("💵", "Int. Recibidos", fmt_cop(_fiscal["total_interes_rcdo"]),
                                "#27AE60", subtitle="Rendimientos")
            with _k8: kpi_card("🔒", "Retenciones",    fmt_cop(_fiscal["total_retenciones"]),
                                "#8E44AD", subtitle="Retefuente / ICA")

            # Graficos
            _gc1, _gc2 = st.columns(2)
            if not _fiscal["timeline"].empty:
                with _gc1:
                    _tl = _fiscal["timeline"].melt("mes", var_name="Tipo", value_name="Valor")
                    _tl["Tipo"] = _tl["Tipo"].map({"debito": "Egresos", "credito": "Ingresos"})
                    _fb_fig = _px_bk.bar(
                        _tl, x="mes", y="Valor", color="Tipo", barmode="group",
                        title="Movimientos por Mes", template="plotly_dark",
                        color_discrete_map={"Egresos": "#E74C3C", "Ingresos": "#27AE60"},
                    )
                    _fb_fig.update_layout(
                        plot_bgcolor="#152238", paper_bgcolor="#0F1C33",
                        font_color="#E8EFF8", xaxis_title="",
                        yaxis=dict(tickformat="$,.0f"),
                        legend=dict(orientation="h", y=1.05),
                    )
                    st.plotly_chart(_fb_fig, use_container_width=True, key=f"bk_bar_{aid}")

            if "cat_label" in _df_w.columns and "debito" in _df_w.columns:
                with _gc2:
                    _pie_df = (
                        _df_w[_df_w["debito"] > 0]
                        .groupby("cat_label")["debito"].sum()
                        .reset_index()
                        .rename(columns={"cat_label": "Categoría", "debito": "Monto"})
                        .sort_values("Monto", ascending=False)
                        .head(8)
                    )
                    if not _pie_df.empty:
                        _fp_fig = _px_bk.pie(
                            _pie_df, names="Categoría", values="Monto",
                            title="Distribución Egresos",
                            template="plotly_dark", hole=0.4,
                        )
                        _fp_fig.update_layout(
                            paper_bgcolor="#0F1C33", font_color="#E8EFF8",
                            legend=dict(font=dict(size=10)),
                        )
                        st.plotly_chart(_fp_fig, use_container_width=True, key=f"bk_pie_{aid}")

            # Tabla categorias
            if not _fiscal["resumen_categoria"].empty:
                with st.expander("📋 Desglose Fiscal por Categoría", expanded=False):
                    _ct = _fiscal["resumen_categoria"].rename(
                        columns={"cat_label": "Categoría",
                                 "debito": "Egresos", "credito": "Ingresos"})
                    _ct_nums = [c for c in ["Egresos", "Ingresos"] if c in _ct.columns]
                    st.dataframe(
                        _ct.style
                           .format({c: "${:,.0f}" for c in _ct_nums})
                           .bar(subset=["Egresos"] if "Egresos" in _ct.columns else [],
                                color="#E74C3C", width=80),
                        use_container_width=True, height=280,
                        key=f"bk_cat_{aid}")

            # Tabla movimientos
            section_header(f"📑 Movimientos ({len(_df_w):,})")
            _te1, _te2, _ = st.columns([2, 2, 6])
            with _te1: _solo_eg = st.checkbox("Solo egresos",  key=f"bk_seg_{aid}")
            with _te2: _solo_in = st.checkbox("Solo ingresos", key=f"bk_sin_{aid}")

            _df_show = _df_w.copy()
            if _solo_eg: _df_show = _df_show[_df_show["debito"].fillna(0)  > 0]
            if _solo_in: _df_show = _df_show[_df_show["credito"].fillna(0) > 0]

            _vis  = [c for c in ["fecha", "cuenta", "descripcion", "debito",
                                  "credito", "saldo", "cat_label"]
                     if c in _df_show.columns]
            _rens = {"fecha": "Fecha", "cuenta": "Cuenta",
                     "descripcion": "Descripción", "debito": "Egreso",
                     "credito": "Ingreso", "saldo": "Saldo", "cat_label": "Categoría"}
            _nums = [_rens.get(c, c) for c in ["debito", "credito", "saldo"] if c in _vis]
            st.dataframe(
                _df_show[_vis].rename(columns=_rens)
                              .style.format({c: "${:,.0f}" for c in _nums}),
                use_container_width=True, height=400,
                key=f"bk_tbl_{aid}")

            # Exportar Excel
            _xl_buf  = _io_bk.BytesIO()
            _cta_fn  = (cuenta or aid).replace(" ", "_")[:15]
            _ban_fn  = banco.replace(" ", "_")[:10]
            _xl_name = f"extracto_{_cta_fn}_{_ban_fn}.xlsx"
            with pd.ExcelWriter(_xl_buf, engine="xlsxwriter") as _xw:
                _df_show[_vis].rename(columns=_rens).to_excel(
                    _xw, index=False, sheet_name="Movimientos")
                if not _fiscal["resumen_categoria"].empty:
                    _fiscal["resumen_categoria"].rename(
                        columns={"cat_label": "Categoría",
                                 "debito": "Egresos", "credito": "Ingresos"}
                    ).to_excel(_xw, index=False, sheet_name="Categorias")
                if not _fiscal["timeline"].empty:
                    _fiscal["timeline"].rename(
                        columns={"mes": "Mes", "debito": "Egresos", "credito": "Ingresos"}
                    ).to_excel(_xw, index=False, sheet_name="Por Mes")
                pd.DataFrame([
                    {"Indicador": "GMF / 4x1000",       "COP": _fiscal["total_gmf"]},
                    {"Indicador": "Intereses Pagados",   "COP": _fiscal["total_interes_pago"]},
                    {"Indicador": "Intereses Recibidos", "COP": _fiscal["total_interes_rcdo"]},
                    {"Indicador": "Retenciones",         "COP": _fiscal["total_retenciones"]},
                    {"Indicador": "Parafiscales",        "COP": _fiscal["total_parafiscales"]},
                    {"Indicador": "Impuestos",           "COP": _fiscal["total_impuestos"]},
                    {"Indicador": "Comisiones",          "COP": _fiscal["total_comisiones"]},
                    {"Indicador": "TOTAL INGRESOS",      "COP": _fiscal["total_ingresos"]},
                    {"Indicador": "TOTAL EGRESOS",       "COP": _fiscal["total_egresos"]},
                    {"Indicador": "FLUJO NETO",          "COP": _neto},
                ]).to_excel(_xw, index=False, sheet_name="KPIs Fiscales")
            st.download_button(
                f"📥 Exportar Excel — {banco} Cta {cuenta or 'N/D'}",
                data=_xl_buf.getvalue(),
                file_name=_xl_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"bk_dl_{aid}",
                use_container_width=True,
            )

        # ── Construir tabs dinamicos ──────────────────────────────────────
        # 1 tab "Consolidado" + 1 tab por cada cuenta detectada
        _acct_list  = list(_bk_accounts.items())
        _tab_labels = ["📊 Consolidado"]
        for _akey, _av in _acct_list:
            _cta_short = (_av["cuenta"] or "???")[-6:]
            _ban_short = _av["banco"][:9]
            _tab_labels.append(f"🏦 {_ban_short} ···{_cta_short}")

        _dyn_tabs = st.tabs(_tab_labels)

        # Tab 0: Consolidado de todas las cuentas
        with _dyn_tabs[0]:
            _render_bk_dashboard(
                _bk_all, "_conso",
                "Todas las cuentas", "",
                f"{len(_bk_accounts)} cuenta(s) cargada(s)",
                [], []
            )

        # Tabs 1..N: una por cada cuenta (auto-generado al cargar nuevos extractos)
        for _ti, (_akey, _av) in enumerate(_acct_list):
            _safe_id = re.sub(r"[^a-z0-9]", "_", _akey.lower())[:28]
            _acct_df = (pd.concat(_av["frames"], ignore_index=True)
                        if _av["frames"] else pd.DataFrame())
            with _dyn_tabs[_ti + 1]:
                _render_bk_dashboard(
                    _acct_df, _safe_id,
                    _av["banco"], _av["cuenta"],
                    _av["titular"], _av["periodos"], _av["metas"]
                )

    else:
        # Estado vacio
        st.markdown(
            '<div style="background:linear-gradient(135deg,#162640,#1E3550);'
            'border:2px dashed #2A4A70;border-radius:16px;'
            'padding:40px 28px;text-align:center;margin:16px 0">'
            '<div style="font-size:3.5rem;margin-bottom:14px">🏦</div>'
            '<h3 style="color:#9DC3E6;margin:0 0 8px 0">Sube tus Extractos Bancarios</h3>'
            '<p style="color:#6A8AAB;font-size:.9rem;margin:0 0 10px 0">'
            'Cada cuenta genera automaticamente su propio dashboard con '
            'KPIs fiscales, graficos y filtros por fecha y categoria'
            '</p>'
            '<div style="display:inline-flex;gap:10px;margin-bottom:18px">'
            '<span style="background:#1A3A5C;border-radius:20px;padding:4px 14px;'
            'color:#9DC3E6;font-size:.8rem">📄 PDF</span>'
            '<span style="background:#1A3A5C;border-radius:20px;padding:4px 14px;'
            'color:#70C995;font-size:.8rem">📊 Excel .xlsx</span>'
            '<span style="background:#1A3A5C;border-radius:20px;padding:4px 14px;'
            'color:#F0C060;font-size:.8rem">📋 Excel .xls</span>'
            '</div>'
            '<div style="display:grid;grid-template-columns:1fr 1fr;'
            'gap:8px;max-width:480px;margin:0 auto;text-align:left">'
            '<div style="color:#7A90AB;font-size:.8rem">📈 Ingresos / Egresos por cuenta</div>'
            '<div style="color:#7A90AB;font-size:.8rem">💸 GMF / 4x1000 automatico</div>'
            '<div style="color:#7A90AB;font-size:.8rem">🔒 Retenciones detectadas</div>'
            '<div style="color:#7A90AB;font-size:.8rem">🏦 Intereses pagados / recibidos</div>'
            '<div style="color:#7A90AB;font-size:.8rem">📅 Filtro por rango de fechas</div>'
            '<div style="color:#7A90AB;font-size:.8rem">📊 Graficos mes y categoria</div>'
            '</div>'
            '<p style="color:#4A6A8A;font-size:.75rem;margin:16px 0 0 0">'
            'Bancolombia · Davivienda · BBVA · Banco de Bogota · Nequi · Bold'
            '</p></div>',
            unsafe_allow_html=True
        )
