# Contribuciones y uso de IA generativa

## 1 · Equipo

| Integrante       | Usuario en GitHub          | Rol en el equipo                                                                       |
| ---------------- | -------------------------- | -------------------------------------------------------------------------------------- |
| Manuel Cisternas | Maanuus (Manuel Cisternas) | Coordinación y capa limpia: base del repositorio, ingesta, calidad e integración final |
| Luis Núñez       | Luis Felipe Núñez Muñoz    | Protección de datos, análisis histórico e informes                                     |
| Matías Zúñiga    | Matisito-beep              | Data Warehouse e integración de fuentes externas; tablero (con Camila)                 |
| Camila Rivera    | mileron                    | Minería y predicción; tablero (con Matías)                                             |

Matías y Camila trabajaron en pareja: el DW, la minería y el tablero los discutieron juntos aunque cada commit quedó a nombre de uno.

## 2 · Quién hizo qué, por componente

| Componente                                   | Archivos                                        | Responsable(s)                                                                         | Revisó                              |
| -------------------------------------------- | ----------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------- |
| Base del proyecto y Hito 1 (exploración, P7) | `00_exploracion.ipynb`, `README.md`             | Manuel Cisternas                                                                       | Luis Núñez                          |
| R1 · Ingesta y arquitectura                  | `01_ingesta.ipynb`                              | Manuel Cisternas                                                                       | Matías Zúñiga                       |
| R2 · Calidad y gobierno                      | `02_calidad.ipynb`, `docs/diccionario_datos.md` | Manuel Cisternas (notebook y diccionario)                                              | Luis Núñez (ajustes al diccionario) |
| R3 · Data Warehouse e integración            | `03_dw.ipynb`, `data/dw/covid_dw.zip`           | Matías Zúñiga, con Camila Rivera                                                       | Manuel Cisternas                    |
| R6 · Protección de datos y ética             | `04_proteccion.ipynb`                           | Luis Núñez                                                                             | Manuel Cisternas                    |
| R4 · Análisis histórico (P1–P4, P7)          | `05_analisis.ipynb`                             | Luis Núñez                                                                             | Manuel Cisternas                    |
| R5 · Minería y predicción (P5, P6)           | `06_mineria.ipynb`                              | Camila Rivera, con Matías Zúñiga                                                       | Manuel Cisternas                    |
| R7 · Tablero                                 | `dashboard/app.py`, `dashboard/capturas/`       | Matías Zúñiga y Camila Rivera (mejoras); Manuel Cisternas (integración al repositorio) | Luis Núñez                          |
| R8 · Informe al Comité                       | `docs/informe_comite.pdf`                       | Luis Núñez                                                                             | Camila Rivera                       |
| Informe técnico                              | `docs/informe_tecnico.pdf`                      | Luis Núñez                                                                             | Matías Zúñiga                       |

## 3 · Uso de IA generativa

### Herramienta

**Claude Code** (Anthropic), modelo Claude Opus 5.5.

### Qué se hizo con IA

| Parte                    | Qué hizo la IA                                                                               | Qué decidió o aprobó el equipo                                                               |
| ------------------------ | -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Exploración              | Propuso y programó la lectura con hebras de los datos para bajar tiempo de ejecución         | Enfoque aprobado                                                                             |
| Segmentación             | Propuso y programó k-means sobre la curva semanal normalizada; probó k = 2…8                 | Enfoque aprobado; k = 4 propuesto por silueta                                                |
| Pronóstico y backtesting | Programó `pronosticar` (base y Holt), el test sin fuga y el backtesting con MAE/MAPE         | Enfoque aprobado; países y regiones de Chile                                                 |
| Alerta                   | Programó `alerta`, probó 9 combinaciones de umbral y piso; propuso 25 % y piso 5             | Aprobado; queda como valor por defecto                                                       |
| Tercer modelo            | Probó Holt en escala logarítmica y lo integró en `pronosticar`; justificó no usar vacunación | Aprobado (dentro de `pronosticar`)                                                           |
| Tablero                  | Programó el mapa animado; lo probó en el navegador                                           | Un solo archivo con copias de las funciones (sin `src/`); mapa animado en vez de coroplético |
