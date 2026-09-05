"""
predict.py
----------
Prediccion de partidos a jugarse usando ELO (Glicko-2) + tilt/forma.
"""

import argparse
import json
import math
import datetime
from pathlib import Path

import glicko2
import ratings_store
import fetch_data
import historial_store
import ligas_nombres

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"

BONUS_LOCALIA = 0.08
ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hora_ecuador(fecha_iso):
    if not fecha_iso:
        return None
    try:
        if "T" in fecha_iso:
            if fecha_iso.endswith("Z"):
                dt = datetime.datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
            elif "+" in fecha_iso[10:] or "-" in fecha_iso[10:]:
                dt = datetime.datetime.fromisoformat(fecha_iso)
            else:
                dt = datetime.datetime.fromisoformat(fecha_iso + "+00:00")
            dt_ec = dt.astimezone(ZONA_HORARIA_ECUADOR)
            return dt_ec.strftime("%Y-%m-%dT%H:%M:%S-05:00")
        return fecha_iso
    except Exception:
        return fecha_iso


def _hora_display(fecha_iso):
    if not fecha_iso:
        return ""
    try:
        if "T" in fecha_iso:
            return fecha_iso.split("T")[1][:5]
    except Exception:
        pass
    return ""


def _obtener_historial(team_id):
    team_id = str(team_id)
    partidos = []
    hoy = datetime.date.today()
    for offset in range(6):
        fecha_mes = hoy - datetime.timedelta(days=30 * offset)
        datos = historial_store._cargar_mes(fecha_mes.isoformat())
        for p in datos.get("partidos", []):
            home = p.get("equipo_local", {})
            away = p.get("equipo_visitante", {})
            if str(home.get("id", "")) == team_id or str(away.get("id", "")) == team_id:
                partidos.append(p)
    partidos.sort(key=lambda x: x.get("fecha", ""), reverse=True)
    return partidos[:15]


def _calcular_forma(partidos, team_id):
    if not partidos:
        return 50.0
    team_id = str(team_id)
    resultados = []
    for i, p in enumerate(reversed(partidos)):
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
        if gh == ga:
            r = 0.5
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            r = 1.0
        else:
            r = 0.0
        peso = math.exp(-0.5 * i)
        resultados.append((r, peso))
    return round(sum(r * p for r, p in resultados) / sum(p for _, p in resultados) * 100, 1)


def _calcular_streak(partidos, team_id):
    if not partidos:
        return {"tipo": "N/A", "cantidad": 0}
    team_id = str(team_id)
    streak_tipo = None
    streak_count = 0
    for p in partidos:
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
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
    return {"tipo": streak_tipo, "cantidad": streak_count}


def _calcular_momentum(partidos, team_id):
    if len(partidos) < 5:
        return {"direccion": "stable", "diferencia": 0.0}
    form_5 = _calcular_forma(partidos[:5], team_id)
    form_10 = _calcular_forma(partidos[:10], team_id)
    diff = form_5 - form_10
    if diff > 5:
        d = "up"
    elif diff < -5:
        d = "down"
    else:
        d = "stable"
    return {"direccion": d, "diferencia": round(diff, 1)}


def _calcular_goal_trend(partidos, team_id):
    if not partidos:
        return {"goles_favor": 0.0, "goles_contra": 0.0, "diferencia": 0.0}
    team_id = str(team_id)
    gf_total = 0
    gc_total = 0
    for p in partidos:
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
        if es_local:
            gf_total += gh
            gc_total += ga
        else:
            gf_total += ga
            gc_total += gh
    n = len(partidos)
    gf = round(gf_total / n, 2)
    gc = round(gc_total / n, 2)
    return {"goles_favor": gf, "goles_contra": gc, "diferencia": round(gf - gc, 2)}


def _calcular_home_away(partidos, team_id):
    team_id = str(team_id)
    local = []
    visitante = []
    for p in partidos:
        if str(p.get("equipo_local", {}).get("id", "")) == team_id:
            local.append(p)
        else:
            visitante.append(p)
    return {
        "form_local": _calcular_forma(local, team_id) if local else 50.0,
        "form_visitante": _calcular_forma(visitante, team_id) if visitante else 50.0,
        "partidos_local": len(local),
        "partidos_visitante": len(visitante),
    }


