"""
Motor de cálculo: llenado completo de ubicaciones ZM_CAJ (cajas) y ZM_PICK (pallet)
--------------------------------------------------------
Reglas:
1. Destino  = ubicaciones con zona de movimiento ZM_CAJ / ZM_PICK que tienen artículo asignado (PREFERENCIA).
2. Faltante = capacidad máxima (piezas/cajas) - stock actual del artículo en la ubicación.
3. Origen   = LPN en áreas ALMAC / ALMPIC, estado D, que existan en la cuadratura de stock.
4. Orden    = FEFO (fecha de caducidad más próxima primero); a igual caducidad (o dentro
              de la tolerancia configurada) se atacan primero los LPN con MENOS cajas (restos),
              para no abrir pallets completos.
"""
import io
import re
import pandas as pd

AREAS_ORIGEN_DEFAULT = ["ALMAC", "ALMPIC"]
ZONAS_DESTINO_DEFAULT = ["ZM_CAJ"]
# nombre para mostrar en pantalla / hoja de operarios
NOMBRE_ZONA = {"ZM_CAJ": "ZM_CAJAS", "ZM_PICK": "ZM_PALLET"}


# ------------------------------------------------------------------ utilidades
def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _txt(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().replace({"nan": "", "None": ""})


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce").fillna(0)


def _leer_csv(archivo, sep=None) -> pd.DataFrame:
    """Lee CSV desde ruta o UploadedFile detectando separador y codificación."""
    raw = archivo.read() if hasattr(archivo, "read") else open(archivo, "rb").read()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            texto = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if sep is None:
        primera = texto.splitlines()[0]
        sep = ";" if primera.count(";") > primera.count(",") else ","
    return _norm_cols(pd.read_csv(io.StringIO(texto), sep=sep, dtype=str))


def nivel_de(ubic: str) -> str:
    partes = str(ubic).split("-")
    return partes[2] if len(partes) >= 3 else ""


def pasillo_de(ubic: str) -> str:
    partes = str(ubic).split("-")
    return partes[0] if partes else ""


# ------------------------------------------------------------------ carga
def cargar_cuadratura(archivo) -> pd.DataFrame:
    df = _leer_csv(archivo)
    req = {"area", "ubicacion", "articulo", "descripcion", "estado_de_inventario", "cantidad"}
    faltan = req - set(df.columns)
    if faltan:
        raise ValueError(f"A la cuadratura le faltan columnas: {', '.join(sorted(faltan))}")
    for c in ["area", "ubicacion", "articulo", "descripcion", "estado_de_inventario"]:
        df[c] = _txt(df[c])
    df["cantidad"] = _num(df["cantidad"])
    return df


def cargar_vida_util(archivo) -> pd.DataFrame:
    df = _leer_csv(archivo)
    req = {"Area", "Ubicacion", "LPN", "Articulo", "Descripcion", "Cantidad",
           "Estado de inventario", "Fecha de caducidad"}
    faltan = req - set(df.columns)
    if faltan:
        raise ValueError(f"A operaciones de vida útil le faltan columnas: {', '.join(sorted(faltan))}")
    for c in ["Area", "Ubicacion", "LPN", "Articulo", "Descripcion", "Estado de inventario"]:
        df[c] = _txt(df[c])
    df["Cantidad"] = _num(df["Cantidad"])
    df["Fecha de caducidad"] = pd.to_datetime(df["Fecha de caducidad"], dayfirst=True, errors="coerce")
    if "Fecha de fabricacion" in df.columns:
        df["Fecha de fabricacion"] = pd.to_datetime(df["Fecha de fabricacion"], dayfirst=True, errors="coerce")
    else:
        df["Fecha de fabricacion"] = pd.NaT
    if "Vida util" in df.columns:
        df["Vida util"] = pd.to_numeric(df["Vida util"], errors="coerce")
    return df


def cargar_maestros(ruta_ubic, ruta_pref, ruta_zonas):
    ubic = _leer_csv(ruta_ubic, sep=",")
    pref = _leer_csv(ruta_pref, sep=",")
    zonas = _leer_csv(ruta_zonas, sep=",")

    ubic = ubic.rename(columns={"NOMBRE UBICACIÓN": "ubicacion", "AREA": "area_maestro",
                                "CAPACIDAD MAXIMA": "capacidad_txt"})
    ubic["ubicacion"] = _txt(ubic["ubicacion"])
    ubic["capacidad"] = ubic["capacidad_txt"].astype(str).str.extract(r"(\d+)")[0].astype(float)
    ubic["unidad_cap"] = ubic["capacidad_txt"].astype(str).str.extract(r"\d+\s*(\S+)")[0]

    pref = pref.rename(columns={"Ubicación": "ubicacion", "Número de artículo": "articulo",
                                "Secuencia": "secuencia"})
    pref["ubicacion"] = _txt(pref["ubicacion"])
    pref["articulo"] = _txt(pref["articulo"])
    pref["secuencia"] = pd.to_numeric(pref["secuencia"], errors="coerce")

    zonas = zonas.rename(columns={"UBICACIÓN": "ubicacion", "ZONA DE TRABAJO": "zona_trabajo",
                                  "ZONA DE MOVIMIENTO": "zona_movimiento", "ZONA DE RECOGIDA": "zona_recogida"})
    for c in zonas.columns:
        zonas[c] = _txt(zonas[c])
    return ubic, pref, zonas


def cargar_paletizado(archivo) -> pd.DataFrame:
    """Norma de paletizado: acepta la BBDD (.xlsx) o el maestro paletizado.csv.
    Devuelve articulo | cajas_por_pallet (solo valores > 0, uno por artículo)."""
    nombre = getattr(archivo, "name", str(archivo)).lower()
    if nombre.endswith((".xlsx", ".xls")):
        df = _norm_cols(pd.read_excel(archivo, dtype=str))
    else:
        df = _leer_csv(archivo)
    df = df.rename(columns={"Numero de material": "articulo", "Número de material": "articulo",
                            "Cajas por Pallet": "cajas_por_pallet"})
    if not {"articulo", "cajas_por_pallet"} <= set(df.columns):
        raise ValueError("La norma de paletizado debe traer 'Numero de material' y 'Cajas por Pallet'")
    df["articulo"] = _txt(df["articulo"])
    df["cajas_por_pallet"] = _num(df["cajas_por_pallet"])
    df = df[df["cajas_por_pallet"] > 0]
    return df.groupby("articulo", as_index=False)["cajas_por_pallet"].max()


# ------------------------------------------------------------------ cálculo
def calcular(cuad: pd.DataFrame, vu: pd.DataFrame, ubic: pd.DataFrame, pref: pd.DataFrame,
             zonas: pd.DataFrame, paletizado: pd.DataFrame = None, areas_origen=None, tolerancia_dias: int = 0,
             vida_util_min: int = 0, permitir_parcial: bool = True, fecha_ref=None,
             zonas_destino=None):
    """zonas_destino: lista en orden de prioridad (p.ej. ["ZM_CAJ", "ZM_PICK"]);
    la primera zona se abastece antes que la segunda cuando comparten artículo."""
    zonas_destino = list(zonas_destino or ZONAS_DESTINO_DEFAULT)
    areas_origen = areas_origen or AREAS_ORIGEN_DEFAULT
    fecha_ref = pd.Timestamp(fecha_ref or pd.Timestamp.today().normalize())
    alertas = []

    # ---------- 1. Ubicaciones destino (ZM_CAJ / ZM_PICK)
    dest = zonas[zonas["zona_movimiento"].str.upper().isin(zonas_destino)][
        ["ubicacion", "zona_trabajo", "zona_movimiento"]].drop_duplicates("ubicacion")
    dest = dest.merge(ubic[["ubicacion", "capacidad", "unidad_cap"]], on="ubicacion", how="left")
    dest = dest.merge(pref[["ubicacion", "articulo", "secuencia"]], on="ubicacion", how="left")

    sin_art = dest[dest["articulo"].isna() | (dest["articulo"] == "")]
    for _, r in sin_art.iterrows():
        alertas.append({"tipo": f"Ubicación {NOMBRE_ZONA.get(r['zona_movimiento'], r['zona_movimiento'])} sin artículo asignado", "ubicacion": r["ubicacion"],
                        "articulo": "", "detalle": "No existe en hoja de preferencias"})
    dest = dest[~dest.index.isin(sin_art.index)].copy()

    # stock actual en la ubicación destino (todas las filas de la cuadratura)
    stock_ubic = cuad[cuad["ubicacion"].isin(dest["ubicacion"])]
    st_art = (stock_ubic.groupby(["ubicacion", "articulo"], as_index=False)["cantidad"].sum()
              .rename(columns={"cantidad": "stock_actual"}))
    dest = dest.merge(st_art, on=["ubicacion", "articulo"], how="left")
    dest["stock_actual"] = dest["stock_actual"].fillna(0)

    # ubicaciones ocupadas por otro artículo -> no se reponen
    otros = stock_ubic.merge(dest[["ubicacion", "articulo"]], on="ubicacion", suffixes=("", "_pref"))
    otros = otros[otros["articulo"] != otros["articulo_pref"]]
    ubic_mezcla = set(otros["ubicacion"])
    for _, r in otros.iterrows():
        alertas.append({"tipo": "Ubicación con otro artículo (no se repone)", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"],
                        "detalle": f"Asignado {r['articulo_pref']} | encontrado {r['articulo']} "
                                   f"({int(r['cantidad'])} cj, estado {r['estado_de_inventario']})"})

    sin_cap = dest[dest["capacidad"].isna()]
    for _, r in sin_cap.iterrows():
        alertas.append({"tipo": "Ubicación sin capacidad en maestro", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"], "detalle": "Revisar hoja UBICACIONES"})

    dest["capacidad"] = dest["capacidad"].fillna(0)
    dest["faltante"] = (dest["capacidad"] - dest["stock_actual"]).clip(lower=0)
    dest.loc[dest["ubicacion"].isin(ubic_mezcla), "faltante"] = 0
    sobre = dest[dest["stock_actual"] > dest["capacidad"]]
    for _, r in sobre.iterrows():
        alertas.append({"tipo": "Sobre capacidad", "ubicacion": r["ubicacion"], "articulo": r["articulo"],
                        "detalle": f"Stock {int(r['stock_actual'])} > capacidad {int(r['capacidad'])}"})
    dest["prioridad_zona"] = dest["zona_movimiento"].str.upper().map({z: i for i, z in enumerate(zonas_destino)})
    dest["zona"] = dest["zona_movimiento"].map(lambda z: NOMBRE_ZONA.get(z, z))
    dest["pasillo"] = dest["ubicacion"].map(pasillo_de)
    dest = dest.sort_values(["prioridad_zona", "secuencia", "ubicacion"]).reset_index(drop=True)

    # ---------- 2. Stock origen: cuadratura (verdad) + vida útil (detalle LPN / fechas)
    cu_o = cuad[cuad["area"].isin(areas_origen) & (cuad["estado_de_inventario"] == "D")]
    cu_o = cu_o.groupby(["ubicacion", "articulo", "area"], as_index=False).agg(
        cant_cuadratura=("cantidad", "sum"), descripcion=("descripcion", "first"))

    vu_o = vu[(vu["Estado de inventario"] == "D")].rename(columns={
        "Ubicacion": "ubicacion", "Articulo": "articulo", "LPN": "lpn", "Cantidad": "cant_lpn",
        "Fecha de caducidad": "caducidad", "Fecha de fabricacion": "fabricacion"})
    vu_o = vu_o[["ubicacion", "articulo", "lpn", "cant_lpn", "caducidad", "fabricacion"]]

    # estándar de pallet estimado = máximo de cajas vistas en un LPN del artículo (todas las áreas)
    std_pallet = vu[vu["Estado de inventario"] == "D"].groupby("Articulo")["Cantidad"].max()

    lpns = cu_o.merge(vu_o, on=["ubicacion", "articulo"], how="left")

    # LPN en vida útil (áreas origen) que NO están en la cuadratura -> no se usan
    vu_area = vu[vu["Area"].isin(areas_origen) & (vu["Estado de inventario"] == "D")]
    llave_cu = set(zip(cu_o["ubicacion"], cu_o["articulo"]))
    for _, r in vu_area.iterrows():
        if (r["Ubicacion"], r["Articulo"]) not in llave_cu:
            alertas.append({"tipo": "LPN en vida útil que no está en cuadratura (excluido)",
                            "ubicacion": r["Ubicacion"], "articulo": r["Articulo"],
                            "detalle": f"LPN {r['LPN']} ({int(r['Cantidad'])} cj)"})

    # sin detalle de LPN / sin fecha -> no se puede asegurar FEFO
    sin_fecha = lpns[lpns["lpn"].isna() | lpns["caducidad"].isna()]
    for _, r in sin_fecha.drop_duplicates(["ubicacion", "articulo"]).iterrows():
        alertas.append({"tipo": "Stock sin fecha de caducidad (excluido por FEFO)", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"],
                        "detalle": f"{int(r['cant_cuadratura'])} cj en cuadratura sin LPN/fecha en vida útil"})
    lpns = lpns[lpns["lpn"].notna() & lpns["caducidad"].notna()].copy()

    # ajustar a la cuadratura: si vida útil suma más que la cuadratura, se recorta desde el LPN más nuevo
    lpns = lpns.sort_values(["ubicacion", "articulo", "caducidad", "cant_lpn"])
    lpns["acum"] = lpns.groupby(["ubicacion", "articulo"])["cant_lpn"].cumsum()
    previo = lpns["acum"] - lpns["cant_lpn"]
    lpns["disponible"] = (lpns["cant_cuadratura"] - previo).clip(lower=0).clip(upper=lpns["cant_lpn"])
    dif = lpns.groupby(["ubicacion", "articulo"]).agg(v=("cant_lpn", "sum"), c=("cant_cuadratura", "first"))
    for (u, a), r in dif[dif["v"] != dif["c"]].iterrows():
        alertas.append({"tipo": "Diferencia cuadratura vs vida útil", "ubicacion": u, "articulo": a,
                        "detalle": f"Cuadratura {int(r['c'])} cj | vida útil {int(r['v'])} cj "
                                   f"(se usa el menor; FEFO sobre lo que tiene fecha)"})
    lpns = lpns[lpns["disponible"] > 0].copy()

    # vida útil mínima
    lpns["dias_vida"] = (lpns["caducidad"] - fecha_ref).dt.days
    excl = lpns[lpns["dias_vida"] <= vida_util_min]
    for _, r in excl.iterrows():
        alertas.append({"tipo": "LPN excluido por vida útil", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"],
                        "detalle": f"LPN {r['lpn']} vence {r['caducidad']:%d-%m-%Y} ({int(r['dias_vida'])} días)"})
    lpns = lpns[lpns["dias_vida"] > vida_util_min].copy()

    # norma de paletizado (BBDD); si el artículo no está, se estima con el mayor LPN visto
    norma = (paletizado.set_index("articulo")["cajas_por_pallet"]
             if paletizado is not None and not paletizado.empty else pd.Series(dtype=float))
    lpns["norma_pallet"] = lpns["articulo"].map(norma)
    lpns["fuente_norma"] = lpns["norma_pallet"].notna().map({True: "BBDD", False: "Estimada"})
    lpns["norma_pallet"] = lpns["norma_pallet"].fillna(lpns["articulo"].map(std_pallet)).fillna(lpns["disponible"])
    lpns["pct_pallet"] = (lpns["disponible"] / lpns["norma_pallet"]).clip(upper=9.99)
    lpns["tipo_lpn"] = (lpns["disponible"] < lpns["norma_pallet"]).map({True: "Resto", False: "Pallet completo"})
    lpns["es_pallet"] = (lpns["tipo_lpn"] == "Pallet completo").astype(int)
    for _, r in lpns[lpns["fuente_norma"] == "Estimada"].drop_duplicates("articulo").iterrows():
        alertas.append({"tipo": "Artículo sin norma de paletizado (se estima)", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"],
                        "detalle": f"Se usa {int(r['norma_pallet'])} cj/pallet (mayor LPN visto)"})
    for _, r in lpns[lpns["disponible"] > lpns["norma_pallet"]].iterrows():
        alertas.append({"tipo": "LPN con más cajas que la norma", "ubicacion": r["ubicacion"],
                        "articulo": r["articulo"],
                        "detalle": f"LPN {r['lpn']}: {int(r['disponible'])} cj vs norma {int(r['norma_pallet'])}"})
    lpns["nivel"] = lpns["ubicacion"].map(nivel_de)

    # ---------- 3. Asignación FEFO + restos primero
    movs = []
    resumen = []
    lpns["restante"] = lpns["disponible"]
    for art, grupo_dest in dest.groupby("articulo", sort=False):
        cand = lpns[lpns["articulo"] == art].copy()
        if not cand.empty:
            base = cand["caducidad"].min()
            cand["bloque_fefo"] = ((cand["caducidad"] - base).dt.days // (tolerancia_dias + 1))
            # FEFO -> dentro del bloque: restos (menos cajas) primero -> niveles altos primero para liberarlos
            cand = cand.sort_values(["bloque_fefo", "caducidad", "es_pallet", "disponible", "nivel"],
                                    ascending=[True, True, True, True, False])
        for _, d in grupo_dest.iterrows():
            falta = d["faltante"]
            asignado = 0
            if falta > 0 and not cand.empty:
                for idx in cand.index:
                    rest = lpns.at[idx, "restante"]
                    if rest <= 0:
                        continue
                    if falta <= 0:
                        break
                    if not permitir_parcial and rest > falta:
                        # no abrir el LPN: se detiene para no saltarse FEFO
                        break
                    tomar = min(rest, falta)
                    r = lpns.loc[idx]
                    movs.append({
                        "secuencia": d["secuencia"],
                        "ubicacion_origen": r["ubicacion"],
                        "area_origen": r["area"],
                        "nivel_origen": r["nivel"],
                        "lpn": r["lpn"],
                        "articulo": art,
                        "descripcion": r["descripcion"],
                        "caducidad": r["caducidad"],
                        "dias_vida": int(r["dias_vida"]),
                        "cajas_lpn": int(rest),
                        "norma_pallet": int(r["norma_pallet"]),
                        "pct_pallet": round(float(r["pct_pallet"]) * 100),
                        "tipo_lpn": r["tipo_lpn"],
                        "fuente_norma": r["fuente_norma"],
                        "cajas_a_mover": int(tomar),
                        "queda_en_lpn": int(rest - tomar),
                        "accion": "Mover LPN completo" if tomar == rest else f"Parcial (queda resto {int(rest - tomar)})",
                        "ubicacion_destino": d["ubicacion"],
                        "pasillo_destino": d["pasillo"],
                        "zona": d["zona"],
                        "zona_trabajo": d["zona_trabajo"],
                    })
                    lpns.at[idx, "restante"] = rest - tomar
                    falta -= tomar
                    asignado += tomar
            if d["ubicacion"] in ubic_mezcla:
                estado = "Bloqueada (otro artículo)"
            elif d["faltante"] <= 0:
                estado = "Ya estaba llena"
            elif asignado >= d["faltante"]:
                estado = "Queda llena"
            elif asignado > 0:
                estado = "Llenado parcial (sin más stock)"
            else:
                estado = "Sin stock en almacenamiento"
            resumen.append({
                "secuencia": d["secuencia"], "ubicacion_destino": d["ubicacion"],
                "pasillo_destino": d["pasillo"], "zona": d["zona"],
                "zona_trabajo": d["zona_trabajo"], "articulo": art,
                "capacidad": int(d["capacidad"]), "stock_actual": int(d["stock_actual"]),
                "faltante": int(d["faltante"]), "a_reponer": int(asignado),
                "stock_final": int(d["stock_actual"] + asignado),
                "pendiente": int(d["faltante"] - asignado), "estado": estado,
            })

    movs = pd.DataFrame(movs)
    resumen = pd.DataFrame(resumen)
    desc = pd.concat([cuad[["articulo", "descripcion"]], vu[["Articulo", "Descripcion"]].rename(
        columns={"Articulo": "articulo", "Descripcion": "descripcion"})]).drop_duplicates("articulo")
    if not resumen.empty:
        resumen = resumen.merge(desc, on="articulo", how="left")
        cols = ["secuencia", "ubicacion_destino", "pasillo_destino", "zona", "zona_trabajo", "articulo", "descripcion", "capacidad",
                "stock_actual", "faltante", "a_reponer", "stock_final", "pendiente", "estado"]
        resumen = resumen[cols].sort_values(["secuencia", "ubicacion_destino"])
    if not movs.empty:
        movs = movs.sort_values(["secuencia", "ubicacion_destino", "caducidad"]).reset_index(drop=True)
        movs.insert(0, "n_tarea", range(1, len(movs) + 1))
        movs = movs.drop(columns="secuencia")

    alertas = pd.DataFrame(alertas, columns=["tipo", "ubicacion", "articulo", "detalle"])
    return movs, resumen, alertas


# ------------------------------------------------------------------ exportación
def a_excel(movs, resumen, alertas, parametros: dict) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter", datetime_format="dd-mm-yyyy") as xw:
        wb = xw.book
        head = wb.add_format({"bold": True, "font_name": "Arial", "font_size": 10, "bg_color": "#1F3864",
                              "font_color": "white", "border": 1, "text_wrap": True, "valign": "vcenter"})
        body = wb.add_format({"font_name": "Arial", "font_size": 10})
        hojas = [("Hoja operarios", hoja_operarios(movs)), ("Movimientos", movs),
                 ("Resumen ubicaciones", resumen), ("Alertas", alertas)]
        for nombre, df in hojas:
            df = df if not df.empty else pd.DataFrame({"info": ["Sin registros"]})
            df.to_excel(xw, sheet_name=nombre, index=False)
            ws = xw.sheets[nombre]
            for i, col in enumerate(df.columns):
                ws.write(0, i, col, head)
                ancho = max(len(str(col)), df[col].astype(str).str.len().max() if len(df) else 0)
                ws.set_column(i, i, min(max(ancho + 2, 10), 45), body)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        p = pd.DataFrame(list(parametros.items()), columns=["Parámetro", "Valor"])
        p.to_excel(xw, sheet_name="Parámetros", index=False)
        xw.sheets["Parámetros"].set_column(0, 1, 40, body)
    return buf.getvalue()


def a_excel_hoja(hoja: pd.DataFrame, parametros: dict) -> bytes:
    """Excel simple solo con la hoja para operarios (lista para imprimir)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        wb = xw.book
        head = wb.add_format({"bold": True, "font_name": "Arial", "font_size": 10, "bg_color": "#1E293B",
                              "font_color": "white", "border": 1, "align": "center", "valign": "vcenter"})
        cel = wb.add_format({"font_name": "Arial", "font_size": 10, "border": 1})
        tit = wb.add_format({"bold": True, "font_name": "Arial", "font_size": 14})
        hoja.to_excel(xw, sheet_name="Hoja operarios", index=False, startrow=3)
        ws = xw.sheets["Hoja operarios"]
        ws.write(0, 0, "REABASTO ZM / HOJA DE RUTA", tit)
        ws.write(1, 0, " | ".join(f"{k}: {v}" for k, v in parametros.items()))
        cols = list(hoja.columns) + ["Check (✓)"]
        for i, c in enumerate(cols):
            ws.write(3, i, c, head)
            ancho = max(len(c), hoja[c].astype(str).str.len().max() if c in hoja and len(hoja) else 0)
            ws.set_column(i, i, min(max(ancho + 2, 8), 45))
        for r in range(len(hoja)):
            for i, c in enumerate(cols):
                v = hoja.iloc[r][c] if c in hoja else ""
                ws.write(4 + r, i, v.item() if hasattr(v, "item") else v, cel)
        ws.set_landscape(); ws.set_paper(9); ws.fit_to_pages(1, 0); ws.repeat_rows(3)
    return buf.getvalue()


# ------------------------------------------------------------------ hoja de operarios
def hoja_operarios(movs: pd.DataFrame, incluir_lpn: bool = False) -> pd.DataFrame:
    """Vista simple para bodega: SKU | Descripción | Origen | Destino | Cantidad."""
    if movs is None or movs.empty:
        return pd.DataFrame()
    df = movs.copy()
    out = pd.DataFrame({
        "N°": range(1, len(df) + 1),
        "Pasillo": df["pasillo_destino"].values,
        "Zona": df["zona"].values,
        "SKU": df["articulo"].values,
        "Descripción": df["descripcion"].values,
        "Ubicación origen": df["ubicacion_origen"].values,
        "Ubicación destino": df["ubicacion_destino"].values,
        "Cantidad solicitada": df["cajas_a_mover"].values,
    })
    if incluir_lpn:
        out.insert(6, "LPN", df["lpn"].values)
        out.insert(7, "Vence", pd.to_datetime(df["caducidad"]).dt.strftime("%d-%m-%Y").values)
    return out


def html_hoja_ruta(hoja: pd.DataFrame, fecha_hora: str, filtros: str, pagina_por_pasillo: bool = True) -> str:
    """HTML imprimible (mismo patrón de la hoja de ruta de reabasto)."""
    from html import escape
    cols_extra = [c for c in ["LPN", "Vence"] if c in hoja.columns]
    cab_extra = "".join(f"<th>{c}</th>" for c in cols_extra)

    def bloque(df, titulo_pasillo):
        filas = ""
        for i, (_, r) in enumerate(df.iterrows(), start=1):
            extra = "".join(f'<td class="c mono">{escape(str(r[c]))}</td>' for c in cols_extra)
            filas += f"""
            <tr>
              <td class="c">{i}</td>
              <td class="mono b">{escape(str(r['SKU']))}</td>
              <td>{escape(str(r['Descripción']))}</td>
              <td class="c b org">{escape(str(r['Ubicación origen']))}</td>
              <td class="c b dst">{escape(str(r['Ubicación destino']))}</td>
              {extra}
              <td class="c b qty">{int(r['Cantidad solicitada'])}</td>
              <td class="chk"></td>
            </tr>"""
        zonas_txt = ", ".join(sorted(df["Zona"].unique()))
        return f"""
        <div class="report-card">
          <table class="header-table">
            <tr><td class="title">Reabasto ZM / Hoja de Ruta</td>
                <td class="r small"><strong>Fecha emisión:</strong> {fecha_hora}</td></tr>
            <tr><td class="sub"><strong>{titulo_pasillo}</strong> &nbsp;·&nbsp; Zona: {zonas_txt}
                 &nbsp;·&nbsp; Tareas: {len(df)} &nbsp;·&nbsp; Cajas: {int(df['Cantidad solicitada'].sum())}</td>
                <td class="r small">{escape(filtros)}</td></tr>
          </table>
          <table class="data-table">
            <thead><tr>
              <th>#</th><th>SKU</th><th>Descripción producto</th><th>Origen</th><th>Destino</th>
              {cab_extra}<th>Cantidad</th><th>Check (✓)</th>
            </tr></thead>
            <tbody>{filas}</tbody>
          </table>
          <table class="firmas"><tr>
            <td>Operario: ____________________</td><td>Hora inicio: ______</td>
            <td>Hora término: ______</td><td>Firma: ____________________</td>
          </tr></table>
        </div>"""

    if pagina_por_pasillo:
        partes = [bloque(g, f"Pasillo {p}") for p, g in hoja.groupby("Pasillo", sort=True)]
    else:
        pas = ", ".join(sorted(hoja["Pasillo"].unique()))
        partes = [bloque(hoja, f"Pasillos: {pas}")]
    cuerpo = '<div class="salto"></div>'.join(partes)

    return f"""
    <style>
      body {{ font-family: Arial, sans-serif; background:#fff; }}
      .report-card {{ border:2px solid #1E293B; border-radius:8px; padding:18px; margin-bottom:18px;
                      background:#FFFFFF; color:#0F172A; font-family:Arial, sans-serif; }}
      .header-table {{ width:100%; border-collapse:collapse; margin-bottom:10px; }}
      .header-table td {{ padding:3px; }}
      .title {{ font-size:20px; font-weight:bold; text-transform:uppercase; letter-spacing:1px; }}
      .sub {{ font-size:14px; color:#334155; }}
      .small {{ font-size:12px; color:#475569; }}
      .r {{ text-align:right; }}
      .data-table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
      .data-table th {{ background:#1E293B; color:#fff; border:1px solid #1E293B; padding:7px 5px;
                        font-size:12px; text-transform:uppercase; }}
      .data-table td {{ border:1px solid #94A3B8; padding:7px 5px; font-size:13px; }}
      .data-table tr:nth-child(even) td {{ background:#F8FAFC; }}
      .c {{ text-align:center; }} .b {{ font-weight:bold; }}
      .mono {{ font-family:monospace; font-size:13px; }}
      .org {{ color:#1E3A8A; font-size:14px; }} .dst {{ color:#065F46; font-size:14px; }}
      .qty {{ font-size:16px; }} .chk {{ width:70px; }}
      .firmas {{ width:100%; margin-top:14px; font-size:12px; }}
      .firmas td {{ padding-top:10px; }}
      @media print {{
        body {{ margin:0; padding:0; }}
        .no-print {{ display:none !important; }}
        .report-card {{ border:none; padding:0; margin:0; }}
        .salto {{ page-break-after:always; break-after:page; }}
        .data-table tr {{ page-break-inside:avoid; }}
        .data-table thead {{ display:table-header-group; }}
        @page {{ size: A4 landscape; margin: 10mm; }}
      }}
    </style>
    {cuerpo}"""
