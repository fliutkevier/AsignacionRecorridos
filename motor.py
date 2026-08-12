"""Resuelve el recorrido de cada ruta de Naturgy contra el callejero del turno.

Regla, validada sobre 731 rutas de los turnos 37 y 38:
  1. (Localidad, Calle) -> conjunto de recorridos.
  2. Un solo recorrido y la vereda existe -> ASIGNADO (EXACTA).
  3. Paridad '-' (defecto de origen) y un solo recorrido -> ASIGNADO (SIN_PARIDAD):
     si la calle entera está en el mismo recorrido, la vereda no aporta nada.
  4. Cualquier otro caso -> REVISAR, con el motivo en DETALLE.

La localidad es obligatoria en la clave: sin ella hubo 20 calles ambiguas en el turno 37
y 14 en el 38. Con ella, cero en ambos.

La paridad es desempate, no clave: (BARRIO, CALLE) ya determina el recorrido (456 claves
entre los dos turnos, cero excepciones). La vereda solo se usaría si una calle cayera en
más de un recorrido.
"""
from __future__ import annotations

import logging
import re

import config
import naturgy
import texto
from callejero import indexar
from modelos import Coincidencia, Estado, Resultado, Tramo

log = logging.getLogger(__name__)

_RUTA = re.compile(config.PATRON_RUTA)


def detectar_turno(tabla: naturgy.Tabla, tramos: list[Tramo]) -> str:
    """Turno del cruce, sacado de los datos (no del nombre del archivo).

    La comparación es sobre el turno normalizado: el callejero suele escribirlo con
    cero adelante ('038') y Naturgy no ('38'), pero son el mismo turno.

    Falla si el callejero y el export son de turnos distintos: sin este control,
    elegir el callejero equivocado produce un archivo casi vacío sin decir por qué.
    """
    del_callejero = tramos[0].turno if tramos else ""

    i_turno = naturgy.indice(tabla.encabezado, "TURNO")
    del_export = {config.turno_norm(f[i_turno]) for f in tabla.filas
                  if 0 <= i_turno < len(f) and f[i_turno].strip()}
    if len(del_export) > 1:
        raise ValueError(
            f"El export de Naturgy mezcla más de un turno: {', '.join(sorted(del_export))}.")

    turno = next(iter(del_export), "")
    if turno and del_callejero and turno != config.turno_norm(del_callejero):
        raise ValueError(
            f"Los archivos son de turnos distintos:\n"
            f"  callejero : turno {del_callejero}\n"
            f"  Naturgy   : turno {turno}\n"
            "Elegí el callejero que corresponde a este export.")

    return turno or del_callejero


def procesar(tabla: naturgy.Tabla,
             tramos: list[Tramo]) -> tuple[list[str], int, list[Resultado], list[Tramo]]:
    """Devuelve (columnas, posición de inserción de MIN/MAX, filas, tramos fuera)."""
    idx = indexar(tramos)

    i_loc = naturgy.indice(tabla.encabezado, "Localidad")
    i_ruta = naturgy.indice(tabla.encabezado, "Ruta")
    i_total = naturgy.indice(tabla.encabezado, "Total Leer")

    conservar = [i for i, h in enumerate(tabla.encabezado)
                 if h not in config.COLS_DESCARTAR]
    columnas = [config.RENOMBRAR.get(tabla.encabezado[i], tabla.encabezado[i])
                for i in conservar]

    # Los números de puerta del callejero van justo después de la columna de referencia.
    pos = (columnas.index(config.INSERTAR_DESPUES) + 1
           if config.INSERTAR_DESPUES in columnas else len(columnas))
    columnas = [*columnas[:pos], *config.COLS_CALLEJERO, *columnas[pos:]]

    filas: list[Resultado] = []
    for f in tabla.filas:
        r = Resultado(
            origen=[f[i] if i < len(f) else "" for i in conservar],
            localidad=f[i_loc].strip(),
            total_leer=f[i_total].strip() if 0 <= i_total < len(f) else "",
        )
        filas.append(r)
        _resolver(r, f[i_ruta].strip(), idx)

    fuera = [t for t in tramos if not t.reclamado]
    _cruce_difuso(filas, fuera)
    return columnas, pos, filas, fuera


