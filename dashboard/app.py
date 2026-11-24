"""Tablero de la Sala de crisis COVID-19 · Gestión de Datos 2026-2.

Se corre desde la raíz del repositorio:
    streamlit run dashboard/app.py

Lee el DW que deja 03_dw (data/dw/covid_dw.zip). Las funciones pronosticar, alerta y suprimir
son copias de 06_mineria y 04_proteccion: el tablero funciona solo, sin importar código de otros archivos.
"""
import sqlite3
import zipfile
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from statsmodels.tsa.holtwinters import ExponentialSmoothing

RAIZ = Path(__file__).parent.parent
CARPETA_DW = RAIZ / "data" / "dw"
PRIMER_DIA = date(2020, 1, 22)
ULTIMO_DIA = date(2023, 3, 9)
UMBRAL_ALERTA = 25        # % de subida semanal de la incidencia
PISO_ALERTA = 5           # casos por 100.000
UMBRAL_POBLACION = 100_000  # bajo esto se suprimen las celdas pequeñas

st.set_page_config(page_title="Sala de crisis COVID-19", page_icon="🦠", layout="wide")


# ---------------------------------------------------------------- 1 · Datos del DW

@st.cache_resource
def conectar():
    """Conexión al DW; si el .db no está, se descomprime el zip (pesa ~130 MB)."""
    if not (CARPETA_DW / "covid_dw.db").exists():
        zipfile.ZipFile(CARPETA_DW / "covid_dw.zip").extractall(CARPETA_DW)
    return sqlite3.connect(CARPETA_DW / "covid_dw.db", check_same_thread=False)


PAISES = """
    SELECT t.pais, d.fecha,
           SUM(f.casos_acumulados)      AS casos_acumulados,
           SUM(f.fallecidos_acumulados) AS fallecidos_acumulados,
           MAX(t.poblacion_pais)        AS poblacion
    FROM fact_covid f
    JOIN dim_territorio t ON t.territorio_key = f.territorio_key
    JOIN dim_fecha d      ON d.fecha_key = f.fecha_key
    GROUP BY t.pais, d.fecha
    ORDER BY t.pais, d.fecha
"""

REGIONES_CHILE = """
    SELECT t.region_estado AS region, d.fecha, t.lat, t.long, t.poblacion,
           f.casos_acumulados, f.fallecidos_acumulados
    FROM fact_covid f
    JOIN dim_territorio t ON t.territorio_key = f.territorio_key
    JOIN dim_fecha d      ON d.fecha_key = f.fecha_key
    WHERE t.pais = 'Chile' AND t.nivel = 'region' AND t.poblacion IS NOT NULL
"""


@st.cache_data
def cargar_paises():
    """Casos y fallecidos nuevos por día de los 196 países (se suman los acumulados y después se resta el día anterior) y de las 16 regiones de Chile."""
    datos = pd.read_sql(PAISES, conectar(), parse_dates=["fecha"])
    for medida in ["casos", "fallecidos"]:
        acumulado = datos.groupby("pais")[f"{medida}_acumulados"]
        datos[f"{medida}_nuevos"] = acumulado.diff().fillna(datos[f"{medida}_acumulados"])
    datos["nivel"] = "pais"

    # Regiones de Chile (el desafío puede sortear una región). La columna se sigue llamando "pais".
    # Existen desde el 20-may-2020; ese primer día sus nuevos quedan vacíos (el acumulado trae casos de antes).
    regiones = (cargar_regiones_chile().rename(columns={"region": "pais"}).drop(columns=["lat", "long"])
                .sort_values(["pais", "fecha"]))
    for medida in ["casos", "fallecidos"]:
        regiones[f"{medida}_nuevos"] = regiones.groupby("pais")[f"{medida}_acumulados"].diff()
    regiones["nivel"] = "region"
    return pd.concat([datos, regiones], ignore_index=True)


@st.cache_data
def cargar_ubicacion():
    return pd.read_sql("SELECT pais, lat, long FROM dim_territorio WHERE nivel = 'pais'", conectar()).set_index("pais")


