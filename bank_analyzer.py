"""
Analizador de Extractos Bancarios Colombianos
=============================================
Soporta:
  - Bancolombia (Cuenta Ahorros / Corriente / QR) — parser especializado
  - Davivienda, Banco de Bogotá, BBVA, Nequi, Bold, Banco Popular, Colpatria
  - Fallback genérico por tabla/regex
  - Archivos Excel / XLS (Bancolombia y genérico)

Flujo:
  1. parse_bank_statement(pdf_path)        → PDF  → detecta banco → parser específico
  2. parse_bank_statement_excel(xlsx_path) → XLSX → detecta banco → parser específico
  3. build_bank_fiscal_report(movimientos) → KPIs fiscales consolidados
"""
import re
import os
import logging
from datetime import datetime
import pandas as pd
import pdfplumber
import streamlit as st

logger = logging.getLogger(__name__)

# ── Detección de banco ────────────────────────────────────────────────────────

BANK_KEYWORDS = {
    "Bancolombia":     ["bancolombia", "sucursal virtual personas", "bancolombia s.a",
                        "estado de cuenta", "cuenta de ahorros"],
    "Davivienda":      ["davivienda", "casa roja"],
    "Banco de Bogotá": ["banco de bogota", "banco de bogotá"],
    "BBVA":            ["bbva"],
    "Nequi":           ["nequi"],
    "Bold":            ["bold.co", "datafono bold", "bold s.a"],
    "Banco Popular":   ["banco popular"],
    "Colpatria":       ["colpatria", "scotiabank"],
    "Bancoomeva":      ["bancoomeva"],
    "Banco Caja Social": ["caja social"],
    "Itaú":            ["itau", "itaú"],
    "AV Villas":       ["av villas"],
}

# ── Categorías fiscales (orden importa: primero = mayor prioridad) ─────────────

CATEGORY_RULES = [
    # GMF / 4x1000
    ("gmf_4x1000",    ["4X1000", "GRAVAMEN MOVIMIENTO", "GMF ", "IMPUESTO GMF",
                        "GRAVAMEN AL MOVIMIENTO"]),
    # Intereses pagados (costos financieros)
    ("interes_pago",  ["INTERESES MORA", "COBRO INT", "CUOTA INT",
                        "INTERES CORRIENTE", "INTERESES CORRIENTES",
                        "INTERES DE MORA", "CARGOS FINANCIEROS", "COBRO INTERESES"]),
    # Intereses recibidos (rendimientos)
    ("interes_rcdo",  ["ABONO INTERESES", "INT AHORROS", "RENDIMIENTO FINANCIERO",
                        "INTERESES AHORROS", "RENDIMIENTOS", "INTERESES CUENTA",
                        "INTERESES CDTE"]),
    # Retenciones
    ("retencion",     ["RETENCION", "RETEFUENTE", "RETE FUENTE",
                        "RET. EN LA FUENTE", "RETENCIÓN EN LA FUENTE",
                        "AUTORETENC", "AUTORETENCION"]),
    # Parafiscales / seguridad social
    ("parafiscal",    ["PARAFISCAL", "SALUD EPS", "PENSION AFP", "ARL ",
                        "CAJA COMP", "SENA ", "ICBF", "SEGURIDAD SOCIAL",
                        "PLANILLA PILA", "APORTES SOCIALES", "PLANILLA SOI"]),
    # Nómina
    ("nomina",        ["NOMINA", "PAGO NOMINA", "DISPERSIÓN NÓMINA",
                        "PLANILLA NOMINA", "PAGO DE NOMINA", "DESPRENDIBLE",
                        "PAGO COLABORADORES"]),
    # Impuestos / DIAN
    ("impuesto",      ["IMPUESTO", "DIAN ", "PAGO DIAN", "ICA BOGOTA",
                        "ICA MEDELLIN", "ICA CALI", "PREDIAL", "VEHICULOS",
                        "TIMBRE", "ICA MUNICIPIO", "INDUSTRIA Y COMERCIO"]),
    # Ingresos: pagos QR, consignaciones, transferencias recibidas
    ("ingreso",       ["PAGO QR", "CONSIGNACION", "DEPOSITO", "ABONO CREDITO",
                        "PAGO RECIBIDO", "PAGO CLIENTE", "ABONO FACTURAS",
                        "TRANSFERENCIA RECIBIDA", "PAGO NEQUI RECIBIDO",
                        "ABONO CREDITO", "DESEMBOLSO"]),
    # Retiros / pagos con tarjeta / cajero
    ("retiro",        ["RETIRO ", "CAJERO", "ATM ", "PAGO TC", "CUOTA TC",
                        "AVANCE TC", "AVANCE ATM", "COMPRA TARJETA", "COMPRA EN"]),
    # Transferencias salientes
    ("transferencia", ["TRANSFERENCIA", "PSE", "NEQUI A", "DAVIPLATA",
                        "TRANSFIYA", "TRASLADO", "MOVIMIENTO BANCARIO",
                        "PAGO NEQUI ENVIADO"]),
    # Comisiones bancarias
    ("comision",      ["CUOTA MANEJO", "COMISION", "COMISIÓN",
                        "CARGO SERVICIO", "SERVICIO BANCARIO",
                        "CUOTA ADMINISTRACION", "CUOTA DE MANEJO"]),
]

