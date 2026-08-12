"""Utilidades de texto compartidas por el lector de callejero y el motor."""
from __future__ import annotations

import difflib


def desmojibake(s: str) -> str | None:
    """El callejero llega con bytes latin-1 renderizados como CP850 (export vía pipeline DOS).

    Casos reales:
        'ALVAR NUÐEZ'   -> 'ALVAR NUÑEZ'
        'B║ PROCREAR'   -> 'Bº PROCREAR'
        'CURAPALIG³E'   -> 'CURAPALIGüE'

    Devuelve None si no cambia nada o si no aplica. El llamador debe indexar AMBAS
    variantes: aplicar esto a ciegas rompería un texto ya correcto ('CHAÑAR' -> 'CHA¥AR').
    Nunca se decide cuál es la buena; se registran las dos.
    """
    if not s:
        return None
    try:
        r = s.encode("cp850").decode("latin-1")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None      # hay caracteres fuera de CP850: no es mojibake de este tipo
    return r if r != s else None


def limpio(s: str) -> str:
    """Variante legible de un texto del callejero (corregida si aplica)."""
    return desmojibake(s) or s


def variantes(s: str) -> set[str]:
    """Las formas bajo las que hay que indexar un texto del callejero."""
    alt = desmojibake(s)
    return {s, alt} if alt else {s}


def similitud(a: str, b: str) -> float:
    """Parecido 0..1 entre dos nombres de calle.

    Se usa SOLO para sugerir en la columna DETALLE; jamás para asignar un recorrido.
    """
    return difflib.SequenceMatcher(None, a, b).ratio()