@st.cache_data
def cargar_regiones_chile():
    return pd.read_sql(REGIONES_CHILE, conectar(), parse_dates=["fecha"])


@st.cache_data
def cargar_semanas():
    """Casos nuevos por 100.000 de cada semana (lunes a domingo) en los países con 1 millón de habitantes o más."""
    grandes = datos[(datos["nivel"] == "pais") & (datos["poblacion"] >= 1_000_000)]
    # Acumulado al domingo de cada semana; casos de la semana = acumulado − el de la semana anterior
    semanas = grandes.set_index("fecha").groupby("pais")[["casos_acumulados", "poblacion"]].resample("W-SUN").last().reset_index()
    # Semana en que el país no aparece en ningún reporte: se repite el acumulado anterior (0 casos esa semana)
    semanas[["casos_acumulados", "poblacion"]] = semanas.groupby("pais")[["casos_acumulados", "poblacion"]].ffill()
    semanas["casos_acumulados"] = semanas["casos_acumulados"].fillna(0)   # semanas antes del primer dato del país
    acumulado = semanas.groupby("pais")["casos_acumulados"]
    semanas["casos_semana"] = acumulado.diff().fillna(semanas["casos_acumulados"])
    semanas["casos_100k"] = (semanas["casos_semana"] / semanas["poblacion"] * 100_000).clip(lower=0)
    # Todas las semanas para todos los países (antes de su primer caso: 0), para que cada cuadro tenga los 157 países
    todas = pd.MultiIndex.from_product([semanas["pais"].unique(), sorted(semanas["fecha"].unique())], names=["pais", "fecha"])
    semanas = semanas.set_index(["pais", "fecha"]).reindex(todas).reset_index()
    semanas[["casos_semana", "casos_100k"]] = semanas[["casos_semana", "casos_100k"]].fillna(0)
    semanas["semana"] = semanas["fecha"].dt.strftime("%Y-%m-%d")
    return semanas.join(cargar_ubicacion(), on="pais")


@st.cache_data
def cargar_calidad():
    calidad = pd.read_parquet(RAIZ / "data" / "clean" / "indice_calidad_pais.parquet")
    calidad = calidad[calidad["poblacion"] >= 1_000_000].set_index("country_region")
    calidad["puesto"] = calidad["indice_calidad"].rank(ascending=False, method="min").astype(int)
    return calidad


# ---------------------------------------------------------------- 2 · Funciones (copias de los notebooks)

def pronosticar(territorio, fecha_corte, horizonte=14):
    """Casos nuevos por día (media móvil 7 días) de los `horizonte` días siguientes al corte, con tres modelos (06_mineria)."""
    hist = datos[(datos["pais"] == territorio) & (datos["fecha"] <= fecha_corte)]
    # solo se usa hist: nada posterior al corte
    media_movil = hist.set_index("fecha")["casos_nuevos"].rolling(7).mean().dropna()

    base = [media_movil.iloc[-1]] * horizonte
    holt = ExponentialSmoothing(media_movil.values, trend="add", damped_trend=True).fit().forecast(horizonte)
    logaritmo = np.log(media_movil.clip(lower=1).values)
    holt_log = np.exp(ExponentialSmoothing(logaritmo, trend="add", damped_trend=True).fit().forecast(horizonte))

    fechas = pd.date_range(pd.Timestamp(fecha_corte) + pd.Timedelta(days=1), periods=horizonte)
    return pd.DataFrame({"fecha": fechas, "base": base, "holt": holt.clip(min=0), "holt_log": holt_log})


