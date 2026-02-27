"""
Data loader and processor for DIAN electronic invoice files.
Handles VENTAS, COMPRAS, NÓMINA ELECTRÓNICA, INFORMACIÓN EXÓGENA and RETENCIONES.
v2: multi-company aware, extended hallazgos H1-H14.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import streamlit as st


# ─── Column mapping ────────────────────────────────────────────────────────────
COLUMNS = {
    "tipo": "Tipo de documento",
    "cufe": "CUFE/CUDE",
    "folio": "Folio",
    "prefijo": "Prefijo",
    "divisa": "Divisa",
    "forma_pago": "Forma de Pago",
    "medio_pago": "Medio de Pago",
    "fecha_emision": "Fecha Emisión",
    "fecha_recepcion": "Fecha Recepción",
    "nit_emisor": "NIT Emisor",
    "nombre_emisor": "Nombre Emisor",
    "nit_receptor": "NIT Receptor",
    "nombre_receptor": "Nombre Receptor",
    "iva": "IVA",
    "ica": "ICA",
    "ic": "IC",
    "inc": "INC",
    "timbre": "Timbre",
    "inc_bolsas": "INC Bolsas",
    "in_carbono": "IN Carbono",
    "in_combustibles": "IN Combustibles",
    "ic_datos": "IC Datos",
    "icl": "ICL",
    "inpp": "INPP",
    "ibua": "IBUA",
    "icui": "ICUI",
    "rete_iva": "Rete IVA",
    "rete_renta": "Rete Renta",
    "rete_ica": "Rete ICA",
    "total": "Total",
    "estado": "Estado",
    "grupo": "Grupo",
}

TAX_COLS = ["IVA", "ICA", "IC", "INC", "ICL", "INPP", "IBUA", "ICUI",
            "Rete IVA", "Rete Renta", "Rete ICA"]
NUMERIC_COLS = TAX_COLS + ["Total"]


# ─── Loader ────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_file(path: str) -> pd.DataFrame:
    """Load a DIAN report Excel file. Row 1 = totals, Row 2 = headers, Data from Row 3."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()

    # Read raw — detect format automatically
    # Formato antiguo: fila 0 = título/totales, fila 1 = headers, fila 2+ = datos
    # Formato nuevo (DIAN directo): fila 0 = headers, fila 1+ = datos
    raw = pd.read_excel(path, header=None, dtype=str)
    _first_cell = str(raw.iloc[0, 0]).strip().lower() if len(raw) > 0 else ""
    if _first_cell == "tipo de documento":
        # Nuevo formato: headers en fila 0
        headers = raw.iloc[0].tolist()
        data    = raw.iloc[1:].copy()
    else:
        # Formato antiguo: headers en fila 1, datos desde fila 2
        headers = raw.iloc[1].tolist() if len(raw) > 1 else raw.iloc[0].tolist()
        data    = raw.iloc[2:].copy()  if len(raw) > 2 else raw.iloc[1:].copy()
    data.columns = headers
    data = data.reset_index(drop=True)

    # Normalizar nombres de columna (strip + fix encoding issues)
    data.columns = [str(c).strip() for c in data.columns]
    _enc_fixes = {
        "Fecha Emisión": ["Fecha Emisi\xf3n", "Fecha Emision", "Fecha emisión", "fecha emisión"],
        "Fecha Recepción": ["Fecha Recepci\xf3n", "Fecha Recepcion", "fecha recepción"],
        "Tipo de documento": ["Tipo De Documento", "tipo de documento"],
    }
    _col_rename = {}
    for _correct, _variants in _enc_fixes.items():
        for _col in data.columns:
            if _col in _variants:
                _col_rename[_col] = _correct
    if _col_rename:
        data = data.rename(columns=_col_rename)

    # Clean numeric columns
    for col in NUMERIC_COLS:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    # Parse dates
    for dcol in ["Fecha Emisión", "Fecha Recepción"]:
        if dcol in data.columns:
            data[dcol] = pd.to_datetime(data[dcol], errors="coerce", dayfirst=True)

    # Derived columns
    if "Total" in data.columns and "IVA" in data.columns:
        data["Base"] = data["Total"] - data["IVA"]

    if "Fecha Emisión" in data.columns:
        data["Mes"] = data["Fecha Emisión"].dt.to_period("M").astype(str)
        data["Bimestre"] = data["Fecha Emisión"].apply(_bimestre)
        data["Semana"] = data["Fecha Emisión"].dt.isocalendar().week.astype(str)

    # Document type short label
    if "Tipo de documento" in data.columns:
        data["Tipo_Label"] = data["Tipo de documento"].apply(_shorten_tipo)

    return data


def _shorten_tipo(val):
    if pd.isna(val):
        return "Desconocido"
    v = str(val).lower()
    if "nota crédito" in v or "nota credito" in v:
        return "Nota Crédito"
    if "nota débito" in v or "nota debito" in v:
        return "Nota Débito"
    if "electrónica" in v or "electronica" in v:
        return "Factura Electrónica"
    if "contingencia" in v:
        return "Contingencia"
    return str(val)


