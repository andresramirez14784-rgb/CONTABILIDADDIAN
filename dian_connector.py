"""
Conector DIAN — Catálogo de Facturas Electrónicas
==================================================
Permite importar facturas (ventas/compras) directamente desde el portal
catalogo-vpfe.dian.gov.co usando el link de token que la DIAN envía por correo.

Flujo:
  1. Usuario pega el AuthToken URL de su correo DIAN
  2. authenticate_dian() hace GET → establece cookie de sesión
  3. discover_endpoints() navega el portal para encontrar endpoints reales
  4. download_invoices() descarga el Excel de facturas del rango de fechas
  5. load_file() procesa el Excel con el pipeline existente
"""
import re
import os
import tempfile
import logging
import requests
from pathlib import Path

logger = logging.getLogger(__name__)

CATALOG_BASE = "https://catalogo-vpfe.dian.gov.co"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Candidatos de endpoint para descarga de listados (formato antiguo y nuevo del portal DIAN)
_ENDPOINTS_VENTAS = [
    f"{CATALOG_BASE}/Document/DownloadIssuedDocuments",
    f"{CATALOG_BASE}/Document/DownloadListIssuedDocuments",
    f"{CATALOG_BASE}/Document/ExportIssuedDocuments",
    f"{CATALOG_BASE}/Document/GetIssuedList",
    f"{CATALOG_BASE}/Document/DownloadEmitidos",
    f"{CATALOG_BASE}/Report/DownloadIssued",
]
_ENDPOINTS_COMPRAS = [
    f"{CATALOG_BASE}/Document/DownloadReceivedDocuments",
    f"{CATALOG_BASE}/Document/DownloadListReceivedDocuments",
    f"{CATALOG_BASE}/Document/ExportReceivedDocuments",
    f"{CATALOG_BASE}/Document/GetReceivedList",
    f"{CATALOG_BASE}/Document/DownloadRecibidos",
    f"{CATALOG_BASE}/Report/DownloadReceived",
]
_PAGE_VENTAS  = f"{CATALOG_BASE}/Document/IssuedDocuments"
_PAGE_COMPRAS = f"{CATALOG_BASE}/Document/ReceivedDocuments"


# ─── Autenticación ────────────────────────────────────────────────────────────

def authenticate_dian(auth_url: str) -> "requests.Session | None":
    """
    Autentica en el catálogo DIAN usando la URL de token del correo.

    Parámetros:
        auth_url: URL completa del correo DIAN, ej:
                  https://catalogo-vpfe.dian.gov.co/User/AuthToken?pk=...&token=...

    Retorna:
        requests.Session autenticada, o None si el token es inválido/expirado.
    """
    session = requests.Session()
    session.headers.update(_BROWSER_HEADERS)
    try:
        resp = session.get(auth_url, timeout=30, allow_redirects=True)
        final_url = resp.url

        # Si redirige al login, el token expiró o es inválido
        if (
            "/User/Login" in final_url
            or "/User/AuthToken" in final_url
            or resp.status_code >= 400
        ):
            logger.warning("Token DIAN inválido o expirado. URL final: %s", final_url)
            return None

        logger.info("Autenticado correctamente en DIAN. URL final: %s", final_url)
        return session

    except requests.exceptions.SSLError:
        # Algunos entornos corporativos tienen SSL interceptado; intentar sin verificar
        session2 = requests.Session()
        session2.headers.update(_BROWSER_HEADERS)
        session2.verify = False
        try:
            resp = session2.get(auth_url, timeout=30, allow_redirects=True)
            if "/User/Login" in resp.url or resp.status_code >= 400:
                return None
            return session2
        except Exception as e:
            logger.error("Error autenticando (sin SSL): %s", e)
            return None

    except Exception as e:
        logger.error("Error autenticando con DIAN: %s", e)
        return None


def check_auth_status(session: "requests.Session") -> dict:
    """
    Verifica si la sesión sigue activa y extrae info del contribuyente.
    Retorna dict con: activa (bool), nit (str), nombre (str).
    """
    try:
        resp = session.get(_PAGE_VENTAS, timeout=15)
        if "/User/Login" in resp.url or resp.status_code >= 400:
            return {"activa": False, "nit": "", "nombre": ""}

        # Intentar extraer NIT y nombre del HTML
        nit = _extract_pattern(resp.text, r'NIT[:\s]+(\d{7,12})')
        nombre = _extract_pattern(resp.text, r'<span[^>]*class="[^"]*empresa[^"]*"[^>]*>([^<]+)<')
        if not nombre:
            nombre = _extract_pattern(resp.text, r'Bienvenido[,\s]+([^<\n]+)')

        return {"activa": True, "nit": nit, "nombre": nombre.strip() if nombre else ""}
    except Exception:
        return {"activa": False, "nit": "", "nombre": ""}


# ─── Descarga de facturas ─────────────────────────────────────────────────────

