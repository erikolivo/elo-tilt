"""
recopilar_dia.py
-----------------
Script principal (corre cada noche y cada tarde via GitHub Actions,
ver .github/workflows/). Para una fecha dada (por defecto, hoy en
hora de Ecuador):

  1. Consulta ESPN (marcador global + ligas curadas) via fetch_data.
  2. Se queda solo con los partidos ya TERMINADOS ("post").
  3. Salta los que ya estaban guardados de una corrida anterior (dedupe
     por fixture_id, ver historial_store.py -- por eso es seguro que
     este script corra dos veces al dia, o se reintente si falla).
  4. Guarda cada partido nuevo en el historial mensual particionado.
  5. Alimenta el rating Glicko-2 propio de ambos equipos.

Es IDEMPOTENTE: correrlo varias veces sobre la misma fecha nunca
duplica un partido ni alimenta el rating dos veces por el mismo
resultado.

Uso:
    python recopilar_dia.py                 # hoy (hora Ecuador)
    python recopilar_dia.py --fecha 2026-08-15
"""

import argparse
import datetime

import fetch_data
import historial_store
import ratings_store

ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hoy_ecuador():
    return datetime.datetime.now(ZONA_HORARIA_ECUADOR).date().isoformat()


def _alimentar_rating(fx, gh, ga):
    if gh > ga:
        resultado_local, resultado_visitante = 1.0, 0.0
    elif gh < ga:
        resultado_local, resultado_visitante = 0.0, 1.0
    else:
        resultado_local, resultado_visitante = 0.5, 0.5

    home, away = fx["teams"]["home"], fx["teams"]["away"]
    llave_local = ratings_store.llave_equipo(home["id"], nombre=home.get("name"))
    llave_visitante = ratings_store.llave_equipo(away["id"], nombre=away.get("name"))

    eq_local = ratings_store.obtener_o_crear(
        llave_local, nombre=home.get("name"),
        pais=fx["league"].get("country"), liga=fx["league"].get("name"))
    eq_visitante = ratings_store.obtener_o_crear(
        llave_visitante, nombre=away.get("name"),
        pais=fx["league"].get("country"), liga=fx["league"].get("name"))

    rating_local_antes, rd_local_antes = eq_local["rating"], eq_local["rd"]
    rating_visitante_antes, rd_visitante_antes = eq_visitante["rating"], eq_visitante["rd"]

    fecha_partido = (fx["fixture"].get("date") or "")[:10] or None

    ratings_store.actualizar_tras_partido(
        llave_local, rating_visitante_antes, rd_visitante_antes,
        resultado_local, fecha=fecha_partido)
    ratings_store.actualizar_tras_partido(
        llave_visitante, rating_local_antes, rd_local_antes,
        resultado_visitante, fecha=fecha_partido)


def procesar_fecha(fecha_iso):
    fixtures = fetch_data.obtener_fixtures_por_fecha(fecha_iso)
    ya_guardados = historial_store.fixture_ids_guardados(fecha_iso)

    nuevos, saltados_no_terminados, saltados_duplicados = 0, 0, 0

    for fx in fixtures:
        fid = fx["fixture"]["id"]

        if fid in ya_guardados:
            saltados_duplicados += 1
            continue

        if fx.get("_estado") != "post":
            saltados_no_terminados += 1
            continue

        gh, ga = fx.get("_goles_local"), fx.get("_goles_visitante")
        if gh is None or ga is None:
            continue

        estadisticas = None
        if fx.get("_liga_slug") and fx["_liga_slug"] != "all":
            estadisticas = fetch_data.obtener_boxscore_en_vivo(fx["_liga_slug"], fid)

        registro = {
            "fixture_id": fid,
            "fecha": fecha_iso,
            "fecha_hora_espn": fx["fixture"].get("date"),
            "liga_pais": fx["league"].get("country"),
            "liga_nombre": fx["league"].get("name"),
            "liga_slug": fx.get("_liga_slug"),
            "equipo_local": fx["teams"]["home"],
            "equipo_visitante": fx["teams"]["away"],
            "goles_local": gh,
            "goles_visitante": ga,
            "estadisticas": estadisticas,
        }

        historial_store.guardar_partido(fecha_iso, registro)
        _alimentar_rating(fx, gh, ga)
        ya_guardados.add(fid)
        nuevos += 1

    print(f"[{fecha_iso}] {nuevos} partido(s) nuevo(s) guardado(s) y sumado(s) al rating. "
          f"{saltados_duplicados} ya estaban. {saltados_no_terminados} aun no terminaban.")
    return nuevos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recopila los resultados de ESPN de un dia y alimenta el rating propio.")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD (por defecto, hoy en hora de Ecuador)")
    args = parser.parse_args()

    fecha = args.fecha or _hoy_ecuador()
    procesar_fecha(fecha)
