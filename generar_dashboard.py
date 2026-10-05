"""
generar_dashboard.py
--------------------
Genera el dashboard HTML autocontenido con predicciones y datos completos
de tilt/momentum/estadisticas para partidos a jugarse.

Lee data/predicciones_cache.json y genera dashboard.html.

Uso:
    python generar_dashboard.py
    python generar_dashboard.py --entrada pred.json --salida mi_dashboard.html
"""

import argparse
import json
from pathlib import Path

import fetch_data

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"
ARCHIVO_SALIDA = Path(__file__).parent / "dashboard.html"
DIR_HISTORIAL = DATA_DIR / "historial_partidos"


from datetime import datetime, timezone, timedelta, date

ZONA_ECUADOR = timezone(timedelta(hours=-5))


def _cargar_resultados_fecha(fecha_iso):
    """Devuelve, para cada fixture de 'fecha_iso', su estado ('in'/'post')
    y marcador, consultando ESPN en vivo (no depende de que
    recopilar_dia.py ya lo haya guardado localmente -- por eso el
    marcador de Hoy se actualiza cada regeneracion del dashboard,
    en vez de esperar a la siguiente corrida de recopilar_dia.py)."""
    if not fecha_iso:
        return {}
    try:
        fixtures = fetch_data.obtener_fixtures_por_fecha(fecha_iso)
    except Exception as e:
        print(f"[AVISO] No se pudo consultar ESPN en vivo para {fecha_iso}: {e}")
        fixtures = []

    resultados = {}
    for fx in fixtures:
        estado = fx.get("_estado")
        if estado not in ("in", "post"):
            continue
        gl, ga = fx.get("_goles_local"), fx.get("_goles_visitante")
        if gl is None or ga is None:
            continue
        fixture_id = fx["fixture"]["id"]
        entrada = {"goles_local": gl, "goles_visitante": ga, "estado": estado, "minuto": fx.get("_minuto", "")}
        resultados[f"fx:{fixture_id}"] = entrada
        nombre_l = fx["teams"]["home"]["name"].lower()
        nombre_v = fx["teams"]["away"]["name"].lower()
        resultados[f"{nombre_l}_{nombre_v}"] = entrada

    return resultados


def _clase_forma(score):
    if score is None:
        return "neutral"
    if score >= 70:
        return "high"
    elif score >= 40:
        return "mid"
    return "low"


def _clase_rating(rating):
    if rating is None:
        return "neutral"
    if rating >= 1700:
        return "elite"
    elif rating >= 1550:
        return "above"
    elif rating >= 1400:
        return "average"
    return "below"


def _clase_rd(rd, partidos):
    if partidos is not None and partidos < 10:
        return "provisional"
    if rd is not None and rd > 100:
        return "high-uncertainty"
    return "normal"


def _icono_momentum(direccion):
    if direccion == "up":
        return '<span class="mom-up">▲</span>'
    elif direccion == "down":
        return '<span class="mom-down">▼</span>'
    return '<span class="mom-stable">—</span>'


def _icono_momentum_texto(direccion):
    return {"up": "▲", "down": "▼", "stable": "—"}.get(direccion, "—")


def _clase_momentum(direccion):
    return {"up": "mom-up", "down": "mom-down", "stable": "mom-stable"}.get(direccion, "mom-stable")


def _clase_signo(valor):
    return "op-pos" if valor > 0 else ("op-neg" if valor < 0 else "op-neutral")


def _streak_html(streak):
    if not streak:
        return '<span class="streak-na">—</span>'
    tipo = streak.get("tipo", "N/A")
    cant = streak.get("cantidad", 0)
    if tipo == "W":
        return f'<span class="streak-w">{cant}V</span>'
    elif tipo == "D":
        return f'<span class="streak-d">{cant}E</span>'
    elif tipo == "L":
        return f'<span class="streak-l">{cant}D</span>'
    return '<span class="streak-na">—</span>'


def _ultimos5_html(ultimos5):
    if not ultimos5 or ultimos5.get("texto") == "N/A":
        return '<span class="streak-na">—</span>'
    texto = ultimos5.get("texto", "N/A")
    resultados = ultimos5.get("resultados", [])
    html_parts = []
    for r in resultados:
        if r == "V":
            html_parts.append('<span class="u5-v">V</span>')
        elif r == "D":
            html_parts.append('<span class="u5-d">D</span>')
        elif r == "E":
            html_parts.append('<span class="u5-e">E</span>')
    return f'<span class="ultimos5" title="{texto}">{"".join(html_parts)}</span>'


def _barra_prob(valor, clase):
    return f'<div class="prob-bar prob-{clase}" style="width:{max(valor, 5)}%">{valor:.0f}%</div>'


def _sparkline(form_score, width=50, height=14):
    fill = int(form_score / 100 * width) if form_score else 0
    color = "#22c55e" if form_score and form_score >= 70 else "#eab308" if form_score and form_score >= 40 else "#ef4444"
    return (f'<svg width="{width}" height="{height}" class="spark">'
            f'<rect x="0" y="0" width="{fill}" height="{height}" fill="{color}" rx="2"/>'
            f'<rect x="{fill}" y="0" width="{width - fill}" height="{height}" fill="#1e293b" rx="2"/>'
            f'</svg>')


def _badge_provisional(partidos):
    if partidos is not None and partidos < 10:
        return '<span class="badge-prov" title="Rating provisional (menos de 10 partidos)">PROV</span>'
    return ""


def _goal_trend_bar(gt):
    if not gt:
        return ""
    gf = gt.get("goles_favor", 0)
    gc = gt.get("goles_contra", 0)
    diff = gt.get("diferencia", 0)
    if gf == 0 and gc == 0:
        return ""
    color = "#22c55e" if diff > 0 else "#ef4444" if diff < 0 else "#94a3b8"
    signo = "+" if diff > 0 else ""
    return f'<span class="gt" title="GF: {gf} | GC: {gc}"><span style="color:{color}">{signo}{diff:.1f}</span></span>'


def _overperformance_badge(op):
    if op is None:
        return ""
    signo = "+" if op > 0 else ""
    texto = f"{signo}{op:.0f}"
    if texto in ("+0", "-0", "0"):
        return ""
    color = "#22c55e" if op > 10 else "#ef4444" if op < -10 else "#94a3b8"
    return f'<span class="op-badge" title="Sobre-rendimiento vs ELO esperado" style="color:{color}">{texto}</span>'


# Regla por diferencia de Elo (Glicko-2). Valores calibrados con backtest, no cambiar sin pedirlo.
VENTAJA_LOCAL_ELO = 50       # puntos de Elo que se suman al local por jugar en casa
UMBRAL_FAVORITO_ELO = 200    # |d| mayor a esto -> favorito claro (código simple 1 o 2)
UMBRAL_PAREJO_ELO = 30       # |d| menor o igual a esto -> partido parejo (código 12)


def _codigo_prediccion(diff_elo):
    """Devuelve el código de predicción (1/2/1X/X2/12) a partir de la diferencia
    de Elo (rating_local - rating_visitante).

    d = diff_elo + VENTAJA_LOCAL_ELO
    |d| > UMBRAL_FAVORITO_ELO -> '1' o '2'
    |d| <= UMBRAL_PAREJO_ELO  -> '12'
    en medio                  -> '1X' (d > 0) o 'X2' (d < 0)
    """
    if diff_elo is None:
        return '-'
    d = diff_elo + VENTAJA_LOCAL_ELO
    if abs(d) > UMBRAL_FAVORITO_ELO:
        return '1' if d > 0 else '2'
    if abs(d) <= UMBRAL_PAREJO_ELO:
        return '12'
    return '1X' if d > 0 else 'X2'


def _tooltip_prediccion(diff_elo, prob_l, prob_e, prob_v):
    """Texto del tooltip de la celda de predicción. Explica de dónde sale el
    código (Elo) y muestra las probabilidades del modelo, que pueden no
    coincidir 1 a 1 con el código porque el código NO usa forma/momentum."""
    d = diff_elo + VENTAJA_LOCAL_ELO
    return (f"Código por Elo: dif {diff_elo:+.0f} + {VENTAJA_LOCAL_ELO} local = {d:+.0f} | "
            f"Prob. modelo: {prob_l:.0f}% | {prob_e:.0f}% | {prob_v:.0f}%")


def _acierto_con_codigo(codigo, gl, ga):
    """True/False si el resultado real (gl, ga) está incluido en el
    código de predicción. Devuelve None si faltan datos."""
    if gl is None or ga is None:
        return None
    if gl > ga:
        real = '1'
    elif gl == ga:
        real = 'X'
    else:
        real = '2'
    return real in codigo


def _field_tilt_bar(ft):
    if not ft:
        return ""
    overall = ft.get("overall", 50)
    if overall == 50:
        return ""
    color = "#22c55e" if overall > 60 else "#ef4444" if overall < 40 else "#94a3b8"
    return f'<span class="ft-badge" title="Control territorial" style="color:{color}">{overall:.0f}%</span>'


def _agrupar_por_liga(predicciones):
    ligas = {}
    for p in predicciones:
        liga_key = p.get("liga_slug") or p.get("liga", "Desconocida")
        liga_nombre = p.get("liga", liga_key)
        if liga_key not in ligas:
            ligas[liga_key] = {"nombre": liga_nombre, "partidos": []}
        ligas[liga_key]["partidos"].append(p)
    return ligas


def _es_destacado(p):
    conf = p.get("confianza", 0)
    diff = abs(p.get("diff_elo", 0))
    return conf > 40 or diff > 150


def _es_parejo(p):
    return p.get("confianza", 100) < 20 or abs(p.get("diff_elo", 999)) < 50


def _es_sorpresa_potencial(p):
    local = p.get("equipo_local", {})
    visitante = p.get("equipo_visitante", {})
    mom_l = local.get("momentum", "stable")
    mom_v = visitante.get("momentum", "stable")
    op_l = local.get("overperformance", 0)
    op_v = visitante.get("overperformance", 0)
    if local.get("rating", 0) < visitante.get("rating", 0):
        return mom_l == "up" or op_l > 10
    return mom_v == "up" or op_v > 10