def download_invoices(
    session: "requests.Session",
    report_type: str,       # "ventas" | "compras"
    fecha_inicio: str,      # "dd/mm/yyyy"
    fecha_fin: str,         # "dd/mm/yyyy"
    progress_cb=None,       # callable(msg: str) opcional para mostrar progreso
) -> "pd.DataFrame":
    """
    Descarga el listado de facturas del catálogo DIAN como DataFrame.

    Estrategia en capas:
      1. Navega la página del listado → obtiene CSRF + descubre endpoint de descarga
      2. Intenta POST al endpoint descubierto con fecha_inicio/fecha_fin
      3. Si falla, prueba endpoints candidatos conocidos
      4. Parsea el Excel resultante con load_file()
    """
    import pandas as pd
    from data_loader import load_file

    def _log(msg):
        logger.info(msg)
        if progress_cb:
            progress_cb(msg)

    page_url = _PAGE_VENTAS if report_type == "ventas" else _PAGE_COMPRAS
    candidates = _ENDPOINTS_VENTAS if report_type == "ventas" else _ENDPOINTS_COMPRAS

    # Paso 1: Cargar la página del listado
    _log(f"Cargando página de {report_type}...")
    try:
        page_resp = session.get(page_url, timeout=20)
    except Exception as e:
        raise ConnectionError(f"No se pudo acceder al catálogo: {e}")

    if "/User/Login" in page_resp.url:
        raise PermissionError("La sesión DIAN expiró. Obten un nuevo link.")

    html = page_resp.text
    csrf = _extract_csrf(html)
    _log(f"CSRF obtenido: {'Sí' if csrf else 'No encontrado (se intentará sin él)'}")

    # Descubrir endpoint de descarga desde el HTML (form action, fetch, ajax)
    discovered = _discover_download_endpoint(html, report_type)
    if discovered:
        _log(f"Endpoint descubierto: {discovered}")
        candidates = [discovered] + candidates

    # Paso 2: Intentar cada endpoint candidato
    payloads = _build_payloads(fecha_inicio, fecha_fin, csrf)

    for endpoint in candidates:
        _log(f"Intentando endpoint: {endpoint.split('/')[-1]}...")
        for payload in payloads:
            try:
                resp = session.post(endpoint, data=payload, timeout=60)
                excel_bytes = _extract_excel(session, resp)
                if excel_bytes:
                    _log(f"✅ Excel descargado ({len(excel_bytes):,} bytes)")
                    tmp = _write_temp(excel_bytes, report_type)
                    df = load_file(tmp)
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass
                    return df
            except Exception as e:
                logger.debug("Endpoint %s falló: %s", endpoint, e)
                continue

    # Paso 3: Intentar descarga GET directa con parámetros en URL
    _log("Intentando descarga GET con parámetros...")
    params = {
        "fechaInicio": fecha_inicio, "FechaInicio": fecha_inicio,
        "fechaFin": fecha_fin, "FechaFin": fecha_fin,
        "formato": "xlsx", "format": "xlsx",
    }
    for endpoint in candidates[:3]:
        try:
            resp = session.get(endpoint, params=params, timeout=60)
            excel_bytes = _extract_excel(session, resp)
            if excel_bytes:
                _log(f"✅ Excel descargado vía GET ({len(excel_bytes):,} bytes)")
                tmp = _write_temp(excel_bytes, report_type)
                df = load_file(tmp)
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
                return df
        except Exception as e:
            logger.debug("GET fallido: %s", e)

    import pandas as pd
    _log("⚠ No se pudo descargar automáticamente. Ver instrucciones manuales.")
    return pd.DataFrame()


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _extract_csrf(html: str) -> str:
    """Extrae el token CSRF anti-forgery de .NET de un HTML."""
    patterns = [
        r'__RequestVerificationToken["\s]+value="([^"]+)"',
        r'name="__RequestVerificationToken"\s+value="([^"]+)"',
        r'"__RequestVerificationToken":"([^"]+)"',
        r'data-csrf="([^"]+)"',
    ]
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1)
    return ""


def _discover_download_endpoint(html: str, report_type: str) -> "str | None":
    """Busca en el HTML el endpoint real de descarga de Excel."""
    keywords = (
        ["emiti", "issued", "ventas", "export", "download", "descarga"]
        if report_type == "ventas"
        else ["recib", "received", "compras", "export", "download", "descarga"]
    )
    # Buscar en actions de forms
    for m in re.finditer(r'action=["\']([^"\']+)["\']', html, re.I):
        url = m.group(1)
        if any(k in url.lower() for k in keywords):
            return url if url.startswith("http") else CATALOG_BASE + url

    # Buscar en fetch/ajax calls
    for m in re.finditer(r"""['"]((?:/Document|/Report|/api)[^'"]{3,80})['"']""", html):
        url = m.group(1)
        if any(k in url.lower() for k in keywords):
            return CATALOG_BASE + url

    return None


