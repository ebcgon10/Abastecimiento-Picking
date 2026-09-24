import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import streamlit.components.v1 as components

import pandas as pd
import streamlit as st

import motor

st.set_page_config(page_title="Abastecimiento Picking | CD Coquimbo", page_icon="📦", layout="wide")

BASE = os.path.dirname(os.path.abspath(__file__))
M = os.path.join(BASE, "maestros")
if not os.path.exists(os.path.join(M, "ubicaciones.csv")):
    M = BASE  # si los maestros quedaron en la raíz del repo

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.titulo {font-size: 1.8rem; font-weight: 700; color: inherit; margin-bottom: 0;}
.sub {color: #666; margin-top: 0;}
div[data-testid="stMetric"] {background: rgba(59, 130, 246, 0.10); border-radius: 10px;
                             padding: 10px 14px; border-left: 5px solid #3B82F6;}
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="titulo">📦 Llenado completo de ubicaciones ZM_CAJA</p>', unsafe_allow_html=True)
st.markdown('<p class="sub">CD Coquimbo · Reposición desde ALMAC / ALMPIC con FEFO y prioridad a restos de pallet</p>',
            unsafe_allow_html=True)


@st.cache_data
def maestros():
    return motor.cargar_maestros(os.path.join(M, "ubicaciones.csv"),
                                 os.path.join(M, "preferencia.csv"),
                                 os.path.join(M, "zonas.csv"))


@st.cache_data
def paletizado_base():
    return motor.cargar_paletizado(os.path.join(M, "paletizado.csv"))


# ------------------------------------------------------------------ barra lateral
with st.sidebar:
    kpi_tareas = st.empty()   # indicador de tareas (se llena después de calcular)
    st.header("1. Archivos")
    f_cuad = st.file_uploader("Cuadratura de stock (.csv)", type=["csv"])
    f_vu = st.file_uploader("Operaciones de vida útil (.csv)", type=["csv"])

    st.header("2. Parámetros")
    zonas_sel = st.multiselect("Zonas a llenar", ["ZM_CAJAS", "ZM_PALLET"], default=["ZM_CAJAS"],
                               help="ZM_CAJAS = zona de movimiento ZM_CAJ · ZM_PALLET = ZM_PICK. "
                                    "Si eliges ambas, se abastece primero la que aparece primero.")
    tol = st.number_input("Tolerancia FEFO (días)", 0, 60, 0,
                          help="0 = FEFO estricto. Con N días, los LPN que vencen dentro de la misma "
                               "ventana se consideran equivalentes y se toman primero los de menos cajas.")

    st.caption("**Reglas fijas:** origen solo ALMAC y ALMPIC · estado D · no se usan LPN vencidos · "
               "se permite sacar cajas de un LPN sin moverlo completo · vencimiento calculado "
               "a la fecha de hoy.")

# ------------------------------------------------------------------ reglas y normas fijas
AREAS_ORIGEN = ["ALMAC", "ALMPIC"]   # almacenamiento y almacenamiento picking
VIDA_UTIL_MIN = 0                    # solo se excluyen LPN vencidos
PERMITIR_PARCIAL = True              # se pueden sacar cajas sin mover el LPN completo
fecha_ref = datetime.now(ZoneInfo("America/Santiago")).date()

if not (f_cuad and f_vu):
    st.info("⬅️ Sube la **cuadratura de stock** y las **operaciones de vida útil** para calcular los movimientos.")
    with st.expander("¿Cómo calcula la app?", expanded=True):
        st.markdown("""
1. **Destinos:** ubicaciones de zona de movimiento **ZM_CAJ** con artículo asignado en preferencias.
2. **Faltante:** capacidad máxima (cajas) − stock actual del artículo en la ubicación.
   Si la ubicación tiene otro artículo, se bloquea y se informa en Alertas.
3. **Origen:** solo LPN en **ALMAC / ALMPIC**, estado **D**, que estén en la **cuadratura de stock**.
   Si vida útil y cuadratura no cuadran, se usa el menor valor.
4. **Orden de consumo:** **FEFO** (vence primero, sale primero). A igual vencimiento se toman
   primero los **restos** (LPN con menos cajas que la norma de paletizado de la BBDD),
   luego los de menos cajas y, a igualdad, los de niveles superiores,
   para liberar segundos niveles y no abrir pallets completos.
""")
    st.stop()

# ------------------------------------------------------------------ cálculo
try:
    cuad = motor.cargar_cuadratura(f_cuad)
    vu = motor.cargar_vida_util(f_vu)
    ub, pr, zm = maestros()
    pal = paletizado_base()
    if not zonas_sel:
        st.warning("Elige al menos una zona a llenar en la barra lateral.")
        st.stop()
    movs, resumen, alertas = motor.calcular(cuad, vu, ub, pr, zm, paletizado=pal, areas_origen=AREAS_ORIGEN,
                                            tolerancia_dias=int(tol), vida_util_min=VIDA_UTIL_MIN,
                                            permitir_parcial=PERMITIR_PARCIAL, fecha_ref=fecha_ref,
                                            zonas_destino=[{"ZM_CAJAS": "ZM_CAJ", "ZM_PALLET": "ZM_PICK"}[z]
                                                           for z in zonas_sel])
except Exception as e:
    st.error(f"No se pudo procesar: {e}")
    st.stop()

# ------------------------------------------------------------------ indicador (barra lateral)
kpi_tareas.metric("Tareas de movimiento", f"{len(movs):,}".replace(",", "."))


def excel_reporte(hojas: dict, parametros: dict) -> bytes:
    """Reporte con el detalle: Movimientos, Resumen por ubicación y Alertas."""
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd-mm-yyyy") as xw:
        head = xw.book.add_format({"bold": True, "font_name": "Arial", "font_size": 10, "bg_color": "#1F3864",
                                   "font_color": "white", "border": 1, "valign": "vcenter"})
        body = xw.book.add_format({"font_name": "Arial", "font_size": 10})
        for nombre, df in hojas.items():
            df = df if not df.empty else pd.DataFrame({"info": ["Sin registros"]})
            df.to_excel(xw, sheet_name=nombre, index=False)
            ws = xw.sheets[nombre]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, head)
                ancho = max(len(str(col)), df[col].astype(str).str.len().max())
                ws.set_column(j, j, min(max(ancho + 2, 10), 45), body)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        pd.DataFrame(list(parametros.items()), columns=["Parámetro", "Valor"]).to_excel(
            xw, sheet_name="Parámetros", index=False)
        xw.sheets["Parámetros"].set_column(0, 1, 40, body)
    return buf.getvalue()


# ------------------------------------------------------------------ hoja para operarios
st.subheader("🖨️ Hoja para operarios")
if movs.empty:
    st.warning("No hay movimientos por realizar con los archivos cargados.")
else:
    h1, h2 = st.columns([1, 2])
    zonas_h = h1.multiselect("Zona", sorted(movs["zona"].unique()),
                             default=sorted(movs["zona"].unique()), key="h_zona")
    base_h = movs[movs["zona"].isin(zonas_h)] if zonas_h else movs
    pasillos_h = h2.multiselect("Pasillo destino (primer tramo de la ubicación)",
                                sorted(base_h["pasillo_destino"].unique()),
                                placeholder="Todos los pasillos", key="h_pas")
    por_pasillo = st.checkbox("Una hoja por pasillo (salto de página)", value=True)

    sel = base_h[base_h["pasillo_destino"].isin(pasillos_h)] if pasillos_h else base_h
    # orden de la hoja: mayor cantidad de cajas a reponer primero
    sel = sel.sort_values(["cajas_a_mover", "ubicacion_destino"], ascending=[False, True])
    hoja = motor.hoja_operarios(sel)

    if hoja.empty:
        st.info("No hay tareas con esos filtros.")
    else:
        fecha_hora = datetime.now(ZoneInfo("America/Santiago")).strftime("%d-%m-%Y %H:%M")
        filtros = f"Zona: {', '.join(zonas_h) or 'Todas'} | Pasillos: {', '.join(pasillos_h) or 'Todos'}"
        html_report = motor.html_hoja_ruta(hoja, fecha_hora, filtros, pagina_por_pasillo=por_pasillo)

        components.html(
            f"""
            {html_report}
            <div style="margin-top:15px; text-align:center;" class="no-print">
                <button onclick="window.print()" style="background-color:#2563EB; color:white;
                    font-weight:bold; padding:12px 24px; font-size:16px; border:none;
                    border-radius:6px; cursor:pointer;">🖨️ Imprimir Hoja de Ruta</button>
            </div>
            """,
            height=800, scrolling=True,
        )

        sufijo = "_".join(pasillos_h) if pasillos_h else "todos"
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Hoja para operarios (HTML)",
                           data=f"<html><head><meta charset='utf-8'></head><body>{html_report}</body></html>",
                           file_name=f"hoja_ruta_pasillo_{sufijo}.html", mime="text/html",
                           use_container_width=True)
        d2.download_button("⬇️ Hoja para operarios (Excel)",
                           data=motor.a_excel_hoja(hoja, {"Emisión": fecha_hora, "Filtros": filtros}),
                           file_name=f"hoja_ruta_pasillo_{sufijo}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)

# ------------------------------------------------------------------ reporte (Excel con el detalle)
st.divider()
params = {
    "Fecha de referencia": fecha_ref.strftime("%d-%m-%Y"),
    "Zonas a llenar": ", ".join(zonas_sel),
    "Áreas de origen": ", ".join(AREAS_ORIGEN),
    "Tolerancia FEFO (días)": int(tol),
    "Vida útil mínima (días)": VIDA_UTIL_MIN,
    "Permitir parcial": "Sí" if PERMITIR_PARCIAL else "No",
    "Archivo cuadratura": f_cuad.name,
    "Archivo vida útil": f_vu.name,
}
st.download_button("📊 Reporte",
                   data=excel_reporte({"Movimientos": movs, "Resumen por ubicación": resumen,
                                       "Alertas": alertas}, params),
                   file_name=f"reporte_abastecimiento_{fecha_ref:%Y%m%d}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   type="primary", use_container_width=True,
                   help="Excel con Movimientos, Resumen por ubicación y Alertas")
