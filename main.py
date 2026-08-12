"""Asigna el recorrido (lote) a cada ruta del export de Naturgy.

  python main.py <callejero.xlsx> <naturgy.csv|xlsx> [-o salida.xlsx]

No modifica ninguno de los dos archivos de entrada.

Códigos de retorno:
  0  todo asignado
  2  terminó bien, pero hay filas en REVISAR (hace falta intervención humana)
  1  error
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import callejero
import colectores as colectores_mod
import config
import escritor
import motor
import naturgy


def _configurar_log(verboso: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verboso else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="recorridos",
        description="Asigna el recorrido (lote) a cada ruta del export de Naturgy.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Salida: hojas RUTAS, REVISAR y FUERA_NATURGY.")
    p.add_argument("callejero", type=Path,
                   help="xlsx del turno: TURNO | RUTA_EMA | BARRIO | CALLE | ALT_MIN | ALT_MAX | c")
    p.add_argument("naturgy", type=Path,
                   help="export del portal, csv (recomendado) o xlsx convertido")
    p.add_argument("-c", "--colectores", type=Path, default=None,
                   help="xlsx con Numero | Colector; agrega la hoja COLECTORES "
                        "y el desplegable de la columna COLECTOR")
    p.add_argument("-o", "--salida", type=Path, default=None,
                   help="xlsx de salida (por defecto TurnoNN_RECORRIDOS.xlsx junto al de Naturgy)")
    p.add_argument("-v", "--verboso", action="store_true")
    args = p.parse_args(argv)

    _configurar_log(args.verboso)
    log = logging.getLogger("main")

    for f in (args.callejero, args.naturgy, args.colectores):
        if f is None:
            continue
        if not f.is_file():
            log.error("ERROR: no existe el archivo %s", f)
            return 1

    inicio = time.perf_counter()

    try:
        log.info("callejero : %s", args.callejero.name)
        tramos = callejero.leer(args.callejero)

        log.info("naturgy   : %s", args.naturgy.name)
        tabla = naturgy.leer(args.naturgy)

        # El nombre depende del turno, que sale de los datos: recién acá se conoce.
        turno = motor.detectar_turno(tabla, tramos)
        salida = args.salida or args.naturgy.parent / config.nombre_salida(turno)

        lista = None
        if args.colectores:
            log.info("colectores: %s", args.colectores.name)
            lista = colectores_mod.leer(args.colectores)

        columnas, pos, filas, fuera = motor.procesar(tabla, tramos)
        r = escritor.escribir(salida, columnas, pos, filas, fuera, lista)
    except ValueError as e:
        log.error("\nERROR: %s", e)
        return 1
    except PermissionError:
        log.error("\nERROR: no se pudo escribir el archivo de salida "
                  "(¿está abierto en Excel?)")
        return 1
    except Exception:  # noqa: BLE001
        log.exception("\nERROR inesperado")
        return 1

    ms = (time.perf_counter() - inicio) * 1000
    log.info("")
    log.info("ASIGNADO      %5d  (%.1f%%)", r.asignadas, r.porcentaje)
    log.info("REVISAR       %5d", r.a_revisar)
    log.info("FUERA_NATURGY %5d  (tramos del callejero sin ruta)", r.fuera_naturgy)
    log.info("")
    log.info("-> %s   [%.0f ms]", salida, ms)

    return 2 if r.a_revisar else 0


if __name__ == "__main__":
    sys.exit(main())
