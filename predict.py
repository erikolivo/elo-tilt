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
import bootstrap_equipos

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"
ARCHIVO_PREDICCIONES_HIST = DATA_DIR / "predicciones_historial.json"

BONUS_LOCALIA = 0.08
ZONA_HORARIA_ECUADOR = datetime.timezone(datetime.timedelta(hours=-5))


def _hoy_ecuador():
    return datetime.datetime.now(ZONA_HORARIA_ECUADOR).date().isoformat()


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
    for i, p in enumerate(partidos):
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


def _calcular_ultimos_5(partidos, team_id):
    if not partidos:
        return {"texto": "N/A", "resultados": []}
    team_id = str(team_id)
    resultados = []
    for p in partidos[:5]:
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
        if gh == ga:
            tipo = "E"
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            tipo = "V"
        else:
            tipo = "D"
        resultados.append(tipo)
    conteo = {"V": 0, "D": 0, "E": 0}
    for r in resultados:
        conteo[r] = conteo.get(r, 0) + 1
    partes = []
    if conteo["V"] > 0:
        partes.append(f"{conteo['V']}V")
    if conteo["D"] > 0:
        partes.append(f"{conteo['D']}D")
    if conteo["E"] > 0:
        partes.append(f"{conteo['E']}E")
    texto = " ".join(partes) if partes else "N/A"
    return {"texto": texto, "resultados": resultados}


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


def _calcular_overperformance(partidos, team_id, rating_actual, rd_actual=None, ratings_data=None):
    if not partidos or not rating_actual:
        return 0.0
    team_id = str(team_id)
    rd_actual = rd_actual or glicko2.RD_INICIAL
    if ratings_data is None:
        ratings_data = ratings_store._cargar()
    equipos_ratings = ratings_data.get("equipos", {})
    scores = []
    for p in partidos:
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = str(p.get("equipo_local", {}).get("id", "")) == team_id
        rival_id = str(p.get("equipo_visitante", {}).get("id", "")) if es_local else str(p.get("equipo_local", {}).get("id", ""))
        rival_key = f"espn:{rival_id}"
        rival_eq = equipos_ratings.get(rival_key, {})
        rating_rival = rival_eq.get("rating", glicko2.RATING_BASE)
        rd_rival = rival_eq.get("rd", glicko2.RD_INICIAL)
        prob_esperada = glicko2.probabilidad_victoria(rating_actual, rd_actual, rating_rival, rd_rival)
        if gh == ga:
            resultado_real = 0.5
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            resultado_real = 1.0
        else:
            resultado_real = 0.0
        scores.append((resultado_real - prob_esperada) * 100)
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def _ajustar_por_localia(pl, pe, pv, es_neutral=False):
    if es_neutral:
        # Sede neutral (ESPN neutralSite): no hay ventaja de local real.
        return (pl, pe, pv)
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


UMBRAL_PJ_OVERPERFORMANCE = 7
UMBRAL_SIGNIFICANCIA_OP = 10
PESO_MAXIMO_AJUSTE_OP = 0.02
ACTIVAR_AJUSTE_OVERPERFORMANCE = True


def _ajustar_por_overperformance(pl, pe, pv, op_h, op_a, pj_h, pj_a):
    """Ajusta la probabilidad según qué tan por encima/debajo de lo
    esperado (según su propio ELO) viene rindiendo cada equipo, solo
    cuando hay suficiente muestra (PJ >= UMBRAL_PJ_OVERPERFORMANCE) y
    el valor no es marginal (|op| > UMBRAL_SIGNIFICANCIA_OP). Un
    equipo que no cumple cualquiera de las dos condiciones se trata
    como neutro (0) para este ajuste puntual."""
    if not ACTIVAR_AJUSTE_OVERPERFORMANCE:
        return (pl, pe, pv)

    op_h_efectivo = op_h if (pj_h >= UMBRAL_PJ_OVERPERFORMANCE and abs(op_h) > UMBRAL_SIGNIFICANCIA_OP) else 0.0
    op_a_efectivo = op_a if (pj_a >= UMBRAL_PJ_OVERPERFORMANCE and abs(op_a) > UMBRAL_SIGNIFICANCIA_OP) else 0.0

    diff_op = op_h_efectivo - op_a_efectivo
    adj = max(-PESO_MAXIMO_AJUSTE_OP, min(PESO_MAXIMO_AJUSTE_OP, diff_op * 0.001))

    pl += adj
    pv -= adj
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