def _build_payloads(fecha_inicio: str, fecha_fin: str, csrf: str) -> list:
    """Construye variantes del payload para distintos formatos de parámetros."""
    base = {
        "fechaInicio": fecha_inicio,
        "fechaFin": fecha_fin,
        "FechaInicio": fecha_inicio,
        "FechaFin": fecha_fin,
    }
    if csrf:
        base["__RequestVerificationToken"] = csrf
    # Variantes de nombres de campo
    alt = {
        "startDate": fecha_inicio,
        "endDate": fecha_fin,
        "StartDate": fecha_inicio,
        "EndDate": fecha_fin,
        "formato": "xlsx",
        "Format": "xlsx",
    }
    if csrf:
        alt["__RequestVerificationToken"] = csrf
    return [base, alt, {**base, **alt}]


def _extract_excel(session: "requests.Session", resp: requests.Response) -> "bytes | None":
    """Extrae bytes de Excel de una respuesta HTTP (directo o via link en JSON/HTML)."""
    ct = resp.headers.get("Content-Type", "")

    # Respuesta directa: archivo Excel en el body
    if (
        "application/vnd.openxmlformats" in ct
        or "application/vnd.ms-excel" in ct
        or "application/octet-stream" in ct
        or (resp.content and resp.content[:4] == b"PK\x03\x04")  # ZIP magic = xlsx
    ):
        if len(resp.content) > 100:
            return resp.content

    # Respuesta JSON con link de descarga
    if "application/json" in ct or resp.text.strip().startswith("{"):
        try:
            import json
            data = json.loads(resp.text)
            url = (
                data.get("url") or data.get("downloadUrl") or
                data.get("link") or data.get("fileUrl") or
                data.get("Url") or data.get("DownloadUrl")
            )
            if url:
                dl = session.get(url if url.startswith("http") else CATALOG_BASE + url, timeout=60)
                if dl.content and len(dl.content) > 100:
                    return dl.content
        except Exception:
            pass

    # Respuesta HTML con link de descarga incrustado
    link = _extract_pattern(resp.text, r"""href=["']([^"']*\.xlsx?[^"']*)["']""")
    if link:
        url = link if link.startswith("http") else CATALOG_BASE + link
        try:
            dl = session.get(url, timeout=60)
            if dl.content and len(dl.content) > 100:
                return dl.content
        except Exception:
            pass

    return None


def _write_temp(content: bytes, suffix_tag: str) -> str:
    """Escribe bytes a un archivo temporal y devuelve la ruta."""
    fd, path = tempfile.mkstemp(suffix=f"_dian_{suffix_tag}.xlsx")
    with os.fdopen(fd, "wb") as f:
        f.write(content)
    return path


def _extract_pattern(text: str, pattern: str) -> "str | None":
    m = re.search(pattern, text, re.I)
    return m.group(1) if m else None


# ─── Función de diagnóstico ───────────────────────────────────────────────────

def diagnose_session(session: "requests.Session") -> dict:
    """
    Herramienta de diagnóstico: inspecciona el portal autenticado y reporta:
    - Si la sesión está activa
    - URLs de páginas accesibles
    - Formularios encontrados (action, fields)
    - Endpoints AJAX detectados en el JS

    Útil para descubrir los endpoints exactos cuando cambia el portal DIAN.
    """
    result = {
        "session_active": False,
        "pages": {},
        "forms": [],
        "ajax_endpoints": [],
    }
    pages_to_check = {
        "ventas": _PAGE_VENTAS,
        "compras": _PAGE_COMPRAS,
        "home": CATALOG_BASE,
    }
    for name, url in pages_to_check.items():
        try:
            r = session.get(url, timeout=15)
            accessible = "/User/Login" not in r.url and r.status_code < 400
            result["pages"][name] = {
                "url": r.url,
                "status": r.status_code,
                "accessible": accessible,
                "size": len(r.content),
            }
            if accessible:
                result["session_active"] = True
                # Extraer forms
                for m in re.finditer(r'<form[^>]*action=["\']([^"\']+)["\'][^>]*>(.*?)</form>',
                                     r.text, re.S | re.I):
                    form_url = m.group(1)
                    fields = re.findall(r'name=["\']([^"\']+)["\']', m.group(2))
                    result["forms"].append({"action": form_url, "fields": fields, "page": name})
                # Extraer endpoints AJAX
                for m in re.finditer(
                    r"""(?:fetch|ajax|axios\.(?:get|post))\s*\(\s*['"](/[^'"]{5,100})['"']""",
                    r.text, re.I,
                ):
                    ep = m.group(1)
                    if ep not in result["ajax_endpoints"]:
                        result["ajax_endpoints"].append(ep)
        except Exception as e:
            result["pages"][name] = {"error": str(e)}

    return result
