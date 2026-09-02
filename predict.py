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

    prob_local = max(0.01, min(0.99, prob_local))
    prob_empate = max(0.01, min(0.99, prob_empate))
    prob_visitante = max(0.01, min(0.99, prob_visitante))
    total = prob_local + prob_empate + prob_visitante
    prob_local, prob_empate, prob_visitante = prob_local/total, prob_empate/total, prob_visitante/total

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

    import ratings_store
    import historial_store
    import datetime

    ratings_data = ratings_store._cargar()
    equipos_ratings = ratings_data.get("equipos", {})

    def _obtener_historial_rapido(team_id):
        team_id = str(team_id)
        partidos = []
        hoy = datetime.date.today()
        for offset in range(6):
            fecha_mes = hoy - datetime.timedelta(days=30 * offset)
            fecha_iso_mes = fecha_mes.isoformat()
            datos = historial_store._cargar_mes(fecha_iso_mes)
            for p in datos.get("partidos", []):
                home = p.get("equipo_local", {})
                away = p.get("equipo_visitante", {})
                if str(home.get("id", "")) == team_id or str(away.get("id", "")) == team_id:
                    partidos.append(p)
        partidos.sort(key=lambda x: x.get("fecha", ""), reverse=True)
        return partidos[:10]

    def _calcular_forma_rapida(partidos, team_id):
        if not partidos:
            return 50.0
        import math
        team_id = str(team_id)
        resultados = []
        for i, p in enumerate(reversed(partidos)):
            home = p.get("equipo_local", {})
            gh = p.get("goles_local", 0)
            ga = p.get("goles_visitante", 0)
            es_local = str(home.get("id", "")) == team_id
            if gh == ga:
                r = 0.5
            elif (gh > ga and es_local) or (ga > gh and not es_local):
                r = 1.0
            else:
                r = 0.0
            peso = math.exp(-0.5 * i)
            resultados.append((r, peso))
        return round(sum(r * p for r, p in resultados) / sum(p for _, p in resultados) * 100, 1)

    def _calcular_streak_rapido(partidos, team_id):
        if not partidos:
            return ("N/A", 0)
        team_id = str(team_id)
        streak_tipo = None
        streak_count = 0
        for p in partidos:
            home = p.get("equipo_local", {})
            gh = p.get("goles_local", 0)
            ga = p.get("goles_visitante", 0)
            es_local = str(home.get("id", "")) == team_id
            if gh == ga:
                tipo = "D"
            elif (gh > ga and es_local) or (ga > gh and not es_local):
                tipo = "W"
            else:
                tipo = "L"
            if streak_tipo is None:
                streak_tipo = tipo
                streak_count = 1
            elif tipo == streak_tipo:
                streak_count += 1
            else:
                break
        return (streak_tipo, streak_count)

    def _calcular_momentum_rapido(partidos, team_id):
        if len(partidos) < 5:
            return "stable"
        form_5 = _calcular_forma_rapida(partidos[:5], team_id)
        form_10 = _calcular_forma_rapida(partidos[:10], team_id)
        diff = form_5 - form_10
        if diff > 5:
            return "up"
        elif diff < -5:
            return "down"
        return "stable"

    predicciones = []
    for fx in fixtures:
        home_id = str(fx["teams"]["home"]["id"])
        away_id = str(fx["teams"]["away"]["id"])

        home_key = f"espn:{home_id}"
        away_key = f"espn:{away_id}"

        home_eq = equipos_ratings.get(home_key, {})
        away_eq = equipos_ratings.get(away_key, {})

        rating_h = home_eq.get("rating", glicko2.RATING_BASE)
        rating_a = away_eq.get("rating", glicko2.RATING_BASE)
        rd_h = home_eq.get("rd", glicko2.RD_INICIAL)
        rd_a = away_eq.get("rd", glicko2.RD_INICIAL)
        partidos_h = home_eq.get("partidos_jugados", 0)
        partidos_a = away_eq.get("partidos_jugados", 0)

        hist_h = _obtener_historial_rapido(home_id)
        hist_a = _obtener_historial_rapido(away_id)

        form_h = _calcular_forma_rapida(hist_h, home_id)
        form_a = _calcular_forma_rapida(hist_a, away_id)
        streak_h_tipo, streak_h_cant = _calcular_streak_rapido(hist_h, home_id)
        streak_a_tipo, streak_a_cant = _calcular_streak_rapido(hist_a, away_id)
        mom_h = _calcular_momentum_rapido(hist_h, home_id)
        mom_a = _calcular_momentum_rapido(hist_a, away_id)

        tilt_home = {
            "team_id": home_id, "nombre": fx["teams"]["home"]["name"],
            "rating": rating_h, "rd": rd_h, "partidos_jugados": partidos_h,
            "form_score": form_h, "momentum": {"direccion": mom_h, "diferencia": 0.0},
            "streak": {"tipo": streak_h_tipo, "cantidad": streak_h_cant},
            "goal_trend": {"goles_favor": 0.0, "goles_contra": 0.0, "diferencia": 0.0},
            "home_away": {"form_local": form_h, "form_visitante": form_h, "partidos_local": 0, "partidos_visitante": 0},
            "field_tilt": {"overall": 50.0}, "overperformance": 0.0,
        }
        tilt_away = {
            "team_id": away_id, "nombre": fx["teams"]["away"]["name"],
            "rating": rating_a, "rd": rd_a, "partidos_jugados": partidos_a,
            "form_score": form_a, "momentum": {"direccion": mom_a, "diferencia": 0.0},
            "streak": {"tipo": streak_a_tipo, "cantidad": streak_a_cant},
            "goal_trend": {"goles_favor": 0.0, "goles_contra": 0.0, "diferencia": 0.0},
            "home_away": {"form_local": form_a, "form_visitante": form_a, "partidos_local": 0, "partidos_visitante": 0},
            "field_tilt": {"overall": 50.0}, "overperformance": 0.0,
        }

        try:
            pred = predecir_partido(fx, tilt_home, tilt_away)
            predicciones.append(pred)
        except Exception as e:
            print(f"[AVISO] Error prediciendo {fx['teams']['home']['name']} vs {fx['teams']['away']['name']}: {e}")

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
