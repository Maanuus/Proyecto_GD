# Sala de crisis COVID-19 · Gestión de Datos IN1232C (2026-2)

Plataforma de datos sobre el registro histórico de COVID-19 de Johns Hopkins University (JHU CSSE),
del **22-ene-2020 al 9-mar-2023** (1.143 reportes diarios): ingesta reproducible, unificación de los cinco esquemas
de los reportes, capa limpia en Parquet, control de calidad de los datos y un Data Warehouse en SQLite (modelo en estrella)
integrado con vacunación (Our World in Data) e indicadores del Banco Mundial.

## Pregunta propia (P7)
**¿Los países que llegaron antes al 50 % de población con esquema completo tuvieron menos fallecidos
por 100.000 durante la ola de ómicron (1-dic-2021 a 31-mar-2022)?**

- 50 % = `people_fully_vaccinated_per_hundred` ≥ 50 (vacunación de Our World in Data).
- Misma ventana de ómicron para todos los países.
- Se responde distinguiendo correlación de causalidad: ingreso, testeo y edad de la población también influyen.

## Fuentes de datos
Los datos crudos **no se descargan ni se guardan**: el código los lee directo desde internet.

| Fuente | Dónde se lee | Para qué |
|---|---|---|
| JHU · reportes diarios (1.143 CSV) | `https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/csse_covid_19_data/csse_covid_19_daily_reports/` | Casos y fallecidos por territorio y día |
| JHU · series de tiempo | `.../csse_covid_19_data/csse_covid_19_time_series/` | Comparar con la suma de los reportes diarios |
| JHU · tabla UID | `.../csse_covid_19_data/UID_ISO_FIPS_LookUp_Table.csv` | Llave de territorio, población, lat/long, ISO3 |
| OWID · vacunación | `https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/vaccinations/vaccinations.csv` | % de población vacunada (P3, P7) |
| Banco Mundial (API) | `https://api.worldbank.org/v2/country/all/indicator/...` | % de 65+ y PIB per cápita 2021 (P7) |

## Cómo reproducir desde cero

Los notebooks se ejecutan **en orden** y cada uno usa los datos que deja el anterior:

| # | Notebook | Lee | Deja |
|---|---|---|---|
| 0 | `00_exploracion` | Reportes JHU de ene–jun 2020 (internet) | — (Hito 1: exploración y perfilado) |
| 1 | `01_ingesta` | Los 1.143 reportes, las series y la tabla UID (internet) | `data/clean/covid_limpio.parquet` |
| 2 | `02_calidad` | `covid_limpio.parquet` + tabla UID y reportes para el linaje (internet) | `data/clean/covid_diario.parquet`, `data/clean/indice_calidad_pais.parquet` |
| 3 | `03_dw` | `covid_diario.parquet` + tabla UID, OWID y Banco Mundial (internet) | `data/dw/covid_dw.db` y `data/dw/covid_dw.zip` |

> `01_ingesta` es el más lento: lee los 1.143 archivos desde internet y usa ~1,3 GB de RAM.
> El repositorio ya trae la capa limpia (`data/clean/`), así que `02_calidad` se puede correr sin pasar por `01_ingesta`.
> El DW (`covid_dw.db`) pesa ~130 MB y GitHub acepta hasta 100 MB por archivo: se sube comprimido como `data/dw/covid_dw.zip`.
> Para usarlo sin correr `03_dw`: `zipfile.ZipFile("../data/dw/covid_dw.zip").extractall("../data/dw")`.

### Opción A · Google Colab (Python 3.12)
Colab ya trae pandas, pyarrow y matplotlib; `00_exploracion` instala `ydata-profiling` en su propia celda.

1. Abrir un notebook del proyecto en Colab: *Archivo → Abrir cuaderno → GitHub* y pegar la URL del repositorio
   (`https://github.com/Maanuus/Proyecto_GD`).
2. Agregar **arriba de todo** una celda que clone el repositorio y entre a `notebooks/` (las rutas de los notebooks son
   relativas a esa carpeta, por ejemplo `../data/clean/...`), y ejecutarla:
   ```python
   !git clone https://github.com/Maanuus/Proyecto_GD.git /content/proyecto
   %cd /content/proyecto/notebooks
   ```
3. *Entorno de ejecución → Ejecutar todas*.
4. Repetir con el siguiente notebook **en el mismo entorno de ejecución**, en el orden 00 → 01 → 02 → 03. En los siguientes basta con
   `%cd /content/proyecto/notebooks` (el `git clone` se hace una sola vez).

### Opción B · Computador local (Python 3.10 a 3.13)
> `ydata-profiling` todavía no es compatible con Python 3.14: usar 3.13 o anterior.
> Si `python --version` dice 3.14, crear el entorno con [uv](https://docs.astral.sh/uv/) (instalar con `pip install uv`),
> que descarga Python 3.12 (el mismo de Colab) sin tocar el Python instalado.

1. Clonar el repositorio y abrir una terminal en su carpeta raíz:
   ```powershell
   git clone https://github.com/Maanuus/Proyecto_GD.git
   cd Proyecto_GD
   ```
2. Crear y activar un entorno virtual con Python 3.12:
   ```powershell
   uv venv --python 3.12 .venv
   .\.venv\Scripts\Activate.ps1
   python --version
   ```
   El prompt debe empezar con `(.venv)` y la versión debe ser 3.12. Si ya se tiene Python 3.10 a 3.13 instalado,
   también sirve `python -m venv .venv` en vez de `uv venv`.
3. Instalar las dependencias y Jupyter (con el entorno activo):
   ```powershell
   uv pip install -r requirements.txt jupyter
   ```
   Si el entorno se creó con `python -m venv`, usar `python -m pip install -r requirements.txt jupyter`.
4. Ejecutar los notebooks en orden, abriéndolos en Jupyter o VS Code (*Run All*), o todos desde la terminal:
   ```powershell
   cd notebooks
   foreach ($nb in "00_exploracion","01_ingesta","02_calidad","03_dw") { jupyter nbconvert --to notebook --execute --inplace "$nb.ipynb" }
   cd ..
   ```

## Estructura
| Carpeta / archivo | Contenido |
|---|---|
| `notebooks/00_exploracion.ipynb` | Hito 1: lectura de ene–jun 2020, nulos, unión de esquemas, casos diarios, top 10, Chile y perfilado |
| `notebooks/01_ingesta.ipynb` | Lectura de los 1.143 reportes, unificación de los cinco esquemas, llave de territorio, capa limpia y comparación CSV frente a Parquet |
| `notebooks/02_calidad.ipynb` | Acumulados → casos diarios, reglas de calidad en seis dimensiones, problemas cuantificados, índice de calidad por país, decisiones y linaje |
| `notebooks/03_dw.ipynb` | Data Warehouse en SQLite: dimensiones de fecha y territorio (país → región → condado), tabla de hechos territorio × día, vacunación de OWID y Banco Mundial con su tasa de cruce, y consultas OLAP |
| `data/clean/` | Capa limpia en Parquet (`covid_limpio` y `covid_diario` con compresión zstd; `indice_calidad_pais`) |
| `data/dw/covid_dw.zip` | Data Warehouse en SQLite (modelo en estrella), comprimido |
| `requirements.txt` | Dependencias de Python |
