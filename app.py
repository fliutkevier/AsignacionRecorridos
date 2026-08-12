"""Ventana de escritorio para los supervisores.

    python app.py

Toda la lógica vive en callejero/naturgy/motor/escritor. Acá solo hay UI.
El procesamiento corre en un hilo aparte para que la ventana no se congele.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from tkinter import Tk, StringVar, filedialog, messagebox, ttk, END, W, E, N, S

import callejero
import colectores as colectores_mod
import config
import escritor
import motor
import naturgy
from modelos import Estado

log = logging.getLogger(__name__)

TITULO = "Asignación de recorridos"
PREFS = Path.home() / ".recorridos.json"


# --------------------------------------------------------------------- helpers
def _cargar_prefs() -> dict:
    try:
        return json.loads(PREFS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - archivo ausente o corrupto: se arranca limpio
        return {}


def _guardar_prefs(d: dict) -> None:
    try:
        PREFS.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001 - no poder recordar carpetas no es motivo de error
        pass


def _abrir(ruta: Path) -> None:
    """Abre un archivo o carpeta con la aplicación por defecto del sistema."""
    try:
        if sys.platform == "win32":
            os.startfile(ruta)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.run(["open", str(ruta)], check=False)
        else:
            subprocess.run(["xdg-open", str(ruta)], check=False)
    except Exception as e:  # noqa: BLE001
        messagebox.showerror(TITULO, f"No se pudo abrir:\n{ruta}\n\n{e}")


def _turno_probable(callejero_path: str) -> str:
    """Turno inferido del nombre del callejero ('TURNO_38__01-04_WR.xlsx' -> '38').

    Solo se usa para avisar de una sobrescritura ANTES de leer los archivos. El nombre
    definitivo lo decide el turno que traen los datos, no esto.
    """
    m = re.search(r"turno[_\s-]*(\d+)", Path(callejero_path).stem, re.IGNORECASE)
    return config.turno_norm(m.group(1)) if m else ""


# ------------------------------------------------------------------------ app
class App:
    def __init__(self, raiz: Tk) -> None:
        self.raiz = raiz
        self.prefs = _cargar_prefs()
        self.cola: queue.Queue = queue.Queue()
        self.salida: Path | None = None
        self.trabajando = False

        raiz.title(TITULO)
        raiz.minsize(760, 560)
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(1, weight=1)

        self.v_callejero = StringVar()
        self.v_naturgy = StringVar()
        self.v_colectores = StringVar(value=self.prefs.get("colectores", ""))
        self.v_destino = StringVar(value=self.prefs.get("destino", ""))
        self.v_estado = StringVar(value="Elegí los dos archivos y presioná Procesar.")

        self._armar_entradas()
        self._armar_resultado()
        self._armar_pie()
        self._revisar_cola()

    # -------------------------------------------------------------- construcción
    def _armar_entradas(self) -> None:
        m = ttk.Frame(self.raiz, padding=(16, 14, 16, 8))
        m.grid(row=0, column=0, sticky=(W, E))
        m.columnconfigure(1, weight=1)

        filas = [
            ("Callejero del turno", self.v_callejero, self._elegir_callejero),
            ("Export de Naturgy", self.v_naturgy, self._elegir_naturgy),
            ("Lista de colectores (opcional)", self.v_colectores, self._elegir_colectores),
            ("Guardar en", self.v_destino, self._elegir_destino),
        ]
        for i, (etiqueta, var, cmd) in enumerate(filas):
            ttk.Label(m, text=etiqueta).grid(row=i * 2, column=0, columnspan=3,
                                             sticky=W, pady=(6 if i else 0, 2))
            ttk.Entry(m, textvariable=var).grid(row=i * 2 + 1, column=0, columnspan=2,
                                                sticky=(W, E), padx=(0, 8), ipady=3)
            ttk.Button(m, text="Buscar…", command=cmd, width=11).grid(row=i * 2 + 1, column=2)

        self.btn = ttk.Button(m, text="Procesar", command=self._procesar)
        self.btn.grid(row=8, column=0, columnspan=3, pady=(16, 4), ipady=6, sticky=(W, E))

        self.barra = ttk.Progressbar(m, mode="indeterminate")
        self.barra.grid(row=9, column=0, columnspan=3, sticky=(W, E))
        self.barra.grid_remove()

    def _armar_resultado(self) -> None:
        m = ttk.Frame(self.raiz, padding=(16, 4, 16, 4))
        m.grid(row=1, column=0, sticky=(N, S, W, E))
        m.columnconfigure(0, weight=1)
        m.rowconfigure(2, weight=1)

        self.resumen = ttk.Label(m, text="", font=("Segoe UI", 10, "bold"))
        self.resumen.grid(row=0, column=0, sticky=W, pady=(4, 6))

        self.titulo_tabla = ttk.Label(m, text="")
        self.titulo_tabla.grid(row=1, column=0, sticky=W, pady=(0, 4))

        cols = ("ruta", "localidad", "calle", "detalle")
        self.tabla = ttk.Treeview(m, columns=cols, show="headings", height=10)
        for c, txt, ancho in (("ruta", "RUTA", 70), ("localidad", "LOCALIDAD", 130),
                              ("calle", "CALLE", 190), ("detalle", "MOTIVO", 420)):
            self.tabla.heading(c, text=txt)
            self.tabla.column(c, width=ancho, anchor=W,
                              stretch=(c == "detalle"))
        self.tabla.grid(row=2, column=0, sticky=(N, S, W, E))
        # Los valores originales NO se leen del widget: Tk convierte '0099' a 99 al
        # devolverlos por item()['values']. Se guardan acá, con la ruta como texto.
        self.pendientes: dict[str, tuple[str, str, str, str]] = {}
        self.tabla.bind("<Double-1>", self._copiar_ruta)

        scroll = ttk.Scrollbar(m, orient="vertical", command=self.tabla.yview)
        scroll.grid(row=2, column=1, sticky=(N, S))
        self.tabla.configure(yscrollcommand=scroll.set)

    def _copiar_ruta(self, _evento) -> None:
        """Doble clic: copia la RUTA al portapapeles, lista para pegar en el portal."""
        sel = self.tabla.selection()
        if not sel:
            return
        ruta = self.pendientes.get(sel[0], ("",))[0]
        if not ruta:
            return
        self.raiz.clipboard_clear()
        self.raiz.clipboard_append(ruta)
        self.v_estado.set(f"Ruta {ruta} copiada al portapapeles.")

    def _armar_pie(self) -> None:
        m = ttk.Frame(self.raiz, padding=(16, 4, 16, 14))
        m.grid(row=2, column=0, sticky=(W, E))
        m.columnconfigure(0, weight=1)

        ttk.Label(m, textvariable=self.v_estado, foreground="#555").grid(row=0, column=0, sticky=W)
        self.btn_abrir = ttk.Button(m, text="Abrir archivo", state="disabled",
                                    command=lambda: self.salida and _abrir(self.salida))
        self.btn_abrir.grid(row=0, column=1, padx=(8, 4))
        self.btn_carpeta = ttk.Button(m, text="Abrir carpeta", state="disabled",
                                      command=lambda: self.salida and _abrir(self.salida.parent))
        self.btn_carpeta.grid(row=0, column=2)

    # ------------------------------------------------------------------ archivos
    def _dir_inicial(self, clave: str) -> str:
        """Arranca donde está el callejero ya elegido: el export y la salida suelen vivir
        en la misma carpeta. Si todavía no hay callejero, usa la última carpeta usada."""
        cal = self.v_callejero.get().strip()
        if cal:
            carpeta = Path(cal).parent
            if carpeta.is_dir():
                return str(carpeta)
        return self.prefs.get(clave, str(Path.home()))

    def _elegir_callejero(self) -> None:
        f = filedialog.askopenfilename(
            title="Callejero del turno",
            initialdir=self.prefs.get("dir_callejero", str(Path.home())),
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if f:
            self.v_callejero.set(f)
            self.prefs["dir_callejero"] = str(Path(f).parent)
            # La salida sigue al callejero: casi siempre van a la misma carpeta.
            # Pisa lo que hubiera; si el supervisor quiere otra, la elige después.
            self.v_destino.set(str(Path(f).parent))

    def _elegir_naturgy(self) -> None:
        f = filedialog.askopenfilename(
            title="Export de Naturgy",
            initialdir=self._dir_inicial("dir_naturgy"),
            filetypes=[("Export del portal", "*.csv *.xlsx"), ("Todos", "*.*")])
        if f:
            self.v_naturgy.set(f)
            self.prefs["dir_naturgy"] = str(Path(f).parent)
            self._sugerir_destino()

    def _elegir_colectores(self) -> None:
        f = filedialog.askopenfilename(
            title="Lista de colectores",
            initialdir=self._dir_inicial("dir_colectores"),
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if f:
            self.v_colectores.set(f)
            self.prefs["colectores"] = f          # la lista cambia poco: se recuerda entera
            self.prefs["dir_colectores"] = str(Path(f).parent)

    def _elegir_destino(self) -> None:
        d = filedialog.askdirectory(
            title="Carpeta de salida",
            initialdir=self.v_destino.get() or self._dir_inicial("destino"))
        if d:
            self.v_destino.set(d)
            self.prefs["destino"] = d

    def _sugerir_destino(self) -> None:
        """Completa la carpeta de salida si todavía está vacía (caso: se eligió primero
        el export). Cuando se elige el callejero, esa carpeta manda y pisa esto."""
        if not self.v_destino.get() and self.v_naturgy.get():
            self.v_destino.set(str(Path(self.v_naturgy.get()).parent))

    def _carpeta_salida(self) -> Path:
        return Path(self.v_destino.get() or Path(self.v_naturgy.get()).parent)

    # ----------------------------------------------------------------- proceso
    def _procesar(self) -> None:
        if self.trabajando:
            return
        cal, nat = self.v_callejero.get().strip(), self.v_naturgy.get().strip()
        for ruta, que in ((cal, "el callejero"), (nat, "el export de Naturgy")):
            if not ruta or not Path(ruta).is_file():
                messagebox.showwarning(TITULO, f"Falta elegir {que}.")
                return

        # El nombre es fijo por turno, así que reprocesar el mismo turno pisa el archivo
        # anterior. Se avisa antes, no después. El turno se saca del nombre del callejero
        # solo para este aviso; el nombre real lo decide el contenido de los datos.
        destino = self._carpeta_salida() / config.nombre_salida(_turno_probable(cal))
        if destino.is_file() and not messagebox.askyesno(
                TITULO, f"Ya existe:\n{destino.name}\n\n¿Reemplazarlo?"):
            return

        self.trabajando = True
        self.salida = None          # el nombre depende del turno: se sabe al leer
        self.btn.state(["disabled"])
        self.btn_abrir.state(["disabled"])
        self.btn_carpeta.state(["disabled"])
        self.barra.grid()
        self.barra.start(12)
        self.tabla.delete(*self.tabla.get_children())
        self.pendientes.clear()
        self.resumen.configure(text="")
        self.titulo_tabla.configure(text="")
        self.v_estado.set("Procesando…")

        col = self.v_colectores.get().strip()
        threading.Thread(target=self._trabajar,
                         args=(Path(cal), Path(nat), self._carpeta_salida(),
                               Path(col) if col else None),
                         daemon=True).start()

    def _trabajar(self, cal: Path, nat: Path, carpeta: Path, col: Path | None) -> None:
        """Corre en un hilo aparte. Se comunica con la UI solo por la cola."""
        salida = carpeta / config.nombre_salida('')
        try:
            tramos = callejero.leer(cal)
            tabla = naturgy.leer(nat)

            # El nombre depende del turno, y el turno sale de los datos.
            turno = motor.detectar_turno(tabla, tramos)
            salida = carpeta / config.nombre_salida(turno)

            lista = colectores_mod.leer(col) if col else None

            columnas, pos, filas, fuera = motor.procesar(tabla, tramos)
            resumen = escritor.escribir(salida, columnas, pos, filas, fuera, lista)
            pendientes = [(f.ruta, f.localidad, f.calle, f.detalle)
                          for f in filas if f.estado == Estado.REVISAR]
            self.cola.put(("ok", resumen, pendientes, salida))
        except ValueError as e:
            self.cola.put(("error", str(e)))
        except PermissionError:
            self.cola.put(("error", f"No se pudo escribir:\n{salida}\n\n"
                                    "¿Está abierto en Excel?"))
        except Exception:  # noqa: BLE001
            self.cola.put(("error", traceback.format_exc()))

    def _revisar_cola(self) -> None:
        try:
            msg = self.cola.get_nowait()
        except queue.Empty:
            pass
        else:
            self._terminar(msg)
        self.raiz.after(120, self._revisar_cola)

    def _terminar(self, msg: tuple) -> None:
        self.trabajando = False
        self.barra.stop()
        self.barra.grid_remove()
        self.btn.state(["!disabled"])

        if msg[0] == "error":
            self.v_estado.set("Terminó con error.")
            messagebox.showerror(TITULO, msg[1])
            return

        _, r, pendientes, self.salida = msg
        self.resumen.configure(            text=f"ASIGNADO  {r.asignadas}  ({r.porcentaje:.1f}%)     "
                 f"REVISAR  {r.a_revisar}     FUERA DE NATURGY  {r.fuera_naturgy}")

        if pendientes:
            self.titulo_tabla.configure(
                text=f"{len(pendientes)} ruta(s) para revisar — también están en la hoja REVISAR:")
            for fila in pendientes:
                iid = self.tabla.insert("", END, values=fila)
                self.pendientes[iid] = fila
        else:
            self.titulo_tabla.configure(text="No quedó ninguna ruta para revisar.")

        self.btn_abrir.state(["!disabled"])
        self.btn_carpeta.state(["!disabled"])
        self.v_estado.set(f"Listo: {self.salida.name}")
        _guardar_prefs(self.prefs)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raiz = Tk()
    try:
        raiz.call("tk", "scaling", 1.3)      # que no se vea diminuto en pantallas HiDPI
    except Exception:  # noqa: BLE001
        pass
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except Exception:  # noqa: BLE001
        pass
    App(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