def alerta(territorio, fecha, umbral=UMBRAL_ALERTA, piso=PISO_ALERTA):
    """¿Estaba activa la alerta ese día? Incidencia (MM7 por 100.000) que sube umbral % o más en 7 días y está sobre el piso (06_mineria)."""
    hist = datos[(datos["pais"] == territorio) & (datos["fecha"] <= fecha)]
    # solo se usa hist: nada posterior a la fecha
    incidencia = hist["casos_nuevos"].rolling(7).mean() / hist["poblacion"] * 100_000
    hoy, semana_antes = incidencia.iloc[-1], incidencia.iloc[-8]
    variacion = (hoy / semana_antes - 1) * 100
    return {"fecha": pd.Timestamp(fecha), "incidencia_100k": float(hoy), "variacion_semanal_pct": float(variacion),
            "activa": bool(variacion >= umbral and hoy >= piso)}


def suprimir(df, umbral_poblacion=UMBRAL_POBLACION):
    """Deja vacíos los casos/fallecidos nuevos de 1 a 4 en territorios con menos de umbral_poblacion habitantes (04_proteccion)."""
    df = df.copy()
    poca_poblacion = df["poblacion"] < umbral_poblacion
    for col in ["casos_nuevos", "fallecidos_nuevos"]:
        celda_pequena = poca_poblacion & df[col].between(1, 4)
        df.loc[celda_pequena, col] = None
    return df


def numero(valor, decimales=0):
    """Número con punto de miles y coma decimal (formato chileno)."""
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def texto_variacion(variacion):
    """Variación semanal para mostrar. Si 7 días antes no hubo casos, el % no se puede calcular (sale infinito o vacío)."""
    if np.isfinite(variacion):
        return f"{numero(variacion, 1)} % en 7 días"
    return "sin casos 7 días antes"


def incidencia_14_dias(tabla, corte, columna_territorio):
    """Casos de los últimos 14 días por 100.000 al corte (diferencia de acumulados)."""
    hoy = tabla[tabla["fecha"] == corte].set_index(columna_territorio)
    antes = tabla[tabla["fecha"] == corte - pd.Timedelta(days=14)].set_index(columna_territorio)
    resultado = hoy[["poblacion"]].copy()
    resultado["casos_14_dias"] = hoy["casos_acumulados"] - antes["casos_acumulados"].reindex(hoy.index).fillna(0)
    resultado["incidencia_14d_100k"] = resultado["casos_14_dias"] / resultado["poblacion"] * 100_000
    return resultado


# ---------------------------------------------------------------- 3 · Filtros

datos = cargar_paises()
regiones_chile = sorted(datos.loc[datos["nivel"] == "region", "pais"].unique())
lista_paises = sorted(datos.loc[datos["nivel"] == "pais", "pais"].unique()) + regiones_chile   # países y después regiones


def etiqueta(territorio):
    """Nombre para mostrar: las regiones llevan '(región de Chile)'."""
    return f"{territorio} (región de Chile)" if territorio in regiones_chile else territorio


st.sidebar.title("🦠 Sala de crisis COVID-19")
pais = st.sidebar.selectbox("País o región de Chile", lista_paises, index=lista_paises.index("Chile"), format_func=etiqueta,
                            help="Nombre como lo publica Johns Hopkins (en inglés y sin tildes): US, Brazil, Korea, South, "
                                 "Biobio, Nuble… Las 16 regiones de Chile están al final de la lista (se puede escribir para buscar).")
es_region = pais in regiones_chile
corte = st.sidebar.date_input("Fecha de corte", value=ULTIMO_DIA, min_value=PRIMER_DIA, max_value=ULTIMO_DIA,
                              help="Todo el tablero muestra solo lo que se sabía hasta este día.")
# Por defecto parte el 1-mar-2020, salvo que el corte sea anterior (no puede quedar después del corte)
desde = st.sidebar.date_input("Tendencia desde", value=min(date(2020, 3, 1), corte), min_value=PRIMER_DIA, max_value=corte)
st.sidebar.caption("Fuente: reportes diarios de Johns Hopkins CSSE (22-ene-2020 → 9-mar-2023), DW del proyecto.")

corte = pd.Timestamp(corte)
serie = datos[(datos["pais"] == pais) & (datos["fecha"] <= corte)].reset_index(drop=True)
if len(serie) < 21:
    st.title(etiqueta(pais))
    st.warning(f"{pais} tiene solo {len(serie)} días de datos hasta el {corte.date()}: se necesitan al menos 21 "
               "para la media móvil, la alerta y el pronóstico. Elige una fecha de corte posterior.")
    st.stop()

