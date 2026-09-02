"""
form_calculator.py
------------------
Calcula indicadores de forma/momentum (tilt) para cada equipo
basandose en su historial reciente de partidos.

Indicadores:
  1. Form Score (0-100): rendimiento ponderado ultimos N partidos
  2. Momentum Direction: si la forma esta subiendo/bajando/estable
  3. Streak: racha actual (victorias/empates/derrotas consecutivos)
  4. Goal Trend: promedio de goles a favor/en contra reciente
  5. Home/away split: forma separada local/visitante
  6. Field tilt: control territorial (desde boxscore si disponible)
  7. Overperformance index: resultado real vs esperado por ELO
"""

import math
import json
from pathlib import Path

import glicko2
import ratings_store
import historial_store

VENTANA_FORMA = 5
VENTANA_MOMENTUM = 3
DECAY_FACTOR = 0.5


def _obtener_partidos_equipo(team_id, n=10):
    """
    Obtiene los ultimos n partidos de un equipo desde el historial
    mensual. Recorre los archivos de los ultimos meses hasta
    completar la ventana o agotar el historial.
    """
    import datetime
    partidos = []
    hoy = datetime.date.today()

    for offset in range(12):
        fecha_mes = hoy - datetime.timedelta(days=30 * offset)
        fecha_iso = fecha_mes.isoformat()
        datos = historial_store._cargar_mes(fecha_iso)

        for p in datos.get("partidos", []):
            home = p.get("equipo_local", {})
            away = p.get("equipo_visitante", {})
            if home.get("id") == team_id or away.get("id") == team_id:
                partidos.append(p)

    partidos.sort(key=lambda x: x.get("fecha", ""), reverse=True)
    return partidos[:n]


def _calcular_form_score(partidos, team_id):
    """
    Form Score con pesos exponenciales.
    El partido mas reciente tiene peso 1, el mas viejo peso e^(-decay * (n-1)).
    Resultado: 1.0 victoria, 0.5 empate, 0.0 derrota.
    Salida: 0-100.
    """
    if not partidos:
        return 50.0

    resultados = []
    for i, p in enumerate(reversed(partidos)):
        home = p.get("equipo_local", {})
        away = p.get("equipo_visitante", {})
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)

        es_local = home.get("id") == team_id

        if gh == ga:
            resultado = 0.5
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            resultado = 1.0
        else:
            resultado = 0.0

        peso = math.exp(-DECAY_FACTOR * i)
        resultados.append((resultado, peso))

    if not resultados:
        return 50.0

    suma_ponderada = sum(r * p for r, p in resultados)
    suma_pesos = sum(p for _, p in resultados)
    return round((suma_ponderada / suma_pesos) * 100, 1)


def _calcular_momentum(form_score_3, form_score_5):
    """
    Compara forma reciente (3 partidos) vs forma amplia (5 partidos).
    Devuelve tupla (direccion, diferencia).
    """
    diff = form_score_3 - form_score_5
    if diff > 5:
        return "up", round(diff, 1)
    elif diff < -5:
        return "down", round(diff, 1)
    return "stable", round(diff, 1)


def _calcular_streak(partidos, team_id):
    """
    Cuenta la racha actual de resultados consecutivos.
    Devuelve tupla (tipo, cantidad): ej ("W", 3), ("D", 1), ("L", 2)
    """
    if not partidos:
        return ("N/A", 0)

    streak_tipo = None
    streak_count = 0

    for p in partidos:
        home = p.get("equipo_local", {})
        away = p.get("equipo_visitante", {})
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = home.get("id") == team_id

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


def _calcular_goal_trend(partidos, team_id):
    """
    Promedio de goles anotados y recibidos en los ultimos partidos.
    Devuelve tupla (gf_promedio, gc_promedio, diferencia).
    """
    if not partidos:
        return (0.0, 0.0, 0.0)

    gf_total = 0
    gc_total = 0
    for p in partidos:
        home = p.get("equipo_local", {})
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = home.get("id") == team_id

        if es_local:
            gf_total += gh
            gc_total += ga
        else:
            gf_total += ga
            gc_total += gh

    n = len(partidos)
    gf_prom = round(gf_total / n, 2)
    gc_prom = round(gc_total / n, 2)
    diff = round(gf_prom - gc_prom, 2)
    return (gf_prom, gc_prom, diff)


