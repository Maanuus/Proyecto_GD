# Sala de crisis COVID-19 · Gestión de Datos IN1232C (2026-2)

Plataforma de datos sobre el registro histórico de COVID-19 de Johns Hopkins University (JHU CSSE),
del **22-ene-2020 al 9-mar-2023** (1.143 reportes diarios): ingesta reproducible, unificación de los cinco esquemas
de los reportes, capa limpia en Parquet, control de calidad, un Data Warehouse en SQLite (modelo en estrella)
integrado con vacunación (Our World in Data) e indicadores del Banco Mundial, análisis de las preguntas del Comité,
segmentación, pronóstico, alerta temprana y un tablero en Streamlit.

## Fuentes de datos

Los datos crudos **no se descargan ni se guardan**: el código los lee directo desde internet. En `01_ingesta`,
una sola celda lee los 1.143 reportes diarios, las series de tiempo y la tabla UID desde las URL raw, sin pasos manuales.

| Fuente                             | Dónde se lee                                                                                                       | Para qué                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- |
| JHU · reportes diarios (1.143 CSV) | `https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_daily_reports/` | Casos y fallecidos por territorio y día        |
| JHU · series de tiempo             | `.../csse_covid_19_data/csse_covid_19_time_series/`                                                                | Comparar con la suma de los reportes diarios   |
| JHU · tabla UID                    | `.../csse_covid_19_data/UID_ISO_FIPS_LookUp_Table.csv`                                                             | Llave de territorio, población, lat/long, ISO3 |
| OWID · vacunación                  | `https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/vaccinations/vaccinations.csv`            | % de población vacunada (P3, P7)               |
| Banco Mundial (API)                | `https://api.worldbank.org/v2/country/all/indicator/...`                                                           | % de 65+ y PIB per cápita 2021 (P7)            |

## Cómo reproducir todo desde cero

Los notebooks se ejecutan **en orden** y cada uno usa los datos que deja el anterior:

| #   | Notebook         | Lee                                                                     | Deja                                                                        |
| --- | ---------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 0   | `00_exploracion` | Reportes JHU de ene–jun 2020 (internet)                                 | — (Hito 1: exploración y perfilado)                                         |
| 1   | `01_ingesta`     | Los 1.143 reportes, las series y la tabla UID (internet)                | `data/clean/covid_limpio.parquet`                                           |
| 2   | `02_calidad`     | `covid_limpio.parquet` + tabla UID y reportes para el linaje (internet) | `data/clean/covid_diario.parquet`, `data/clean/indice_calidad_pais.parquet` |
| 3   | `03_dw`          | `covid_diario.parquet` + tabla UID, OWID y Banco Mundial (internet)     | `data/dw/covid_dw.db` y `data/dw/covid_dw.zip`                              |
| 4   | `04_proteccion`  | DW                                                                      | — (protección de datos y supresión de celdas pequeñas)                      |
| 5   | `05_analisis`    | DW + `indice_calidad_pais.parquet`                                      | — (P1 a P4 y P7)                                                            |
| 6   | `06_mineria`     | DW + `indice_calidad_pais.parquet`                                      | — (segmentación, pronóstico, alerta temprana, P5 y P6)                      |

> `01_ingesta` es el más exigente: lee los 1.143 archivos desde internet y usa ~1,3 GB de RAM.
> El DW (`covid_dw.db`) pesa ~130 MB y GitHub acepta hasta 100 MB por archivo: se sube comprimido como `data/dw/covid_dw.zip`.
>
> **Atajo:** el repositorio ya trae la capa limpia (`data/clean/`) y el DW comprimido. Para revisar el análisis basta
> con correr 04, 05 y 06: cada uno descomprime el DW solo.

### Requisitos previos