def _bimestre(fecha):
    if pd.isna(fecha):
        return "Sin fecha"
    mes = fecha.month
    anio = fecha.year
    bim = ((mes - 1) // 2) + 1
    meses = {1: "Ene-Feb", 2: "Mar-Abr", 3: "May-Jun",
             4: "Jul-Ago", 5: "Sep-Oct", 6: "Nov-Dic"}
    return f"Bim {bim} ({meses.get(bim,'')}) {anio}"


# ─── KPIs ──────────────────────────────────────────────────────────────────────
def compute_kpis(ventas: pd.DataFrame, compras: pd.DataFrame) -> dict:
    """Compute main KPIs for the executive dashboard."""
    kpis = {}

    # Ventas
    ventas_fe = ventas[ventas["Tipo_Label"] == "Factura Electrónica"] if "Tipo_Label" in ventas.columns else ventas
    compras_fe = compras[compras["Tipo_Label"] == "Factura Electrónica"] if "Tipo_Label" in compras.columns else compras

    kpis["total_ventas"] = ventas["Total"].sum() if "Total" in ventas.columns else 0
    kpis["total_compras"] = compras["Total"].sum() if "Total" in compras.columns else 0
    kpis["iva_generado"] = ventas["IVA"].sum() if "IVA" in ventas.columns else 0
    kpis["iva_descontable"] = compras["IVA"].sum() if "IVA" in compras.columns else 0
    kpis["iva_neto"] = kpis["iva_generado"] - kpis["iva_descontable"]
    kpis["base_ventas"] = ventas["Base"].sum() if "Base" in ventas.columns else 0
    kpis["base_compras"] = compras["Base"].sum() if "Base" in compras.columns else 0
    kpis["margen_bruto"] = (
        (kpis["base_ventas"] - kpis["base_compras"]) / kpis["base_ventas"] * 100
        if kpis["base_ventas"] > 0 else 0
    )
    kpis["num_facturas_ventas"] = len(ventas_fe)
    kpis["num_facturas_compras"] = len(compras_fe)
    kpis["notas_credito_ventas"] = len(ventas[ventas["Tipo_Label"] == "Nota Crédito"]) if "Tipo_Label" in ventas.columns else 0
    kpis["notas_credito_compras"] = len(compras[compras["Tipo_Label"] == "Nota Crédito"]) if "Tipo_Label" in compras.columns else 0

    # Top clientes / proveedores
    if "Nombre Receptor" in ventas.columns and "Total" in ventas.columns:
        top_clientes = (
            ventas.groupby("Nombre Receptor")["Total"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
        top_clientes.columns = ["Cliente", "Total"]
        kpis["top_clientes"] = top_clientes
    else:
        kpis["top_clientes"] = pd.DataFrame()

    if "Nombre Emisor" in compras.columns and "Total" in compras.columns:
        top_proveedores = (
            compras.groupby("Nombre Emisor")["Total"]
            .sum()
            .sort_values(ascending=False)
            .head(10)
            .reset_index()
        )
        top_proveedores.columns = ["Proveedor", "Total"]
        kpis["top_proveedores"] = top_proveedores
    else:
        kpis["top_proveedores"] = pd.DataFrame()

    return kpis


# ─── Audit findings ─────────────────────────────────────────────────────────
def detect_hallazgos(ventas: pd.DataFrame, compras: pd.DataFrame) -> list[dict]:
    """Detect audit findings and return list of findings with risk level."""
    hallazgos = []

    # H1: Notas crédito en ventas reducen base gravable
    nc_ventas = ventas[ventas["Tipo_Label"] == "Nota Crédito"] if "Tipo_Label" in ventas.columns else pd.DataFrame()
    if len(nc_ventas) > 0:
        impacto = nc_ventas["Total"].sum()
        hallazgos.append({
            "codigo": "H1",
            "nivel": "🟡 MEDIO",
            "color": "#FFFACD",
            "area": "Ventas",
            "descripcion": f"Se detectaron {len(nc_ventas)} nota(s) crédito en ventas por valor total de ${impacto:,.0f} COP. "
                           "Estas reducen la base gravable de ingresos reportados.",
            "cuenta": "4135 / 2408",
            "impacto": abs(impacto),
            "norma": "Art. 481 ET — Notas crédito electrónicas DIAN Res. 000042/2020",
            "procedimiento": "1. Verificar que cada NC tenga relación con FE original. "
                             "2. Confirmar que la base neta concilia con declaraciones IVA. "
                             "3. Revisar contabilización en cuenta 4135.",
        })

    # H2: Notas crédito en compras reducen IVA descontable
    nc_compras = compras[compras["Tipo_Label"] == "Nota Crédito"] if "Tipo_Label" in compras.columns else pd.DataFrame()
    if len(nc_compras) > 0:
        impacto = nc_compras["IVA"].sum() if "IVA" in nc_compras.columns else 0
        hallazgos.append({
            "codigo": "H2",
            "nivel": "🟡 MEDIO",
            "color": "#FFFACD",
            "area": "Compras",
            "descripcion": f"Se detectaron {len(nc_compras)} nota(s) crédito en compras. "
                           f"IVA descontable reducido: ${impacto:,.0f} COP.",
            "cuenta": "1355 / 2408",
            "impacto": abs(impacto),
            "norma": "Art. 485 ET — IVA Descontable; Resolución DIAN 000042/2020",
            "procedimiento": "1. Cruzar NC con FE recibida original. "
                             "2. Ajustar IVA descontable en Form. 300. "
                             "3. Verificar reversión contable en 1355.",
        })

    # H3: IVA neto a pagar/favor
    iva_neto = (ventas["IVA"].sum() if "IVA" in ventas.columns else 0) - \
               (compras["IVA"].sum() if "IVA" in compras.columns else 0)
    if abs(iva_neto) > 0:
        if iva_neto > 0:
            nivel = "🔴 ALTO"
            color = "#FCE4D6"
            desc = f"IVA neto a pagar estimado: ${iva_neto:,.0f} COP. Verificar que esté declarado."
        else:
            nivel = "⚪ BAJO-MEDIO"
            color = "#E8F5E9"
            desc = f"IVA a favor estimado: ${abs(iva_neto):,.0f} COP. Verificar solicitud de devolución o compensación."
        hallazgos.append({
            "codigo": "H3",
            "nivel": nivel,
            "color": color,
            "area": "IVA",
            "descripcion": desc,
            "cuenta": "2408 / 1355",
            "impacto": abs(iva_neto),
            "norma": "Art. 477-513 ET — Declaración bimestral IVA Form. 300",
            "procedimiento": "1. Extraer saldo cuenta 2408 del balance. "
                             "2. Restar saldo cuenta 1355. "
                             "3. Comparar con Form. 300 presentados.",
        })

    # H4: Facturas sin CUFE (posible contingencia)
    if "CUFE/CUDE" in compras.columns:
        sin_cufe = compras[compras["CUFE/CUDE"].isna() | (compras["CUFE/CUDE"] == "")]
        if len(sin_cufe) > 0:
            hallazgos.append({
                "codigo": "H4",
                "nivel": "🟠 MEDIO-ALTO",
                "color": "#FFF0E0",
                "area": "Compras",
                "descripcion": f"{len(sin_cufe)} factura(s) de compra sin CUFE/CUDE. "
                               "Pueden ser documentos de contingencia o no validados DIAN.",
                "cuenta": "Múltiples cuentas de costo",
                "impacto": sin_cufe["Total"].sum(),
                "norma": "Resolución DIAN 000042/2020 — Factura electrónica obligatoria",
                "procedimiento": "1. Solicitar FE válida al proveedor. "
                                 "2. Si es contingencia, verificar consecutivo habilitado. "
                                 "3. Rechazar deducción si no hay FE válida.",
            })

    # H5: Proveedores con alta concentración (>30% compras)
    if "Nombre Emisor" in compras.columns:
        prov_total = compras.groupby("Nombre Emisor")["Total"].sum()
        total_comp = prov_total.sum()
        if total_comp > 0:
            concentradas = prov_total[prov_total / total_comp > 0.30]
            for proveedor, valor in concentradas.items():
                pct = valor / total_comp * 100
                hallazgos.append({
                    "codigo": f"H5",
                    "nivel": "⚪ BAJO-MEDIO",
                    "color": "#F3F3F3",
                    "area": "Compras",
                    "descripcion": f"Proveedor '{proveedor}' representa el {pct:.1f}% de las compras totales "
                                   f"(${valor:,.0f} COP). Alta concentración de proveedor.",
                    "cuenta": "61xx / 51xx",
                    "impacto": valor,
                    "norma": "Principio de diversificación — Gestión de riesgo proveedor",
                    "procedimiento": "1. Evaluar dependencia comercial. "
                                     "2. Verificar precios de mercado. "
                                     "3. Documentar política de compras.",
                })

    # H6: Retenciones en compras
    if "Rete Renta" in compras.columns:
        total_rte = compras["Rete Renta"].sum()
        if total_rte > 0:
            hallazgos.append({
                "codigo": "H6",
                "nivel": "🟣 MEDIO",
                "color": "#F3E5F5",
                "area": "Retenciones",
                "descripcion": f"Retención en fuente practicada en compras: ${total_rte:,.0f} COP. "
                               "Verificar declaración Form. 350 y pago oportuno.",
                "cuenta": "2365",
                "impacto": total_rte,
                "norma": "Art. 365-419 ET — Retención en la Fuente; Form. 350 DIAN",
                "procedimiento": "1. Cruzar con Form. 350 presentado. "
                                 "2. Verificar tarifa aplicada por concepto. "
                                 "3. Confirmar pago oportuno (máx. día 22 mes siguiente).",
            })

    return hallazgos


# ─── Nómina Electrónica parser ────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_nomina(path_or_bytes) -> pd.DataFrame:
    """
    Parse Nómina Electrónica DIAN export (.xlsx).
    DIAN portal: Facturación Electrónica > Nómina Electrónica > Reporte
    Expected columns (flexible): Empleado, NIT, Período, Devengado, Deducido,
    Rete Fuente, Salud, Pensión, Total, Estado.
    Also handles the same 32-column FE format if nómina was exported that way.
    """
    try:
        if isinstance(path_or_bytes, (str, Path)):
            raw = pd.read_excel(path_or_bytes, header=None)
        else:
            raw = pd.read_excel(path_or_bytes, header=None)
    except Exception:
        return pd.DataFrame()

    # Detect header row (first row with text content)
    header_row = 0
    for i, row in raw.iterrows():
        non_null = row.dropna()
        if len(non_null) >= 3 and any(isinstance(v, str) for v in non_null):
            header_row = i
            break

    headers = raw.iloc[header_row].tolist()
    data = raw.iloc[header_row + 1:].copy()
    data.columns = headers
    data = data.reset_index(drop=True)
    data = data.dropna(how="all")

    # Normalize common nomina column names
    rename_map = {
        col: col for col in data.columns  # keep as-is first
    }
    # Try to identify key columns by content patterns
    _nomina_numeric = []
    for col in data.columns:
        if col and isinstance(col, str):
            low = col.lower()
            if any(k in low for k in ["devengado", "bruto", "salario base"]):
                rename_map[col] = "Devengado"
            elif any(k in low for k in ["deducido", "deduccion", "descuento"]):
                rename_map[col] = "Deducido"
            elif any(k in low for k in ["rete", "retencion", "ret. fuente"]):
                rename_map[col] = "Rete Fuente"
            elif any(k in low for k in ["salud", "eps"]):
                rename_map[col] = "Salud Empleado"
            elif any(k in low for k in ["pension", "afp"]):
                rename_map[col] = "Pension Empleado"
            elif any(k in low for k in ["total", "neto", "pagar"]) and "dev" not in low:
                rename_map[col] = "Total Pagar"
            elif any(k in low for k in ["nombre", "empleado", "trabajador"]):
                rename_map[col] = "Nombre Empleado"
            elif any(k in low for k in ["nit", "cedula", "identificacion"]):
                rename_map[col] = "NIT Empleado"
            elif any(k in low for k in ["fecha", "periodo", "período"]):
                rename_map[col] = "Periodo"

    data = data.rename(columns={k: v for k, v in rename_map.items() if k != v})

    # Numeric coerce
    num_cols = ["Devengado", "Deducido", "Rete Fuente", "Salud Empleado",
                "Pension Empleado", "Total Pagar"]
    for col in num_cols:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    # Fallback: if no Devengado found, treat "Total" as Devengado
    if "Devengado" not in data.columns and "Total" in data.columns:
        data["Devengado"] = pd.to_numeric(data["Total"], errors="coerce").fillna(0)

    # Date
    if "Periodo" in data.columns:
        data["Periodo"] = pd.to_datetime(data["Periodo"], errors="coerce", dayfirst=True)
        data["Mes"] = data["Periodo"].dt.to_period("M").astype(str)

    return data


def compute_nomina_kpis(nomina: pd.DataFrame) -> dict:
    if nomina.empty:
        return {}
    kpis = {}
    kpis["total_devengado"]    = nomina["Devengado"].sum()    if "Devengado"       in nomina.columns else 0
    kpis["total_deducido"]     = nomina["Deducido"].sum()     if "Deducido"        in nomina.columns else 0
    kpis["total_rete_fuente"]  = nomina["Rete Fuente"].sum()  if "Rete Fuente"     in nomina.columns else 0
    kpis["total_pagar"]        = nomina["Total Pagar"].sum()  if "Total Pagar"     in nomina.columns else 0
    kpis["num_empleados"]      = nomina["NIT Empleado"].nunique() if "NIT Empleado" in nomina.columns else len(nomina)
    # Carga patronal estimada (~38.5% sobre devengado)
    kpis["carga_patronal_est"] = kpis["total_devengado"] * 0.385
    kpis["costo_laboral_total"] = kpis["total_devengado"] + kpis["carga_patronal_est"]
    return kpis


# ─── Información Exógena parser ───────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_exogena(path_or_bytes) -> pd.DataFrame:
    """
    Parse Información Exógena / Medios Magnéticos DIAN.
    Formatos 1001 (pagos a terceros), 1007 (ingresos recibidos),
    1008 (saldos en cuentas bancarias), etc.
    Flexible parser: detects columns by name patterns.
    """
    try:
        if isinstance(path_or_bytes, (str, Path)):
            raw = pd.read_excel(path_or_bytes, header=None)
        else:
            raw = pd.read_excel(path_or_bytes, header=None)
    except Exception:
        return pd.DataFrame()

    # Find header row
    header_row = 0
    for i, row in raw.iterrows():
        non_null = row.dropna()
        if len(non_null) >= 4:
            header_row = i
            break

    headers = raw.iloc[header_row].tolist()
    data = raw.iloc[header_row + 1:].copy()
    data.columns = headers
    data = data.reset_index(drop=True).dropna(how="all")

    # Normalize column names
    rename_map = {}
    for col in data.columns:
        if not isinstance(col, str):
            continue
        low = col.lower()
        if any(k in low for k in ["nit tercero", "nit del", "identificacion"]):
            rename_map[col] = "NIT Tercero"
        elif any(k in low for k in ["nombre", "razon social", "razón"]):
            rename_map[col] = "Nombre Tercero"
        elif any(k in low for k in ["concepto", "formato"]):
            rename_map[col] = "Concepto"
        elif any(k in low for k in ["valor bruto", "monto", "valor pagado", "ingreso"]):
            rename_map[col] = "Valor Bruto"
        elif any(k in low for k in ["retencion", "retención", "rete"]):
            rename_map[col] = "Retencion"
        elif any(k in low for k in ["valor neto", "neto"]):
            rename_map[col] = "Valor Neto"
        elif any(k in low for k in ["periodo", "período", "año", "anio"]):
            rename_map[col] = "Periodo"

    data = data.rename(columns={k: v for k, v in rename_map.items() if k != v})

    for col in ["Valor Bruto", "Retencion", "Valor Neto"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    return data


# ─── Retenciones Practicadas parser ──────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_retenciones(path_or_bytes) -> pd.DataFrame:
    """
    Parse retenciones practicadas / certificados de retención DIAN.
    Columns: Agente retenedor, NIT, Concepto, Base, Tarifa %, Valor retenido, Período.
    """
    try:
        if isinstance(path_or_bytes, (str, Path)):
            raw = pd.read_excel(path_or_bytes, header=None)
        else:
            raw = pd.read_excel(path_or_bytes, header=None)
    except Exception:
        return pd.DataFrame()

    header_row = 0
    for i, row in raw.iterrows():
        if len(row.dropna()) >= 3:
            header_row = i
            break

    headers = raw.iloc[header_row].tolist()
    data = raw.iloc[header_row + 1:].copy()
    data.columns = headers
    data = data.reset_index(drop=True).dropna(how="all")

    rename_map = {}
    for col in data.columns:
        if not isinstance(col, str):
            continue
        low = col.lower()
        if "agente" in low or "retenedor" in low:
            rename_map[col] = "Agente Retenedor"
        elif "nit" in low:
            rename_map[col] = "NIT Retenedor"
        elif "concepto" in low:
            rename_map[col] = "Concepto"
        elif "base" in low:
            rename_map[col] = "Base"
        elif "tarifa" in low or "%" in low:
            rename_map[col] = "Tarifa"
        elif "valor" in low or "retenido" in low or "retencion" in low.replace("ó","o"):
            rename_map[col] = "Valor Retenido"
        elif "periodo" in low or "período" in low:
            rename_map[col] = "Periodo"

    data = data.rename(columns={k: v for k, v in rename_map.items() if k != v})

    for col in ["Base", "Tarifa", "Valor Retenido"]:
        if col in data.columns:
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

    return data


# ─── Extended hallazgos H7-H14 ───────────────────────────────────────────────
def detect_hallazgos_extended(
    ventas: pd.DataFrame,
    compras: pd.DataFrame,
    nomina: pd.DataFrame = None,
    exogena: pd.DataFrame = None,
    retenciones: pd.DataFrame = None,
) -> list[dict]:
    """Detect H7-H14 based on cross-referencing additional DIAN data."""
    hallazgos = []

    # H7: Empleados en nómina sin retención en fuente
    if nomina is not None and not nomina.empty:
        if "Rete Fuente" in nomina.columns and "Devengado" in nomina.columns:
            # Employees earning > 4.1M COP (aprox. retención threshold 2026)
            UMBRAL_RENTA = 4_100_000
            alto_ingreso = nomina[nomina["Devengado"] > UMBRAL_RENTA]
            sin_rete = alto_ingreso[alto_ingreso["Rete Fuente"] == 0] if len(alto_ingreso) > 0 else pd.DataFrame()
            if len(sin_rete) > 0:
                impacto = sin_rete["Devengado"].sum() * 0.04  # aprox. 4% retención
                hallazgos.append({
                    "codigo": "H7",
                    "nivel": "🔴 ALTO",
                    "color": "#FCE4D6",
                    "area": "Nómina",
                    "descripcion": f"{len(sin_rete)} empleado(s) con devengado > $4.1M sin retención en fuente registrada. "
                                   f"Base total afectada: ${sin_rete['Devengado'].sum():,.0f} COP.",
                    "cuenta": "2370 / 5105",
                    "impacto": impacto,
                    "norma": "Art. 383-387 ET — Tabla de retención en la fuente para asalariados",
                    "procedimiento": "1. Verificar tabla de retención Art. 383 ET. "
                                     "2. Calcular retención mensual por empleado. "
                                     "3. Presentar corrección Form. 350 si aplica. "
                                     "4. Pagar intereses de mora Art. 634 ET.",
                })

        # H8: Carga patronal estimada
        kpis_nom = compute_nomina_kpis(nomina)
        if kpis_nom.get("total_devengado", 0) > 0:
            carga = kpis_nom["carga_patronal_est"]
            hallazgos.append({
                "codigo": "H8",
                "nivel": "🟡 MEDIO",
                "color": "#FFFACD",
                "area": "Nómina",
                "descripcion": f"Carga patronal estimada (38.5% s/devengado): ${carga:,.0f} COP. "
                               f"Devengado total: ${kpis_nom['total_devengado']:,.0f} COP. "
                               "Verificar gasto contable cuentas 51xx/52xx.",
                "cuenta": "2370 / 2380 / 5110",
                "impacto": carga,
                "norma": "CST Art. 204 — Salud: 8.5%; Art. 33 Ley 100/93 — Pensión: 12%; SENA 2%, ICBF 3%",
                "procedimiento": "1. Cruzar planilla PILA con nómina electrónica. "
                                 "2. Verificar pagos UGPP. "
                                 "3. Conciliar con cuentas 2370, 2380, 2390.",
            })

    # H9: Exógena — clientes reportados sin FE correspondiente
    if exogena is not None and not exogena.empty and not ventas.empty:
        if "NIT Tercero" in exogena.columns and "Valor Bruto" in exogena.columns:
            if "NIT Receptor" in ventas.columns:
                nits_fe = set(ventas["NIT Receptor"].dropna().astype(str))
                sin_fe = exogena[~exogena["NIT Tercero"].astype(str).isin(nits_fe)]
                if len(sin_fe) > 0:
                    impacto = sin_fe["Valor Bruto"].sum()
                    hallazgos.append({
                        "codigo": "H9",
                        "nivel": "🟠 MEDIO-ALTO",
                        "color": "#FFF0E0",
                        "area": "Exógena",
                        "descripcion": f"{len(sin_fe)} tercero(s) en información exógena sin factura electrónica correspondiente. "
                                       f"Valor total: ${impacto:,.0f} COP. Posible ingreso no facturado.",
                        "cuenta": "4135 / 2408",
                        "impacto": impacto,
                        "norma": "Art. 616-1 ET — Obligación de facturar; Res. DIAN 000042/2020",
                        "procedimiento": "1. Listar terceros en exógena sin FE. "
                                         "2. Verificar si operación está exenta de facturación. "
                                         "3. Emitir FE retroactiva si aplica o documentar excepción.",
                    })

    # H10: Exógena — diferencia > 5% entre exógena proveedores y compras FE
    if exogena is not None and not exogena.empty and not compras.empty:
        if "Valor Bruto" in exogena.columns and "Total" in compras.columns:
            total_exogena = exogena["Valor Bruto"].sum()
            total_compras = compras["Total"].sum()
            if total_compras > 0:
                diff_pct = abs(total_exogena - total_compras) / total_compras * 100
                if diff_pct > 5:
                    hallazgos.append({
                        "codigo": "H10",
                        "nivel": "🟠 MEDIO-ALTO",
                        "color": "#FFF0E0",
                        "area": "Exógena",
                        "descripcion": f"Diferencia del {diff_pct:.1f}% entre exógena proveedores "
                                       f"(${total_exogena:,.0f}) y compras FE (${total_compras:,.0f}). "
                                       "Diferencia supera umbral 5%.",
                        "cuenta": "61xx / 1355",
                        "impacto": abs(total_exogena - total_compras),
                        "norma": "Art. 771-2 ET — Procedencia de costos y deducciones",
                        "procedimiento": "1. Cruzar NIT a NIT exógena vs FE recibidas. "
                                         "2. Identificar diferencias por proveedor. "
                                         "3. Solicitar corrección de exógena o FE según corresponda.",
                    })

    # H11: Retenciones sufridas sin certificados
    if retenciones is not None and not retenciones.empty:
        if "Valor Retenido" in retenciones.columns:
            total_ret_sufrida = retenciones["Valor Retenido"].sum()
            if total_ret_sufrida > 0:
                hallazgos.append({
                    "codigo": "H11",
                    "nivel": "🟣 MEDIO",
                    "color": "#F3E5F5",
                    "area": "Retenciones",
                    "descripcion": f"Retenciones sufridas cargadas: ${total_ret_sufrida:,.0f} COP. "
                                   "Verificar que todos los certificados estén recibidos y cruzados en cuenta 1355-05.",
                    "cuenta": "1355-05 / 2365",
                    "impacto": total_ret_sufrida,
                    "norma": "Art. 374-378 ET — Certificados de retención",
                    "procedimiento": "1. Solicitar certificados a todos los agentes retenedores. "
                                     "2. Cruzar con saldo 1355-05. "
                                     "3. Imputar en declaración renta Form. 110.",
                })

    # H12: IVA multi-período — variación > 30%
    if not ventas.empty and "Bimestre" in ventas.columns and "IVA" in ventas.columns:
        bim_iva = ventas.groupby("Bimestre")["IVA"].sum()
        if len(bim_iva) >= 2:
            vals = bim_iva.values
            for i in range(1, len(vals)):
                if vals[i - 1] > 0:
                    var = abs(vals[i] - vals[i - 1]) / vals[i - 1] * 100
                    if var > 30:
                        hallazgos.append({
                            "codigo": "H12",
                            "nivel": "🟡 MEDIO",
                            "color": "#FFFACD",
                            "area": "IVA",
                            "descripcion": f"Variación de IVA generado entre bimestres: {var:.0f}%. "
                                           "Variación > 30% puede generar alerta automática DIAN (AOR).",
                            "cuenta": "2408",
                            "impacto": abs(vals[i] - vals[i - 1]),
                            "norma": "Programa AOR DIAN — Análisis de Riesgo Omisión; Art. 648 ET",
                            "procedimiento": "1. Documentar causa de variación (estacionalidad, cambio negocio). "
                                             "2. Preparar respuesta ante posible requerimiento DIAN. "
                                             "3. Conservar soportes de transacciones del bimestre con mayor IVA.",
                        })
                        break  # only report once

    # H13: Retención en compras pero sin declaración esperada
    if not compras.empty and "Rete Renta" in compras.columns:
        rte_compras = compras["Rete Renta"].sum()
        if rte_compras > 0 and (retenciones is None or retenciones.empty):
            hallazgos.append({
                "codigo": "H13",
                "nivel": "🟣 MEDIO",
                "color": "#F3E5F5",
                "area": "Retenciones",
                "descripcion": f"Se detectaron retenciones practicadas en compras (${rte_compras:,.0f} COP) "
                               "pero no se cargó archivo de Form. 350. Verificar declaración.",
                "cuenta": "2365",
                "impacto": rte_compras,
                "norma": "Art. 365 ET — Agente de retención; Form. 350 DIAN",
                "procedimiento": "1. Cargar archivo Form. 350 en módulo Retenciones. "
                                 "2. Verificar que monto declarado = monto practicado. "
                                 "3. Pagar diferencias + intereses si hay mora.",
            })

    # H14: Empleados nómina sin aportes seguridad social visibles
    if nomina is not None and not nomina.empty:
        if "Salud Empleado" in nomina.columns and "Pension Empleado" in nomina.columns:
            sin_aportes = nomina[
                (nomina["Salud Empleado"] == 0) & (nomina["Pension Empleado"] == 0)
            ]
            if len(sin_aportes) > len(nomina) * 0.1:  # más del 10% sin aportes
                impacto = sin_aportes["Devengado"].sum() * 0.085 if "Devengado" in sin_aportes.columns else 0
                hallazgos.append({
                    "codigo": "H14",
                    "nivel": "🔴 ALTO",
                    "color": "#FCE4D6",
                    "area": "Nómina",
                    "descripcion": f"{len(sin_aportes)} empleado(s) sin aportes salud/pensión visibles en nómina. "
                                   "Posible incumplimiento UGPP.",
                    "cuenta": "2370 / 2380",
                    "impacto": impacto,
                    "norma": "Ley 100/1993 Art. 204 — Cotizaciones obligatorias; Decreto 780/2016 UGPP",
                    "procedimiento": "1. Cruzar planilla PILA con nómina electrónica. "
                                     "2. Verificar si empleado es independiente (exento). "
                                     "3. Reportar a UGPP si hay incumplimiento.",
                })

    return hallazgos


# ─── IVA Conciliation ──────────────────────────────────────────────────────────
def build_iva_conciliation(ventas: pd.DataFrame, compras: pd.DataFrame) -> pd.DataFrame:
    """Build bimestral IVA conciliation table."""
    records = []

    for df, label in [(ventas, "Ventas"), (compras, "Compras")]:
        if "Bimestre" not in df.columns or "IVA" not in df.columns:
            continue
        grp = df.groupby("Bimestre").agg(
            Total=("Total", "sum"),
            IVA=("IVA", "sum"),
            Documentos=("Total", "count"),
        ).reset_index()
        grp["Tipo"] = label
        records.append(grp)

    if not records:
        return pd.DataFrame()

    combined = pd.concat(records, ignore_index=True)

    # Pivot for conciliation view
    pivot = combined.pivot_table(
        index="Bimestre",
        columns="Tipo",
        values=["Total", "IVA", "Documentos"],
        aggfunc="sum",
        fill_value=0,
    )
    pivot.columns = [f"{b}_{a}" for a, b in pivot.columns]
    pivot = pivot.reset_index()

    # Add computed columns if both sides exist
    if "IVA_Ventas" in pivot.columns and "IVA_Compras" in pivot.columns:
        pivot["IVA_Neto"] = pivot["IVA_Ventas"] - pivot["IVA_Compras"]
        pivot["Posicion"] = pivot["IVA_Neto"].apply(
            lambda x: "A PAGAR" if x > 0 else "A FAVOR"
        )

    return pivot


# ─── Reportes globales de Clientes y Proveedores ──────────────────────────────

def build_client_summary(ventas: pd.DataFrame) -> pd.DataFrame:
    """Resumen de TODOS los clientes con métricas completas por período.
    Retorna: Nombre Receptor, NIT Receptor, Facturas, Períodos, Total, Base, IVA, Rete Renta
    Ordenado por Total descendente.
    """
    if ventas.empty or "Nombre Receptor" not in ventas.columns:
        return pd.DataFrame()

    group_cols = ["Nombre Receptor"]
    if "NIT Receptor" in ventas.columns:
        group_cols.append("NIT Receptor")

    agg_cols = {}
    if "CUFE/CUDE" in ventas.columns:
        agg_cols["CUFE/CUDE"] = "count"
    elif "Folio" in ventas.columns:
        agg_cols["Folio"] = "count"
    else:
        ventas = ventas.copy(); ventas["_n"] = 1; agg_cols["_n"] = "count"

    if "Total" in ventas.columns:       agg_cols["Total"] = "sum"
    if "Base" in ventas.columns:        agg_cols["Base"] = "sum"
    if "IVA" in ventas.columns:         agg_cols["IVA"] = "sum"
    if "Rete Renta" in ventas.columns:  agg_cols["Rete Renta"] = "sum"
    if "Rete ICA" in ventas.columns:    agg_cols["Rete ICA"] = "sum"
    if "Mes" in ventas.columns:         agg_cols["Mes"] = "nunique"

    grp = ventas.groupby(group_cols, as_index=False).agg(agg_cols)

    # Renombrar conteo a "Facturas" y meses únicos a "Períodos"
    rename = {}
    for c in ["CUFE/CUDE", "Folio", "_n"]:
        if c in grp.columns:
            rename[c] = "Facturas"; break
    if "Mes" in grp.columns:
        rename["Mes"] = "Períodos"
    grp = grp.rename(columns=rename)

    # ── Flags de responsabilidad fiscal (inferidos de los datos de facturas) ──
    grp["Resp_IVA"]    = grp["IVA"].gt(0)        if "IVA"       in grp.columns else False
    grp["Ret_Renta"]   = grp["Rete Renta"].gt(0) if "Rete Renta" in grp.columns else False
    grp["Ret_ICA"]     = grp["Rete ICA"].gt(0)   if "Rete ICA"  in grp.columns else False
    grp["Gran_Contrib"] = grp["Total"].gt(500_000_000) if "Total" in grp.columns else False

    def _cl_badges(row):
        b = []
        if row.get("Resp_IVA"):     b.append("IVA ✓")
        if row.get("Ret_Renta"):    b.append("Renta ✓")
        if row.get("Ret_ICA"):      b.append("ICA ✓")
        if row.get("Gran_Contrib"): b.append("⭐ Gran Cont.")
        return " | ".join(b) if b else "—"

    grp["Obligaciones"] = grp.apply(_cl_badges, axis=1)

    sort_col = "Total" if "Total" in grp.columns else grp.columns[-1]
    return grp.sort_values(sort_col, ascending=False).reset_index(drop=True)


def build_supplier_summary(compras: pd.DataFrame) -> pd.DataFrame:
    """Resumen de TODOS los proveedores con métricas completas por período.
    Retorna: Nombre Emisor, NIT Emisor, Facturas, Períodos, Total, Base, IVA, Rete Renta
    Ordenado por Total descendente.
    """
    if compras.empty or "Nombre Emisor" not in compras.columns:
        return pd.DataFrame()

    group_cols = ["Nombre Emisor"]
    if "NIT Emisor" in compras.columns:
        group_cols.append("NIT Emisor")

    agg_cols = {}
    if "CUFE/CUDE" in compras.columns:
        agg_cols["CUFE/CUDE"] = "count"
    elif "Folio" in compras.columns:
        agg_cols["Folio"] = "count"
    else:
        compras = compras.copy(); compras["_n"] = 1; agg_cols["_n"] = "count"

    if "Total" in compras.columns:       agg_cols["Total"] = "sum"
    if "Base" in compras.columns:        agg_cols["Base"] = "sum"
    if "IVA" in compras.columns:         agg_cols["IVA"] = "sum"
    if "Rete Renta" in compras.columns:  agg_cols["Rete Renta"] = "sum"
    if "Rete ICA" in compras.columns:    agg_cols["Rete ICA"] = "sum"
    if "Mes" in compras.columns:         agg_cols["Mes"] = "nunique"

    grp = compras.groupby(group_cols, as_index=False).agg(agg_cols)

    rename = {}
    for c in ["CUFE/CUDE", "Folio", "_n"]:
        if c in grp.columns:
            rename[c] = "Facturas"; break
    if "Mes" in grp.columns:
        rename["Mes"] = "Períodos"
    grp = grp.rename(columns=rename)

    # ── Flags de responsabilidad fiscal (inferidos de los datos de facturas) ──
    grp["Resp_IVA"]    = grp["IVA"].gt(0)        if "IVA"       in grp.columns else False
    grp["Ret_Renta"]   = grp["Rete Renta"].gt(0) if "Rete Renta" in grp.columns else False
    grp["Ret_ICA"]     = grp["Rete ICA"].gt(0)   if "Rete ICA"  in grp.columns else False
    grp["Gran_Contrib"] = grp["Total"].gt(500_000_000) if "Total" in grp.columns else False

    def _pv_badges(row):
        b = []
        if row.get("Resp_IVA"):     b.append("IVA ✓")
        if row.get("Ret_Renta"):    b.append("Renta ✓")
        if row.get("Ret_ICA"):      b.append("ICA ✓")
        if row.get("Gran_Contrib"): b.append("⭐ Gran Cont.")
        return " | ".join(b) if b else "—"

    grp["Obligaciones"] = grp.apply(_pv_badges, axis=1)

    sort_col = "Total" if "Total" in grp.columns else grp.columns[-1]
    return grp.sort_values(sort_col, ascending=False).reset_index(drop=True)


def build_entity_monthly_pivot(df: pd.DataFrame, entity_col: str) -> pd.DataFrame:
    """Pivot: entidad (cliente o proveedor) × Mes → Total COP.
    Útil para ver la tendencia de compras/ventas por período para cada entidad.
    Columnas ordenadas cronológicamente.
    """
    if df.empty or "Mes" not in df.columns or entity_col not in df.columns:
        return pd.DataFrame()
    if "Total" not in df.columns:
        return pd.DataFrame()
    pivot = df.pivot_table(
        index=entity_col, columns="Mes", values="Total",
        aggfunc="sum", fill_value=0
    )
    pivot.columns.name = None
    # Ordenar columnas cronológicamente
    pivot = pivot[sorted(pivot.columns)]
    return pivot