def _calcular_home_away_split(partidos, team_id):
    """
    Separa forma en local vs visitante.
    Devuelve dict con forma local, forma visitante, y count de cada uno.
    """
    local_partidos = []
    visitante_partidos = []

    for p in partidos:
        home = p.get("equipo_local", {})
        if home.get("id") == team_id:
            local_partidos.append(p)
        else:
            visitante_partidos.append(p)

    return {
        "form_local": _calcular_form_score(local_partidos, team_id) if local_partidos else 50.0,
        "form_visitante": _calcular_form_score(visitante_partidos, team_id) if visitante_partidos else 50.0,
        "partidos_local": len(local_partidos),
        "partidos_visitante": len(visitante_partidos),
    }


def _calcular_field_tilt(partidos, team_id):
    """
    Control territorial aproximado basado en estadisticas del boxscore.
    Calcula: posesion, tiros, corners como proxy de dominio territorial.
    Solo funciona si el historial tiene estadisticas guardadas.
    """
    stats_acum = {"posesion": [], "tiros": [], "tiros_arco": [], "corners": []}

    for p in partidos:
        estadisticas = p.get("estadisticas")
        if not estadisticas:
            continue

        home = p.get("equipo_local", {})
        es_local = home.get("id") == team_id
        clave_equipo = "home" if es_local else "away"

        eq_stats = estadisticas.get(clave_equipo)
        rival_stats = estadisticas.get("away" if es_local else "home")

        if not eq_stats or not rival_stats:
            continue

        def _parsear(valor):
            if isinstance(valor, str):
                valor = valor.replace("%", "").strip()
            try:
                return float(valor)
            except (TypeError, ValueError):
                return None

        for clave, nombre_stat in [
            ("posesion", "Possession"),
            ("tiros", "Total Shots"),
            ("tiros_arco", "Shots on Goal"),
            ("corners", "Corner Kicks"),
        ]:
            eq_val = _parsear(eq_stats.get(nombre_stat))
            rival_val = _parsear(rival_stats.get(nombre_stat))
            if eq_val is not None and rival_val is not None and (eq_val + rival_val) > 0:
                pct = (eq_val / (eq_val + rival_val)) * 100
                stats_acum[clave].append(pct)

    resultado = {}
    for clave, valores in stats_acum.items():
        if valores:
            resultado[clave] = round(sum(valores) / len(valores), 1)
        else:
            resultado[clave] = 50.0

    if any(v != 50.0 for v in stats_acum.values() if stats_acum[v]):
        all_vals = [v for v in stats_acum.values() if v]
        resultado["overall"] = round(sum(all_vals) / len(all_vals), 1) if all_vals else 50.0
    else:
        resultado["overall"] = 50.0

    return resultado


def _calcular_overperformance(partidos, team_id, rating_actual):
    """
    Compara resultado real vs resultado esperado por ELO.
    Si el equipo gana con ELO menor → sobre-rendimiento positivo.
    Si pierde con ELO mayor → sobre-rendimiento negativo.
    Salida: score promedio (-100 a +100).
    """
    if not partidos or not rating_actual:
        return 0.0

    overperformance_scores = []

    for p in partidos:
        home = p.get("equipo_local", {})
        away = p.get("equipo_visitante", {})
        gh = p.get("goles_local", 0)
        ga = p.get("goles_visitante", 0)
        es_local = home.get("id") == team_id

        rival_id = away.get("id") if es_local else home.get("id")
        rival_llave = ratings_store.llave_equipo(rival_id)
        rival_eq = ratings_store.obtener_o_crear(rival_llave)
        rating_rival = rival_eq.get("rating", glicko2.RATING_BASE)

        diff_elo = rating_actual - rating_rival
        prob_esperada = glicko2.probabilidad_victoria(
            rating_actual, glicko2.RD_INICIAL,
            rating_rival, glicko2.RD_INICIAL
        )

        if gh == ga:
            resultado_real = 0.5
        elif (gh > ga and es_local) or (ga > gh and not es_local):
            resultado_real = 1.0
        else:
            resultado_real = 0.0

        op = (resultado_real - prob_esperada) * 100
        overperformance_scores.append(op)

    if not overperformance_scores:
        return 0.0

    return round(sum(overperformance_scores) / len(overperformance_scores), 1)


