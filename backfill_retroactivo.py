"""
backfill_retroactivo.py
------------------------
Corrida MANUAL (una sola vez, o cuando se quiera extender el
historial hacia atras). Recorre los ultimos N dias en orden
CRONOLOGICO (del mas viejo al mas reciente) y llama a
recopilar_dia.procesar_fecha() para cada uno.

Por que en orden cronologico: aunque el guardado del historial no lo
necesita (es solo un registro particionado), alimentar Glicko-2 en
orden real de los partidos es mas fiel al comportamiento esperado del
rating.

Pausa entre dias: ESPN no documenta un limite de peticiones, pero
tampoco lo descarta -- se mantiene prudencia con una pausa entre cada
dia para no generar una rafaga de cientos de peticiones seguidas
(recordar que cada dia ya implica consultar el marcador global +
todas las ligas descubiertas, ver fetch_data.py).

Uso:
    python backfill_retroactivo.py --dias 30
    python backfill_retroactivo.py --dias 30 --pausa 2
"""

import argparse
import datetime
import time

import recopilar_dia

ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hoy_ecuador():
    return datetime.datetime.now(ZONA_HORARIA_ECUADOR).date()


def correr(dias, pausa_segundos=2):
    hoy = _hoy_ecuador()
    fechas = [(hoy - datetime.timedelta(days=i)).isoformat() for i in range(dias, 0, -1)]

    total_nuevos = 0
    for i, fecha in enumerate(fechas, 1):
        print(f"--- Backfill {i}/{len(fechas)}: {fecha} ---")
        try:
            total_nuevos += recopilar_dia.procesar_fecha(fecha)
        except Exception as e:
            print(f"[AVISO] Fallo procesando {fecha}, se sigue con el resto: {e}")
        if i < len(fechas):
            time.sleep(pausa_segundos)

    print(f"\nBackfill completo: {total_nuevos} partido(s) nuevo(s) en total sobre {dias} dia(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill retroactivo del historial y el rating propio.")
    parser.add_argument("--dias", type=int, default=30, help="Cuantos dias hacia atras (por defecto 30)")
    parser.add_argument("--pausa", type=float, default=2.0, help="Segundos de pausa entre cada dia")
    args = parser.parse_args()

    correr(args.dias, pausa_segundos=args.pausa)