CATEGORY_LABELS = {
    "gmf_4x1000":    "GMF / 4×1000",
    "interes_pago":  "Intereses Pagados",
    "interes_rcdo":  "Intereses Recibidos",
    "retencion":     "Retenciones",
    "parafiscal":    "Parafiscales",
    "nomina":        "Nómina",
    "impuesto":      "Impuestos",
    "ingreso":       "Ingresos / Pagos QR",
    "retiro":        "Retiros / Pagos Tarjeta",
    "transferencia": "Transferencias",
    "comision":      "Comisiones Bancarias",
    "otro":          "Otros Movimientos",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _detect_bank(text: str) -> str:
    tl = text.lower()
    for bank, kws in BANK_KEYWORDS.items():
        if any(k in tl for k in kws):
            return bank
    return "Banco Genérico"


def _classify(desc: str) -> str:
    if not desc:
        return "otro"
    du = str(desc).upper()
    for cat, keywords in CATEGORY_RULES:
        if any(k in du for k in keywords):
            return cat
    return "otro"


def _extract_pattern(text: str, pattern: str):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else None


def _clean_number(s) -> float:
    """Convierte '1.234.567,89' o '1,234,567.89' a float."""
    if s is None or str(s).strip() in ("", "-", "—", "."):
        return 0.0
    s = str(s).strip()
    # Formato colombiano: puntos como miles, coma como decimal → 1.234.567,89
    if re.match(r'^\d{1,3}(\.\d{3})+(,\d+)?$', s):
        s = s.replace('.', '').replace(',', '.')
    else:
        # Quitar comas (separador de miles en formato americano)
        s = s.replace(',', '')
    try:
        return float(re.sub(r'[^\d\.\-]', '', s))
    except ValueError:
        return 0.0


# ── Parser específico Bancolombia ─────────────────────────────────────────────

def _parse_bancolombia(pages, header_text: str):
    """
    Parser especializado para extractos Bancolombia Cuenta de Ahorros/Corriente.

    Formato de transacciones:
        d/mm  DESCRIPCION  [SUCURSAL]  [DCTO.]  VALOR  SALDO
    - Fechas: d/mm (sin año, el año se deduce del header HASTA: YYYY/MM/DD)
    - VALOR = siempre positivo
    - Determina CRÉDITO vs DÉBITO comparando saldos consecutivos

    Returns: (movimientos_df, titular, cuenta)
    """
    # 1. Extraer año y mes final del header
    year_match = re.search(r'HASTA:\s*(\d{4})/(\d{2})/\d{2}', header_text)
    year      = year_match.group(1) if year_match else str(datetime.now().year)
    end_month = int(year_match.group(2)) if year_match else datetime.now().month

    # 2. Extraer titular: línea después de "AHORROS" o "CORRIENTE"
    titular = _extract_pattern(header_text,
        r'(?:CUENTA DE AHORROS|CUENTA CORRIENTE|CUPO DE CREDITO)\s*\n\s*([A-Z][A-Z\s&\.]{2,50})\s*\n') or ""
    titular = titular.strip()

    # 3. Extraer número de cuenta
    cuenta = _extract_pattern(header_text, r'N.MERO\s+([\d]+)') or ""

    # 4. Extraer datos del resumen (para validación y KPIs extra)
    saldo_anterior = _clean_number(
        _extract_pattern(header_text, r'SALDO ANTERIOR\s*\$?\s*([\d,\.]+)') or '0')
    total_abonos   = _clean_number(
        _extract_pattern(header_text, r'TOTAL ABONOS\s*\$?\s*([\d,\.]+)') or '0')
    total_cargos   = _clean_number(
        _extract_pattern(header_text, r'TOTAL CARGOS\s*\$?\s*([\d,\.]+)') or '0')
    saldo_actual   = _clean_number(
        _extract_pattern(header_text, r'SALDO ACTUAL\s*\$?\s*([\d,\.]+)') or '0')
    intereses      = _clean_number(
        _extract_pattern(header_text, r'INTERESES PAGADOS\s*\$?\s*([\d,\.]+)') or '0')
    retefuente     = _clean_number(
        _extract_pattern(header_text, r'RETEFUENTE\s*\$?\s*([\d,\.]+)') or '0')

    # 5. Parsear transacciones línea por línea
    # Patrón: d/mm  DESCRIPCION  valor  saldo  (los campos intermedios son opcionales)
    tx_pat = re.compile(
        r'^(\d{1,2}/\d{2})\s+'     # Fecha: d/mm
        r'(.+?)\s+'                 # Descripción (mínimo 1 palabra)
        r'([\d,\.]+)\s+'           # Valor
        r'([\d,\.]+)\s*$',         # Saldo
        re.M
    )

    rows = []
    prev_saldo = saldo_anterior if saldo_anterior > 0 else None

    for page in pages:
        txt = page.extract_text() or ''

        for m in tx_pat.finditer(txt):
            fecha_raw = m.group(1)   # e.g. "1/01" or "31/12"
            desc      = m.group(2).strip()
            valor     = _clean_number(m.group(3))
            saldo     = _clean_number(m.group(4))

            # Filtrar filas de encabezado de tabla
            du = desc.upper()
            if any(k in du for k in ['FECHA', 'DESCRIPCI', 'SUCURSAL', 'DCTO', 'VALOR SALDO']):
                continue
            # Filtrar valores muy pequeños que son probablemente artefactos de parsing
            if valor < 0.01:
                continue

            # Determinar año correcto (el extracto puede cruzar años)
            try:
                day, mon = fecha_raw.split('/')
                tx_year = int(year)
                # Si el mes de la transacción es mayor que el mes final,
                # la transacción pertenece al año anterior
                if int(mon) > end_month:
                    tx_year -= 1
                fecha_full = f"{int(day):02d}/{int(mon):02d}/{tx_year}"
            except Exception:
                fecha_full = fecha_raw

            # Determinar si es crédito (saldo sube) o débito (saldo baja)
            if prev_saldo is not None:
                # Tolerancia de 1 COP para errores de redondeo
                is_credit = (saldo - prev_saldo) > -1
            else:
                # Sin saldo previo: inferir por descripción
                is_credit = any(k in desc.upper() for k in
                                ['ABONO', 'PAGO QR', 'CONSIGNACION', 'DEPOSITO',
                                 'TRANSFERENCIA RECIBIDA', 'INTERESES'])
            prev_saldo = saldo

            rows.append({
                'fecha':       fecha_full,
                'descripcion': desc,
                'debito':      0.0 if is_credit else valor,
                'credito':     valor if is_credit else 0.0,
                'saldo':       saldo,
                'banco':       'Bancolombia',
                'titular':     titular,
                'cuenta':      cuenta,
            })

    if not rows:
        df = pd.DataFrame(columns=['fecha','descripcion','debito','credito',
                                   'saldo','banco','titular','cuenta','categoria','cat_label'])
    else:
        df = pd.DataFrame(rows)
        df['categoria'] = df['descripcion'].apply(_classify)
        df['cat_label'] = df['categoria'].map(CATEGORY_LABELS).fillna('Otros Movimientos')

    # Meta del resumen para info adicional
    meta = {
        'saldo_anterior': saldo_anterior,
        'total_abonos':   total_abonos,
        'total_cargos':   total_cargos,
        'saldo_actual':   saldo_actual,
        'intereses':      intereses,
        'retefuente':     retefuente,
    }

    return df, titular, cuenta, meta


# ── Parser genérico (tablas estructuradas) ────────────────────────────────────

def _parse_tables(pages) -> pd.DataFrame:
    """Estrategia 1: pdfplumber extract_tables()."""
    all_rows = []
    header_row = None

    for page in pages:
        for tbl in page.extract_tables():
            if not tbl:
                continue
            for row in tbl:
                if not row or not any(row):
                    continue
                clean_row = [str(c).strip() if c else "" for c in row]
                row_text = " ".join(clean_row).upper()
                if any(k in row_text for k in ["FECHA", "DESCRIPCION", "DÉBITO", "CRÉDITO"]):
                    if header_row is None:
                        header_row = clean_row
                    continue
                if re.search(r'\d{2}[\/\-]\d{2}[\/\-]\d{2,4}', row_text):
                    all_rows.append(clean_row)

    if not all_rows:
        return pd.DataFrame()
    if header_row:
        max_cols = max(len(header_row), max(len(r) for r in all_rows))
        header_row = (header_row + [""] * max_cols)[:max_cols]
        all_rows = [(r + [""] * max_cols)[:max_cols] for r in all_rows]
        try:
            return pd.DataFrame(all_rows, columns=header_row)
        except Exception:
            pass
    return pd.DataFrame(all_rows)


def _parse_text_regex(pages) -> pd.DataFrame:
    """Estrategia 2: texto + regex para fechas dd/mm/yyyy."""
    pat = re.compile(
        r'(\d{2}[\/\-]\d{2}[\/\-]\d{2,4})'
        r'\s+(.{5,80?}?)\s+'
        r'([\d,\.]+)(?:\s+([\d,\.]+))?(?:\s+([\d,\.]+))?\s*$',
        re.M
    )
    rows = []
    for page in pages:
        txt = page.extract_text() or ""
        for m in pat.finditer(txt):
            rows.append({
                "fecha_raw":   m.group(1),
                "descripcion": m.group(2).strip(),
                "col1":        m.group(3) or "",
                "col2":        m.group(4) or "",
                "col3":        m.group(5) or "",
            })
    return pd.DataFrame(rows)


def _normalize_from_table(df_raw: pd.DataFrame, banco: str) -> pd.DataFrame:
    if df_raw.empty:
        return pd.DataFrame()
    cols = [str(c).lower().strip() for c in df_raw.columns]

    def _find(keywords):
        for kw in keywords:
            for i, c in enumerate(cols):
                if kw in c:
                    return df_raw.iloc[:, i]
        return None

    fecha_s = _find(["fecha", "date"])
    desc_s  = _find(["descripcion", "concepto", "detalle", "movimiento"])
    deb_s   = _find(["debito", "egreso", "cargo", "retiro"])
    cred_s  = _find(["credito", "ingreso", "abono"])
    sald_s  = _find(["saldo", "balance"])

    if fecha_s is None and len(df_raw.columns) > 0: fecha_s = df_raw.iloc[:, 0]
    if desc_s  is None and len(df_raw.columns) > 1: desc_s  = df_raw.iloc[:, 1]

    out = pd.DataFrame()
    out["fecha"]       = fecha_s.astype(str).str.strip() if fecha_s is not None else ""
    out["descripcion"] = desc_s.astype(str).str.strip()  if desc_s  is not None else ""
    out["debito"]      = deb_s.apply(_clean_number)  if deb_s  is not None else 0.0
    out["credito"]     = cred_s.apply(_clean_number) if cred_s is not None else 0.0
    out["saldo"]       = sald_s.apply(_clean_number) if sald_s is not None else 0.0
    out["banco"]       = banco
    out["categoria"]   = out["descripcion"].apply(_classify)
    out["cat_label"]   = out["categoria"].map(CATEGORY_LABELS).fillna("Otros Movimientos")

    out = out[out["descripcion"].str.len() > 2]
    out = out[~out["descripcion"].str.upper().str.match(
        r'^(DESCRIPCI[OÓ]N|CONCEPTO|MOVIMIENTO|FECHA|DETALLE|SALDO)\s*$', na=False)]
    return out.reset_index(drop=True)


def _normalize_from_text(df_raw: pd.DataFrame, banco: str) -> pd.DataFrame:
    if df_raw.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["fecha"]       = df_raw.get("fecha_raw", "").astype(str).str.strip()
    out["descripcion"] = df_raw.get("descripcion", "").astype(str).str.strip()
    out["debito"]      = df_raw.get("col1", pd.Series("0")).apply(_clean_number)
    out["credito"]     = df_raw.get("col2", pd.Series("0")).apply(_clean_number)
    out["saldo"]       = df_raw.get("col3", pd.Series("0")).apply(_clean_number)
    out["banco"]       = banco
    out["categoria"]   = out["descripcion"].apply(_classify)
    out["cat_label"]   = out["categoria"].map(CATEGORY_LABELS).fillna("Otros Movimientos")
    return out[out["descripcion"].str.len() > 2].reset_index(drop=True)


# ── Parser Excel Bancolombia ──────────────────────────────────────────────────

def _parse_bancolombia_excel(file_path: str):
    """
    Parser especializado para extractos Bancolombia en Excel (.xlsx / .xls).

    Bancolombia exporta dos formatos principales:
      A) Columnas: FECHA | DESCRIPCION | OFICINA | REFERENCIA | VALOR | SALDO
         VALOR puede ser firmado (+ crédito, - débito) o siempre positivo.
      B) Columnas: FECHA | DESCRIPCION | ABONOS | CARGOS | SALDO

    Returns: (movimientos_df, titular, cuenta, meta)
    """
    titular = ""
    cuenta  = ""
    meta    = {}
    all_rows = []

    try:
        engine = "xlrd" if str(file_path).lower().endswith(".xls") else "openpyxl"
        xl = pd.ExcelFile(file_path, engine=engine)

        for sh in xl.sheet_names:
            df_raw = pd.read_excel(xl, sheet_name=sh, header=None, dtype=str).fillna("")

            # ── Escanear filas de cabecera para metadatos ─────────────────
            header_lines = []
            col_header_row = None

            for idx, row in df_raw.iterrows():
                vals = [str(v).strip() for v in row.values if str(v).strip() not in ("", "nan")]
                if not vals:
                    continue
                row_joined = " ".join(vals)
                row_upper  = row_joined.upper()
                header_lines.append(row_joined)

                # Detectar fila de encabezados de columnas
                kw_hits = sum(1 for k in ["FECHA", "DESCRIPCI", "VALOR", "SALDO",
                                           "ABONO", "CARGO", "REFERENCIA"]
                              if k in row_upper)
                if kw_hits >= 2 and col_header_row is None:
                    col_header_row = idx
                    break

            header_text = "\n".join(header_lines)

            # Extraer titular y cuenta de las filas de cabecera
            if not titular:
                for pat in [
                    r'(?:TITULAR|NOMBRE CLIENTE|CLIENTE)[:\s\n]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s&\.]{3,60})',
                    r'CUENTA DE AHORROS\s*\n?\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s&\.]{3,60})',
                ]:
                    t = _extract_pattern(header_text, pat)
                    if t:
                        titular = t.strip()
                        break

            if not cuenta:
                for pat in [
                    r'(?:N[UÚ]MERO|CUENTA|CUENTA No\.?|No\.?\s*CUENTA|CUENTA DE AHORROS)[:\s]*([\d]{6,18})',
                    r'\b(\d{10,18})\b',
                ]:
                    c = _extract_pattern(header_text, pat)
                    if c:
                        cuenta = c.strip()
                        break

            if col_header_row is None:
                continue  # No se encontró tabla de transacciones en esta hoja

            # ── Leer datos desde la fila de encabezados ───────────────────
            df_data = pd.read_excel(xl, sheet_name=sh,
                                    header=col_header_row, dtype=str).fillna("")
            df_data.columns = [str(c).upper().strip() for c in df_data.columns]

            def _find_col(*kws):
                for kw in kws:
                    for c in df_data.columns:
                        if kw in c:
                            return c
                return None

            fecha_col  = _find_col("FECHA")
            desc_col   = _find_col("DESCRIPCI", "CONCEPTO", "MOVIMIENTO", "DETALLE")
            saldo_col  = _find_col("SALDO")
            abono_col  = _find_col("ABONO", "CRÉDITO", "CREDITO", "INGRESO")
            cargo_col  = _find_col("CARGO", "DÉBITO", "DEBITO", "EGRESO")
            valor_col  = _find_col("VALOR") if (abono_col is None and cargo_col is None) else None

            if fecha_col is None:
                continue

            for _, row in df_data.iterrows():
                fecha_raw = str(row.get(fecha_col, "")).strip()
                if not fecha_raw or fecha_raw.upper() in ("FECHA", "NAN", ""):
                    continue

                # Parsear fecha (soporta ISO, dd/mm/yyyy, serial Excel)
                fecha_parsed = ""
                try:
                    if re.match(r'\d{4}-\d{2}-\d{2}', fecha_raw):
                        fecha_parsed = pd.to_datetime(fecha_raw).strftime("%d/%m/%Y")
                    elif re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', fecha_raw):
                        fecha_parsed = pd.to_datetime(fecha_raw, dayfirst=True,
                                                      errors="coerce")
                        fecha_parsed = fecha_parsed.strftime("%d/%m/%Y") if not pd.isna(fecha_parsed) else fecha_raw
                    elif fecha_raw.replace('.', '', 1).isdigit():
                        # Número serial de Excel
                        fecha_parsed = pd.to_datetime(float(fecha_raw), unit='D',
                                                      origin='1899-12-30').strftime("%d/%m/%Y")
                    else:
                        fecha_parsed = fecha_raw
                except Exception:
                    fecha_parsed = fecha_raw

                desc  = str(row.get(desc_col, "")).strip() if desc_col else ""
                saldo = _clean_number(str(row.get(saldo_col, "0"))) if saldo_col else 0.0

                # Determinar débito / crédito
                if abono_col and cargo_col:
                    # Formato con columnas separadas ABONOS / CARGOS
                    credito = _clean_number(str(row.get(abono_col, "0")))
                    debito  = _clean_number(str(row.get(cargo_col, "0")))
                elif valor_col:
                    # Columna VALOR única — puede ser firmado o siempre positivo
                    v_raw   = str(row.get(valor_col, "0"))
                    # Formato colombiano con paréntesis: (1.234) = débito
                    v_signed = v_raw.replace('(', '-').replace(')', '')
                    v_clean  = _clean_number(v_signed)
                    if '-' in v_raw or '(' in v_raw:
                        debito  = abs(v_clean)
                        credito = 0.0
                    elif v_clean < 0:
                        debito  = abs(v_clean)
                        credito = 0.0
                    else:
                        # Valor positivo sin signo: inferir por descripción
                        is_cr = any(k in desc.upper() for k in [
                            'ABONO', 'CONSIGNACION', 'DEPOSITO', 'PAGO QR',
                            'TRANSFERENCIA RECIBIDA', 'INTERESES', 'RENDIMIENTO',
                            'PAGO NEQUI RECIBIDO', 'DESEMBOLSO',
                        ])
                        credito = v_clean if is_cr else 0.0
                        debito  = 0.0 if is_cr else v_clean
                else:
                    continue

                if credito == 0 and debito == 0:
                    continue
                if not desc or len(desc) < 2:
                    continue

                all_rows.append({
                    "fecha":       fecha_parsed,
                    "descripcion": desc,
                    "debito":      debito,
                    "credito":     credito,
                    "saldo":       saldo,
                    "banco":       "Bancolombia",
                    "titular":     titular,
                    "cuenta":      cuenta,
                })

    except Exception as e:
        logger.error("Error parseando Bancolombia Excel '%s': %s", file_path, e)
        empty = pd.DataFrame(columns=["fecha", "descripcion", "debito", "credito",
                                       "saldo", "banco", "titular", "cuenta",
                                       "categoria", "cat_label"])
        return empty, titular, cuenta, meta

    if not all_rows:
        df = pd.DataFrame(columns=["fecha", "descripcion", "debito", "credito",
                                    "saldo", "banco", "titular", "cuenta",
                                    "categoria", "cat_label"])
    else:
        df = pd.DataFrame(all_rows)
        df["categoria"] = df["descripcion"].apply(_classify)
        df["cat_label"] = df["categoria"].map(CATEGORY_LABELS).fillna("Otros Movimientos")

    return df, titular, cuenta, meta


def _parse_excel_generic(file_path: str, banco: str):
    """
    Parser genérico para extractos bancarios Excel de cualquier banco.
    Busca la primera hoja con columna de fecha + descripción + valores numéricos.
    Returns: (movimientos_df, titular, cuenta, meta)
    """
    titular = ""
    cuenta  = ""
    meta    = {}
    all_rows = []

    try:
        engine = "xlrd" if str(file_path).lower().endswith(".xls") else "openpyxl"
        xl = pd.ExcelFile(file_path, engine=engine)

        for sh in xl.sheet_names:
            df_raw = pd.read_excel(xl, sheet_name=sh, header=None, dtype=str).fillna("")

            col_header_row = None
            header_lines   = []

            for idx, row in df_raw.iterrows():
                vals = [str(v).strip() for v in row.values if str(v).strip() not in ("", "nan")]
                row_upper = " ".join(vals).upper()
                header_lines.append(" ".join(vals))
                kw_hits = sum(1 for k in ["FECHA", "DESCRIPCI", "VALOR", "SALDO",
                                           "DÉBITO", "CRÉDITO", "ABONO", "CARGO"]
                              if k in row_upper)
                if kw_hits >= 2 and col_header_row is None:
                    col_header_row = idx
                    break

            header_text = "\n".join(header_lines)
            if not titular:
                t = _extract_pattern(header_text,
                    r'(?:TITULAR|NOMBRE|CLIENTE)[:\s]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-záéíóúñ\s&\.]{3,60})')
                if t: titular = t.strip()
            if not cuenta:
                c = _extract_pattern(header_text, r'\b(\d{8,18})\b')
                if c: cuenta = c.strip()

            if col_header_row is None:
                df_data = pd.read_excel(xl, sheet_name=sh, dtype=str).fillna("")
            else:
                df_data = pd.read_excel(xl, sheet_name=sh,
                                        header=col_header_row, dtype=str).fillna("")

            if len(df_data) < 2:
                continue

            # Reutilizar _normalize_from_table para hacer el mapeo de columnas
            df_norm = _normalize_from_table(df_data, banco)
            if not df_norm.empty:
                df_norm["titular"] = titular
                df_norm["cuenta"]  = cuenta
                all_rows.append(df_norm)
                break  # Usar la primera hoja con datos válidos

    except Exception as e:
        logger.error("Error parseando Excel genérico '%s': %s", file_path, e)

    if not all_rows:
        df = pd.DataFrame(columns=["fecha", "descripcion", "debito", "credito",
                                    "saldo", "banco", "categoria", "cat_label"])
    else:
        df = pd.concat(all_rows, ignore_index=True)

    return df, titular, cuenta, meta


# ── API pública ───────────────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def parse_bank_statement(pdf_path: str) -> dict:
    """
    Extrae movimientos de un extracto bancario PDF colombiano.

    Retorna dict:
        banco, cuenta, titular, periodo, movimientos (DataFrame), meta (dict)
    """
    result = {
        "banco":       "Banco Genérico",
        "cuenta":      "",
        "titular":     "",
        "periodo":     "",
        "movimientos": pd.DataFrame(columns=[
            "fecha", "descripcion", "debito", "credito",
            "saldo", "banco", "categoria", "cat_label"
        ]),
        "meta": {},
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return result

            # Texto de las primeras 2 páginas para detección
            header_text = ""
            for p in pdf.pages[:2]:
                header_text += (p.extract_text() or "") + "\n"

            result["banco"] = _detect_bank(header_text)

            # Extraer período del header
            per_m = re.search(
                r'(?:DESDE|FROM):\s*(\d{4}/\d{2}/\d{2}).*?(?:HASTA|TO):\s*(\d{4}/\d{2}/\d{2})',
                header_text, re.I | re.S
            )
            if per_m:
                d1 = per_m.group(1).replace('/', '-')
                d2 = per_m.group(2).replace('/', '-')
                result["periodo"] = f"{d1} al {d2}"

            # ── Bancolombia: parser especializado ────────────────────────────
            if result["banco"] == "Bancolombia":
                movs, titular, cuenta, meta = _parse_bancolombia(pdf.pages, header_text)
                result["movimientos"] = movs
                result["titular"]     = titular
                result["cuenta"]      = cuenta
                result["meta"]        = meta
                logger.info("Bancolombia '%s': %d movimientos | cuenta %s | %s",
                            os.path.basename(pdf_path), len(movs), cuenta, titular)
                return result

            # ── Genérico: intentar tablas primero, luego texto ────────────────
            result["cuenta"]  = _extract_pattern(header_text,
                r'N[ºo°]?\s*(?:cuenta|cta)[\s:\-]+([\d\-\s]{6,20})') or ""
            result["titular"] = _extract_pattern(header_text,
                r'(?:cliente|titular|nombre)[:\s]+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑa-z\s]{4,50})') or ""

            df_raw = _parse_tables(pdf.pages)
            if not df_raw.empty and len(df_raw) >= 3:
                df_norm = _normalize_from_table(df_raw, result["banco"])
                if not df_norm.empty and len(df_norm) >= 2:
                    result["movimientos"] = df_norm
                    return result

            df_text = _parse_text_regex(pdf.pages)
            if not df_text.empty:
                result["movimientos"] = _normalize_from_text(df_text, result["banco"])

            logger.info("Genérico '%s': %d movimientos",
                        os.path.basename(pdf_path), len(result["movimientos"]))

    except Exception as e:
        logger.error("Error procesando '%s': %s", pdf_path, e)
        raise

    return result


@st.cache_data(show_spinner=False)
def parse_bank_statement_excel(excel_path: str) -> dict:
    """
    Extrae movimientos de un extracto bancario en Excel (.xlsx / .xls) colombiano.

    Retorna el mismo dict que parse_bank_statement():
        banco, cuenta, titular, periodo, movimientos (DataFrame), meta (dict)
    """
    result = {
        "banco":       "Banco Genérico",
        "cuenta":      "",
        "titular":     "",
        "periodo":     "",
        "movimientos": pd.DataFrame(columns=[
            "fecha", "descripcion", "debito", "credito",
            "saldo", "banco", "categoria", "cat_label"
        ]),
        "meta": {},
    }

    try:
        # Detectar banco leyendo las primeras filas
        engine = "xlrd" if str(excel_path).lower().endswith(".xls") else "openpyxl"
        df_peek = pd.read_excel(excel_path, header=None, nrows=15,
                                dtype=str, engine=engine).fillna("")
        header_text = "\n".join(
            " ".join(str(v) for v in row.values)
            for _, row in df_peek.iterrows()
        )
        result["banco"] = _detect_bank(header_text)

        # Extraer período si está en el header
        per_m = re.search(
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})\s*(?:AL|A|-|–)\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            header_text, re.I
        )
        if not per_m:
            per_m = re.search(
                r'(\d{4}[/\-]\d{2}[/\-]\d{2})\s*(?:AL|A|-|–)\s*(\d{4}[/\-]\d{2}[/\-]\d{2})',
                header_text, re.I
            )
        if per_m:
            result["periodo"] = f"{per_m.group(1)} al {per_m.group(2)}"

        # Parsear según banco
        if result["banco"] == "Bancolombia":
            movs, titular, cuenta, meta = _parse_bancolombia_excel(excel_path)
        else:
            movs, titular, cuenta, meta = _parse_excel_generic(excel_path, result["banco"])

        result["movimientos"] = movs
        result["titular"]     = titular
        result["cuenta"]      = cuenta
        result["meta"]        = meta

        logger.info("Excel '%s': %d movimientos | banco %s | cuenta %s",
                    os.path.basename(excel_path), len(movs), result["banco"], cuenta)

    except Exception as e:
        logger.error("Error procesando Excel '%s': %s", excel_path, e)
        raise

    return result


