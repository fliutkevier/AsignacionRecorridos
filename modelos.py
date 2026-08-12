"""Modelos de dominio."""
from __future__ import annotations

from dataclasses import dataclass, field

import texto


class Estado:
    """Estados terminales que el motor escribe en la columna ESTADO."""
    ASIGNADO = "ASIGNADO"
    REVISAR = "REVISAR"


class Coincidencia:
    """Cómo se llegó al recorrido. Vacío cuando no se resolvió."""
    EXACTA = "EXACTA"
    SIN_PARIDAD = "SIN_PARIDAD"
    NINGUNA = ""


@dataclass(slots=True)
class Tramo:
    """Un tramo de calle del callejero (una fila del xlsx del turno)."""
    turno: str
    recorrido: int              # columna RUTA_EMA: el lote, siempre numérico
    barrio: str
    calle: str
    alt_min: str
    alt_max: str
    paridad: str                # 'I' | 'P', deducida del último dígito de alt_min
    medidores: int              # columna 'c'

    reclamado: bool = False     # lo tomó alguna ruta de Naturgy
    sugerencia: str = ""        # texto que agrega el cruce difuso al DETALLE

    @property
    def barrio_limpio(self) -> str:
        return texto.limpio(self.barrio)

    @property
    def calle_limpia(self) -> str:
        return texto.limpio(self.calle)


@dataclass(slots=True)
class Resultado:
    """Una fila de la salida: lo conservado de Naturgy más lo que agrega el bot."""
    origen: list[str]                       # columnas de Naturgy que se conservan, en orden
    localidad: str = ""
    ruta: str = ""                          # '0087' — SIEMPRE texto, nunca numérico
    calle: str = ""                         # parseada; no se escribe, es diagnóstico interno
    paridad: str = ""                       # 'I' | 'P' | '-'
    total_leer: str = ""
    alt_min: str = ""                       # números de puerta del tramo del callejero;
    alt_max: str = ""                       # vacíos si la ruta no resolvió
    recorrido: int | None = None            # None cuando no se resolvió
    estado: str = Estado.REVISAR
    coincidencia: str = Coincidencia.NINGUNA
    detalle: str = ""
    calle_ausente: bool = False             # candidata al cruce difuso

    def tomar_alturas(self, tramos: list) -> None:
        """Rango de puerta del tramo. Si la ruta abarca varios tramos (paridad '-' con
        ambas veredas en el mismo recorrido), se toma el rango que los cubre a todos."""
        if not tramos:
            return
        self.alt_min = min((t.alt_min for t in tramos), key=_num)
        self.alt_max = max((t.alt_max for t in tramos), key=_num)

    def fila(self, pos_insercion: int) -> list:
        """Fila final. `pos_insercion` es dónde van MIN/MAX dentro de las de Naturgy.
        COLECTOR va vacía: la completa el supervisor con el desplegable."""
        return [*self.origen[:pos_insercion], self.alt_min, self.alt_max,
                *self.origen[pos_insercion:],
                self.ruta, self.recorrido, None,
                self.estado, self.coincidencia, self.detalle]


def _num(altura: str) -> int:
    """Valor numérico de una altura ('00205' -> 205) para poder compararlas."""
    digitos = "".join(c for c in altura if c.isdigit())
    return int(digitos) if digitos else 0


@dataclass(slots=True)
class Resumen:
    """Resultado agregado, para el log del CLI."""
    total: int
    asignadas: int
    a_revisar: int
    fuera_naturgy: int

    @property
    def porcentaje(self) -> float:
        return 100.0 * self.asignadas / self.total if self.total else 0.0