poblacion = serie["poblacion"].max()
pequeno = poblacion < UMBRAL_POBLACION

st.title(f"{etiqueta(pais)} · datos hasta el {corte.strftime('%d-%m-%Y')}")
if es_region:
    st.caption("Chile informa por región desde el 20-may-2020: la serie de la región parte ese día.")
if pequeno:
    st.info(f"🔒 {pais} tiene {numero(poblacion)} habitantes (menos de {numero(UMBRAL_POBLACION)}). Para proteger a las personas "
            "(Ley 19.628 / 21.719) sus datos se muestran **por semana** y los conteos de 1 a 4 se ocultan («<5»: quedan vacíos en los gráficos). "
            "Mostrarlos día a día permitiría recuperar los valores ocultos restando acumulados.")

tab_resumen, tab_mapas, tab_alerta = st.tabs(["📊 Resumen", "🗺️ Mapas", "🚨 Alerta y pronóstico"])


# ---------------------------------------------------------------- 4 · Resumen

with tab_resumen:
    if pequeno:
        # Semanas que terminan en domingo; solo semanas completas hasta el corte
        mostrar = serie.set_index("fecha").resample("W-SUN").agg(
            {"casos_acumulados": "last", "fallecidos_acumulados": "last", "casos_nuevos": "sum",
             "fallecidos_nuevos": "sum", "poblacion": "max"}).reset_index()
        mostrar = mostrar[mostrar["fecha"] <= corte]
        mostrar = suprimir(mostrar)
        periodo = "semana"
    else:
        mostrar = serie.copy()
        periodo = "día"

    ultimo = mostrar.iloc[-1]
    estado = alerta(pais, corte)
    letalidad = ultimo["fallecidos_acumulados"] / ultimo["casos_acumulados"] * 100 if ultimo["casos_acumulados"] > 0 else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Casos acumulados", numero(ultimo["casos_acumulados"]),
              help=f"Al {ultimo['fecha'].date()}. Por 100.000: {numero(ultimo['casos_acumulados'] / poblacion * 100_000)}")
    k2.metric("Fallecidos acumulados", numero(ultimo["fallecidos_acumulados"]),
              help=f"Por 100.000: {numero(ultimo['fallecidos_acumulados'] / poblacion * 100_000, 1)}")
    k3.metric("Incidencia por 100.000", numero(estado["incidencia_100k"], 1),
              delta=texto_variacion(estado["variacion_semanal_pct"]), delta_color="inverse",
              help="Media móvil de 7 días de los casos nuevos por cada 100.000 habitantes, y su variación frente a 7 días antes.")
    k4.metric("Letalidad aparente", f"{numero(letalidad, 2)} %",
              help="Fallecidos ÷ casos acumulados. Depende del testeo: con pocos tests se ven menos casos y la letalidad sube.")
    k5.metric("Alerta temprana", "ACTIVA 🔴" if estado["activa"] else "No ✅",
              help=f"Se activa si la incidencia sube ≥ {UMBRAL_ALERTA} % en una semana y está sobre {PISO_ALERTA} por 100.000.")

    # Tendencia: dato diario (o semanal) por 100.000 y media móvil de 7 días
    tramo = mostrar[mostrar["fecha"] >= pd.Timestamp(desde)].copy()
    columnas = st.columns(2)
    for columna, medida, color in zip(columnas, ["casos", "fallecidos"], ["#1f77b4", "#d62728"]):
        tramo[f"{medida}_100k"] = tramo[f"{medida}_nuevos"] / poblacion * 100_000
        figura = go.Figure()
        if pequeno:
            figura.add_bar(x=tramo["fecha"], y=tramo[f"{medida}_100k"], marker_color=color, name="por semana")
        else:
            figura.add_scatter(x=tramo["fecha"], y=tramo[f"{medida}_100k"], line=dict(color="lightgray", width=1), name="diario")
            figura.add_scatter(x=tramo["fecha"], y=tramo[f"{medida}_100k"].rolling(7).mean(), line=dict(color=color),
                               name="media móvil 7 días")
        figura.update_layout(title=f"{medida.capitalize()} nuevos por 100.000 (por {periodo})", height=340,
                             margin=dict(t=50, b=20), legend=dict(orientation="h", y=-0.15))
        columna.plotly_chart(figura, width="stretch")

    # Ranking: países con 1 millón de habitantes o más, por casos de los últimos 14 días por 100.000
    st.subheader("Ranking · casos de los últimos 14 días por 100.000 habitantes")
    st.caption("Países con 1 millón de habitantes o más (157). Diferencia de acumulados al corte y 14 días antes.")
    ranking = incidencia_14_dias(datos[datos["nivel"] == "pais"], corte, "pais")
    ranking = ranking[ranking["poblacion"] >= 1_000_000].sort_values("incidencia_14d_100k", ascending=False)
    ranking["puesto"] = range(1, len(ranking) + 1)
    top = ranking.head(15).reset_index()
    top["color"] = np.where(top["pais"] == pais, "seleccionado", "otros")
    figura = px.bar(top, x="incidencia_14d_100k", y="pais", orientation="h", color="color",
                    color_discrete_map={"seleccionado": "#d62728", "otros": "#1f77b4"},
                    labels={"incidencia_14d_100k": "casos por 100.000 (14 días)", "pais": ""})
    figura.update_layout(yaxis=dict(autorange="reversed"), showlegend=False, height=450, margin=dict(t=10))
    columna_grafico, columna_texto = st.columns([3, 1])
    columna_grafico.plotly_chart(figura, width="stretch")
    if pais in ranking.index:
        fila = ranking.loc[pais]
        columna_texto.metric(f"Puesto de {pais}", f"{int(fila['puesto'])} de {len(ranking)}",
                             help=f"{numero(fila['incidencia_14d_100k'], 1)} casos por 100.000 en 14 días")
    else:
        columna_texto.caption(f"{pais} es una región: el ranking es de países (las regiones están en la pestaña Mapas)."
                              if es_region else f"{pais} tiene menos de 1 millón de habitantes: no entra al ranking.")