def _score_relevancia(p):
    elo_avg = (p.get("equipo_local", {}).get("rating", 1500) + p.get("equipo_visitante", {}).get("rating", 1500)) / 2
    conf = p.get("confianza", 0)
    elo_norm = min(max((elo_avg - 1200) / 600, 0), 1)
    return elo_norm * 60 + (conf / 100) * 40


def _score_ajuste_forma(p):
    diff_elo = abs(p.get("diff_elo", 0))
    prob_l = p["prediccion"]["prob_local"]
    prob_v = p["prediccion"]["prob_visitante"]
    if prob_l > prob_v:
        favorito_prob = prob_l
    else:
        favorito_prob = prob_v
    return diff_elo * (1 - favorito_prob / 100)


VENTANA_DIAS_ACIERTO_GLOBAL = 90


def _calcular_porcentaje_aciertos_global():
    """Recorre historial_partidos/*.json de los ultimos
    VENTANA_DIAS_ACIERTO_GLOBAL dias, cuenta aciertos/calificados usando
    el mismo criterio que ya se usa fila por fila (umbral de 5 PJ,
    codigo 1/X/2/1X/X2/12). Devuelve (calificados, aciertos, porcentaje)
    o (0, 0, None) si no hay datos suficientes."""
    if not DIR_HISTORIAL.exists():
        return (0, 0, None)

    hoy = date.today()
    limite = hoy - timedelta(days=VENTANA_DIAS_ACIERTO_GLOBAL)

    calificados = 0
    aciertos = 0

    for archivo in sorted(DIR_HISTORIAL.glob("*.json"), reverse=True):
        try:
            aaaa_mm = archivo.stem  # "YYYY-MM"
            anio, mes = int(aaaa_mm[:4]), int(aaaa_mm[5:7])
        except (ValueError, IndexError):
            continue
        # Si el mes completo del archivo es anterior al limite, se puede
        # dejar de escanear archivos mas viejos (estan ordenados desc).
        if date(anio, mes, 1) < date(limite.year, limite.month, 1):
            break

        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        for p in datos.get("partidos", []):
            fecha_p = p.get("fecha", "")
            if not fecha_p or fecha_p < limite.isoformat():
                continue
            pred = p.get("prediccion_previa")
            if not pred:
                continue
            pj_h = pred.get("pj_h")
            pj_a = pred.get("pj_a")
            if pj_h is None or pj_a is None or pj_h < 5 or pj_a < 5:
                continue
            gl, ga = p.get("goles_local"), p.get("goles_visitante")
            if gl is None or ga is None:
                continue
            diff = pred.get("diff_elo")
            if diff is None:
                continue
            codigo = _codigo_prediccion(diff)
            es_acierto = _acierto_con_codigo(codigo, gl, ga)
            if es_acierto is None:
                continue
            calificados += 1
            if es_acierto:
                aciertos += 1

    if calificados == 0:
        return (0, 0, None)
    porcentaje = round(100 * aciertos / calificados, 1)
    return (calificados, aciertos, porcentaje)


