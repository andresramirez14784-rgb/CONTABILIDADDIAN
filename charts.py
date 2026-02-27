"""
Professional Plotly chart builders for the accounting dashboard.
Color palette: corporate blue #1F3864 + accent colors.
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import numpy as np

# ─── Brand colors ───────────────────────────────────────────────────────────
PRIMARY    = "#1F3864"
SECONDARY  = "#2E75B6"
ACCENT     = "#ED7D31"
SUCCESS    = "#70AD47"
DANGER     = "#C00000"
WARNING    = "#FFD700"
LIGHT_BLUE = "#9DC3E6"
BG_DARK    = "#0F1C33"
BG_CARD    = "#1A2B4A"
TEXT_WHITE = "#FFFFFF"
TEXT_MUTED = "#A0B4CC"

PALETTE = [PRIMARY, SECONDARY, ACCENT, SUCCESS, DANGER, WARNING,
           LIGHT_BLUE, "#7030A0", "#00B0F0", "#FF6B6B"]

LAYOUT_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Arial, sans-serif", color=TEXT_WHITE, size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    legend=dict(
        bgcolor="rgba(31,56,100,0.6)",
        bordercolor=SECONDARY,
        borderwidth=1,
        font=dict(color=TEXT_WHITE),
    ),
)


def _fmt_cop(value) -> str:
    """Format number as Colombian Peso."""
    try:
        return f"${value:,.0f}"
    except Exception:
        return str(value)


# ─── Revenue vs Cost bar ──────────────────────────────────────────────────────
def chart_ventas_vs_compras(kpis: dict) -> go.Figure:
    categories = ["Ventas Brutas", "IVA Ventas", "Compras Brutas", "IVA Compras"]
    values     = [
        kpis.get("base_ventas", 0),
        kpis.get("iva_generado", 0),
        kpis.get("base_compras", 0),
        kpis.get("iva_descontable", 0),
    ]
    colors = [SUCCESS, SECONDARY, DANGER, WARNING]

    fig = go.Figure(go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[_fmt_cop(v) for v in values],
        textposition="outside",
        textfont=dict(color=TEXT_WHITE, size=11),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="📊 Ventas vs Compras — Base + IVA", font=dict(size=15, color=TEXT_WHITE)),
        yaxis=dict(gridcolor="rgba(255,255,255,0.07)", tickformat="$,.0f", color=TEXT_WHITE),
        xaxis=dict(color=TEXT_WHITE),
        height=340,
    )
    return fig


# ─── IVA waterfall ───────────────────────────────────────────────────────────
def chart_iva_waterfall(kpis: dict) -> go.Figure:
    iva_gen  = kpis.get("iva_generado", 0)
    iva_desc = kpis.get("iva_descontable", 0)
    iva_neto = iva_gen - iva_desc

    fig = go.Figure(go.Waterfall(
        name="IVA",
        orientation="v",
        measure=["absolute", "relative", "total"],
        x=["IVA Generado", "(-) IVA Descontable", "IVA Neto"],
        y=[iva_gen, -iva_desc, 0],
        text=[_fmt_cop(iva_gen), _fmt_cop(iva_desc), _fmt_cop(abs(iva_neto))],
        textposition="outside",
        textfont=dict(color=TEXT_WHITE),
        connector=dict(line=dict(color=LIGHT_BLUE, width=1, dash="dot")),
        increasing=dict(marker=dict(color=DANGER)),
        decreasing=dict(marker=dict(color=SUCCESS)),
        totals=dict(marker=dict(color=ACCENT)),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="💧 Posición IVA — Cascada", font=dict(size=15, color=TEXT_WHITE)),
        yaxis=dict(gridcolor="rgba(255,255,255,0.07)", tickformat="$,.0f", color=TEXT_WHITE),
        xaxis=dict(color=TEXT_WHITE),
        height=340,
        showlegend=False,
    )
    return fig


# ─── Sales by client (horizontal bar) ────────────────────────────────────────
def chart_top_clientes(top_clientes: pd.DataFrame, n: int = 10) -> go.Figure:
    if top_clientes.empty:
        return _empty_fig("Sin datos de clientes")
    df = top_clientes.head(n).sort_values("Total", ascending=True)
    fig = go.Figure(go.Bar(
        x=df["Total"],
        y=df["Cliente"].apply(lambda x: str(x)[:35]),
        orientation="h",
        marker=dict(
            color=df["Total"],
            colorscale=[[0, SECONDARY], [1, SUCCESS]],
            showscale=False,
        ),
        text=[_fmt_cop(v) for v in df["Total"]],
        textposition="outside",
        textfont=dict(color=TEXT_WHITE, size=10),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"👥 Top {n} Clientes por Ventas", font=dict(size=15, color=TEXT_WHITE)),
        xaxis=dict(tickformat="$,.0f", color=TEXT_WHITE, gridcolor="rgba(255,255,255,0.07)"),
        yaxis=dict(color=TEXT_WHITE, automargin=True),
        height=max(300, n * 35),
    )
    return fig


# ─── Purchases by supplier ────────────────────────────────────────────────────
def chart_top_proveedores(top_prov: pd.DataFrame, n: int = 10) -> go.Figure:
    if top_prov.empty:
        return _empty_fig("Sin datos de proveedores")
    df = top_prov.head(n).sort_values("Total", ascending=True)
    fig = go.Figure(go.Bar(
        x=df["Total"],
        y=df["Proveedor"].apply(lambda x: str(x)[:35]),
        orientation="h",
        marker=dict(
            color=df["Total"],
            colorscale=[[0, WARNING], [1, DANGER]],
            showscale=False,
        ),
        text=[_fmt_cop(v) for v in df["Total"]],
        textposition="outside",
        textfont=dict(color=TEXT_WHITE, size=10),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"🏭 Top {n} Proveedores por Compras", font=dict(size=15, color=TEXT_WHITE)),
        xaxis=dict(tickformat="$,.0f", color=TEXT_WHITE, gridcolor="rgba(255,255,255,0.07)"),
        yaxis=dict(color=TEXT_WHITE, automargin=True),
        height=max(300, n * 35),
    )
    return fig


# ─── Sales over time ──────────────────────────────────────────────────────────
def chart_ventas_tiempo(ventas: pd.DataFrame) -> go.Figure:
    if ventas.empty or "Fecha Emisión" not in ventas.columns:
        return _empty_fig("Sin datos temporales")

    df = ventas.dropna(subset=["Fecha Emisión"]).copy()
    df["Fecha"] = df["Fecha Emisión"].dt.date
    daily = df.groupby("Fecha").agg(
        Total=("Total", "sum"),
        Facturas=("Total", "count"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["Fecha"], y=daily["Total"],
        mode="lines+markers",
        name="Ventas diarias",
        line=dict(color=SUCCESS, width=2),
        marker=dict(color=SUCCESS, size=5),
        fill="tozeroy",
        fillcolor="rgba(112,173,71,0.15)",
        hovertemplate="<b>%{x}</b><br>Ventas: %{y:$,.0f}<extra></extra>",
    ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="📈 Ventas Diarias", font=dict(size=15, color=TEXT_WHITE)),
        xaxis=dict(color=TEXT_WHITE, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(color=TEXT_WHITE, tickformat="$,.0f", gridcolor="rgba(255,255,255,0.07)"),
        height=310,
        showlegend=False,
    )
    return fig


# ─── Compras over time ───────────────────────────────────────────────────────
def chart_compras_tiempo(compras: pd.DataFrame) -> go.Figure:
    if compras.empty or "Fecha Emisión" not in compras.columns:
        return _empty_fig("Sin datos temporales")

    df = compras.dropna(subset=["Fecha Emisión"]).copy()
    df["Fecha"] = df["Fecha Emisión"].dt.date
    daily = df.groupby("Fecha").agg(Total=("Total", "sum")).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["Fecha"], y=daily["Total"],
        mode="lines+markers",
        line=dict(color=DANGER, width=2),
        marker=dict(color=DANGER, size=5),
        fill="tozeroy",
        fillcolor="rgba(192,0,0,0.15)",
        hovertemplate="<b>%{x}</b><br>Compras: %{y:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="📉 Compras Diarias", font=dict(size=15, color=TEXT_WHITE)),
        xaxis=dict(color=TEXT_WHITE, gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(color=TEXT_WHITE, tickformat="$,.0f", gridcolor="rgba(255,255,255,0.07)"),
        height=310,
        showlegend=False,
    )
    return fig


# ─── Document type donut ─────────────────────────────────────────────────────
def chart_tipo_documentos(df: pd.DataFrame, titulo: str) -> go.Figure:
    if df.empty or "Tipo_Label" not in df.columns:
        return _empty_fig("Sin datos")

    counts = df.groupby("Tipo_Label")["Total"].sum().reset_index()
    fig = go.Figure(go.Pie(
        labels=counts["Tipo_Label"],
        values=counts["Total"],
        hole=0.55,
        marker=dict(colors=PALETTE[:len(counts)]),
        textinfo="label+percent",
        textfont=dict(color=TEXT_WHITE, size=11),
        hovertemplate="%{label}: %{value:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=titulo, font=dict(size=15, color=TEXT_WHITE)),
        height=320,
        showlegend=True,
    )
    return fig


# ─── IVA bimestral stacked bar ────────────────────────────────────────────────
def chart_iva_bimestral(iva_pivot: pd.DataFrame) -> go.Figure:
    if iva_pivot.empty or "Bimestre" not in iva_pivot.columns:
        return _empty_fig("Sin datos de conciliación IVA")

    fig = go.Figure()

    if "IVA_Ventas" in iva_pivot.columns:
        fig.add_trace(go.Bar(
            name="IVA Generado",
            x=iva_pivot["Bimestre"],
            y=iva_pivot["IVA_Ventas"],
            marker_color=DANGER,
            text=[_fmt_cop(v) for v in iva_pivot["IVA_Ventas"]],
            textposition="inside",
            textfont=dict(color=TEXT_WHITE),
        ))
    if "IVA_Compras" in iva_pivot.columns:
        fig.add_trace(go.Bar(
            name="IVA Descontable",
            x=iva_pivot["Bimestre"],
            y=iva_pivot["IVA_Compras"],
            marker_color=SUCCESS,
            text=[_fmt_cop(v) for v in iva_pivot["IVA_Compras"]],
            textposition="inside",
            textfont=dict(color=TEXT_WHITE),
        ))
    if "IVA_Neto" in iva_pivot.columns:
        fig.add_trace(go.Scatter(
            name="IVA Neto",
            x=iva_pivot["Bimestre"],
            y=iva_pivot["IVA_Neto"],
            mode="lines+markers+text",
            marker=dict(color=WARNING, size=10, symbol="diamond"),
            line=dict(color=WARNING, width=2, dash="dash"),
            text=[_fmt_cop(v) for v in iva_pivot["IVA_Neto"]],
            textposition="top center",
            textfont=dict(color=WARNING, size=11),
        ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="💰 Conciliación IVA Bimestral", font=dict(size=15, color=TEXT_WHITE)),
        barmode="group",
        xaxis=dict(color=TEXT_WHITE),
        yaxis=dict(color=TEXT_WHITE, tickformat="$,.0f", gridcolor="rgba(255,255,255,0.07)"),
        height=360,
    )
    return fig


# ─── Hallazgos gauge ─────────────────────────────────────────────────────────
def chart_riesgo_gauge(hallazgos: list[dict]) -> go.Figure:
    """Gauge showing overall risk level."""
    if not hallazgos:
        score = 0
    else:
        weights = {"🔴 ALTO": 3, "🟠 MEDIO-ALTO": 2, "🟡 MEDIO": 1.5,
                   "🟣 MEDIO": 1, "⚪ BAJO-MEDIO": 0.5}
        score = min(100, sum(weights.get(h["nivel"], 1) for h in hallazgos) * 10)

    color = DANGER if score > 60 else (WARNING if score > 30 else SUCCESS)
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        domain=dict(x=[0, 1], y=[0, 1]),
        title=dict(text="Índice de Riesgo Fiscal", font=dict(color=TEXT_WHITE, size=14)),
        number=dict(font=dict(color=color, size=28)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor=TEXT_WHITE, tickfont=dict(color=TEXT_WHITE)),
            bar=dict(color=color, thickness=0.3),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[0, 33], color="rgba(112,173,71,0.3)"),
                dict(range=[33, 66], color="rgba(255,215,0,0.3)"),
                dict(range=[66, 100], color="rgba(192,0,0,0.3)"),
            ],
            threshold=dict(line=dict(color=TEXT_WHITE, width=2), thickness=0.7, value=score),
        ),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        height=260,
    )
    return fig


# ─── Scatter: unit price analysis ────────────────────────────────────────────
def chart_scatter_proveedores(compras: pd.DataFrame) -> go.Figure:
    if compras.empty or "Nombre Emisor" not in compras.columns:
        return _empty_fig("Sin datos")

    df = compras.groupby("Nombre Emisor").agg(
        Total=("Total", "sum"),
        Facturas=("Total", "count"),
        IVA=("IVA", "sum"),
    ).reset_index()
    df["Ticket_Prom"] = df["Total"] / df["Facturas"]

    fig = px.scatter(
        df, x="Facturas", y="Total",
        size="IVA", color="IVA",
        hover_name="Nombre Emisor",
        color_continuous_scale=[[0, SECONDARY], [0.5, WARNING], [1, DANGER]],
        labels={"Facturas": "Nº Facturas", "Total": "Total Comprado (COP)"},
    )
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="🔵 Dispersión Proveedores (tamaño = IVA)", font=dict(size=15, color=TEXT_WHITE)),
        height=340,
        coloraxis_showscale=False,
    )
    return fig


# ─── Helpers ──────────────────────────────────────────────────────────────────
def _empty_fig(msg: str = "Sin datos disponibles") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=msg, xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color=TEXT_MUTED),
    )
    fig.update_layout(**LAYOUT_BASE, height=300)
    return fig


# ─── Nómina charts ────────────────────────────────────────────────────────────
def chart_nomina_mensual(nomina: pd.DataFrame) -> go.Figure:
    """Devengado vs Deducido vs Rete Fuente por mes."""
    if nomina.empty or "Devengado" not in nomina.columns:
        return _empty_fig("Sin datos de nómina")

    grp_col = "Mes" if "Mes" in nomina.columns else None
    if grp_col is None:
        # Use index as month label
        nomina = nomina.copy()
        nomina["Mes"] = "Período"
        grp_col = "Mes"

    grp = nomina.groupby(grp_col).agg(
        Devengado=("Devengado", "sum"),
        Deducido=("Deducido", "sum") if "Deducido" in nomina.columns else ("Devengado", "count"),
        ReteFuente=("Rete Fuente", "sum") if "Rete Fuente" in nomina.columns else ("Devengado", "count"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Devengado", x=grp[grp_col], y=grp["Devengado"],
        marker_color=SUCCESS,
        text=[_fmt_cop(v) for v in grp["Devengado"]],
        textposition="inside", textfont=dict(color=TEXT_WHITE, size=10),
    ))
    if "Deducido" in nomina.columns:
        fig.add_trace(go.Bar(
            name="Deducido", x=grp[grp_col], y=grp["Deducido"],
            marker_color=DANGER,
            text=[_fmt_cop(v) for v in grp["Deducido"]],
            textposition="inside", textfont=dict(color=TEXT_WHITE, size=10),
        ))
    if "Rete Fuente" in nomina.columns:
        fig.add_trace(go.Scatter(
            name="Rete Fuente",
            x=grp[grp_col], y=grp["ReteFuente"],
            mode="lines+markers+text",
            marker=dict(color=WARNING, size=8),
            line=dict(color=WARNING, width=2),
            text=[_fmt_cop(v) for v in grp["ReteFuente"]],
            textposition="top center",
            textfont=dict(color=WARNING, size=10),
        ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="👥 Nómina — Devengado vs Deducido", font=dict(size=15, color=TEXT_WHITE)),
        barmode="group",
        xaxis=dict(color=TEXT_WHITE),
        yaxis=dict(color=TEXT_WHITE, tickformat="$,.0f", gridcolor="rgba(255,255,255,0.07)"),
        height=360,
    )
    return fig


def chart_top_empleados(nomina: pd.DataFrame, n: int = 10) -> go.Figure:
    """Top empleados por devengado."""
    if nomina.empty or "Devengado" not in nomina.columns:
        return _empty_fig("Sin datos de nómina")

    name_col = "Nombre Empleado" if "Nombre Empleado" in nomina.columns else nomina.columns[0]
    df = nomina.groupby(name_col)["Devengado"].sum().sort_values(ascending=True).tail(n).reset_index()
    df.columns = ["Empleado", "Devengado"]

    fig = go.Figure(go.Bar(
        x=df["Devengado"],
        y=df["Empleado"].apply(lambda x: str(x)[:30]),
        orientation="h",
        marker=dict(color=df["Devengado"], colorscale=[[0, PRIMARY], [1, SUCCESS]], showscale=False),
        text=[_fmt_cop(v) for v in df["Devengado"]],
        textposition="outside",
        textfont=dict(color=TEXT_WHITE, size=10),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text=f"🏆 Top {n} Empleados por Devengado", font=dict(size=15, color=TEXT_WHITE)),
        xaxis=dict(tickformat="$,.0f", color=TEXT_WHITE, gridcolor="rgba(255,255,255,0.07)"),
        yaxis=dict(color=TEXT_WHITE, automargin=True),
        height=max(300, n * 35),
    )
    return fig


def chart_nomina_composicion(kpis: dict) -> go.Figure:
    """Pie chart: costo laboral total breakdown."""
    dev = kpis.get("total_devengado", 0)
    carga = kpis.get("carga_patronal_est", 0)
    if dev == 0:
        return _empty_fig("Sin datos de nómina")

    fig = go.Figure(go.Pie(
        labels=["Devengado Empleados", "Carga Patronal Estimada"],
        values=[dev, carga],
        hole=0.5,
        marker=dict(colors=[SUCCESS, ACCENT]),
        textinfo="label+percent",
        textfont=dict(color=TEXT_WHITE, size=11),
        hovertemplate="%{label}: %{value:$,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="⚖️ Composición Costo Laboral", font=dict(size=15, color=TEXT_WHITE)),
        height=300,
    )
    return fig


# ─── Exógena charts ───────────────────────────────────────────────────────────
def chart_exogena_cruce(ventas: pd.DataFrame, exogena: pd.DataFrame) -> go.Figure:
    """Side-by-side: ventas FE vs valor exógena clientes."""
    fe_total   = ventas["Total"].sum() if not ventas.empty and "Total" in ventas.columns else 0
    exg_total  = exogena["Valor Bruto"].sum() if not exogena.empty and "Valor Bruto" in exogena.columns else 0
    diferencia = fe_total - exg_total

    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="Ventas FE (DIAN)", x=["Facturación Electrónica"], y=[fe_total],
        marker_color=SUCCESS,
        text=[_fmt_cop(fe_total)], textposition="outside",
        textfont=dict(color=TEXT_WHITE),
    ))
    fig.add_trace(go.Bar(
        name="Exógena Reportada", x=["Información Exógena"], y=[exg_total],
        marker_color=SECONDARY,
        text=[_fmt_cop(exg_total)], textposition="outside",
        textfont=dict(color=TEXT_WHITE),
    ))
    fig.add_trace(go.Bar(
        name="Diferencia", x=["Diferencia"], y=[abs(diferencia)],
        marker_color=DANGER if diferencia != 0 else SUCCESS,
        text=[_fmt_cop(diferencia)], textposition="outside",
        textfont=dict(color=TEXT_WHITE),
    ))

    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="🔍 Cruce FE vs Información Exógena", font=dict(size=15, color=TEXT_WHITE)),
        barmode="group",
        xaxis=dict(color=TEXT_WHITE),
        yaxis=dict(color=TEXT_WHITE, tickformat="$,.0f", gridcolor="rgba(255,255,255,0.07)"),
        height=340,
        showlegend=True,
    )
    return fig


def chart_retenciones_tipos(compras: pd.DataFrame) -> go.Figure:
    """Pie chart of retention types in purchases."""
    if compras.empty:
        return _empty_fig("Sin datos de compras")

    ret_cols = [c for c in ["Rete Renta", "Rete IVA", "Rete ICA"] if c in compras.columns]
    if not ret_cols:
        return _empty_fig("Sin columnas de retención")

    totals = {col: compras[col].sum() for col in ret_cols if compras[col].sum() > 0}
    if not totals:
        return _empty_fig("Sin retenciones registradas")

    fig = go.Figure(go.Pie(
        labels=list(totals.keys()),
        values=list(totals.values()),
        hole=0.5,
        marker=dict(colors=[DANGER, SECONDARY, WARNING]),
        textinfo="label+percent+value",
        texttemplate="%{label}<br>%{percent}<br>%{value:$,.0f}",
        textfont=dict(color=TEXT_WHITE, size=10),
    ))
    fig.update_layout(
        **LAYOUT_BASE,
        title=dict(text="✂️ Tipos de Retención en Compras", font=dict(size=15, color=TEXT_WHITE)),
        height=320,
    )
    return fig