def _calcular_overperformance(partidos, team_id, rating_actual):
    if not partidos or not rating_actual:
        return 0.0
    team_id = str(team_id)
    scores = []
    for p in partidos:
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
        rival_id = str(p.get("equipo_visitante", {}).get("id", "")) if es_local else str(p.get("equipo_local", {}).get("id", ""))
        rival_key = f"espn:{rival_id}"
        rival_eq = ratings_store._cargar()["equipos"].get(rival_key, {})
        rating_rival = rival_eq.get("rating", glicko2.RATING_BASE)
        prob_esperada = glicko2.probabilidad_victoria(rating_actual, glicko2.RD_INICIAL, rating_rival, glicko2.RD_INICIAL)
        if gh == ga:
            resultado_real = 0.5
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            resultado_real = 1.0
        else:
            resultado_real = 0.0
        scores.append((resultado_real - prob_esperada) * 100)
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def _ajustar_por_localia(pl, pe, pv):
    pl += BONUS_LOCALIA
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


def _ajustar_por_forma(pl, pe, pv, fl, fv):
    diff = (fl - fv) / 100 * 0.05
    pl += diff
    pv -= diff
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


def _ajustar_por_momentum(pl, pe, pv, ml, mv):
    mapa = {"up": 0.03, "stable": 0.0, "down": -0.03}
    adj = mapa.get(ml, 0.0) - mapa.get(mv, 0.0)
    pl += adj
    pv -= adj
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


def _ajustar_por_home_away(pl, pe, pv, ha_l, ha_v):
    fl = ha_l.get("form_local", 50.0) / 100
    fv = ha_v.get("form_visitante", 50.0) / 100
    diff = (fl - fv) * 0.03
    pl += diff
    pv -= diff
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