def _resolver(r: Resultado, crudo: str, idx) -> None:
    m = _RUTA.match(crudo)
    if not m:
        r.detalle = f"no se pudo interpretar «{crudo}»"
        return

    r.calle = m.group(1).strip()
    r.paridad = m.group(2)
    r.ruta = m.group(3)          # texto: los ceros a la izquierda son significativos

    por_paridad = idx.get((r.localidad, r.calle))
    if not por_paridad:
        r.detalle = "la calle no figura en el callejero de este turno"
        r.calle_ausente = True
        return

    tramo = por_paridad.get(r.paridad)
    if tramo is not None:
        tramo.reclamado = True
        r.recorrido = tramo.recorrido
        r.estado = Estado.ASIGNADO
        r.coincidencia = Coincidencia.EXACTA
        r.tomar_alturas([tramo])
        return

    recorridos = sorted({t.recorrido for t in por_paridad.values()})

    # Paridad inválida en origen ('-'). Si TODOS los tramos de esa calle en esa localidad
    # caen en el mismo recorrido, la vereda no aporta nada y el resultado es inequívoco:
    # se asigna. Se marca SIN_PARIDAD para poder filtrarlas después y corregir el origen.
    if r.paridad not in ("I", "P") and len(recorridos) == 1:
        tramos = list(por_paridad.values())
        for t in tramos:
            t.reclamado = True
        r.recorrido = recorridos[0]
        r.estado = Estado.ASIGNADO
        r.coincidencia = Coincidencia.SIN_PARIDAD
        r.tomar_alturas(tramos)
        r.detalle = (f"paridad «{r.paridad}» inválida en origen; la calle está entera "
                     f"en el recorrido {recorridos[0]}, así que la vereda no hace falta")
        return

    # La calle está, pero no se puede decidir. Se informa el candidato y NO se asigna.
    candidato = (f"; candidato único: recorrido {recorridos[0]}" if len(recorridos) == 1
                 else f"; candidatos: {', '.join(map(str, recorridos))}")

    if r.paridad in ("I", "P"):
        veredas = "".join(sorted(por_paridad))
        r.detalle = f"la calle existe pero solo con vereda {veredas}{candidato}"
    else:
        r.coincidencia = Coincidencia.SIN_PARIDAD
        r.detalle = (f"paridad «{r.paridad}» inválida en origen, "
                     f"corregir en Naturgy y reexportar{candidato}")


def _cruce_difuso(filas: list[Resultado], fuera: list[Tramo]) -> None:
    """Enriquece el DETALLE de los dos lados cuando una calle ausente se parece a un
    tramo huérfano. Encontró 'GUTEMBERG' (typo del callejero) contra 'GUTENBERG'.

    NUNCA escribe recorrido ni cambia el estado: la fila sigue en REVISAR y decide el
    supervisor. Es una pista, no una resolución.
    """
    tomados: dict[int, Resultado] = {}

    # Ordenado por vereda para que el reparto entre I y P sea determinista.
    candidatas = sorted((r for r in filas if r.calle_ausente), key=lambda r: r.paridad)

    for r in candidatas:
        mejor, puntaje = None, 0.0
        for t in fuera:
            if id(t) in tomados or t.barrio_limpio.upper() != r.localidad.upper():
                continue
            s = texto.similitud(r.calle, t.calle_limpia)
            if t.paridad == r.paridad:
                s += 0.001      # desempate: dos rutas de la misma calle no van al mismo tramo
            if s > puntaje:
                mejor, puntaje = t, s

        if mejor is None or puntaje < config.UMBRAL_SUGERENCIA:
            continue

        tomados[id(mejor)] = r
        r.detalle += (f". ¿Será «{mejor.calle_limpia}»? (recorrido {mejor.recorrido}, "
                      f"vereda {mejor.paridad}, {mejor.medidores} medidores, "
                      f"{min(puntaje, 1.0):.0%} similar)")
        mejor.sugerencia = (f". ¿Corresponde a la ruta {r.ruta} «{r.calle}» "
                            f"(vereda {r.paridad}, {r.total_leer} a leer)?")
