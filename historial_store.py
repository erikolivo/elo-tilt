"""
historial_store.py
-------------------
Guarda el historial crudo de partidos terminados, particionado por
mes (data/historial_partidos/YYYY-MM.json), y sirve DE PASO como el
registro anti-duplicado: si un fixture_id ya esta en el archivo del
mes correspondiente a su fecha, no se vuelve a guardar ni se vuelve a
alimentar el rating por el (ver recopilar_dia.py). Esto reemplaza la
idea original de un archivo separado 'fixtures_procesados_rating.json'
(ver README, seccion "Anti-duplicado") -- un archivo aparte hubiera
sido informacion redundante con lo que ya vive aqui.

El orden en que se escriben los partidos dentro de cada archivo NO
importa para el calculo normal (Glicko-2 es incremental, ver README
seccion "Particionado"). Solo importa si algun dia se necesita
RECONSTRUIR el rating desde cero -- en ese caso hay que procesar los
archivos mensuales en orden cronologico de fecha de partido, no de
orden de insercion.
"""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DIR_HISTORIAL = DATA_DIR / "historial_partidos"


def _archivo_del_mes(fecha_iso):
    aaaa_mm = fecha_iso[:7]  # "YYYY-MM"
    return DIR_HISTORIAL / f"{aaaa_mm}.json"


def _cargar_mes(fecha_iso):
    archivo = _archivo_del_mes(fecha_iso)
    if archivo.exists():
        try:
            return json.loads(archivo.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"partidos": []}


def _guardar_mes(fecha_iso, datos):
    DIR_HISTORIAL.mkdir(parents=True, exist_ok=True)
    _archivo_del_mes(fecha_iso).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fixture_ids_guardados(fecha_iso):
    """IDs de fixtures ya guardados en el archivo del mes de esta
    fecha (sin filtrar por fecha exacta -- un mes completo cabe sin
    problema en memoria, ver estimados de tamano en el README)."""
    datos = _cargar_mes(fecha_iso)
    return {p["fixture_id"] for p in datos["partidos"]}


def guardar_partido(fecha_iso, registro):
    """Agrega 'registro' (debe incluir la llave 'fixture_id') al
    archivo del mes correspondiente. No verifica duplicados aqui --
    el llamador debe consultar fixture_ids_guardados() antes, para no
    tener que recargar el archivo del mes en cada partido."""
    datos = _cargar_mes(fecha_iso)
    datos["partidos"].append(registro)
    _guardar_mes(fecha_iso, datos)