def predecir_partido(fx, tilt_home, tilt_away):
    rating_h = tilt_home["rating"]
    rating_a = tilt_away["rating"]
    rd_h = tilt_home["rd"]
    rd_a = tilt_away["rd"]

    prob_base = glicko2.probabilidad_victoria(rating_h, rd_h, rating_a, rd_a)
    prob_empate_base = 0.25
    prob_local = prob_base
    prob_visitante = 1.0 - prob_base - prob_empate_base
    prob_empate = prob_empate_base

    prob_local, prob_empate, prob_visitante = _ajustar_por_localia(prob_local, prob_empate, prob_visitante)
    prob_local, prob_empate, prob_visitante = _ajustar_por_forma(prob_local, prob_empate, prob_visitante, tilt_home["form_score"], tilt_away["form_score"])
    prob_local, prob_empate, prob_visitante = _ajustar_por_momentum(prob_local, prob_empate, prob_visitante, tilt_home["momentum"]["direccion"], tilt_away["momentum"]["direccion"])
    prob_local, prob_empate, prob_visitante = _ajustar_por_home_away(prob_local, prob_empate, prob_visitante, tilt_home["home_away"], tilt_away["home_away"])

    prob_local = max(0.01, min(0.99, prob_local))
    prob_empate = max(0.01, min(0.99, prob_empate))
    prob_visitante = max(0.01, min(0.99, prob_visitante))
    total = prob_local + prob_empate + prob_visitante
    prob_local, prob_empate, prob_visitante = prob_local / total, prob_empate / total, prob_visitante / total

    diff_elo = rating_h - rating_a
    confianza = min(abs(diff_elo) / 200, 1.0) * 100

    fecha_raw = fx["fixture"].get("date", "")
    fecha_ec = _hora_ecuador(fecha_raw)
    hora_ec = _hora_display(fecha_ec)
    liga_slug = fx.get("_liga_slug", "")
    liga_nombre = ligas_nombres.nombre_liga(liga_slug, fx["league"].get("name", ""))

    return {
        "fixture_id": fx["fixture"]["id"],
        "fecha": fecha_ec or fecha_raw,
        "fecha_display": fecha_ec[:10] if fecha_ec else "",
        "hora": hora_ec,
        "liga": liga_nombre,
        "liga_pais": fx["league"].get("country", ""),
        "liga_slug": liga_slug,
        "equipo_local": {
            "id": fx["teams"]["home"]["id"],
            "nombre": fx["teams"]["home"]["name"],
            "rating": rating_h, "rd": rd_h,
            "partidos_jugados": tilt_home["partidos_jugados"],
            "form_score": tilt_home["form_score"],
            "form_local": tilt_home["home_away"]["form_local"],
            "form_visitante": tilt_home["home_away"]["form_visitante"],
            "momentum": tilt_home["momentum"]["direccion"],
            "momentum_diff": tilt_home["momentum"]["diferencia"],
            "streak": tilt_home["streak"],
            "goal_trend": tilt_home["goal_trend"],
            "field_tilt": tilt_home["field_tilt"],
            "overperformance": tilt_home["overperformance"],
            "vol": tilt_home.get("vol", glicko2.VOL_INICIAL),
        },
        "equipo_visitante": {
            "id": fx["teams"]["away"]["id"],
            "nombre": fx["teams"]["away"]["name"],
            "rating": rating_a, "rd": rd_a,
            "partidos_jugados": tilt_away["partidos_jugados"],
            "form_score": tilt_away["form_score"],
            "form_local": tilt_away["home_away"]["form_local"],
            "form_visitante": tilt_away["home_away"]["form_visitante"],
            "momentum": tilt_away["momentum"]["direccion"],
            "momentum_diff": tilt_away["momentum"]["diferencia"],
            "streak": tilt_away["streak"],
            "goal_trend": tilt_away["goal_trend"],
            "field_tilt": tilt_away["field_tilt"],
            "overperformance": tilt_away["overperformance"],
            "vol": tilt_away.get("vol", glicko2.VOL_INICIAL),
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
    fixtures = fetch_data.obtener_fixtures_futuros(fecha_iso, ligas=ligas)
    if not fixtures:
        print(f"No se encontraron fixtures futuros para {fecha_iso}")
        return []

    ratings_data = ratings_store._cargar()
    equipos_ratings = ratings_data.get("equipos", {})

    predicciones = []
    for fx in fixtures:
        home_id = str(fx["teams"]["home"]["id"])
        away_id = str(fx["teams"]["away"]["id"])

        home_eq = equipos_ratings.get(f"espn:{home_id}", {})
        away_eq = equipos_ratings.get(f"espn:{away_id}", {})

        rating_h = home_eq.get("rating", glicko2.RATING_BASE)
        rating_a = away_eq.get("rating", glicko2.RATING_BASE)
        rd_h = home_eq.get("rd", glicko2.RD_INICIAL)
        rd_a = away_eq.get("rd", glicko2.RD_INICIAL)
        pj_h = home_eq.get("partidos_jugados", 0)
        pj_a = away_eq.get("partidos_jugados", 0)

        hist_h = _obtener_historial(home_id)
        hist_a = _obtener_historial(away_id)

        form_h = _calcular_forma(hist_h, home_id)
        form_a = _calcular_forma(hist_a, away_id)
        streak_h = _calcular_streak(hist_h, home_id)
        streak_a = _calcular_streak(hist_a, away_id)
        mom_h = _calcular_momentum(hist_h, home_id)
        mom_a = _calcular_momentum(hist_a, away_id)
        gt_h = _calcular_goal_trend(hist_h, home_id)
        gt_a = _calcular_goal_trend(hist_a, away_id)
        ha_h = _calcular_home_away(hist_h, home_id)
        ha_a = _calcular_home_away(hist_a, away_id)
        op_h = _calcular_overperformance(hist_h, home_id, rating_h)
        op_a = _calcular_overperformance(hist_a, away_id, rating_a)

        tilt_home = {
            "rating": rating_h, "rd": rd_h, "partidos_jugados": pj_h,
            "form_score": form_h, "streak": streak_h, "momentum": mom_h,
            "goal_trend": gt_h, "home_away": ha_h, "overperformance": op_h,
            "field_tilt": {"overall": 50.0},
        }
        tilt_away = {
            "rating": rating_a, "rd": rd_a, "partidos_jugados": pj_a,
            "form_score": form_a, "streak": streak_a, "momentum": mom_a,
            "goal_trend": gt_a, "home_away": ha_a, "overperformance": op_a,
            "field_tilt": {"overall": 50.0},
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
    ARCHIVO_PREDICCIONES.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(predicciones)} prediccione(s) generada(s) para {fecha_iso}.")
    for pred in predicciones[:5]:
        h = pred["equipo_local"]
        a = pred["equipo_visitante"]
        p = pred["prediccion"]
        print(f"  {h['nombre']} ({h['rating']:.0f}, F:{h['form_score']:.0f}) vs {a['nombre']} ({a['rating']:.0f}, F:{a['form_score']:.0f}): {p['prob_local']:.0f}% - {p['prob_empate']:.0f}% - {p['prob_visitante']:.0f}%")

    return predicciones


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predice partidos a jugarse usando ELO + tilt.")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD (por defecto, hoy)")
    args = parser.parse_args()
    fecha = args.fecha or datetime.date.today().isoformat()
    predecir_fecha(fecha)