| Qué      | Detalle                                                                                                         |
| -------- | --------------------------------------------------------------------------------------------------------------- |
| Python   | **3.12** (el mismo de Colab). Sirve de 3.10 a 3.13; **no 3.14**, porque `ydata-profiling` todavía no lo soporta |
| Git      | Para clonar el repositorio (también se puede descargar como .zip desde GitHub)                                  |
| Internet | Los notebooks leen los datos crudos desde las URL raw                                                           |
| Memoria  | ~2 GB de RAM libres                                                                                             |

Probado con: Python 3.12.13, pandas 2.3.3, numpy 2.3.5, pyarrow 26.0.1, matplotlib 3.10.0, ydata-profiling 4.18.4,
scikit-learn 1.9.1 y statsmodels 0.15.0.

### Opción A · Google Colab

Colab ya trae pandas, pyarrow, matplotlib, scikit-learn y statsmodels; `00_exploracion` instala `ydata-profiling` en su
propia celda.

1. Abrir un notebook del proyecto en Colab: _Archivo → Abrir cuaderno → GitHub_ y pegar la URL del repositorio
   (`https://github.com/Maanuus/Proyecto_GD`).
2. Agregar **arriba de todo** una celda que clone el repositorio y entre a `notebooks/` (las rutas de los notebooks son
   relativas a esa carpeta, por ejemplo `../data/clean/...`), y ejecutarla:
   ```python
   !git clone https://github.com/Maanuus/Proyecto_GD.git /content/proyecto
   %cd /content/proyecto/notebooks
   ```
3. _Entorno de ejecución → Ejecutar todas_.
4. Repetir con el siguiente notebook **en el mismo entorno de ejecución** (así encuentra lo que dejó el anterior), en el
   orden 00 → 01 → 02 → 03 → 04 → 05 → 06. En los siguientes basta con `%cd /content/proyecto/notebooks`
   (el `git clone` se hace una sola vez).

> Si Colab pide **reiniciar la sesión** después de la celda `%pip` de `00_exploracion`, reiniciarla, volver a ejecutar
> `%cd /content/proyecto/notebooks` y seguir desde la celda siguiente al `%pip`.

### Opción B · Computador local (Windows, PowerShell)

Los comandos usan directamente el Python del entorno (`.venv\Scripts\python`), así que no hace falta activarlo y
todo queda instalado en el mismo lugar que usa el notebook.

1. **Clonar el repositorio** y entrar a su carpeta raíz:
   ```powershell
   git clone https://github.com/Maanuus/Proyecto_GD.git
   cd Proyecto_GD
   ```
