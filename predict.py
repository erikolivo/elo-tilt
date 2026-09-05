"""
predict.py
----------
Prediccion de partidos a jugarse usando ELO (Glicko-2) + tilt/forma.

Para cada partido futuro:
  1. Obtiene ratings Glicko-2 de ambos equipos
  2. Calcula probabilidad base desde diferencia de ELO
  3. Ajusta por: localia, forma reciente, momentum, home/away
  4. Genera prediccion final con probabilidades

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
import ligas_nombres

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"

PESO_ELO = 0.50
PESO_FORMA = 0.20
PESO_MOMENTUM = 0.10
PESO_HOME_AWAY = 0.10
PESO_LOCALIA = 0.10

BONUS_LOCALIA = 0.08

ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hora_ecuador(fecha_iso):
    """Convierte una fecha ISO (con o sin timezone) a hora Ecuador (UTC-5)."""
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
    """Devuelve hora legible para mostrar en dashboard (HH:MM)."""
    if not fecha_iso:
        return ""
    try:
        if "T" in fecha_iso:
            parte = fecha_iso.split("T")[1][:5]
            return parte
    except Exception:
        pass
    return ""


def _ajustar_por_localia(prob_local, prob_empate, prob_visitante):
    prob_local += BONUS_LOCALIA
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_forma(prob_local, prob_empate, prob_visitante, forma_local, forma_visitante):
    diff_forma = (forma_local - forma_visitante) / 100
    ajuste = diff_forma * 0.05
    prob_local += ajuste
    prob_visitante -= ajuste
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_momentum(prob_local, prob_empate, prob_visitante, mom_local, mom_visitante):
    mapa = {"up": 0.03, "stable": 0.0, "down": -0.03}
    mom_l = mapa.get(mom_local, 0.0)
    mom_v = mapa.get(mom_visitante, 0.0)
    ajuste = mom_l - mom_v
    prob_local += ajuste
    prob_visitante -= ajuste
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _ajustar_por_home_away(prob_local, prob_empate, prob_visitante, ha_local, ha_visitante):
    form_l = ha_local.get("form_local", 50.0) / 100
    form_v = ha_visitante.get("form_visitante", 50.0) / 100
    diff = (form_l - form_v) * 0.03
    prob_local += diff
    prob_visitante -= diff
    total = prob_local + prob_empate + prob_visitante
    return (prob_local / total, prob_empate / total, prob_visitante / total)


def _streak_a_json(streak_tuple):
    tipo, cant = streak_tuple
    return {"tipo": tipo, "cantidad": cant}


def _goal_trend_a_json(gt_tuple):
    gf, gc, diff = gt_tuple
    return {"goles_favor": gf, "goles_contra": gc, "diferencia": diff}


def _field_tilt_a_json(ft_dict):
    return {k: v for k, v in ft_dict.items()}


def _momentum_a_json(mom_tuple):
    direccion, diferencia = mom_tuple
    return {"direccion": direccion, "diferencia": diferencia}


def predecir_partido(fx, tilt_home, tilt_away):
    """
    Genera prediccion para un solo partido.
    Devuelve dict con probabilidades y metadata completa.
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

    fecha_raw = fx["fixture"].get("date", "")
    fecha_ec = _hora_ecuador(fecha_raw)
    hora_ec = _hora_display(fecha_ec)

    liga_slug = fx.get("_liga_slug", "")
    liga_name_espn = fx["league"].get("name", "")
    liga_nombre = ligas_nombres.nombre_liga(liga_slug, liga_name_espn)

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
            "rating": rating_h,
            "rd": rd_h,
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
            "rating": rating_a,
            "rd": rd_a,
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
    """
    Obtiene todos los fixtures futuros de una fecha y genera
    predicciones para cada uno usando form_calculator real.
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
                "team_id": str(t["id"]),
                "nombre": t["name"],
                "pais": fx["league"].get("country"),
                "liga": fx.get("_liga_slug"),
            })

    unique_ids = set()
    equipos_unicos = []
    for eq in equipos_info:
        if eq["team_id"] not in unique_ids:
            unique_ids.add(eq["team_id"])
            equipos_unicos.append(eq)

    print(f"Calculando tilt para {len(equipos_unicos)} equipos (con cache)...")
    tilt_cache = {}
    for eq in equipos_unicos:
        tid = eq["team_id"]
        if tid not in tilt_cache:
            tilt_cache[tid] = form_calculator.calcular_tilt_completo(
                tid, nombre=eq.get("nombre"),
                pais=eq.get("pais"), liga=eq.get("liga")
            )
    print(f"Tilt calculado para {len(tilt_cache)} equipos.")

    predicciones = []
    for fx in fixtures:
        home_id = str(fx["teams"]["home"]["id"])
        away_id = str(fx["teams"]["away"]["id"])

        tilt_home = tilt_cache.get(home_id)
        if tilt_home is None:
            tilt_home = form_calculator.calcular_tilt_completo(
                home_id, nombre=fx["teams"]["home"]["name"])
            tilt_cache[home_id] = tilt_home

        tilt_away = tilt_cache.get(away_id)
        if tilt_away is None:
            tilt_away = form_calculator.calcular_tilt_completo(
                away_id, nombre=fx["teams"]["away"]["name"])
            tilt_cache[away_id] = tilt_away

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