# ---------------------------------------------------------------- 5 · Mapas

with tab_mapas:
    st.subheader("Mundo · casos de los últimos 14 días por 100.000")
    mundo = incidencia_14_dias(datos[datos["nivel"] == "pais"], corte, "pais").join(cargar_ubicacion())
    # Supresión: en países chicos no se dibujan conteos de 1 a 4
    chico = (mundo["poblacion"] < UMBRAL_POBLACION) & mundo["casos_14_dias"].between(1, 4)
    mundo = mundo[~chico & (mundo["incidencia_14d_100k"] > 0)].reset_index()
    figura = px.scatter_geo(mundo, lat="lat", lon="long", size="incidencia_14d_100k", color="incidencia_14d_100k",
                            hover_name="pais", hover_data={"casos_14_dias": ":,.0f", "incidencia_14d_100k": ":.1f",
                                                          "lat": False, "long": False},
                            color_continuous_scale="Reds", size_max=30, projection="natural earth",
                            labels={"incidencia_14d_100k": "por 100.000", "casos_14_dias": "casos 14 días"})
    figura.update_layout(height=520, margin=dict(t=10, b=10, l=0, r=0))
    st.plotly_chart(figura, width="stretch", config={"scrollZoom": False})
    st.caption(f"{len(mundo)} países con casos en los 14 días previos al corte. Tamaño y color = casos por 100.000. "
               "Ubicación: latitud y longitud de la tabla UID de Johns Hopkins.")

    st.subheader("Animación · la pandemia semana a semana")
    # Solo semanas completas hasta el corte (la semana termina en domingo)
    semanas = cargar_semanas()
    semanas = semanas[semanas["fecha"] <= corte].sort_values(["fecha", "pais"])   # los cuadros siguen el orden de las filas
    if semanas["semana"].nunique() < 2:
        st.info("Se necesitan al menos dos semanas completas antes del corte para animar el mapa.")
    else:
        tope = semanas["casos_100k"].quantile(0.99)   # escala fija para todas las semanas (sin que un extremo la aplaste)
        semanas["tamano"] = semanas["casos_100k"].clip(upper=tope)
        figura = px.scatter_geo(semanas, lat="lat", lon="long", size="tamano", color="casos_100k",
                                animation_frame="semana", hover_name="pais",
                                hover_data={"casos_semana": ":,.0f", "casos_100k": ":.1f", "lat": False, "long": False,
                                            "semana": False, "tamano": False},
                                range_color=[0, tope], color_continuous_scale="YlOrRd", size_max=30, projection="natural earth",
                                labels={"casos_100k": "por 100.000", "casos_semana": "casos de la semana"})
        figura.update_traces(marker=dict(line=dict(width=0.5, color="gray")))   # borde para ver también las burbujas claras
        figura.update_geos(showland=True, landcolor="#e8e8e8")
        figura.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 150
        figura.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 0
        figura.update_layout(height=560, margin=dict(t=10, b=10, l=0, r=0))
        st.plotly_chart(figura, width="stretch", config={"scrollZoom": False})
        st.caption(f"Casos nuevos de cada semana (lunes a domingo) por 100.000, {semanas['pais'].nunique()} países con 1 millón "
                   f"de habitantes o más, {semanas['semana'].nunique()} semanas hasta el corte. ▶ para reproducir; la barra "
                   "permite ir a una semana. Escala de color fija (tope = percentil 99) para comparar semanas.")

    st.subheader("Chile · regiones")
    regiones = cargar_regiones_chile()
    if corte < pd.Timestamp("2020-06-03"):
        st.info("Chile informa por región desde el 20-may-2020: elige una fecha de corte desde el 3-jun-2020 "
                "para tener 14 días de datos regionales.")
    else:
        por_region = incidencia_14_dias(regiones, corte, "region")
        por_region = por_region.join(regiones.drop_duplicates("region").set_index("region")[["lat", "long"]]).reset_index()
        figura = px.scatter_geo(por_region, lat="lat", lon="long", size=por_region["incidencia_14d_100k"].clip(lower=0),
                                color="incidencia_14d_100k", hover_name="region",
                                hover_data={"casos_14_dias": ":,.0f", "incidencia_14d_100k": ":.1f", "lat": False, "long": False},
                                color_continuous_scale="Reds", size_max=30,
                                labels={"incidencia_14d_100k": "por 100.000", "casos_14_dias": "casos 14 días"})
        # Chile es largo y angosto: se fija el recuadro (latitud −56 a −17, longitud −80 a −64)
        figura.update_geos(projection_type="mercator", lataxis_range=[-56, -17], lonaxis_range=[-80, -64],
                           showcountries=True, showland=True, landcolor="#f2f2f2")
        figura.update_layout(height=700, margin=dict(t=10, b=10, l=0, r=0), coloraxis_colorbar=dict(len=0.5))
        columna_mapa, columna_tabla = st.columns([1, 1])
        columna_mapa.plotly_chart(figura, width="stretch", config={"scrollZoom": False})
        tabla = por_region.sort_values("incidencia_14d_100k", ascending=False)[["region", "casos_14_dias", "incidencia_14d_100k"]]
        tabla.columns = ["región", "casos 14 días", "por 100.000"]
        columna_tabla.dataframe(tabla.round(1), hide_index=True, height=600)


