"""
predict.py
----------
Prediccion de partidos a jugarse usando ELO (Glicko-2) + tilt/forma.

Para cada partido futuro:
  1. Obtiene ratings Glicko-2 de ambos equipos
  2. Calcula probabilidad base desde diferencia de ELO
  3. Ajusta por: localia, forma reciente, momentum, home/away
  4. Genera predicción final con probabilidades

Uso:
    python predict.py                     # hoy
    python predict.py --fecha 2026-09-06  # fecha especifica
    python predict.py --salida pred.json  # guardar en archivo
"""

import argparse
import json
import datetime
from pathlib import Path

import glicko2
import ratings_store
import fetch_data
import form_calculator

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"

# Pesos para ajuste de prediccion
PESO_ELO = 0.50
PESO_FORMA = 0.20
PESO_MOMENTUM = 0.10
PESO_HOME_AWAY = 0.10
PESO_LOCALIA = 0.10

BONUS_LOCALIA = 0.08


def _ajustar_por_localia(prob_local, prob_empate, prob_visitante):
    """Aplica el factor de localia: +8% al local, redistribuido."""
    prob_local += BONUS_LOCALIA
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_forma(prob_local, prob_empate, prob_visitante, forma_local, forma_visitante):
    """Ajusta segun diferencia de forma. Maximo +/- 5%."""
    diff_forma = (forma_local - forma_visitante) / 100
    ajuste = diff_forma * 0.05

    prob_local += ajuste
    prob_visitante -= ajuste
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_momentum(prob_local, prob_empate, prob_visitante, mom_local, mom_visitante):
    """Ajusta segun momentum direction. Maximo +/- 3%."""
    mapa = {"up": 0.03, "stable": 0.0, "down": -0.03}
    mom_l = mapa.get(mom_local, 0.0)
    mom_v = mapa.get(mom_visitante, 0.0)
    ajuste = mom_l - mom_v

    prob_local += ajuste
    prob_visitante -= ajuste
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_home_away(prob_local, prob_empate, prob_visitante, ha_local, ha_visitante):
    """Ajusta segun rendimiento local/visitante."""
    form_l = ha_local.get("form_local", 50.0) / 100
    form_v = ha_visitante.get("form_visitante", 50.0) / 100
    diff = (form_l - form_v) * 0.03

    prob_local += diff
    prob_visitante -= diff
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def predecir_partido(fx, tilt_home, tilt_away):
    """
    Genera prediccion para un solo partido.
    Devuelve dict con probabilidades y metadata.
    """
    rating_h = tilt_home["rating"]
    rating_a = tilt_away["rating"]
    rd_h = tilt_home["rd"]
    rd_a = tilt_away["rd"]

    prob_base = glicko2.probabilidad_victoria(rating_h, rd_h, rating_a, rd_a)
    prob_empate_base = 0.25

    prob_local = prob_base
    prob_visitante = 1.0 - prob_base - prob_empate_base
    prob_empate = prob_empate_base

    prob_local, prob_empate, prob_visitante = _ajustar_por_localia(
        prob_local, prob_empate, prob_visitante)

    prob_local, prob_empate, prob_visitante = _ajustar_por_forma(
        prob_local, prob_empate, prob_visitante,
        tilt_home["form_score"], tilt_away["form_score"])

    prob_local, prob_empate, prob_visitante = _ajustar_por_momentum(
        prob_local, prob_empate, prob_visitante,
        tilt_home["momentum"]["direccion"], tilt_away["momentum"]["direccion"])

    prob_local, prob_empate, prob_visitante = _ajustar_por_home_away(
        prob_local, prob_empate, prob_visitante,
        tilt_home["home_away"], tilt_away["home_away"])

    diff_elo = rating_h - rating_a
    confianza = min(abs(diff_elo) / 200, 1.0) * 100

    return {
        "fixture_id": fx["fixture"]["id"],
        "fecha": fx["fixture"].get("date", "")[:10],
        "liga": fx["league"].get("name", ""),
        "liga_pais": fx["league"].get("country", ""),
        "liga_slug": fx.get("_liga_slug", ""),
        "equipo_local": {
            "id": fx["teams"]["home"]["id"],
            "nombre": fx["teams"]["home"]["name"],
            "rating": rating_h,
            "form_score": tilt_home["form_score"],
            "momentum": tilt_home["momentum"]["direccion"],
            "streak": tilt_home["streak"],
        },
        "equipo_visitante": {
            "id": fx["teams"]["away"]["id"],
            "nombre": fx["teams"]["away"]["name"],
            "rating": rating_a,
            "form_score": tilt_away["form_score"],
            "momentum": tilt_away["momentum"]["direccion"],
            "streak": tilt_away["streak"],
        },
        "prediccion": {
            "prob_local": round(prob_local * 100, 1),
            "prob_empate": round(prob_empate * 100, 1),
            "prob_visitante": round(prob_visitante * 100, 1),
        },
        "diff_elo": round(diff_elo, 1),
        "confianza": round(confianza, 1),
    }


def predecir_fecha(fecha_iso, ligas=None):
    """
    Obtiene todos los fixtures futuros de una fecha y genera
    predicciones para cada uno.
    """
    fixtures = fetch_data.obtener_fixtures_futuros(fecha_iso, ligas=ligas)

    if not fixtures:
        print(f"No se encontraron fixtures futuros para {fecha_iso}")
        return []

    equipos_info = []
    for fx in fixtures:
        for lado in ["home", "away"]:
            t = fx["teams"][lado]
            equipos_info.append({
                "team_id": t["id"],
                "nombre": t["name"],
                "pais": fx["league"].get("country"),
                "liga": fx["league"].get("name"),
            })

    unique_ids = set()
    equipos_unicos = []
    for eq in equipos_info:
        if eq["team_id"] not in unique_ids:
            unique_ids.add(eq["team_id"])
            equipos_unicos.append(eq)

    print(f"Calculando tilt para {len(equipos_unicos)} equipos...")
    tilt_map = form_calculator.tiltear_multiples(equipos_unicos)

    predicciones = []
    for fx in fixtures:
        home_id = fx["teams"]["home"]["id"]
        away_id = fx["teams"]["away"]["id"]

        tilt_home = tilt_map.get(home_id, form_calculator.calcular_tilt_completo(
            home_id, nombre=fx["teams"]["home"]["name"]))
        tilt_away = tilt_map.get(away_id, form_calculator.calcular_tilt_completo(
            away_id, nombre=fx["teams"]["away"]["name"]))

        pred = predecir_partido(fx, tilt_home, tilt_away)
        predicciones.append(pred)

    predicciones.sort(key=lambda x: (x["liga"], x["fecha"], x["diff_elo"]), reverse=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = {
        "generado": datetime.datetime.utcnow().isoformat() + "Z",
        "fecha_consulta": fecha_iso,
        "total": len(predicciones),
        "predicciones": predicciones,
    }
    ARCHIVO_PREDICCIONES.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(predicciones)} prediccione(s) generada(s) para {fecha_iso}.")
    for pred in predicciones[:10]:
        h = pred["equipo_local"]["nombre"]
        a = pred["equipo_visitante"]["nombre"]
        p = pred["prediccion"]
        print(f"  {h} vs {a}: {p['prob_local']:.0f}% - {p['prob_empate']:.0f}% - {p['prob_visitante']:.0f}%")

    return predicciones


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predice partidos a jugarse usando ELO + tilt.")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD (por defecto, hoy)")
    args = parser.parse_args()

    hoy = datetime.date.today().isoformat()
    fecha = args.fecha or hoy
    predecir_fecha(fecha)
