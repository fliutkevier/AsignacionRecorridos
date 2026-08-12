"""Configuración central. Nada de valores hardcodeados en el resto del código."""
from __future__ import annotations

# --- Callejero (xlsx TURNO_NN__dd-mm_WR.xlsx) --------------------------------
# RUTA_EMA es el RECORRIDO (el lote), no una ruta. Nombre engañoso del origen.
CALLEJERO_HEADER = ("TURNO", "RUTA_EMA", "BARRIO", "CALLE", "ALT_MIN", "ALT_MAX", "c")
CALLEJERO_COL = {n: i + 1 for i, n in enumerate(CALLEJERO_HEADER)}  # 1-based

# --- Export de Naturgy (csv del portal, o xlsx si alguien lo convirtió) ------
NATURGY_HEADER_MINIMO = ("TURNO", "Localidad", "Ruta")
NATURGY_ENCODING = "utf-8-sig"        # el CSV viene UTF-8 CON BOM

# La columna `Ruta` trae "CALLE / ( X ) / NNNN". El grupo 3 es la ruta de Naturgy.
PATRON_RUTA = r"^(.*?)\s*/\s*\(\s*(.)\s*\)\s*/\s*(\d+)\s*$"

# Columnas del export que NO van a la salida.
COLS_DESCARTAR = frozenset({
    "Nro. Período", "Año Período",
    "Leídos", "Ctd. Avisos", "Ctd. Avisos A", "Ctd. Avisos Z",
    "Ctd. Avisos R", "Ctd. Avisos D", "Ctd. Avisos 5",
})

# `Ruta` cruda se renombra para no confundirla con la RUTA de 4 dígitos.
RENOMBRAR = {"Ruta": "Ruta Naturgy", "Localidad": "LOCALIDAD"}

# --- Colectores (xlsx con Numero | Colector) ---------------------------------
COLECTORES_HEADER = ("Numero", "Colector")
HOJA_COLECTORES = "COLECTORES"
COLS_COLECTORES = ("NUMERO", "COLECTOR")
# La columna que el supervisor completa con el desplegable.
COL_COLECTOR = "COLECTOR"
# Filas del xlsx que llevan el desplegable (aunque estén vacías, para poder crecer).
FILAS_VALIDACION_EXTRA = 200

# Columnas que se traen del callejero (números de puerta del tramo), insertadas
# justo después de la columna de referencia.
COLS_CALLEJERO = ("MIN", "MAX")
INSERTAR_DESPUES = "Ruta Naturgy"

# Columnas del export que deben quedar NUMÉRICAS en el xlsx de salida.
COLS_NUMERICAS = frozenset({"TURNO", "Total Leer"})

# --- Salida -------------------------------------------------------------------
# Nombre del archivo generado. Un cruce = un turno.
_NOMBRE_SALIDA = "Turno{turno}_RECORRIDOS.xlsx"
_NOMBRE_SIN_TURNO = "RECORRIDOS.xlsx"          # si el turno no se pudo determinar


def turno_norm(turno: str) -> str:
    """Turno sin ceros a la izquierda: '03' -> '3', '038' -> '38'.

    Muchos callejeros escriben el turno con cero adelante y el export de Naturgy no.
    Sin esto, la validación de turnos los toma como distintos y corta de más.
    Si no es numérico se devuelve tal cual (no se rompe con un valor inesperado).
    """
    t = (turno or "").strip()
    if not t.isdigit():
        return t
    return t.lstrip("0") or "0"


def nombre_salida(turno: str) -> str:
    """Turno37_RECORRIDOS.xlsx — un cruce es siempre de un solo turno."""
    return _NOMBRE_SALIDA.format(turno=turno_norm(turno)) if turno else _NOMBRE_SIN_TURNO


COLS_NUEVAS = ("RUTA", "RECORRIDO", "COLECTOR", "ESTADO", "COINCIDENCIA", "DETALLE")
HOJA_RUTAS = "RUTAS"
HOJA_REVISAR = "REVISAR"
HOJA_FUERA = "FUERA_NATURGY"
COLS_FUERA = ("RECORRIDO", "BARRIO", "CALLE", "ALT_MIN", "ALT_MAX",
              "PARIDAD", "MEDIDORES", "DETALLE")

# --- Cruce difuso -------------------------------------------------------------
# Solo escribe texto en DETALLE. NUNCA asigna un recorrido ni cambia el ESTADO.
UMBRAL_SUGERENCIA = 0.85

# --- Formato ------------------------------------------------------------------
FUENTE = "Arial"
TAM_FUENTE = 10
COLOR_ENCABEZADO = "1F3864"
COLOR_REVISAR = "FFF2CC"
ANCHO_MIN, ANCHO_MAX = 9, 65
