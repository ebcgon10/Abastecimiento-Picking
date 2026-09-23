import os
from datetime import date

import pandas as pd
import streamlit as st

import motor

st.set_page_config(page_title="Llenado ZM_CAJA | CD Coquimbo", page_icon="📦", layout="wide")

BASE = os.path.dirname(os.path.abspath(__file__))
M = os.path.join(BASE, "maestros")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem;}
.titulo {font-size: 1.8rem; font-weight: 700; color: #1F3864; margin-bottom: 0;}
.sub {color: #666; margin-top: 0;}
div[data-testid="stMetric"] {background: #F3F6FB; border-radius: 10px; padding: 10px 14px;
                             border-left: 5px solid #1F3864;}
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
    st.header("1. Archivos")
    f_cuad = st.file_uploader("Cuadratura de stock (.csv)", type=["csv"])
    f_vu = st.file_uploader("Operaciones de vida útil (.csv)", type=["csv"])

    st.header("2. Parámetros")
    areas = st.multiselect("Áreas de origen", ["ALMAC", "ALMPIC"], default=["ALMAC", "ALMPIC"],
                           help="ALMAC = almacenamiento, ALMPIC = almacenamiento picking")
    tol = st.number_input("Tolerancia FEFO (días)", 0, 60, 0,
                          help="0 = FEFO estricto. Con N días, los LPN que vencen dentro de la misma "
                               "ventana se consideran equivalentes y se toman primero los de menos cajas.")
    vu_min = st.number_input("Excluir LPN con vida útil ≤ (días)", 0, 365, 0,
                             help="0 = solo excluye vencidos.")
    parcial = st.checkbox("Permitir sacar cajas de un LPN sin moverlo completo", value=True,
                          help="Si se desmarca, solo se mueven LPN que caben completos en la ubicación.")
    fecha_ref = st.date_input("Fecha de referencia", value=date.today(), format="DD-MM-YYYY")

    with st.expander("Maestros (opcional)"):
        st.caption("La app ya trae ubicaciones, preferencias y zonas. Súbelos aquí solo si cambiaron.")
        f_ub = st.file_uploader("ubicaciones.csv", type=["csv"], key="ub")
        f_pr = st.file_uploader("preferencia.csv", type=["csv"], key="pr")
        f_zm = st.file_uploader("zonas.csv", type=["csv"], key="zm")
        f_pal = st.file_uploader("Norma de paletizado (BBDD .xlsx o paletizado.csv)",
                                 type=["xlsx", "csv"], key="pal")

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
    if f_ub or f_pr or f_zm:
        ub, pr, zm = motor.cargar_maestros(f_ub or os.path.join(M, "ubicaciones.csv"),
                                           f_pr or os.path.join(M, "preferencia.csv"),
                                           f_zm or os.path.join(M, "zonas.csv"))
    else:
        ub, pr, zm = maestros()
    pal = motor.cargar_paletizado(f_pal) if f_pal else paletizado_base()
    movs, resumen, alertas = motor.calcular(cuad, vu, ub, pr, zm, paletizado=pal, areas_origen=areas,
                                            tolerancia_dias=int(tol), vida_util_min=int(vu_min),
                                            permitir_parcial=parcial, fecha_ref=fecha_ref)
except Exception as e:
    st.error(f"No se pudo procesar: {e}")
    st.stop()

# ------------------------------------------------------------------ indicadores
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Tareas de movimiento", f"{len(movs):,}".replace(",", "."))
c2.metric("Cajas a mover", f"{int(movs['cajas_a_mover'].sum()) if len(movs) else 0:,}".replace(",", "."))
c3.metric("Ubicaciones que quedan llenas", int((resumen["estado"] == "Queda llena").sum()))
c4.metric("Sin stock para reponer", int((resumen["estado"] == "Sin stock en almacenamiento").sum()))
c5.metric("LPN restos liberados",
          int(((movs["tipo_lpn"] == "Resto") & (movs["queda_en_lpn"] == 0)).sum()) if len(movs) else 0)

tab1, tab2, tab3 = st.tabs(["🚚 Movimientos", "📍 Resumen por ubicación", "⚠️ Alertas"])

with tab1:
    if movs.empty:
        st.warning("No hay movimientos por realizar con los parámetros actuales.")
    else:
        f1, f2, f3 = st.columns(3)
        zt = f1.multiselect("Zona de trabajo", sorted(movs["zona_trabajo"].dropna().unique()))
        tipo = f2.multiselect("Tipo de LPN origen", ["Resto", "Pallet completo"])
        buscar = f3.text_input("Buscar artículo / ubicación / LPN")
        vista = movs.copy()
        if zt:
            vista = vista[vista["zona_trabajo"].isin(zt)]
        if tipo:
            vista = vista[vista["tipo_lpn"].isin(tipo)]
        if buscar:
            b = buscar.upper()
            vista = vista[vista.apply(lambda r: b in " ".join(map(str, r.values)).upper(), axis=1)]
        st.dataframe(vista, use_container_width=True, hide_index=True,
                     column_config={"caducidad": st.column_config.DateColumn("caducidad", format="DD-MM-YYYY")})
        st.caption("Tipo de LPN según la norma de cajas por pallet de la BBDD. "
                   "pct_pallet = % del pallet que tiene el LPN. Si fuente_norma = Estimada, "
                   "el artículo no está en la BBDD y se usa el mayor LPN visto.")

with tab2:
    est = st.multiselect("Estado", sorted(resumen["estado"].unique()),
                         default=[e for e in resumen["estado"].unique() if e != "Ya estaba llena"])
    st.dataframe(resumen[resumen["estado"].isin(est)] if est else resumen,
                 use_container_width=True, hide_index=True)
    st.bar_chart(resumen["estado"].value_counts())

with tab3:
    if alertas.empty:
        st.success("Sin alertas.")
    else:
        st.dataframe(alertas["tipo"].value_counts().rename("cantidad"), use_container_width=True)
        tip = st.selectbox("Ver detalle de", ["Todas"] + sorted(alertas["tipo"].unique()))
        st.dataframe(alertas if tip == "Todas" else alertas[alertas["tipo"] == tip],
                     use_container_width=True, hide_index=True)

# ------------------------------------------------------------------ descarga
params = {
    "Fecha de referencia": fecha_ref.strftime("%d-%m-%Y"),
    "Áreas de origen": ", ".join(areas),
    "Tolerancia FEFO (días)": int(tol),
    "Vida útil mínima (días)": int(vu_min),
    "Permitir parcial": "Sí" if parcial else "No",
    "Archivo cuadratura": f_cuad.name,
    "Archivo vida útil": f_vu.name,
}
st.download_button("⬇️ Descargar Excel de movimientos",
                   data=motor.a_excel(movs, resumen, alertas, params),
                   file_name=f"llenado_ZM_CAJA_{fecha_ref:%Y%m%d}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   type="primary")