EMPATE_BASE_MAXIMO = 25.0   # % de empate cuando los equipos estan parejos (diff ~ 0)
EMPATE_BASE_MINIMO = 12.0   # % de empate piso, para partidos muy desparejos
EMPATE_DECAY = 40.0         # cuantos puntos de diff ELO equivalen a 1 punto menos de empate


def _prob_empate_base(diff_elo):
    """Probabilidad base de empate (antes de los demas ajustes),
    decreciendo linealmente con la diferencia de ELO entre los dos
    equipos, con un piso para no llegar a valores irreales.
    Devuelve un PORCENTAJE (0-100): diff=0 -> 25, diff=400 -> 15, diff>=520 -> 12."""
    valor = EMPATE_BASE_MAXIMO - abs(diff_elo) / EMPATE_DECAY
    return max(EMPATE_BASE_MINIMO, valor)


MESES_H2H = 24
MIN_PARTIDOS_H2H = 2
PESO_MAXIMO_AJUSTE_H2H = 0.015  # tope conservador, mas chico que overperformance (0.02)


def _historial_h2h(team_h_id, team_a_id):
    """Busca enfrentamientos directos previos entre estos dos equipos
    especificos (en cualquier orden de local/visitante) en los ultimos
    MESES_H2H meses. Devuelve (n_partidos, resultado_promedio_h) donde
    resultado_promedio_h es el promedio de resultado (1.0/0.5/0.0) desde
    la perspectiva de team_h_id, o (0, None) si no hay suficientes."""
    team_h_id, team_a_id = str(team_h_id), str(team_a_id)
    hoy = datetime.date.today()
    resultados = []

    for i in range(MESES_H2H):
        fecha_mes = (hoy.replace(day=1) - datetime.timedelta(days=30 * i))
        fecha_iso = fecha_mes.isoformat()
        datos = historial_store._cargar_mes(fecha_iso)
        for p in datos.get("partidos", []):
            h_id = str(p.get("equipo_local", {}).get("id", ""))
            a_id = str(p.get("equipo_visitante", {}).get("id", ""))
            ids_partido = {h_id, a_id}
            if ids_partido != {team_h_id, team_a_id}:
                continue
            gl, ga = p.get("goles_local"), p.get("goles_visitante")
            if gl is None or ga is None:
                continue
            team_h_era_local = (h_id == team_h_id)
            if gl == ga:
                resultados.append(0.5)
            elif (gl > ga) == team_h_era_local:
                resultados.append(1.0)
            else:
                resultados.append(0.0)

    if len(resultados) < MIN_PARTIDOS_H2H:
        return (len(resultados), None)
    return (len(resultados), sum(resultados) / len(resultados))


def _ajustar_por_h2h(pl, pe, pv, team_h_id, team_a_id):
    n, promedio = _historial_h2h(team_h_id, team_a_id)
    if promedio is None:
        return (pl, pe, pv)
    # promedio > 0.5 -> el equipo local de HOY historicamente le gana a este rival
    # promedio < 0.5 -> historicamente le cuesta contra este rival especifico
    desviacion = promedio - 0.5  # rango -0.5 a +0.5
    adj = desviacion * 2 * PESO_MAXIMO_AJUSTE_H2H  # escala al tope conservador
    pl += adj
    pv -= adj
    t = pl + pe + pv
    return (pl / t, pe / t, pv / t)