def build_bank_fiscal_report(movimientos: pd.DataFrame) -> dict:
    """
    Genera reporte fiscal consolidado desde DataFrame de movimientos bancarios.

    Retorna dict con KPIs fiscales + resumen por categoría + timeline mensual.
    """
    empty_rpt = {
        "total_gmf": 0, "total_interes_pago": 0, "total_interes_rcdo": 0,
        "total_retenciones": 0, "total_parafiscales": 0, "total_impuestos": 0,
        "total_comisiones": 0, "total_ingresos": 0, "total_egresos": 0,
        "resumen_categoria": pd.DataFrame(),
        "timeline": pd.DataFrame(),
    }

    if movimientos is None or movimientos.empty:
        return empty_rpt

    def _sum_cat(cat: str, col: str) -> float:
        if "categoria" not in movimientos.columns or col not in movimientos.columns:
            return 0.0
        return float(movimientos.loc[movimientos["categoria"] == cat, col].sum())

    rpt = {
        "total_gmf":          _sum_cat("gmf_4x1000",   "debito"),
        "total_interes_pago": _sum_cat("interes_pago",  "debito"),
        "total_interes_rcdo": _sum_cat("interes_rcdo",  "credito"),
        "total_retenciones":  _sum_cat("retencion",     "debito"),
        "total_parafiscales": _sum_cat("parafiscal",    "debito"),
        "total_impuestos":    _sum_cat("impuesto",      "debito"),
        "total_comisiones":   _sum_cat("comision",      "debito"),
        "total_ingresos":     float(movimientos["credito"].sum()) if "credito" in movimientos.columns else 0.0,
        "total_egresos":      float(movimientos["debito"].sum())  if "debito"  in movimientos.columns else 0.0,
    }

    # Resumen por categoría
    if "cat_label" in movimientos.columns:
        grp_cols = [c for c in ["cat_label", "debito", "credito"] if c in movimientos.columns]
        rpt["resumen_categoria"] = (
            movimientos[grp_cols]
            .groupby("cat_label").sum(numeric_only=True)
            .reset_index()
            .sort_values("debito", ascending=False)
            .reset_index(drop=True)
        )
    else:
        rpt["resumen_categoria"] = pd.DataFrame()

    # Timeline mensual
    if "fecha" in movimientos.columns:
        try:
            _m = movimientos.copy()
            _m["mes"] = pd.to_datetime(
                _m["fecha"], dayfirst=True, errors="coerce"
            ).dt.to_period("M").astype(str)
            _m = _m[_m["mes"].notna() & (_m["mes"] != "NaT") & (_m["mes"] != "nan")]
            num_cols = [c for c in ["debito", "credito"] if c in _m.columns]
            if num_cols and not _m.empty:
                rpt["timeline"] = (
                    _m.groupby("mes")[num_cols]
                    .sum(numeric_only=True)
                    .reset_index()
                    .sort_values("mes")
                )
            else:
                rpt["timeline"] = pd.DataFrame()
        except Exception:
            rpt["timeline"] = pd.DataFrame()
    else:
        rpt["timeline"] = pd.DataFrame()

    return rpt