# ---------------------------------------------------------------- 6 · Alerta, pronóstico y calidad

with tab_alerta:
    st.subheader("Alerta temprana")
    if estado["activa"]:
        st.error(f"🔴 **ALERTA ACTIVA** el {corte.date()}: variación semanal {texto_variacion(estado['variacion_semanal_pct'])}; "
                 f"la incidencia está en {numero(estado['incidencia_100k'], 1)} por 100.000.")
    else:
        st.success(f"✅ Sin alerta el {corte.date()}: variación semanal {texto_variacion(estado['variacion_semanal_pct'])}, "
                   f"incidencia {numero(estado['incidencia_100k'], 1)} por 100.000.")
    st.caption(f"Regla: alerta si la incidencia (MM7 por 100.000) **sube ≥ {UMBRAL_ALERTA} % en una semana** y está **sobre "
               f"{PISO_ALERTA} por 100.000**. Calibrada con la historia de Chile: anticipó 4 de 5 olas (7 a 17 días antes) "
               "con 7 falsas alarmas en 3 años (06_mineria).")

    # Indicador de los últimos 120 días con sus umbrales
    indicador = serie[["fecha"]].copy()
    indicador["incidencia"] = serie["casos_nuevos"].rolling(7).mean() / poblacion * 100_000
    indicador["variacion"] = (indicador["incidencia"] / indicador["incidencia"].shift(7) - 1) * 100
    indicador = indicador.tail(120)
    columna_1, columna_2 = st.columns(2)
    figura = px.line(indicador, x="fecha", y="variacion", labels={"variacion": "variación semanal (%)", "fecha": ""})
    figura.add_hline(y=UMBRAL_ALERTA, line_dash="dash", line_color="red", annotation_text=f"umbral {UMBRAL_ALERTA} %")
    figura.update_layout(title="Variación semanal de la incidencia", height=320, margin=dict(t=50, b=20))
    columna_1.plotly_chart(figura, width="stretch")
    figura = px.line(indicador, x="fecha", y="incidencia", labels={"incidencia": "MM7 por 100.000", "fecha": ""})
    figura.add_hline(y=PISO_ALERTA, line_dash="dash", line_color="red", annotation_text=f"piso {PISO_ALERTA}")
    figura.update_layout(title="Incidencia (media móvil 7 días por 100.000)", height=320, margin=dict(t=50, b=20))
    columna_2.plotly_chart(figura, width="stretch")

    st.subheader("Pronóstico a 14 días")
    st.caption("`pronosticar(territorio, fecha_corte, 14)`: usa **solo los datos hasta el corte**. Tres modelos: base "
               "(media móvil del corte repetida), Holt (tendencia amortiguada) y Holt en escala logarítmica, el de menor "
               "error en el backtesting de Chile (MAPE 12,0 %). Ninguno anticipa el giro de un pico.")
    if st.button(f"▶ Pronosticar {pais} desde el {corte.date()}", type="primary"):
        pronostico = pronosticar(pais, corte)
        historia = serie.set_index("fecha")["casos_nuevos"].rolling(7).mean().tail(60)
        # Lo que pasó después del corte: solo para comparar, la función no lo ve
        completa = datos[datos["pais"] == pais].set_index("fecha")["casos_nuevos"].rolling(7).mean()
        real = completa.reindex(pronostico["fecha"])

        figura = go.Figure()
        figura.add_scatter(x=historia.index, y=historia, line=dict(color="black"), name="historia hasta el corte")
        if real.notna().any():
            figura.add_scatter(x=real.index, y=real, line=dict(color="gray", dash="dash"), name="lo que pasó (no lo ve)")
        for modelo, color, nombre in [("base", "#1f77b4", "base"), ("holt", "#ff7f0e", "Holt"), ("holt_log", "#2ca02c", "Holt log")]:
            figura.add_scatter(x=pronostico["fecha"], y=pronostico[modelo], line=dict(color=color), name=nombre)
        figura.add_vline(x=corte, line_color="red", line_width=1)
        figura.update_layout(title=f"{pais} · casos nuevos por día (media móvil 7 días)", height=420, margin=dict(t=50))
        st.plotly_chart(figura, width="stretch")

        tabla = pronostico.assign(real=real.values).set_index("fecha").round(0)
        tabla.index = tabla.index.date
        columna_1, columna_2 = st.columns([2, 1])
        if pequeno:
            # Igual que en el Resumen: en territorios chicos no se muestra el detalle día a día (04_proteccion)
            columna_1.info(f"🔒 {pais} tiene menos de {numero(UMBRAL_POBLACION)} habitantes: por protección de datos no se "
                           "muestra la tabla día a día. El gráfico usa la media móvil de 7 días y el error resume los 14 días.")
        else:
            columna_1.dataframe(tabla, height=530)
        if real.notna().all():
            # El MAPE divide por lo real: los días con 0 casos (países que informan una vez a la semana) no se pueden usar
            con_casos = real.values > 0
            errores = pd.DataFrame({modelo: {"MAE": (pronostico[modelo] - real.values).abs().mean(),
                                             "MAPE (%)": ((pronostico[modelo] - real.values).abs()[con_casos]
                                                          / real.values[con_casos]).mean() * 100}
                                    for modelo in ["base", "holt", "holt_log"]}).T.round(1)
            columna_2.write("**Error frente a lo que pasó**")
            columna_2.dataframe(errores)
            if not con_casos.all():
                columna_2.caption(f"El MAPE usa solo los {con_casos.sum()} de 14 días con casos (no se divide por 0); "
                                  "el MAE usa los 14.")
        else:
            columna_2.info("El corte está a menos de 14 días del fin de los datos (9-mar-2023): no hay con qué comparar.")

    st.subheader("Advertencias de calidad")
    calidad = cargar_calidad()
    pais_calidad = "Chile" if es_region else pais   # el índice es por país: una región usa el de Chile
    if pais_calidad in calidad.index:
        fila = calidad.loc[pais_calidad]
        st.write(f"**Índice de calidad de {pais_calidad}: {numero(fila['indice_calidad'], 1)} de 100** "
                 f"(puesto {int(fila['puesto'])} de {len(calidad)}; 100 = mejor).")
    # Problemas en los 28 días previos al corte (mismas reglas que 02_calidad, a nivel país)
    reciente = serie.copy()
    reciente["media_7_previos"] = reciente["casos_nuevos"].shift(1).rolling(7).mean()
    reciente = reciente[(reciente["fecha"] > corte - pd.Timedelta(days=28)) & (reciente["casos_acumulados"] > 0)]
    sin_cambio = (reciente["casos_nuevos"] == 0).sum()
    retrocesos = (reciente["casos_nuevos"] < 0).sum()
    picos = ((reciente["casos_nuevos"] > 5 * reciente["media_7_previos"]) & (reciente["casos_nuevos"] >= 100)).sum()
    avisos = []
    if sin_cambio:
        avisos.append(f"**Días sin reporte: {sin_cambio}** (acumulado sin cambio) en las 4 semanas previas: puede informar "
                      "una vez a la semana o con atraso; mirar la media móvil, no el dato diario.")
    if retrocesos:
        avisos.append(f"**Días en que el acumulado baja: {retrocesos}** (correcciones): esos días los casos nuevos son negativos.")
    if picos:
        avisos.append(f"**Picos de rezago: {picos}** (más de 5 veces la media de los 7 días previos): carga de casos atrasados "
                      "que infla la media móvil, la alerta y el pronóstico.")
    for aviso in avisos:
        st.warning(aviso)
    if not avisos:
        st.success("Sin días sin reporte, retrocesos ni picos de rezago en las 4 semanas previas al corte.")
    with st.expander("Cautelas generales para leer el tablero"):
        st.markdown(
            "- **Casos dependen del testeo:** más tests, más casos; la letalidad aparente (fallecidos ÷ casos) baja.\n"
            "- **Comparar países exige cautela:** distinto testeo, definición de fallecido, edad de la población y momento de la ola.\n"
            "- **Desde 2022 muchos países informan una vez a la semana:** el dato diario es ruido; usar la media móvil.\n"
            "- **Chile 21-mar-2022:** +11.447 fallecidos en un día (carga en bloque); infla la media móvil de esa semana.\n"
            "- **Protección de datos:** países con menos de 100.000 habitantes se muestran por semana y con conteos 1–4 como «<5»."
        )