def predecir_partido(fx, tilt_home, tilt_away):
    rating_h = tilt_home["rating"]
    rating_a = tilt_away["rating"]
    rd_h = tilt_home["rd"]
    rd_a = tilt_away["rd"]
    diff_elo = rating_h - rating_a

    prob_base = glicko2.probabilidad_victoria(rating_h, rd_h, rating_a, rd_a)
    # _prob_empate_base devuelve % (0-100); aca se trabaja con fracciones.
    prob_empate_base = _prob_empate_base(diff_elo) / 100.0
    prob_local = prob_base
    prob_visitante = 1.0 - prob_base - prob_empate_base
    prob_empate = prob_empate_base

    es_neutral = fx.get("_neutral", False)
    prob_local, prob_empate, prob_visitante = _ajustar_por_localia(prob_local, prob_empate, prob_visitante, es_neutral=es_neutral)
    prob_local, prob_empate, prob_visitante = _ajustar_por_forma(prob_local, prob_empate, prob_visitante, tilt_home["form_score"], tilt_away["form_score"])
    prob_local, prob_empate, prob_visitante = _ajustar_por_momentum(prob_local, prob_empate, prob_visitante, tilt_home["momentum"]["direccion"], tilt_away["momentum"]["direccion"])
    prob_local, prob_empate, prob_visitante = _ajustar_por_home_away(prob_local, prob_empate, prob_visitante, tilt_home["home_away"], tilt_away["home_away"])
    prob_local, prob_empate, prob_visitante = _ajustar_por_overperformance(
        prob_local, prob_empate, prob_visitante,
        tilt_home.get("overperformance", 0), tilt_away.get("overperformance", 0),
        tilt_home.get("partidos_jugados", 0), tilt_away.get("partidos_jugados", 0),
    )
    prob_local, prob_empate, prob_visitante = _ajustar_por_h2h(
        prob_local, prob_empate, prob_visitante,
        fx["teams"]["home"]["id"], fx["teams"]["away"]["id"],
    )

    prob_local = max(0.01, min(0.99, prob_local))
    prob_empate = max(0.01, min(0.99, prob_empate))
    prob_visitante = max(0.01, min(0.99, prob_visitante))
    total = prob_local + prob_empate + prob_visitante
    prob_local, prob_empate, prob_visitante = prob_local / total, prob_empate / total, prob_visitante / total

    confianza = min(abs(diff_elo) / 200, 1.0) * 100

    fecha_raw = fx["fixture"].get("date", "")
    fecha_ec = _hora_ecuador(fecha_raw)
    hora_ec = _hora_display(fecha_ec)
    liga_slug = fx.get("_liga_slug", "")
    liga_nombre = ligas_nombres.nombre_liga(liga_slug, fx["league"].get("name", ""))
    pais_liga = ligas_nombres.pais_por_slug(liga_slug)

    return {
        "fixture_id": fx["fixture"]["id"],
        "fecha": fecha_ec or fecha_raw,
        "fecha_display": fecha_ec[:10] if fecha_ec else "",
        "hora": hora_ec,
        "liga": liga_nombre,
        "liga_pais": fx["league"].get("country", "") or pais_liga,
        "liga_slug": liga_slug,
        "equipo_local": {
            "id": fx["teams"]["home"]["id"],
            "nombre": fx["teams"]["home"]["name"],
            "pais": pais_liga,
            "rating": rating_h, "rd": rd_h,
            "partidos_jugados": tilt_home["partidos_jugados"],
            "pj_reales": tilt_home.get("pj_reales", tilt_home["partidos_jugados"]),
            "form_score": tilt_home["form_score"],
            "form_local": tilt_home["home_away"]["form_local"],
            "form_visitante": tilt_home["home_away"]["form_visitante"],
            "momentum": tilt_home["momentum"]["direccion"],
            "momentum_diff": tilt_home["momentum"]["diferencia"],
            "streak": tilt_home["streak"],
            "ultimos5": tilt_home["ultimos5"],
            "goal_trend": tilt_home["goal_trend"],
            "field_tilt": tilt_home["field_tilt"],
            "overperformance": tilt_home["overperformance"],
            "vol": tilt_home.get("vol", glicko2.VOL_INICIAL),
        },
        "equipo_visitante": {
            "id": fx["teams"]["away"]["id"],
            "nombre": fx["teams"]["away"]["name"],
            "pais": pais_liga,
            "rating": rating_a, "rd": rd_a,
            "partidos_jugados": tilt_away["partidos_jugados"],
            "pj_reales": tilt_away.get("pj_reales", tilt_away["partidos_jugados"]),
            "form_score": tilt_away["form_score"],
            "form_local": tilt_away["home_away"]["form_local"],
            "form_visitante": tilt_away["home_away"]["form_visitante"],
            "momentum": tilt_away["momentum"]["direccion"],
            "momentum_diff": tilt_away["momentum"]["diferencia"],
            "streak": tilt_away["streak"],
            "ultimos5": tilt_away["ultimos5"],
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


def _fusionar_con_anteriores(predicciones_nuevas, fecha_iso):
    """Combina las predicciones recien calculadas (solo fixtures 'pre'
    en este momento) con las que ya estaban guardadas para ese mismo
    dia. Un partido que ya empezo o termino deja de venir de
    obtener_fixtures_futuros (que solo trae 'pre'), pero su prediccion
    ORIGINAL (calculada cuando todavia era 'pre') se preserva -- no
    tiene sentido recalcularla con datos de forma/momentum que ya
    cambiaron a mitad de un partido en curso."""
    archivo_fecha = DATA_DIR / f"predicciones_{fecha_iso}.json"
    anteriores = []
    if archivo_fecha.exists():
        try:
            anteriores = json.loads(archivo_fecha.read_text(encoding="utf-8")).get("predicciones", [])
        except Exception:
            anteriores = []

    fids_nuevos = {p.get("fixture_id") for p in predicciones_nuevas if p.get("fixture_id")}
    preservados = [p for p in anteriores if p.get("fixture_id") not in fids_nuevos]

    fusionadas = predicciones_nuevas + preservados
    fusionadas.sort(key=lambda x: x.get("fecha", ""))
    return fusionadas


def predecir_fecha(fecha_iso, ligas=None):
    fixtures = fetch_data.obtener_fixtures_futuros(fecha_iso, ligas=ligas)
    if not fixtures:
        print(f"No se encontraron fixtures futuros para {fecha_iso}")
        return []

    # obtener_fixtures_futuros trae fecha_iso + 2 dias mas (ventana UTC a
    # proposito, para cubrir findes). Aqui nos quedamos SOLO con los que,
    # en hora de Ecuador, caen exactamente en fecha_iso -- si no, un
    # partido de las 8pm Ecuador (1am UTC del dia siguiente) se cuela en
    # el dia equivocado.
    fixtures = [
        fx for fx in fixtures
        if (_hora_ecuador(fx["fixture"].get("date", "")) or "")[:10] == fecha_iso
    ]
    if not fixtures:
        print(f"No se encontraron fixtures para {fecha_iso} (tras filtrar por hora de Ecuador)")
        return []

    ratings_data = ratings_store._cargar()
    equipos_ratings = ratings_data.get("equipos", {})

    predicciones = []
    for fx in fixtures:
        home_id = str(fx["teams"]["home"]["id"])
        away_id = str(fx["teams"]["away"]["id"])
        home_name = fx["teams"]["home"]["name"]
        away_name = fx["teams"]["away"]["name"]
        liga_slug_fx = fx.get("_liga_slug", "")

        # Tarea 2: resolver alias/fuzzy en el LADO DE LECTURA también
        # (para no leer un registro "nuevo en 1500" cuando ya existe uno
        # con nombre muy similar bajo otro ID).
        home_llave = ratings_store.resolver_llave(f"espn:{home_id}", nombre=home_name, equipos=equipos_ratings)
        away_llave = ratings_store.resolver_llave(f"espn:{away_id}", nombre=away_name, equipos=equipos_ratings)

        # Tarea 3: bootstrap automático para equipos con pocos partidos
        # (PJ < 4, o aún no en ratings) — reset+replay con historial de ESPN.
        bootstrap_equipos.bootstrap_si_hace_falta(
            home_llave, home_id, home_name, liga_slug_fx, equipos_ratings)
        bootstrap_equipos.bootstrap_si_hace_falta(
            away_llave, away_id, away_name, liga_slug_fx, equipos_ratings)

        home_eq = equipos_ratings.get(home_llave, {})
        away_eq = equipos_ratings.get(away_llave, {})

        rating_h = home_eq.get("rating", glicko2.RATING_BASE)
        rating_a = away_eq.get("rating", glicko2.RATING_BASE)
        rd_h = home_eq.get("rd", glicko2.RD_INICIAL)
        rd_a = away_eq.get("rd", glicko2.RD_INICIAL)
        pj_h = home_eq.get("partidos_jugados", 0)
        pj_a = away_eq.get("partidos_jugados", 0)
        pj_h_real = home_eq.get("pj_reales", pj_h)
        pj_a_real = away_eq.get("pj_reales", pj_a)

        hist_h = _obtener_historial(home_id)
        hist_a = _obtener_historial(away_id)

        form_h = _calcular_forma(hist_h, home_id)
        form_a = _calcular_forma(hist_a, away_id)
        streak_h = _calcular_streak(hist_h, home_id)
        streak_a = _calcular_streak(hist_a, away_id)
        ultimos5_h = _calcular_ultimos_5(hist_h, home_id)
        ultimos5_a = _calcular_ultimos_5(hist_a, away_id)
        mom_h = _calcular_momentum(hist_h, home_id)
        mom_a = _calcular_momentum(hist_a, away_id)
        gt_h = _calcular_goal_trend(hist_h, home_id)
        gt_a = _calcular_goal_trend(hist_a, away_id)
        ha_h = _calcular_home_away(hist_h, home_id)
        ha_a = _calcular_home_away(hist_a, away_id)
        op_h = _calcular_overperformance(hist_h, home_id, rating_h, rd_h, ratings_data)
        op_a = _calcular_overperformance(hist_a, away_id, rating_a, rd_a, ratings_data)

        tilt_home = {
            "rating": rating_h, "rd": rd_h, "partidos_jugados": pj_h, "pj_reales": pj_h_real,
            "form_score": form_h, "streak": streak_h, "ultimos5": ultimos5_h,
            "momentum": mom_h, "goal_trend": gt_h, "home_away": ha_h,
            "overperformance": op_h, "field_tilt": {"overall": 50.0},
        }
        tilt_away = {
            "rating": rating_a, "rd": rd_a, "partidos_jugados": pj_a, "pj_reales": pj_a_real,
            "form_score": form_a, "streak": streak_a, "ultimos5": ultimos5_a,
            "momentum": mom_a, "goal_trend": gt_a, "home_away": ha_a,
            "overperformance": op_a, "field_tilt": {"overall": 50.0},
        }

        try:
            pred = predecir_partido(fx, tilt_home, tilt_away)
            predicciones.append(pred)
        except Exception as e:
            print(f"[AVISO] Error prediciendo {fx['teams']['home']['name']} vs {fx['teams']['away']['name']}: {e}")

    predicciones.sort(key=lambda x: x.get("fecha", ""))

    # NUEVO: fusionar con lo que ya estaba guardado para este mismo dia,
    # para no perder partidos que ya empezaron/terminaron y por eso
    # dejaron de venir en 'predicciones' (ver _fusionar_con_anteriores).
    predicciones_finales = _fusionar_con_anteriores(predicciones, fecha_iso)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cache = {
        "generado": datetime.datetime.utcnow().isoformat() + "Z",
        "fecha_consulta": fecha_iso,
        "total": len(predicciones_finales),
        "predicciones": predicciones_finales,
    }

    # El cache FIJO (predicciones_cache.json, el que lee la pestana Hoy
    # por defecto) solo se sobrescribe si fecha_iso es HOY en Ecuador.
    # Si predict.py corre para otra fecha (ej. manana), no debe tocar el
    # archivo que usa Hoy.
    if fecha_iso == _hoy_ecuador():
        ARCHIVO_PREDICCIONES.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # Ademas del cache fijo, guardar una copia por fecha para que la
    # pestana Manana (y generar_dashboard.py --fecha) puedan leer
    # predicciones de un dia especifico, no solo "hoy".
    archivo_por_fecha = DATA_DIR / f"predicciones_{fecha_iso}.json"
    archivo_por_fecha.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # Guardar predicciones en historial indexadas por fixture_id para uso futuro (Opcion B - Acierto real)
    hist = {}
    if ARCHIVO_PREDICCIONES_HIST.exists():
        try:
            hist = json.loads(ARCHIVO_PREDICCIONES_HIST.read_text(encoding="utf-8"))
        except Exception:
            hist = {}
    for pred in predicciones_finales:
        fid = pred.get("fixture_id", "")
        if fid:
            hist[fid] = {
                "fecha": pred.get("fecha", ""),
                "prob_local": pred["prediccion"]["prob_local"],
                "prob_empate": pred["prediccion"]["prob_empate"],
                "prob_visitante": pred["prediccion"]["prob_visitante"],
                "diff_elo": pred.get("diff_elo", 0),
                "pj_h": pred["equipo_local"].get("partidos_jugados", 0),
                "pj_a": pred["equipo_visitante"].get("partidos_jugados", 0),
                "rating_local": pred["equipo_local"].get("rating", 0),
                "rating_visitante": pred["equipo_visitante"].get("rating", 0),
                "overperformance_h": pred["equipo_local"].get("overperformance", 0),
                "overperformance_a": pred["equipo_visitante"].get("overperformance", 0),
            }
    ARCHIVO_PREDICCIONES_HIST.write_text(json.dumps(hist, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{len(predicciones_finales)} prediccion(es) totales para {fecha_iso} "
          f"({len(predicciones)} nueva(s)/actualizada(s), {len(predicciones_finales) - len(predicciones)} preservada(s)).")
    for pred in predicciones_finales[:5]:
        h = pred["equipo_local"]
        a = pred["equipo_visitante"]
        p = pred["prediccion"]
        print(f"  {h['nombre']} ({h['rating']:.0f}, F:{h['form_score']:.0f}) vs {a['nombre']} ({a['rating']:.0f}, F:{a['form_score']:.0f}): {p['prob_local']:.0f}% - {p['prob_empate']:.0f}% - {p['prob_visitante']:.0f}%")

    return predicciones_finales


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predice partidos a jugarse usando ELO + tilt.")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD (por defecto, hoy)")
    args = parser.parse_args()
    fecha = args.fecha or _hoy_ecuador()
    predecir_fecha(fecha)
