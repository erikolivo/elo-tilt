"""
actualizar.py
-------------
Script maestro que ejecuta todo el pipeline:
  1. Recopila resultados del dia (alimenta rating Glicko-2)
  2. Predice partidos futuros (con tilt/momentum)
  3. Genera el dashboard HTML

Ejecutar manualmente o desde GitHub Actions.

Uso:
    python actualizar.py                  # pipeline completo
    python actualizar.py --solo-prediccion  # solo predecir + dashboard
    python actualizar.py --solo-dashboard   # solo regenerar HTML
"""

import argparse
import datetime
import sys

ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hoy_ecuador():
    return datetime.datetime.now(ZONA_HORARIA_ECUADOR).date().isoformat()


def paso_recopilar(fecha):
    import recopilar_dia
    print(f"\n{'='*50}")
    print(f"PASO 1: Recopilando resultados de {fecha}")
    print(f"{'='*50}")
    try:
        nuevos = recopilar_dia.procesar_fecha(fecha)
        print(f"Recopilacion completa: {nuevos} partido(s) nuevo(s).")
    except Exception as e:
        print(f"[ERROR] Fallo la recopilacion: {e}")


def paso_predecir(fecha):
    import predict
    print(f"\n{'='*50}")
    print(f"PASO 2: Prediciendo partidos futuros")
    print(f"{'='*50}")
    try:
        predicciones = predict.predecir_fecha(fecha)
        print(f"Prediccion completa: {len(predicciones)} partido(s).")
    except Exception as e:
        print(f"[ERROR] Fallo la prediccion: {e}")


def paso_dashboard():
    import generar_dashboard
    print(f"\n{'='*50}")
    print(f"PASO 3: Generando dashboard HTML")
    print(f"{'='*50}")
    try:
        resultado = generar_dashboard.generar()
        if resultado:
            print(f"Dashboard generado: {resultado}")
    except Exception as e:
        print(f"[ERROR] Fallo al generar dashboard: {e}")


def main():
    parser = argparse.ArgumentParser(description="Pipeline completo de actualizacion.")
    parser.add_argument("--solo-prediccion", action="store_true",
                        help="Solo predecir + generar dashboard (sin recopilar)")
    parser.add_argument("--solo-dashboard", action="store_true",
                        help="Solo regenerar el HTML del dashboard")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD (por defecto, hoy)")
    args = parser.parse_args()

    fecha = args.fecha or _hoy_ecuador()

    if args.solo_dashboard:
        paso_dashboard()
        return

    if not args.solo_prediccion:
        paso_recopilar(fecha)

    paso_predecir(fecha)
    paso_dashboard()

    print(f"\n{'='*50}")
    print("Pipeline completo.")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