2. **Crear el entorno virtual con Python 3.12.** Con el lanzador `py` de Windows (`py --list` muestra las versiones
   instaladas):
   ```powershell
   py -3.12 -m venv .venv
   ```
   Si no se tiene Python 3.12 (o solo se tiene 3.14), crearlo con [uv](https://docs.astral.sh/uv/), que descarga
   Python 3.12 sin tocar el instalado. `--seed` deja `pip` dentro del entorno, así los pasos siguientes son iguales:
   ```powershell
   pip install uv
   uv venv --python 3.12 --seed .venv
   ```
3. **Instalar las dependencias y Jupyter:**
   ```powershell
   .venv\Scripts\python -m pip install -r requirements.txt jupyter "setuptools<81"
   ```
   `setuptools<81` es necesario: `ydata-profiling` usa `pkg_resources`, que setuptools 81 o superior ya no incluye.
4. **Comprobar la instalación** (debe imprimir `ok`):
   ```powershell
   .venv\Scripts\python -c "import pandas, pyarrow, matplotlib, ydata_profiling, sklearn, statsmodels; print('ok')"
   ```
5. **Ejecutar los notebooks**, de una de estas dos formas:
   - Todos con un solo comando desde la terminal (en orden, del 00 al 06):
     ```powershell
     cd notebooks
     foreach ($nb in "00_exploracion","01_ingesta","02_calidad","03_dw","04_proteccion","05_analisis","06_mineria") { ..\.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace "$nb.ipynb" }
     cd ..
     ```
   - Uno por uno en VS Code: abrir el notebook, elegir como kernel (arriba a la derecha) el Python de `.venv` y
     _Run All_. Si se elige otro Python, el notebook no encuentra los paquetes instalados.

> En macOS o Linux los pasos son los mismos cambiando `py -3.12` por `python3.12` y `.venv\Scripts\python` por
> `.venv/bin/python`.
>
> En `00_exploracion` es normal el aviso `DeprecationWarning` al importar `ydata_profiling`: no afecta el resultado.

## Tablero

Desde la **raíz** del repositorio, con el entorno de la opción B:

```powershell
.venv\Scripts\python -m pip install streamlit plotly
.venv\Scripts\python -m streamlit run dashboard/app.py
```

Se abre en `http://localhost:8501`. La primera carga descomprime el DW y lo consulta (unos segundos; después queda en caché).

- **Barra lateral:** país y **fecha de corte**. Todo el tablero muestra solo lo que se sabía hasta esa fecha.
- **Resumen:** KPI al corte, tendencia con media móvil de 7 días y ranking de países (casos de 14 días por 100.000).
- **Mapas:** burbujas de incidencia en el mundo y en las regiones de Chile, y mapa animado semana a semana.
- **Alerta y pronóstico:** alerta temprana con su umbral visible, botón **Pronosticar** (`pronosticar(país, corte, 14)`,
  tres modelos) y advertencias de calidad.
- Países con menos de 100.000 habitantes se muestran por semana y con conteos de 1 a 4 ocultos (protección de datos).

Capturas en `dashboard/capturas/`.

## Estructura

| Carpeta / archivo                | Contenido                                                                                                                                                                                          |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `notebooks/00_exploracion.ipynb` | Hito 1: lectura de ene–jun 2020, nulos, unión de esquemas, casos diarios, top 10, Chile y perfilado                                                                                                |
| `notebooks/01_ingesta.ipynb`     | Lectura de los 1.143 reportes, unificación de los cinco esquemas, llave de territorio, capa limpia, comparación CSV frente a Parquet y arquitectura (motor, capas y nube)                          |
| `notebooks/02_calidad.ipynb`     | Acumulados → casos diarios, reglas de calidad en seis dimensiones, problemas cuantificados, índice de calidad por país, decisiones y linaje                                                        |
| `notebooks/03_dw.ipynb`          | Data Warehouse en SQLite: dimensiones de fecha y territorio (país → región → condado), tabla de hechos territorio × día, vacunación de OWID y Banco Mundial con su tasa de cruce, y consultas OLAP |
| `notebooks/04_proteccion.ipynb`  | Argumento legal (Leyes 19.628 y 21.719), supresión de celdas pequeñas y advertencias de interpretación                                                                                             |
| `notebooks/05_analisis.ipynb`    | P1 a P4 y P7: Chile frente a Sudamérica, regiones y olas, letalidad y vacunación, confiabilidad por país                                                                                           |
| `notebooks/06_mineria.ipynb`     | Segmentación con k-means, `pronosticar` con backtesting, `alerta` temprana, P5 y P6                                                                                                                |
| `dashboard/`                     | Tablero en Streamlit (`app.py`) y capturas                                                                                                                                                         |
| `data/clean/`                    | Capa limpia en Parquet (`covid_limpio` y `covid_diario` con compresión zstd; `indice_calidad_pais`)                                                                                                |
| `data/dw/covid_dw.zip`           | Data Warehouse en SQLite (modelo en estrella), comprimido                                                                                                                                          |
| `docs/diccionario_datos.md`      | Diccionario de la tabla unificada                                                                                                                                                                  |
| `docs/informe_tecnico.pdf`       | Informe técnico                                                                                                                                                                                    |
| `docs/informe_comite.pdf`        | Informe al Comité                                                                                                                                                                                  |
| `contribuciones.md`              | Quién hizo qué y cómo se usó IA generativa                                                                                                                                                         |
| `requirements.txt`               | Dependencias de Python                                                                                                                                                                             |