def generar_html(predicciones, titulo="ELO + Tilt Tracker", fecha_consulta=None, build_ts=None):
    ligas = _agrupar_por_liga(predicciones)
    todos_equipos = {}
    for p in predicciones:
        for lado in ["equipo_local", "equipo_visitante"]:
            eq = p[lado]
            todos_equipos[eq["id"]] = eq

    # Rankings solo con equipos de mas de 10 partidos reales jugados (sin contar
    # bootstrap) -- temprano en la temporada casi ninguno pasa, a proposito.
    elegibles = [eq for eq in todos_equipos.values() if eq.get("pj_reales", 0) > 10]
    ranking_forma = sorted(elegibles, key=lambda x: x.get("form_score", 50), reverse=True)[:30]
    ranking_elo = sorted(elegibles, key=lambda x: x.get("rating", 1500), reverse=True)[:30]

    liga_counts = {}
    for p in predicciones:
        lk = p.get("liga_slug", "")
        liga_counts[lk] = liga_counts.get(lk, 0) + 1
    liga_top = max(liga_counts.items(), key=lambda x: x[1]) if liga_counts else ("", 0)
    liga_top_nombre = ligas.get(liga_top[0], {}).get("liga", liga_top[0]) if liga_top[0] else "N/A"

    generado = predicciones[0].get("fecha_display", "") if predicciones else ""
    if predicciones:
        generado = predicciones[0].get("fecha", "")[:10]

    resultados = _cargar_resultados_fecha(fecha_consulta) if fecha_consulta else {}

    all_ligas_json = json.dumps([{"slug": k, "nombre": v["nombre"]} for k, v in sorted(ligas.items())])

    historial_months = sorted(f.stem for f in DIR_HISTORIAL.glob("*.json"))
    historial_months_json = json.dumps(historial_months)

    calificados, aciertos, porcentaje = _calcular_porcentaje_aciertos_global()
    texto_aciertos = f"{porcentaje}%" if porcentaje is not None else "–"
    tooltip_aciertos = (f"{aciertos}/{calificados} calificados (últimos {VENTANA_DIAS_ACIERTO_GLOBAL} días)"
                        if calificados else "Sin suficientes datos todavía")

    excel_rows = ""
    for p in predicciones:
        h = p["equipo_local"]
        a = p["equipo_visitante"]
        pred = p["prediccion"]
        hora = p.get("hora", "")
        fecha_d = p.get("fecha_display", "")
        diff = p.get("diff_elo", 0)
        slug = p.get("liga_slug", "")

        prob_l = pred["prob_local"]
        prob_e = pred["prob_empate"]
        prob_v = pred["prob_visitante"]
        codigo_pred = _codigo_prediccion(diff)

        diff_signo = "+" if diff > 0 else ""

        u5_h = h.get("ultimos5", {})
        u5_a = a.get("ultimos5", {})

        mom_h = h.get("momentum", "stable")
        mom_h_diff = h.get("momentum_diff", 0)
        mom_a = a.get("momentum", "stable")
        mom_a_diff = a.get("momentum_diff", 0)
        op_h = h.get("overperformance", 0)
        op_a = a.get("overperformance", 0)

        fixture_id = p.get("fixture_id", "")
        key_fx = f"fx:{fixture_id}" if fixture_id else ""
        url_espn = f"https://www.espn.com/soccer/match/_/gameId/{fixture_id}" if fixture_id else None
        key = f"{h['nombre'].lower()}_{a['nombre'].lower()}"
        key_inv = f"{a['nombre'].lower()}_{h['nombre'].lower()}"
        resultado = resultados.get(key_fx) if key_fx else None
        if not resultado:
            resultado = resultados.get(key) or resultados.get(key_inv)
        pj_h_pred = h.get('partidos_jugados', 0)
        pj_a_pred = a.get('partidos_jugados', 0)
        pj_suficiente = pj_h_pred >= 5 and pj_a_pred >= 5

        clase_marcador = ""
        acierto_parcial = False
        if resultado and resultado.get("estado") == "post" and pj_suficiente:
            marcador = f"{resultado['goles_local']} - {resultado['goles_visitante']}"
            gl = resultado['goles_local']
            ga = resultado['goles_visitante']
            acierto = "✓" if _acierto_con_codigo(codigo_pred, gl, ga) else "✗"
            clase_marcador = "marcador-finalizado"
        elif resultado and resultado.get("estado") == "post":
            marcador = f"{resultado['goles_local']} - {resultado['goles_visitante']}"
            acierto = ""
            clase_marcador = "marcador-finalizado"
        elif resultado and resultado.get("estado") == "in" and pj_suficiente:
            marcador = f"{resultado['goles_local']} - {resultado['goles_visitante']}"
            gl = resultado['goles_local']
            ga = resultado['goles_visitante']
            acierto = "✓" if _acierto_con_codigo(codigo_pred, gl, ga) else "✗"
            acierto_parcial = True
            clase_marcador = "marcador-vivo"
        elif resultado and resultado.get("estado") == "in":
            marcador = f"{resultado['goles_local']} - {resultado['goles_visitante']}"
            acierto = ""
            clase_marcador = "marcador-vivo"
        else:
            marcador = "?"
            acierto = ""

        if acierto == '✓':
            clase_acierto = 'acierto-parcial-ok' if acierto_parcial else 'acierto-ok'
        elif acierto == '✗':
            clase_acierto = 'acierto-parcial-fail' if acierto_parcial else 'acierto-fail'
        else:
            clase_acierto = ''

        if resultado and resultado.get("estado") == "post":
            minuto_col = "FIN"
        elif resultado and resultado.get("estado") == "in":
            minuto_col = resultado.get("minuto") or "EN VIVO"
        else:
            minuto_col = ""

        excel_rows += f'''<tr class="excel-row" data-fixture-id="{fixture_id}" data-slug="{slug}" data-fecha="{fecha_d}" data-elo-h="{h.get('rating', 0):.0f}" data-form-h="{h.get('form_score', 50):.0f}" data-home="{h['nombre'].lower()}" data-away="{a['nombre'].lower()}" data-diff="{diff:.0f}" data-pj-h="{h.get('pj_reales', h.get('partidos_jugados', 0))}" data-pj-a="{a.get('pj_reales', a.get('partidos_jugados', 0))}" data-pj-h-total="{pj_h_pred}" data-pj-a-total="{pj_a_pred}">
  <td class="ex-fecha">{fecha_d}</td>
  <td class="ex-hora">{hora}</td>
  <td class="ex-local">{f'<a href="{url_espn}" target="_blank">{h["nombre"]}</a>' if url_espn else h['nombre']}{_badge_provisional(h.get('pj_reales', h.get('partidos_jugados')))}</td>
  <td class="ex-elo {_clase_rating(h.get('rating'))}">{h.get('rating', 0):.0f} <span class="pj-count">{h.get('partidos_jugados', 0)}PJ</span></td>
  <td class="ex-forma {_clase_forma(h.get('form_score'))}">{h.get('form_score', 50):.0f}</td>
  <td class="ex-racha">{_ultimos5_html(u5_h)} {_overperformance_badge(op_h)}</td>
  <td class="ex-marcador {clase_marcador}">{marcador}</td>
  <td class="ex-minuto {clase_marcador}">{minuto_col}</td>
  <td class="ex-visitante">{f'<a href="{url_espn}" target="_blank">{a["nombre"]}</a>' if url_espn else a['nombre']}{_badge_provisional(a.get('pj_reales', a.get('partidos_jugados')))}</td>
  <td class="ex-elo {_clase_rating(a.get('rating'))}">{a.get('rating', 0):.0f} <span class="pj-count">{a.get('partidos_jugados', 0)}PJ</span></td>
  <td class="ex-forma {_clase_forma(a.get('form_score'))}">{a.get('form_score', 50):.0f}</td>
  <td class="ex-racha">{_ultimos5_html(u5_a)} {_overperformance_badge(op_a)}</td>
  <td class="ex-diff" style="color:{'#22c55e' if diff > 0 else '#ef4444' if diff < 0 else '#94a3b8'}">{diff_signo}{diff:.0f}</td>
  <td class="ex-pred best" title="{_tooltip_prediccion(diff, prob_l, prob_e, prob_v)}">{codigo_pred}</td>
  <td class="ex-acierto {clase_acierto}" title="{'Provisional -- puede cambiar mientras el partido siga en curso' if acierto_parcial else ''}">{acierto}</td>
  <td><button class="expand-btn" onclick="toggleDetalle('{fixture_id}')">▾</button></td>
</tr>
<tr class="detail-row" id="detail-{fixture_id}" style="display:none">
  <td colspan="16">
    <div class="detail-panel">
      <div class="detail-team">
        <strong>{h["nombre"]}</strong>
        <span class="{_clase_momentum(mom_h)}">{_icono_momentum_texto(mom_h)} Momentum ({mom_h_diff:+.1f})</span>
        <span class="{_clase_signo(op_h)}">Overperf: {op_h:+.1f}</span>
      </div>
      <div class="detail-team">
        <strong>{a["nombre"]}</strong>
        <span class="{_clase_momentum(mom_a)}">{_icono_momentum_texto(mom_a)} Momentum ({mom_a_diff:+.1f})</span>
        <span class="{_clase_signo(op_a)}">Overperf: {op_a:+.1f}</span>
      </div>
    </div>
  </td>
</tr>
'''

    ranking_rows_forma = ""
    for i, eq in enumerate(ranking_forma, 1):
        ranking_rows_forma += f'''<tr>
<td class="rk">{i}</td>
<td class="rk-name">{eq['nombre']}</td>
<td class="rk-pais" data-pais="{eq.get('pais', '')}">{eq.get('pais', '')}</td>
<td><span class="elo {_clase_rating(eq.get('rating'))}">{eq.get('rating', 0):.0f}</span></td>
<td class="{_clase_forma(eq.get('form_score'))}">{eq.get('form_score', 50):.0f}</td>
<td>{_icono_momentum(eq.get('momentum'))}</td>
<td>{_streak_html(eq.get('streak'))}</td>
<td>{_overperformance_badge(eq.get('overperformance'))}</td>
</tr>
'''

    ranking_rows_elo = ""
    for i, eq in enumerate(ranking_elo, 1):
        ranking_rows_elo += f'''<tr>
<td class="rk">{i}</td>
<td class="rk-name">{eq['nombre']}</td>
<td class="rk-pais" data-pais="{eq.get('pais', '')}">{eq.get('pais', '')}</td>
<td><span class="elo {_clase_rating(eq.get('rating'))}">{eq.get('rating', 0):.0f}</span></td>
<td>{_badge_provisional(eq.get('partidos_jugados'))}</td>
<td class="{_clase_forma(eq.get('form_score'))}">{eq.get('form_score', 50):.0f}</td>
<td>{_icono_momentum(eq.get('momentum'))}</td>
</tr>
'''

    paises_en_datos = sorted(set(eq.get("pais", "") for eq in todos_equipos.values() if eq.get("pais")))
    paises_json = json.dumps(paises_en_datos)

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="build" content="{build_ts or ''}">
<title>{titulo}</title>
<style>
:root {{
  --bg: #0a0e17;
  --surface: #111827;
  --surface2: #1a2234;
  --border: #1e2d3d;
  --text: #e2e8f0;
  --text2: #94a3b8;
  --text3: #64748b;
  --accent: #38bdf8;
  --accent2: #818cf8;
  --green: #22c55e;
  --yellow: #eab308;
  --red: #ef4444;
  --orange: #f97316;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: var(--bg); color: var(--text); line-height: 1.5; }}
.container {{ max-width: 1280px; margin: 0 auto; padding: 16px; }}

/* Header */
.header {{ text-align: center; padding: 32px 16px 24px; }}
.header h1 {{ font-size: 2em; font-weight: 800; letter-spacing: -0.02em;
              background: linear-gradient(135deg, var(--accent), var(--accent2));
              -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.header .sub {{ color: var(--text2); font-size: 0.9em; margin-top: 4px; }}

/* Stats bar */
.stats {{ display: flex; justify-content: center; gap: 32px; padding: 16px;
          margin-bottom: 20px; flex-wrap: wrap; }}
.stat {{ text-align: center; }}
.stat-val {{ font-size: 1.6em; font-weight: 700; color: var(--accent); }}
.stat-label {{ font-size: 0.75em; color: var(--text3); text-transform: uppercase; letter-spacing: 0.05em; }}

/* Controls */
.controls {{ display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; align-items: center; }}
.search {{ flex: 1; min-width: 200px; padding: 8px 14px; background: var(--surface);
           border: 1px solid var(--border); border-radius: 8px; color: var(--text);
           font-size: 0.9em; outline: none; }}
.search:focus {{ border-color: var(--accent); }}
.search::placeholder {{ color: var(--text3); }}
.date-select {{ padding: 8px 14px; background: var(--surface); border: 1px solid var(--border); border-radius: 8px; color: var(--text); font-size: 0.9em; outline: none; cursor: pointer; }}
.date-select:focus {{ border-color: var(--accent); }}

/* Sort buttons */
.sort-btns {{ display: flex; gap: 4px; }}
.sort-btn {{ padding: 6px 12px; background: var(--surface); border: 1px solid var(--border);
             border-radius: 6px; color: var(--text2); cursor: pointer; font-size: 0.8em;
             transition: all 0.15s; white-space: nowrap; }}
.sort-btn:hover {{ border-color: var(--accent); color: var(--text); }}
.sort-btn.active {{ background: var(--accent2); color: white; border-color: var(--accent2); }}
.toggle-label {{ display: flex; align-items: center; gap: 6px; padding: 6px 12px; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; color: var(--text2); cursor: pointer; font-size: 0.8em; white-space: nowrap; user-select: none; }}
.toggle-label:hover {{ border-color: var(--accent); color: var(--text); }}
.toggle-label input:checked {{ accent-color: var(--accent); }}

/* Tabs */
.tabs {{ display: flex; gap: 4px; flex-wrap: wrap; }}
.tab {{ padding: 6px 14px; background: var(--surface); border: 1px solid var(--border);
        border-radius: 6px; color: var(--text2); cursor: pointer; font-size: 0.82em;
        transition: all 0.15s; white-space: nowrap; }}
.tab:hover {{ border-color: var(--accent); color: var(--text); }}
.tab.active {{ background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }}
.tab .count {{ font-size: 0.8em; opacity: 0.7; margin-left: 4px; }}

.view-tabs {{ display: flex; gap: 4px; margin-bottom: 16px; justify-content: center; }}
.view-tabs .tab {{ padding: 8px 20px; font-size: 0.9em; }}

/* League filter */
.league-filter {{ display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 16px; }}
.lf-btn {{ padding: 4px 10px; background: var(--surface); border: 1px solid var(--border);
           border-radius: 4px; color: var(--text3); cursor: pointer; font-size: 0.75em; }}
.lf-btn:hover {{ border-color: var(--accent); color: var(--text2); }}
.lf-btn.active {{ background: var(--surface2); color: var(--accent); border-color: var(--accent); }}

/* Badges & tags */
.elo {{ padding: 1px 7px; border-radius: 10px; font-size: 0.8em; font-weight: 700; }}
.elite {{ background: rgba(56,189,248,0.15); color: var(--accent); }}
.above {{ background: rgba(34,197,94,0.12); color: var(--green); }}
.average {{ background: rgba(148,163,184,0.12); color: var(--text2); }}
.below {{ background: rgba(239,68,68,0.12); color: var(--red); }}

.badge-prov {{ font-size: 0.6em; padding: 1px 5px; background: rgba(234,179,8,0.15);
               color: var(--yellow); border-radius: 4px; font-weight: 700; letter-spacing: 0.04em; }}
.pj-count {{ font-size: 0.65em; color: var(--text3); font-weight: 500; margin-left: 3px; }}
.elo-pre {{ font-size: 0.7em; color: var(--text2); }}

.tf {{ font-weight: 700; font-size: 0.85em; }}
.high {{ color: var(--green); }}
.mid {{ color: var(--yellow); }}
.low {{ color: var(--red); }}
.neutral {{ color: var(--text3); }}

.mom-up {{ color: var(--green); font-size: 0.75em; }}
.mom-down {{ color: var(--red); font-size: 0.75em; }}
.mom-stable {{ color: var(--text3); font-size: 0.75em; }}

.streak-w {{ color: var(--green); font-weight: 700; font-size: 0.8em; }}
.streak-d {{ color: var(--text3); font-weight: 700; font-size: 0.8em; }}
.streak-l {{ color: var(--red); font-weight: 700; font-size: 0.8em; }}
.streak-na {{ color: var(--text3); font-size: 0.8em; }}

.spark {{ border-radius: 2px; vertical-align: middle; }}

.gt {{ font-size: 0.75em; font-weight: 600; }}
.op-badge {{ font-size: 0.7em; font-weight: 700; }}
.ft-badge {{ font-size: 0.7em; font-weight: 600; }}
.sub-item {{ white-space: nowrap; }}

/* Rankings */
.ranking-section {{ margin-top: 32px; }}
.ranking-title {{ font-size: 1.1em; font-weight: 700; color: var(--accent); margin-bottom: 12px;
                  padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
.ranking-tabs {{ display: flex; gap: 4px; margin-bottom: 12px; }}
.rtab {{ padding: 6px 12px; background: var(--surface); border: 1px solid var(--border);
         border-radius: 6px; color: var(--text2); cursor: pointer; font-size: 0.82em; }}
.rtab.active {{ background: var(--accent); color: var(--bg); border-color: var(--accent); }}

/* Country filter */
.country-filter {{ display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 12px; }}
.cf-btn {{ padding: 4px 10px; background: var(--surface); border: 1px solid var(--border);
           border-radius: 4px; color: var(--text3); cursor: pointer; font-size: 0.75em; }}
.cf-btn:hover {{ border-color: var(--accent); color: var(--text2); }}
.cf-btn.active {{ background: var(--surface2); color: var(--accent); border-color: var(--accent); }}

.rk-pais {{ font-size: 0.8em; color: var(--text3); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 8px 10px; background: var(--surface2); color: var(--text3);
      font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.04em; font-weight: 600; }}
td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); font-size: 0.85em; }}
tr:hover {{ background: var(--surface2); }}
.rk {{ color: var(--text3); font-weight: 700; width: 30px; }}
.rk-name {{ font-weight: 500; }}

.footer {{ text-align: center; color: var(--text3); font-size: 0.75em; padding: 24px 0; }}
.hidden {{ display: none !important; }}

/* Excel table styles */
.excel-section {{ margin-top: 32px; background: var(--surface); border-radius: 12px; padding: 16px; border: 1px solid var(--border); }}
.excel-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
.excel-header h3 {{ color: var(--accent); font-size: 1.1em; }}
.excel-controls {{ display: flex; gap: 4px; }}
.excel-btn {{ padding: 6px 12px; background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; color: var(--text2); cursor: pointer; font-size: 0.82em; }}
.excel-btn.active {{ background: var(--accent); color: var(--bg); border-color: var(--accent); }}
.excel-table-container {{ overflow-x: auto; }}
.excel-table {{ width: 100%; border-collapse: collapse; font-size: 0.82em; }}
.excel-table th {{ background: var(--surface2); color: var(--text3); padding: 8px 10px; text-align: left; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.04em; position: sticky; top: 0; }}
.excel-table td {{ padding: 7px 10px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
.excel-table tr:hover {{ background: var(--surface2); }}
.excel-table a {{ color: var(--text); text-decoration: none; }}
.excel-table a:hover {{ color: var(--accent); text-decoration: underline; }}
.ex-fecha {{ color: var(--text3); font-size: 0.9em; }}
.ex-hora {{ color: var(--accent); font-weight: 600; }}
.ex-local, .ex-visitante {{ font-weight: 500; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }}
.ex-elo {{ font-weight: 700; padding: 2px 6px; border-radius: 8px; }}
.ex-forma {{ font-weight: 600; }}
.ex-racha {{ font-size: 0.9em; }}
.ex-goles {{ color: var(--text2); font-size: 0.9em; }}
.ex-marcador {{ font-weight: 700; color: var(--accent); font-size: 1.1em; text-align: center; }}
.marcador-vivo {{ color: var(--green); }}
.marcador-finalizado {{ color: var(--accent); }}
.ex-diff {{ font-weight: 700; }}
.ex-pred {{ font-size: 0.9em; color: var(--text2); }}
.ex-pred.best {{ color: var(--accent); font-weight: 600; }}
.ultimos5 {{ display: inline-flex; gap: 2px; }}
.u5-v {{ background: rgba(34,197,94,0.2); color: var(--green); padding: 1px 4px; border-radius: 3px; font-weight: 700; font-size: 0.85em; }}
.u5-d {{ background: rgba(239,68,68,0.2); color: var(--red); padding: 1px 4px; border-radius: 3px; font-weight: 700; font-size: 0.85em; }}
.u5-e {{ background: rgba(148,163,184,0.15); color: var(--text3); padding: 1px 4px; border-radius: 3px; font-weight: 700; font-size: 0.85em; }}
.live-indicator {{ color: var(--red) !important; font-weight: 700; animation: pulse 1.5s infinite; }}
.live-row {{ background: rgba(239,68,68,0.05) !important; }}
@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
.ex-acierto {{ text-align: center; font-weight: 700; font-size: 1.1em; }}
.acierto-ok {{ color: var(--green); }}
.acierto-fail {{ color: var(--red); }}
.acierto-parcial-ok {{ color: var(--green); opacity: 0.55; border-bottom: 1px dashed var(--green); }}
.acierto-parcial-fail {{ color: var(--red); opacity: 0.55; border-bottom: 1px dashed var(--red); }}

.expand-btn {{ background: none; border: none; cursor: pointer; font-size: 14px; color: var(--accent, #888); transition: transform 0.2s ease; padding: 2px 6px; }}
.expand-btn.open {{ transform: rotate(180deg); }}
.detail-row td {{ padding: 0; }}
.detail-panel {{ display: flex; gap: 24px; padding: 10px 16px; background: rgba(255,255,255,0.03); font-size: 13px; flex-wrap: wrap; }}
.detail-team {{ display: flex; flex-direction: column; gap: 4px; }}
.mom-up {{ color: #4caf50; }}
.mom-down {{ color: #f44336; }}
.mom-stable {{ color: #999; }}
.op-pos {{ color: #4caf50; }}
.op-neg {{ color: #f44336; }}
.op-neutral {{ color: #999; }}

@media (max-width: 768px) {{
  .stats {{ gap: 16px; }}
  .tabs {{ gap: 3px; }}
  .tab {{ padding: 5px 10px; font-size: 0.78em; }}
}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{titulo}</h1>
    <div class="sub">Predicciones con Glicko-2 + Tilt/Momentum | {len(predicciones)} partidos | {generado}</div>
  </div>

  <div class="stats">
    <div class="stat"><div class="stat-val">{len(predicciones)}</div><div class="stat-label">Partidos</div></div>
    <div class="stat"><div class="stat-val">{len(ligas)}</div><div class="stat-label">Ligas</div></div>
    <div class="stat"><div class="stat-val" id="statAciertos" data-global="{texto_aciertos}" data-global-title="{tooltip_aciertos}" title="{tooltip_aciertos}">{texto_aciertos}</div><div class="stat-label">% Aciertos</div></div>
  </div>

  <div class="controls">
    <input type="text" class="search" id="searchBox" placeholder="Buscar equipo..." oninput="aplicarFiltros()">
    <select class="date-select" id="dateSelect" onchange="cambiarFecha(this.value)">
      <option value="hoy">Hoy</option>
      <option value="ayer">Ayer</option>
      <option value="manana">Mañana</option>
      <option value="en-vivo">🔴 En Vivo</option>
    </select>
    <div class="sort-btns">
      <button class="sort-btn" onclick="sortExcel('elo-desc')" title="Mayor ELO primero">ELO ↓</button>
      <button class="sort-btn" onclick="sortExcel('elo-asc')" title="Menor ELO primero">ELO ↑</button>
      <button class="sort-btn" onclick="sortExcel('form-desc')" title="Mayor forma primero">Forma ↓</button>
      <button class="sort-btn" onclick="sortExcel('form-asc')" title="Menor forma primero">Forma ↑</button>
      <button class="sort-btn" onclick="sortExcel('diff-desc')" title="Mayor diff ELO">Diff ↓</button>
      <button class="sort-btn" onclick="sortExcel('diff-asc')" title="Menor diff ELO">Diff ↑</button>
      <label class="toggle-label"><input type="checkbox" id="confiableToggle" onchange="aplicarFiltros()"> Solo confiables (10+PJ)</label>
<label class="toggle-label"><input type="checkbox" id="mostrarTodosToggle" onchange="aplicarFiltros()"> Mostrar todos</label>
    </div>
  </div>

  <div class="league-filter" id="leagueFilter">
    <div class="lf-btn active" data-slug="todas" onclick="setLiga('todas')">Todas</div>
  </div>

  <div class="excel-section" id="excelSection">
    <div class="excel-table-container">
      <table class="excel-table">
        <thead>
          <tr>
            <th>Fecha</th>
            <th>Hora</th>
            <th>Local</th>
            <th>ELO</th>
            <th>Forma</th>
            <th>Racha</th>
            <th>Marcador</th>
            <th>Minuto</th>
            <th>Visitante</th>
            <th>ELO</th>
            <th>Forma</th>
            <th>Racha</th>
            <th>Diff</th>
            <th>Pred</th>
            <th>Acierto</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {excel_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="ranking-section">
    <div class="ranking-title">Rankings ELO</div>
    <p class="ranking-disclaimer" style="font-size:11px;color:#888;margin-top:4px;">
      El ranking global mezcla ligas y competiciones que no siempre se enfrentan entre sí — comparar el ELO de dos equipos de ligas distintas no es una comparación directa de su nivel real.
    </p>
    <div class="ranking-tabs">
      <div class="rtab active" data-rtab="global" onclick="showRanking('global')">Global</div>
      <div class="rtab" data-rtab="forma" onclick="showRanking('forma')">Por Forma</div>
    </div>
    <div class="country-filter" id="countryFilter">
      <div class="cf-btn active" data-pais="todos" onclick="filterCountry('todos')">Todos</div>
    </div>
    <div id="rankGlobal">
      <table>
        <thead><tr><th>#</th><th>Equipo</th><th>País</th><th>ELO</th><th>RD</th><th>Forma</th><th>Momentum</th></tr></thead>
        <tbody>{ranking_rows_elo}</tbody>
      </table>
    </div>
    <div id="rankForma" class="hidden">
      <table>
        <thead><tr><th>#</th><th>Equipo</th><th>País</th><th>ELO</th><th>Forma</th><th>Momentum</th><th>Racha</th><th>Overperf</th></tr></thead>
        <tbody>{ranking_rows_forma}</tbody>
      </table>
    </div>
  </div>

  <div class="footer">ELO + Tilt Tracker | Actualizado: {predicciones[0].get('fecha', '')[:10] if predicciones else 'N/A'} | v2.1</div>
</div>

<script>
const ligas = {all_ligas_json};
const paises = {paises_json};
const historialMonths = {historial_months_json};
let ligaActual = 'todas';
let paisActual = 'todos';
let historialCache = null;

async function cargarTodoElHistorial() {{
  if (historialCache) return historialCache;
  const todos = [];
  for (const m of historialMonths) {{
    try {{
      const res = await fetch('data/historial_partidos/' + m + '.json');
      if (res.ok) {{
        const data = await res.json();
        if (data.partidos) todos.push(...data.partidos);
      }}
    }} catch(e) {{}}
  }}
  historialCache = todos;
  return todos;
}}

function calcularEstadisticas(nombre, todosPartidos) {{
  const n = nombre.toLowerCase();
  const mismos = todosPartidos.filter(p => {{
    const ln = (p.equipo_local?.name || '').toLowerCase();
    const vn = (p.equipo_visitante?.name || '').toLowerCase();
    return ln.includes(n) || vn.includes(n);
  }}).sort((a,b) => (b.fecha || '').localeCompare(a.fecha || ''));
  const ultimos10 = mismos.slice(0, 10);
  if (ultimos10.length === 0) return {{ form_score: null, streak: null, ultimos5: null }};
  let puntos = 0;
  const resultados = [];
  for (const p of ultimos10) {{
    const ln = (p.equipo_local?.name || '').toLowerCase();
    const gl = p.goles_local ?? 0;
    const ga = p.goles_visitante ?? 0;
    const esLocal = ln.includes(n);
    const GF = esLocal ? gl : ga;
    const GC = esLocal ? ga : gl;
    if (GF > GC) {{ puntos += 3; resultados.push('V'); }}
    else if (GF === GC) {{ puntos += 1; resultados.push('E'); }}
    else {{ resultados.push('D'); }}
  }}
  const form_score = Math.round((puntos / (ultimos10.length * 3)) * 100);
  const u5 = resultados.slice(0, 5);
  const ultimos5 = {{ texto: u5.map(r => r === 'V' ? 'Victoria' : r === 'E' ? 'Empate' : 'Derrota').join(', '), resultados: u5 }};
  let streak_tipo = null, streak_cantidad = 0;
  if (u5.length > 0) {{
    streak_tipo = u5[0] === 'V' ? 'W' : u5[0] === 'E' ? 'D' : 'L';
    for (const r of u5) {{
      const t = r === 'V' ? 'W' : r === 'E' ? 'D' : 'L';
      if (t === streak_tipo) streak_cantidad++;
      else break;
    }}
  }}
  const streak = streak_tipo ? {{ tipo: streak_tipo, cantidad: streak_cantidad }} : null;
  return {{ form_score, streak, ultimos5 }};
}}

function initLeagueButtons() {{
  const cont = document.getElementById('leagueFilter');
  const slugsVistos = new Set();
  document.querySelectorAll('.excel-row').forEach(c => {{
    const s = c.dataset.slug;
    if (s && !slugsVistos.has(s)) {{
      slugsVistos.add(s);
      const nombre = ligas.find(l => l.slug === s)?.nombre || s;
      const btn = document.createElement('div');
      btn.className = 'lf-btn';
      btn.dataset.slug = s;
      btn.textContent = nombre;
      btn.onclick = () => setLiga(s);
      cont.appendChild(btn);
    }}
  }});
}}

function setLiga(slug) {{
  ligaActual = slug;
  document.querySelectorAll('#leagueFilter .lf-btn').forEach(b => b.classList.toggle('active', b.dataset.slug === slug));
  aplicarFiltros();
}}

function showRanking(r) {{
  document.querySelectorAll('.rtab').forEach(t => t.classList.toggle('active', t.dataset.rtab === r));
  document.getElementById('rankGlobal').classList.toggle('hidden', r !== 'global');
  document.getElementById('rankForma').classList.toggle('hidden', r !== 'forma');
}}

function initCountryButtons() {{
  const cont = document.getElementById('countryFilter');
  paises.forEach(p => {{
    const btn = document.createElement('div');
    btn.className = 'cf-btn';
    btn.dataset.pais = p;
    btn.textContent = p;
    btn.onclick = () => filterCountry(p);
    cont.appendChild(btn);
  }});
}}

function filterCountry(pais) {{
  paisActual = pais;
  document.querySelectorAll('#countryFilter .cf-btn').forEach(b => b.classList.toggle('active', b.dataset.pais === pais));
  document.querySelectorAll('#rankGlobal tbody tr, #rankForma tbody tr').forEach(row => {{
    const cell = row.querySelector('.rk-pais');
    const p = cell ? cell.dataset.pais : '';
    row.style.display = (pais === 'todos' || p === pais) ? '' : 'none';
  }});
  renumberVisible('rankGlobal');
  renumberVisible('rankForma');
}}

function renumberVisible(sectionId) {{
  const rows = document.querySelectorAll('#' + sectionId + ' tbody tr');
  let n = 1;
  rows.forEach(row => {{
    if (row.style.display !== 'none') {{
      row.querySelector('.rk').textContent = n++;
    }}
  }});
}}

function aplicarFiltros() {{
  const q = document.getElementById('searchBox').value.toLowerCase().trim();
  const soloConfiables = document.getElementById('confiableToggle')?.checked || false;
  const mostrarTodos = document.getElementById('mostrarTodosToggle')?.checked || false;
  document.querySelectorAll('.excel-row').forEach(row => {{
    const local = row.dataset.home || '';
    const away = row.dataset.away || '';
    const pjH = parseInt(row.dataset.pjH || '0');
    const pjA = parseInt(row.dataset.pjA || '0');
    let show = true;
    if (q && !local.includes(q) && !away.includes(q)) show = false;
    // Por defecto (mostrarTodos sin marcar) se ocultan equipos con menos
    // de 5 partidos reales (sin contar bootstrap) -- ver README pj_reales.
    if (!mostrarTodos && (pjH < 5 || pjA < 5)) show = false;
    if (soloConfiables && (pjH < 10 || pjA < 10)) show = false;
    row.style.display = show ? '' : 'none';
  }});
  actualizarPorcentajeAciertos();
}}

function actualizarPorcentajeAciertos() {{
  const filasVisibles = Array.from(document.querySelectorAll('.excel-row'))
    .filter(row => row.style.display !== 'none');
  let ok = 0, total = 0;
  filasVisibles.forEach(row => {{
    if (row.querySelector('.acierto-ok')) {{ ok++; total++; }}
    else if (row.querySelector('.acierto-fail')) {{ total++; }}
  }});
  const el = document.getElementById('statAciertos');
  if (!el) return;
  // Si hoy hay partidos ya finalizados calificados, muestra el % de hoy;
  // si no, muestra el % global de los ultimos 90 dias (data-global) para
  // no dejar nunca el guion fijo "-".
  el.textContent = total > 0 ? `${{Math.round(100 * ok / total)}}%` : (el.dataset.global || '–');
  el.title = total > 0 ? `${{ok}}/${{total}} partidos calificados hoy` : (el.dataset.globalTitle || '');
}}

function toggleDetalle(fixtureId) {{
  const fila = document.getElementById('detail-' + fixtureId);
  const boton = event.currentTarget;
  if (!fila) return;
  const abierta = fila.style.display !== 'none';
  fila.style.display = abierta ? 'none' : 'table-row';
  boton.classList.toggle('open', !abierta);
}}

function sortExcel(criterion) {{
  document.querySelectorAll('.sort-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  const tbody = document.querySelector('.excel-table tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  rows.sort((a, b) => {{
    if (criterion === 'elo-desc') return parseFloat(b.dataset.eloH || 0) - parseFloat(a.dataset.eloH || 0);
    if (criterion === 'elo-asc') return parseFloat(a.dataset.eloH || 0) - parseFloat(b.dataset.eloH || 0);
    if (criterion === 'form-desc') return parseFloat(b.dataset.formH || 0) - parseFloat(a.dataset.formH || 0);
    if (criterion === 'form-asc') return parseFloat(a.dataset.formH || 0) - parseFloat(b.dataset.formH || 0);
    if (criterion === 'diff-desc') return Math.abs(parseFloat(b.dataset.diff || 0)) - Math.abs(parseFloat(a.dataset.diff || 0));
    if (criterion === 'diff-asc') return Math.abs(parseFloat(a.dataset.diff || 0)) - Math.abs(parseFloat(b.dataset.diff || 0));
    return 0;
  }});
  rows.forEach(row => tbody.appendChild(row));
}}

let intervaloMarcadoresHoy = null;

initLeagueButtons();
initCountryButtons();
aplicarFiltros();
iniciarRefrescoMarcadoresHoy();  // Hoy es la vista con la que carga la pagina

function cambiarFecha(valor) {{
  if (valor === 'hoy') {{
    window.location.href = window.location.href.split('?')[0];
  }} else if (valor === 'ayer') {{
    detenerRefrescoMarcadoresHoy();
    cargarHistorial('ayer');
  }} else if (valor === 'manana') {{
    detenerRefrescoMarcadoresHoy();
    cargarHistorial('manana');
  }} else if (valor === 'en-vivo') {{
    detenerRefrescoMarcadoresHoy();
    cargarEnVivo();
  }}
}}

function claseRating(r) {{
  if (!r) return '';
  if (r >= 1700) return 'elite';
  if (r >= 1550) return 'above';
  if (r >= 1400) return 'average';
  return 'below';
}}

function claseForma(f) {{
  if (f == null) return '';
  if (f >= 70) return 'high';
  if (f >= 40) return 'mid';
  return 'low';
}}

// Traduccion JS de _overperformance_badge (Python): positivo >10 verde,
// negativo <-10 rojo, cerca de cero gris; sin badge en 0.
function overperformanceBadgeJs(op) {{
  if (op == null) return '';
  const texto = (op > 0 ? '+' : '') + Math.round(op);
  if (texto === '+0' || texto === '-0' || texto === '0') return '';
  const color = op > 10 ? '#22c55e' : (op < -10 ? '#ef4444' : '#94a3b8');
  return `<span class="op-badge" title="Sobre-rendimiento vs ELO esperado" style="color:${{color}}">${{texto}}</span>`;
}}

function streakHtml(s) {{
  if (!s) return '-';
  const t = s.tipo || 'N/A';
  const c = s.cantidad || 0;
  if (t === 'W') return `<span class="streak-w">${{c}}V</span>`;
  if (t === 'D') return `<span class="streak-d">${{c}}E</span>`;
  if (t === 'L') return `<span class="streak-l">${{c}}D</span>`;
  return '-';
}}

// Regla por diferencia de Elo (Glicko-2). Valores calibrados con backtest, no cambiar sin pedirlo.
const VENTAJA_LOCAL_ELO = 50;
const UMBRAL_FAVORITO_ELO = 200;
const UMBRAL_PAREJO_ELO = 30;

function codigoPrediccion(diffElo) {{
  const d = diffElo + VENTAJA_LOCAL_ELO;
  if (Math.abs(d) > UMBRAL_FAVORITO_ELO) {{
    return d > 0 ? '1' : '2';
  }}
  if (Math.abs(d) <= UMBRAL_PAREJO_ELO) {{
    return '12';
  }}
  return d > 0 ? '1X' : 'X2';
}}

// Respaldo: regla antigua por probabilidades. Solo se usa si el registro guardado
// no trae diff_elo (predicciones viejas).
const UMBRAL_FAVORITO_CLARO = 12;

function codigoPrediccionLegacy(probL, probE, probV) {{
  const opciones = [['1', probL], ['X', probE], ['2', probV]].sort((a, b) => b[1] - a[1]);
  const [primera, segunda] = opciones;
  if (primera[1] - segunda[1] > UMBRAL_FAVORITO_CLARO) {{
    return primera[0];
  }}
  const incluidas = new Set([primera[0], segunda[0]]);
  if (incluidas.has('1') && incluidas.has('X')) return '1X';
  if (incluidas.has('X') && incluidas.has('2')) return 'X2';
  return '12';
}}

function aciertoConCodigo(codigo, gl, ga) {{
  if (gl == null || ga == null) return null;
  let real;
  if (gl > ga) real = '1';
  else if (gl === ga) real = 'X';
  else real = '2';
  return codigo.includes(real);
}}

function ultimos5Html(u5) {{
  if (!u5 || !u5.resultados || u5.resultados.length === 0) return '<span class="streak-na">—</span>';
  return u5.resultados.map(r => {{
    if (r === 'V') return '<span class="u5-v">V</span>';
    if (r === 'D') return '<span class="u5-d">D</span>';
    if (r === 'E') return '<span class="u5-e">E</span>';
    return '';
  }}).join('');
}}

function fechaEcuadorISO(offsetDias = 0) {{
  const ahora = new Date();
  // Hora de Ecuador via Intl, para no depender de la zona horaria del navegador.
  const partes = new Intl.DateTimeFormat('en-CA', {{
    timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit'
  }}).formatToParts(ahora).reduce((acc, p) => {{ acc[p.type] = p.value; return acc; }}, {{}});
  const base = new Date(`${{partes.year}}-${{partes.month}}-${{partes.day}}T00:00:00-05:00`);
  base.setDate(base.getDate() + offsetDias);
  return base.toISOString().slice(0, 10);
}}

async function cargarHistorial(cuando) {{
  const tbody = document.querySelector('.excel-table tbody');
  tbody.innerHTML = '<tr><td colspan="16" style="text-align:center; padding:20px;">Cargando...</td></tr>';
  
  const offset = cuando === 'ayer' ? -1 : (cuando === 'manana' ? 1 : 0);
  const fechaIso = fechaEcuadorISO(offset);
  const [yyyy, mm, dd] = fechaIso.split('-');
  
  try {{
    const [dataRatings, allMatches] = await Promise.all([
      fetch('data/ratings_propios.json').then(r => r.json()),
      cargarTodoElHistorial()
    ]);
    const equipos = dataRatings.equipos || {{}};
    
    let partidos = [];
    
    if (cuando === 'manana') {{
      let prediccionesDelDia = {{}};
      try {{
        const resPred = await fetch('data/predicciones_' + fechaIso + '.json');
        if (resPred.ok) {{
          const dataPred = await resPred.json();
          (dataPred.predicciones || []).forEach(p => {{
            if (p.fixture_id) prediccionesDelDia[p.fixture_id] = p;
          }});
        }}
      }} catch (e) {{
        console.warn('[Manana] No se pudo cargar predicciones del dia:', e);
      }}

      const resESPN = await fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=' + yyyy + mm + dd);
      if (!resESPN.ok) throw new Error('Error ESPN: ' + resESPN.status);
      const dataESPN = await resESPN.json();
      if (dataESPN.events) {{
        dataESPN.events.forEach(event => {{
          const comp = event.competitions?.[0];
          if (!comp) return;
          const equiposComp = comp.competitors || [];
          if (equiposComp.length < 2) return;

          // Descartar eventos cuya fecha real en Ecuador no coincide con fechaIso.
          const fechaEventoEc = new Intl.DateTimeFormat('en-CA', {{
            timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit'
          }}).format(new Date(event.date));
          if (fechaEventoEc !== fechaIso) return;

          const local = equiposComp.find(e => e.homeAway === 'home') || equiposComp[0];
          const visitante = equiposComp.find(e => e.homeAway === 'away') || equiposComp[1];
          const fixtureId = String(event.id);
          const pred = prediccionesDelDia[fixtureId];

          partidos.push({{
            fecha: fechaIso,
            fecha_hora_utc: event.date,
            equipo_local: {{ name: local.team?.displayName || 'N/A' }},
            equipo_visitante: {{ name: visitante.team?.displayName || 'N/A' }},
            goles_local: null,
            goles_visitante: null,
            hora: new Date(event.date).toLocaleTimeString('es-EC', {{ hour: '2-digit', minute: '2-digit', timeZone: 'America/Guayaquil' }}),
            prediccion_previa: pred ? {{
              prob_local: pred.prediccion.prob_local,
              prob_empate: pred.prediccion.prob_empate,
              prob_visitante: pred.prediccion.prob_visitante,
              diff_elo: pred.diff_elo,
              pj_h: pred.equipo_local.partidos_jugados,
              pj_a: pred.equipo_visitante.partidos_jugados,
              rating_local: pred.equipo_local.rating,
              rating_visitante: pred.equipo_visitante.rating,
              overperformance_h: pred.equipo_local.overperformance,
              overperformance_a: pred.equipo_visitante.overperformance,
            }} : null,
          }});
        }});
      }}
    }} else {{
      const archivo = 'data/historial_partidos/' + yyyy + '-' + mm + '.json';
      const resHistorial = await fetch(archivo);
      if (!resHistorial.ok) throw new Error('No se encontro historial para ' + fechaIso + ': ' + resHistorial.status);
      const dataHistorial = await resHistorial.json();
      partidos = (dataHistorial.partidos || []).filter(p => p.fecha === fechaIso);
    }}
    
    function buscarElo(nombre, teamId) {{
      if (teamId) {{
        const key = 'espn:' + teamId;
        if (equipos[key]) return equipos[key];
      }}
      const nombreLower = nombre.toLowerCase();
      for (const [key, eq] of Object.entries(equipos)) {{
        if (eq.nombre && eq.nombre.toLowerCase().includes(nombreLower)) return eq;
      }}
      return null;
    }}
    
    partidos.sort((a, b) => {{
      const ta = a.fecha_hora_utc || a.fecha_hora_espn || '';
      const tb = b.fecha_hora_utc || b.fecha_hora_espn || '';
      return ta.localeCompare(tb);
    }});

    let html = '';
    partidos.forEach(p => {{
      const nombreLocal = p.equipo_local?.name || 'N/A';
      const nombreVisitante = p.equipo_visitante?.name || 'N/A';
      const idLocal = p.equipo_local?.id;
      const idVisitante = p.equipo_visitante?.id;
      const gl = p.goles_local;
      const ga = p.goles_visitante;
      const marcador = gl != null ? gl + ' - ' + ga : '?';
      const hora = p.hora || '-';
      
      const eqLocal = buscarElo(nombreLocal, idLocal);
      const eqVisitante = buscarElo(nombreVisitante, idVisitante);
      const eloLocal = eqLocal ? eqLocal.rating.toFixed(0) : '-';
      const eloVisitante = eqVisitante ? eqVisitante.rating.toFixed(0) : '-';
      
      const statsLocal = calcularEstadisticas(nombreLocal, allMatches);
      const statsVisitante = calcularEstadisticas(nombreVisitante, allMatches);
      const formaLocal = statsLocal.form_score != null ? statsLocal.form_score : '-';
      const formaVisitante = statsVisitante.form_score != null ? statsVisitante.form_score : '-';
      
      const diff = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : '-';
      
      let acierto = '';
      const pred = p.prediccion_previa;
      const eloLocalPre = (cuando === 'ayer' && pred?.rating_local != null) ? pred.rating_local.toFixed(0) : null;
      const eloVisitantePre = (cuando === 'ayer' && pred?.rating_visitante != null) ? pred.rating_visitante.toFixed(0) : null;
      const opHPre = pred?.overperformance_h;
      const opAPre = pred?.overperformance_a;
      let diffMostrado = diff;
      let codigoPred = '-';
      let tooltipPred = '';
      if (pred) {{
        const tieneDiff = (pred.diff_elo !== undefined && pred.diff_elo !== null);
        codigoPred = tieneDiff
          ? codigoPrediccion(pred.diff_elo)
          : codigoPrediccionLegacy(pred.prob_local, pred.prob_empate, pred.prob_visitante);
        if (pred.diff_elo !== undefined) {{
          const signoPre = pred.diff_elo > 0 ? '+' : '';
          diffMostrado = `${{signoPre}}${{pred.diff_elo.toFixed(0)}}`;
        }}
        const probTxt = pred.prob_local.toFixed(0) + '% | ' + pred.prob_empate.toFixed(0) + '% | ' + pred.prob_visitante.toFixed(0) + '%';
        if (tieneDiff) {{
          const dAj = pred.diff_elo + VENTAJA_LOCAL_ELO;
          const sg = (n) => (n > 0 ? '+' : '') + n.toFixed(0);
          tooltipPred = `Código por Elo: dif ${{sg(pred.diff_elo)}} + ${{VENTAJA_LOCAL_ELO}} local = ${{sg(dAj)}} | Prob. modelo: ${{probTxt}}`;
        }} else {{
          tooltipPred = `Prob. modelo: ${{probTxt}}`;
        }}
        const pjSuficiente = (pred.pj_h === undefined || pred.pj_a === undefined)
          ? false
          : (pred.pj_h >= 5 && pred.pj_a >= 5);
        if (gl != null && ga != null && pjSuficiente) {{
          const esAcierto = aciertoConCodigo(codigoPred, gl, ga);
          acierto = esAcierto
            ? '<span class="acierto-ok">&#10003;</span>'
            : '<span class="acierto-fail">&#10007;</span>';
        }}
      }}
      
      const pjLocal = eqLocal ? (eqLocal.partidos_jugados || 0) : 0;
      const pjVisitante = eqVisitante ? (eqVisitante.partidos_jugados || 0) : 0;
      const pjLocalReal = eqLocal ? (eqLocal.pj_reales ?? eqLocal.partidos_jugados ?? 0) : 0;
      const pjVisitanteReal = eqVisitante ? (eqVisitante.pj_reales ?? eqVisitante.partidos_jugados ?? 0) : 0;
      const provH = eqLocal && pjLocalReal < 10 ? '<span class="badge-prov">PROV</span>' : '';
      const provV = eqVisitante && pjVisitanteReal < 10 ? '<span class="badge-prov">PROV</span>' : '';
      
      // Ayer siempre trae marcador (partidos terminados) -> FIN; Manana
      // nunca (aun no se juegan) -> vacio.
      const minutoCol = gl != null ? 'FIN' : '';
      
      const eloHAttr = eqLocal ? eqLocal.rating.toFixed(0) : 0;
      const formHAttr = statsLocal.form_score != null ? statsLocal.form_score : 0;
      const diffAttr = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : 0;
      const ligaSlug = p.liga_slug || '';
      
      html += `<tr class="excel-row" data-home="${{nombreLocal.toLowerCase()}}" data-away="${{nombreVisitante.toLowerCase()}}" data-pj-h="${{pjLocalReal}}" data-pj-a="${{pjVisitanteReal}}" data-elo-h="${{eloHAttr}}" data-form-h="${{formHAttr}}" data-diff="${{diffAttr}}" data-slug="${{ligaSlug}}" data-fecha="${{fechaIso}}">
        <td class="ex-fecha">${{fechaIso}}</td>
        <td class="ex-hora">${{hora}}</td>
        <td class="ex-local">${{nombreLocal}}${{provH}}</td>
        <td class="ex-elo ${{claseRating(eqLocal?.rating)}}">${{eloLocal}} <span class="pj-count">${{pjLocal}}PJ</span>${{eloLocalPre ? `<br><span class="elo-pre">antes: ${{eloLocalPre}}</span>` : ''}}</td>
        <td class="ex-forma ${{claseForma(formaLocal)}}">${{formaLocal}}</td>
        <td class="ex-racha">${{ultimos5Html(statsLocal.ultimos5)}}${{opHPre != null ? overperformanceBadgeJs(opHPre) : ''}}</td>
        <td class="ex-marcador marcador-finalizado">${{marcador}}</td>
        <td class="ex-minuto marcador-finalizado">${{minutoCol}}</td>
        <td class="ex-visitante">${{nombreVisitante}}${{provV}}</td>
        <td class="ex-elo ${{claseRating(eqVisitante?.rating)}}">${{eloVisitante}} <span class="pj-count">${{pjVisitante}}PJ</span>${{eloVisitantePre ? `<br><span class="elo-pre">antes: ${{eloVisitantePre}}</span>` : ''}}</td>
        <td class="ex-forma ${{claseForma(formaVisitante)}}">${{formaVisitante}}</td>
        <td class="ex-racha">${{ultimos5Html(statsVisitante.ultimos5)}}${{opAPre != null ? overperformanceBadgeJs(opAPre) : ''}}</td>
        <td class="ex-diff">${{diffMostrado}}</td>
        <td class="ex-pred" title="${{tooltipPred}}">${{codigoPred}}</td>
        <td class="ex-acierto">${{acierto}}</td>
        <td></td>
      </tr>`;
    }});
    
    if (html === '') {{
      html = '<tr><td colspan="16" style="text-align:center; padding:20px;">No hay partidos para esta fecha</td></tr>';
    }}
    
    tbody.innerHTML = html;
    aplicarFiltros();
  }} catch (error) {{
    console.error('[Ayer/Manana] Error:', error);
    tbody.innerHTML = `<tr><td colspan="16" style="text-align:center; padding:20px; color:#ef4444;">Error: ${{error.message}}</td></tr>`;
  }}
}}

async function refrescarMarcadoresHoy() {{
  try {{
    const fechaHoyIso = fechaEcuadorISO(0);
    const yyyymmdd = fechaHoyIso.replace(/-/g, '');
    const resESPN = await fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=' + yyyymmdd);
    if (!resESPN.ok) return;
    const dataESPN = await resESPN.json();

    const porFixture = {{}};
    (dataESPN.events || []).forEach(event => {{
      const comp = event.competitions?.[0];
      if (!comp) return;
      const status = comp.status?.type || {{}};
      const equipos = comp.competitors || [];
      const local = equipos.find(e => e.homeAway === 'home');
      const visitante = equipos.find(e => e.homeAway === 'away');
      porFixture[String(event.id)] = {{
        estado: status.state,  // 'pre' | 'in' | 'post'
        minuto: status.shortDetail || '',
        gl: local ? parseInt(local.score || 0) : null,
        ga: visitante ? parseInt(visitante.score || 0) : null,
      }};
    }});

    document.querySelectorAll('.excel-row[data-fixture-id]').forEach(row => {{
      const fid = row.dataset.fixtureId;
      if (!fid) return;
      const info = porFixture[fid];
      if (!info || info.estado === 'pre' || info.gl == null || info.ga == null) return;

      const claseMarcador = info.estado === 'post' ? 'marcador-finalizado' : 'marcador-vivo';
      const marcadorTxt = `${{info.gl}} - ${{info.ga}}`;

      const celdaMarcador = row.querySelector('.ex-marcador');
      if (celdaMarcador) {{
        celdaMarcador.textContent = marcadorTxt;
        celdaMarcador.className = 'ex-marcador ' + claseMarcador;
      }}

      const celdaMinuto = row.querySelector('.ex-minuto');
      if (celdaMinuto) {{
        celdaMinuto.textContent = info.estado === 'post' ? 'FIN' : (info.minuto || 'EN VIVO');
        celdaMinuto.className = 'ex-minuto ' + claseMarcador;
      }}

      const celdaAcierto = row.querySelector('.ex-acierto');
      const celdaPred = row.querySelector('.ex-pred');
      if (celdaAcierto && celdaPred) {{
        const codigo = celdaPred.textContent.trim();
        const pjHTotal = parseInt(row.dataset.pjHTotal || '0');
        const pjATotal = parseInt(row.dataset.pjATotal || '0');
        if (codigo && codigo !== '-' && pjHTotal >= 5 && pjATotal >= 5) {{
          const esAcierto = aciertoConCodigo(codigo, info.gl, info.ga);
          const esParcial = info.estado === 'in';
          const claseAcierto = esAcierto
            ? (esParcial ? 'acierto-parcial-ok' : 'acierto-ok')
            : (esParcial ? 'acierto-parcial-fail' : 'acierto-fail');
          const simbolo = esAcierto ? '&#10003;' : '&#10007;';
          // Limpia la clase que pudo poner Python en el <td> para que
          // el span recien escrito quede como unica fuente de verdad
          // (evita doble conteo en el % y heredar el opacity 0.55
          // cuando un parcial se vuelve definitivo sin recargar).
          celdaAcierto.className = 'ex-acierto';
          celdaAcierto.innerHTML = `<span class="${{claseAcierto}}">${{simbolo}}</span>`;
          celdaAcierto.title = esParcial ? 'Provisional -- puede cambiar mientras el partido siga en curso' : '';
        }}
      }}
    }});

    actualizarPorcentajeAciertos();
  }} catch (e) {{
    console.warn('[Hoy] No se pudo refrescar marcadores en vivo:', e);
  }}
}}

function iniciarRefrescoMarcadoresHoy() {{
  refrescarMarcadoresHoy();
  if (intervaloMarcadoresHoy) clearInterval(intervaloMarcadoresHoy);
  intervaloMarcadoresHoy = setInterval(refrescarMarcadoresHoy, 60000);
}}

function detenerRefrescoMarcadoresHoy() {{
  if (intervaloMarcadoresHoy) {{
    clearInterval(intervaloMarcadoresHoy);
    intervaloMarcadoresHoy = null;
  }}
}}

async function cargarEnVivo() {{
  const tbody = document.querySelector('.excel-table tbody');
  tbody.innerHTML = '<tr><td colspan="16" style="text-align:center; padding:20px;">Cargando partidos en vivo...</td></tr>';
  
  try {{
    const fechaHoyIso = fechaEcuadorISO(0);
    let prediccionesHoy = {{}};
    try {{
      const resPred = await fetch('data/predicciones_' + fechaHoyIso + '.json');
      if (resPred.ok) {{
        const dataPred = await resPred.json();
        (dataPred.predicciones || []).forEach(p => {{
          if (p.fixture_id) prediccionesHoy[p.fixture_id] = p;
        }});
      }}
    }} catch (e) {{
      console.warn('[EnVivo] No se pudo cargar predicciones de hoy:', e);
    }}

    const [dataESPN, dataRatings, allMatches] = await Promise.all([
      fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard').then(r => {{
        if (!r.ok) throw new Error('Error ESPN: ' + r.status);
        return r.json();
      }}),
      fetch('data/ratings_propios.json').then(r => r.json()),
      cargarTodoElHistorial()
    ]);
    const equipos = dataRatings.equipos || {{}};
    
    function buscarElo(nombre, teamId) {{
      if (teamId) {{
        const key = 'espn:' + teamId;
        if (equipos[key]) return equipos[key];
      }}
      const nombreLower = nombre.toLowerCase();
      for (const [key, eq] of Object.entries(equipos)) {{
        if (eq.nombre && eq.nombre.toLowerCase().includes(nombreLower)) return eq;
      }}
      return null;
    }}
    
    let html = '';
    if (dataESPN.events && dataESPN.events.length > 0) {{
      dataESPN.events.forEach(event => {{
        const competiciones = event.competitions || [];
        competiciones.forEach(comp => {{
          const status = comp.status?.type?.name || '';
          if (status !== 'STATUS_IN_PROGRESS' && status !== 'STATUS_HALFTIME' && status !== 'STATUS_SECOND_HALF' && status !== 'STATUS_FIRST_HALF' && status !== 'STATUS_END_PERIOD') return;
          const equiposComp = comp.competitors || [];
          if (equiposComp.length >= 2) {{
            const local = equiposComp.find(e => e.homeAway === 'home') || equiposComp[0];
            const visitante = equiposComp.find(e => e.homeAway === 'away') || equiposComp[1];
            const marcador = `${{local.score || 0}} - ${{visitante.score || 0}}`;
            const fechaLocal = new Date(event.date).toLocaleDateString('es-EC', {{ timeZone: 'America/Guayaquil', year: 'numeric', month: '2-digit', day: '2-digit' }}).split('/').reverse().join('-');
            const hora = new Date(event.date).toLocaleTimeString('es-EC', {{ hour: '2-digit', minute: '2-digit', timeZone: 'America/Guayaquil' }});
            
            const nombreLocal = local.team?.displayName || local.team?.shortDisplayName || 'N/A';
            const nombreVisitante = visitante.team?.displayName || visitante.team?.shortDisplayName || 'N/A';
            const idLocal = local.team?.id;
            const idVisitante = visitante.team?.id;
            const fixtureId = String(event.id);
            const predVivo = prediccionesHoy[fixtureId];
            let codigoPredVivo = '-';
            let tooltipPredVivo = '';
            if (predVivo) {{
              codigoPredVivo = codigoPrediccion(predVivo.diff_elo);
              const probTxt = predVivo.prediccion.prob_local.toFixed(0) + '% | ' + predVivo.prediccion.prob_empate.toFixed(0) + '% | ' + predVivo.prediccion.prob_visitante.toFixed(0) + '%';
              const dAj = predVivo.diff_elo + VENTAJA_LOCAL_ELO;
              const sg = (n) => (n > 0 ? '+' : '') + n.toFixed(0);
              tooltipPredVivo = `Código por Elo: dif ${{sg(predVivo.diff_elo)}} + ${{VENTAJA_LOCAL_ELO}} local = ${{sg(dAj)}} | Prob. modelo: ${{probTxt}}`;
            }}
            let aciertoVivo = '';
            if (predVivo) {{
              const pjHVivo = predVivo.equipo_local?.partidos_jugados;
              const pjAVivo = predVivo.equipo_visitante?.partidos_jugados;
              const pjSuficienteVivo = (pjHVivo != null && pjAVivo != null) && pjHVivo >= 5 && pjAVivo >= 5;
              const glVivo = parseInt(local.score || 0);
              const gaVivo = parseInt(visitante.score || 0);
              if (pjSuficienteVivo) {{
                const esAciertoVivo = aciertoConCodigo(codigoPredVivo, glVivo, gaVivo);
                aciertoVivo = esAciertoVivo
                  ? '<span class="acierto-parcial-ok">&#10003;</span>'
                  : '<span class="acierto-parcial-fail">&#10007;</span>';
              }}
            }}
            
            const eqLocal = buscarElo(nombreLocal, idLocal);
            const eqVisitante = buscarElo(nombreVisitante, idVisitante);
            const eloLocal = eqLocal ? eqLocal.rating.toFixed(0) : '-';
            const eloVisitante = eqVisitante ? eqVisitante.rating.toFixed(0) : '-';
            
            const statsLocal = calcularEstadisticas(nombreLocal, allMatches);
            const statsVisitante = calcularEstadisticas(nombreVisitante, allMatches);
            const formaLocal = statsLocal.form_score != null ? statsLocal.form_score : '-';
            const formaVisitante = statsVisitante.form_score != null ? statsVisitante.form_score : '-';
            
            const diff = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : '-';
            
            const pjLocal = eqLocal ? (eqLocal.partidos_jugados || 0) : 0;
            const pjVisitante = eqVisitante ? (eqVisitante.partidos_jugados || 0) : 0;
            const pjLocalReal = eqLocal ? (eqLocal.pj_reales ?? eqLocal.partidos_jugados ?? 0) : 0;
            const pjVisitanteReal = eqVisitante ? (eqVisitante.pj_reales ?? eqVisitante.partidos_jugados ?? 0) : 0;
            const provH = eqLocal && pjLocalReal < 10 ? '<span class="badge-prov">PROV</span>' : '';
            const provV = eqVisitante && pjVisitanteReal < 10 ? '<span class="badge-prov">PROV</span>' : '';
            
            const eloHAttr = eqLocal ? eqLocal.rating.toFixed(0) : 0;
            const formHAttr = statsLocal.form_score != null ? statsLocal.form_score : 0;
            const diffAttr = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : 0;
            
            html += `<tr class="excel-row live-row" data-home="${{nombreLocal.toLowerCase()}}" data-away="${{nombreVisitante.toLowerCase()}}" data-pj-h="${{pjLocalReal}}" data-pj-a="${{pjVisitanteReal}}" data-elo-h="${{eloHAttr}}" data-form-h="${{formHAttr}}" data-diff="${{diffAttr}}">
              <td class="ex-fecha">${{fechaLocal}}</td>
              <td class="ex-hora live-indicator">${{hora}}</td>
              <td class="ex-local">${{nombreLocal}}${{provH}}</td>
              <td class="ex-elo ${{claseRating(eqLocal?.rating)}}">${{eloLocal}}</td>
              <td class="ex-forma ${{claseForma(formaLocal)}}">${{formaLocal}}</td>
              <td class="ex-racha">${{ultimos5Html(statsLocal.ultimos5)}}</td>
              <td class="ex-marcador marcador-vivo">${{marcador}}</td>
              <td class="ex-minuto marcador-vivo">${{comp.status?.type?.shortDetail || ''}}</td>
              <td class="ex-visitante">${{nombreVisitante}}${{provV}}</td>
              <td class="ex-elo ${{claseRating(eqVisitante?.rating)}}">${{eloVisitante}}</td>
              <td class="ex-forma ${{claseForma(formaVisitante)}}">${{formaVisitante}}</td>
              <td class="ex-racha">${{ultimos5Html(statsVisitante.ultimos5)}}</td>
              <td class="ex-diff">${{diff}}</td>
              <td class="ex-pred" title="${{tooltipPredVivo}}">${{codigoPredVivo}}</td>
              <td class="ex-acierto" title="Provisional -- puede cambiar mientras el partido siga en curso">${{aciertoVivo}}</td>
              <td></td>
            </tr>`;
          }}
        }});
      }});
    }}
    
    if (html === '') {{
      html = '<tr><td colspan="16" style="text-align:center; padding:20px;">No hay partidos en vivo ahora</td></tr>';
    }}
    
    tbody.innerHTML = html;
    aplicarFiltros();
  }} catch (error) {{
    console.error('[EnVivo] Error:', error);
    tbody.innerHTML = `<tr><td colspan="16" style="text-align:center; padding:20px; color:#ef4444;">Error: ${{error.message}}</td></tr>`;
  }}
}}
</script>
</body>
</html>'''
    return html


def generar(predicciones=None, archivo_entrada=None, archivo_salida=None, fecha=None):
    if predicciones is None:
        if fecha:
            archivo_fecha = DATA_DIR / f"predicciones_{fecha}.json"
            if archivo_fecha.exists():
                archivo_entrada = archivo_fecha
            else:
                archivo_entrada = archivo_entrada or ARCHIVO_PREDICCIONES
        else:
            archivo_entrada = archivo_entrada or ARCHIVO_PREDICCIONES
        
        if not archivo_entrada.exists():
            print(f"[ERROR] No existe {archivo_entrada}. Ejecuta predict.py primero.")
            return None
        data = json.loads(archivo_entrada.read_text(encoding="utf-8"))
        predicciones = data.get("predicciones", [])

    if not predicciones:
        print("[AVISO] No hay predicciones para generar el dashboard.")
        return None

    if not fecha:
        fecha = datetime.now(ZONA_ECUADOR).strftime("%Y-%m-%d")

    build_ts = datetime.now(ZONA_ECUADOR).strftime("%Y%m%d%H%M%S")

    html = generar_html(predicciones, fecha_consulta=fecha, build_ts=build_ts)
    salida = archivo_salida or ARCHIVO_SALIDA
    Path(salida).write_text(html, encoding="utf-8")
    print(f"Dashboard generado: {salida}")
    return str(salida)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el dashboard HTML.")
    parser.add_argument("--entrada", help="Archivo JSON de predicciones")
    parser.add_argument("--salida", help="Archivo HTML de salida")
    parser.add_argument("--fecha", help="Fecha YYYY-MM-DD para cargar predicciones específicas")
    args = parser.parse_args()
    generar(archivo_entrada=args.entrada, archivo_salida=args.salida, fecha=args.fecha)