def calcular_tilt_completo(team_id, nombre=None, pais=None, liga=None):
    """
    Calcula todos los indicadores de tilt para un equipo.
    Devuelve un dict con todos los indicadores.
    """
    team_id = str(team_id)

    try:
        llave = ratings_store.llave_equipo(team_id, pais=pais, nombre=nombre)
        eq = ratings_store.obtener_o_crear(llave, nombre=nombre, pais=pais, liga=liga)
    except Exception:
        eq = {"rating": glicko2.RATING_BASE, "rd": glicko2.RD_INICIAL, "partidos_jugados": 0}

    try:
        partidos_5 = _obtener_partidos_equipo(team_id, n=VENTANA_FORMA)
    except Exception:
        partidos_5 = []

    partidos_3 = partidos_5[:VENTANA_MOMENTUM]

    form_score = _calcular_form_score(partidos_5, team_id)
    form_score_3 = _calcular_form_score(partidos_3, team_id)
    momentum_dir, momentum_diff = _calcular_momentum(form_score_3, form_score)
    streak_tipo, streak_count = _calcular_streak(partidos_5, team_id)
    gf, gc, goal_diff = _calcular_goal_trend(partidos_5, team_id)
    home_away = _calcular_home_away_split(partidos_5, team_id)
    field_tilt = _calcular_field_tilt(partidos_5, team_id)
    overperf = _calcular_overperformance(partidos_5, team_id, eq.get("rating", glicko2.RATING_BASE))

    return {
        "team_id": team_id,
        "nombre": nombre or eq.get("nombre"),
        "rating": eq.get("rating", glicko2.RATING_BASE),
        "rd": eq.get("rd", glicko2.RD_INICIAL),
        "partidos_jugados": eq.get("partidos_jugados", 0),
        "form_score": form_score,
        "momentum": {
            "direccion": momentum_dir,
            "diferencia": momentum_diff,
        },
        "streak": {
            "tipo": streak_tipo,
            "cantidad": streak_count,
        },
        "goal_trend": {
            "goles_favor": gf,
            "goles_contra": gc,
            "diferencia": goal_diff,
        },
        "home_away": home_away,
        "field_tilt": field_tilt,
        "overperformance": overperf,
    }


def tiltear_multiples(equipos_info):
    """
    Calcula tilt para multiples equipos de una vez.
    'equipos_info' es una lista de dicts con keys: team_id, nombre, pais, liga.
    Devuelve dict mapeando team_id -> tilt_info.
    """
    resultados = {}
    for eq in equipos_info:
        tid = eq.get("team_id")
        if tid:
            tid = str(tid)
            try:
                resultados[tid] = calcular_tilt_completo(
                    tid, nombre=eq.get("nombre"),
                    pais=eq.get("pais"), liga=eq.get("liga")
                )
            except Exception as e:
                print(f"[AVISO] Error calculando tilt para {tid}: {e}")
                resultados[tid] = {
                    "team_id": tid, "nombre": eq.get("nombre"),
                    "rating": glicko2.RATING_BASE, "rd": glicko2.RD_INICIAL,
                    "partidos_jugados": 0, "form_score": 50.0,
                    "momentum": {"direccion": "stable", "diferencia": 0.0},
                    "streak": {"tipo": "N/A", "cantidad": 0},
                    "goal_trend": {"goles_favor": 0.0, "goles_contra": 0.0, "diferencia": 0.0},
                    "home_away": {"form_local": 50.0, "form_visitante": 50.0, "partidos_local": 0, "partidos_visitante": 0},
                    "field_tilt": {"posesion": 50.0, "tiros": 50.0, "overall": 50.0},
                    "overperformance": 0.0,
                }
    return resultados
