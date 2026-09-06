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

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_PREDICCIONES = DATA_DIR / "predicciones_cache.json"
ARCHIVO_SALIDA = Path(__file__).parent / "dashboard.html"
DIR_HISTORIAL = DATA_DIR / "historial_partidos"


from datetime import datetime, timezone, timedelta

ZONA_ECUADOR = timezone(timedelta(hours=-5))


def _cargar_resultados_fecha(fecha_iso):
    if not fecha_iso:
        return {}
    aaaa_mm = fecha_iso[:7]
    archivo = DIR_HISTORIAL / f"{aaaa_mm}.json"
    if not archivo.exists():
        return {}
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
        resultados = {}
        for p in datos.get("partidos", []):
            if p.get("fecha") == fecha_iso:
                fixture_id = p.get("fixture_id", "")
                if fixture_id:
                    resultados[f"fx:{fixture_id}"] = {
                        "goles_local": p.get("goles_local", 0),
                        "goles_visitante": p.get("goles_visitante", 0)
                    }
                nombre_l = p.get("equipo_local", {}).get("name", "").lower()
                nombre_v = p.get("equipo_visitante", {}).get("name", "").lower()
                if nombre_l and nombre_v:
                    resultados[f"{nombre_l}_{nombre_v}"] = {
                        "goles_local": p.get("goles_local", 0),
                        "goles_visitante": p.get("goles_visitante", 0)
                    }
        return resultados
    except Exception:
        return {}


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
    if op is None or op == 0:
        return ""
    color = "#22c55e" if op > 10 else "#ef4444" if op < -10 else "#94a3b8"
    signo = "+" if op > 0 else ""
    return f'<span class="op-badge" title="Sobre-rendimiento vs ELO esperado" style="color:{color}">{signo}{op:.0f}</span>'


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


def generar_html(predicciones, titulo="ELO + Tilt Tracker", fecha_consulta=None, build_ts=None):
    ligas = _agrupar_por_liga(predicciones)
    todos_equipos = {}
    for p in predicciones:
        for lado in ["equipo_local", "equipo_visitante"]:
            eq = p[lado]
            todos_equipos[eq["id"]] = eq

    ranking_forma = sorted(todos_equipos.values(), key=lambda x: x.get("form_score", 50), reverse=True)[:30]
    ranking_elo = sorted(todos_equipos.values(), key=lambda x: x.get("rating", 1500), reverse=True)[:30]

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

        diff_signo = "+" if diff > 0 else ""

        nombre_limpio_h = h['nombre'].replace("'", "").replace('"', '')
        nombre_limpio_a = a['nombre'].replace("'", "").replace('"', '')
        busqueda = f"{nombre_limpio_h} vs {nombre_limpio_a} {fecha_d} site:bessoccer.com"
        url_google = f"https://www.google.com/search?q={busqueda.replace(' ', '+')}"

        u5_h = h.get("ultimos5", {})
        u5_a = a.get("ultimos5", {})

        fixture_id = p.get("fixture_id", "")
        key_fx = f"fx:{fixture_id}" if fixture_id else ""
        key = f"{h['nombre'].lower()}_{a['nombre'].lower()}"
        key_inv = f"{a['nombre'].lower()}_{h['nombre'].lower()}"
        resultado = resultados.get(key_fx) if key_fx else None
        if not resultado:
            resultado = resultados.get(key) or resultados.get(key_inv)
        if resultado:
            marcador = f"{resultado['goles_local']} - {resultado['goles_visitante']}"
            gl = resultado['goles_local']
            ga = resultado['goles_visitante']
            max_prob = max(prob_l, prob_v)
            if max_prob > 69:
                if prob_l > prob_v:
                    acierto = "✓" if gl > ga else "✗"
                else:
                    acierto = "✓" if ga > gl else "✗"
            else:
                acierto = "-"
        else:
            marcador = "?"
            acierto = ""

        excel_rows += f'''<tr class="excel-row" data-slug="{slug}" data-fecha="{fecha_d}" data-elo-h="{h.get('rating', 0):.0f}" data-form-h="{h.get('form_score', 50):.0f}" data-home="{h['nombre'].lower()}" data-away="{a['nombre'].lower()}" data-diff="{diff:.0f}">
  <td class="ex-fecha">{fecha_d}</td>
  <td class="ex-hora">{hora}</td>
  <td class="ex-local"><a href="{url_google}" target="_blank">{h['nombre']}</a></td>
  <td class="ex-elo {_clase_rating(h.get('rating'))}">{h.get('rating', 0):.0f}</td>
  <td class="ex-forma {_clase_forma(h.get('form_score'))}">{h.get('form_score', 50):.0f}</td>
  <td class="ex-racha">{_ultimos5_html(u5_h)}</td>
  <td class="ex-marcador">{marcador}</td>
  <td class="ex-visitante"><a href="{url_google}" target="_blank">{a['nombre']}</a></td>
  <td class="ex-elo {_clase_rating(a.get('rating'))}">{a.get('rating', 0):.0f}</td>
  <td class="ex-forma {_clase_forma(a.get('form_score'))}">{a.get('form_score', 50):.0f}</td>
  <td class="ex-racha">{_ultimos5_html(u5_a)}</td>
  <td class="ex-diff" style="color:{'#22c55e' if diff > 0 else '#ef4444' if diff < 0 else '#94a3b8'}">{diff_signo}{diff:.0f}</td>
  <td class="ex-pred best">{prob_l:.0f}% | {prob_e:.0f}% | {prob_v:.0f}%</td>
  <td class="ex-acierto {'acierto-ok' if acierto == '✓' else 'acierto-fail' if acierto == '✗' else ''}">{acierto}</td>
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

/* Match cards - grid of boxes */
.match-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
.mc {{ background: var(--surface); border-radius: 10px; padding: 12px;
       border: 1px solid var(--border); transition: all 0.2s; position: relative; overflow: hidden; }}
.mc:hover {{ border-color: var(--accent); transform: translateY(-2px);
             box-shadow: 0 6px 24px rgba(56,189,248,0.1); }}
.card-highlight {{ border-color: var(--accent); box-shadow: 0 0 0 1px rgba(56,189,248,0.2); }}
.card-suspense {{ border-color: var(--orange); box-shadow: 0 0 0 1px rgba(249,115,22,0.2); }}

.mc-datetime {{ display: flex; justify-content: space-between; align-items: center;
                margin-bottom: 6px; }}
.mc-date {{ font-size: 0.72em; color: var(--text3); font-weight: 500; }}
.mc-time {{ font-size: 0.8em; color: var(--accent); font-weight: 700; }}

.mc-liga-tag {{ font-size: 0.65em; color: var(--text3); background: var(--surface2);
                padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 8px;
                max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}

.mc-teams {{ display: flex; flex-direction: column; gap: 4px; }}
.mc-team-row {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
.mc-team-info {{ display: flex; flex-direction: column; gap: 1px; min-width: 0; flex: 1; }}
.mc-team-name {{ font-weight: 600; font-size: 0.85em; line-height: 1.2;
                 overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.mc-tilt-line {{ display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }}

.mc-prob {{ font-size: 1.3em; font-weight: 800; color: var(--text3); white-space: nowrap;
            min-width: 48px; text-align: right; }}
.mc-prob.best {{ color: var(--accent); }}

.mc-draw-row {{ text-align: center; padding: 2px 0; font-size: 0.85em; }}
.mc-draw-pct {{ color: var(--text2); font-weight: 700; font-size: 1.2em; }}
.mc-draw-label {{ color: var(--text3); font-size: 0.8em; font-weight: 500; }}

.mc-link {{ text-decoration: none; color: inherit; display: block; cursor: pointer; }}

.mc-meta-row {{ display: flex; justify-content: space-between; margin-top: 8px;
                padding-top: 6px; border-top: 1px solid var(--border);
                font-size: 0.68em; color: var(--text3); gap: 4px; flex-wrap: wrap; }}

/* Badges & tags */
.elo {{ padding: 1px 7px; border-radius: 10px; font-size: 0.8em; font-weight: 700; }}
.elite {{ background: rgba(56,189,248,0.15); color: var(--accent); }}
.above {{ background: rgba(34,197,94,0.12); color: var(--green); }}
.average {{ background: rgba(148,163,184,0.12); color: var(--text2); }}
.below {{ background: rgba(239,68,68,0.12); color: var(--red); }}

.badge-prov {{ font-size: 0.6em; padding: 1px 5px; background: rgba(234,179,8,0.15);
               color: var(--yellow); border-radius: 4px; font-weight: 700; letter-spacing: 0.04em; }}

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

@media (max-width: 768px) {{
  .match-grid {{ grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 8px; }}
  .mc {{ padding: 10px; }}
  .mc-team-name {{ font-size: 0.8em; }}
  .mc-prob {{ font-size: 1.1em; }}
  .stats {{ gap: 16px; }}
  .tabs {{ gap: 3px; }}
  .tab {{ padding: 5px 10px; font-size: 0.78em; }}
}}
@media (max-width: 480px) {{
  .match-grid {{ grid-template-columns: 1fr; }}
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
            <th>Visitante</th>
            <th>ELO</th>
            <th>Forma</th>
            <th>Racha</th>
            <th>Diff</th>
            <th>Pred</th>
            <th>Acierto</th>
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
let catActual = 'todos';
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
  document.querySelectorAll('.mc-link').forEach(c => {{
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

function setCat(cat) {{
  catActual = cat;
  document.querySelectorAll('#catTabs .tab').forEach(t => t.classList.toggle('active', t.dataset.cat === cat));
  aplicarFiltros();
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
  document.querySelectorAll('.excel-row').forEach(row => {{
    const local = row.dataset.home || '';
    const away = row.dataset.away || '';
    const show = !q || local.includes(q) || away.includes(q);
    row.style.display = show ? '' : 'none';
  }});
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
    if (criterion === 'diff-desc') return parseFloat(b.dataset.diff || 0) - parseFloat(a.dataset.diff || 0);
    if (criterion === 'diff-asc') return parseFloat(a.dataset.diff || 0) - parseFloat(b.dataset.diff || 0);
    return 0;
  }});
  rows.forEach(row => tbody.appendChild(row));
}}

initLeagueButtons();
initCountryButtons();

function cambiarFecha(valor) {{
  if (valor === 'hoy') {{
    window.location.href = window.location.href.split('?')[0];
  }} else if (valor === 'ayer') {{
    cargarHistorial('ayer');
  }} else if (valor === 'manana') {{
    cargarHistorial('manana');
  }} else if (valor === 'en-vivo') {{
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

function streakHtml(s) {{
  if (!s) return '-';
  const t = s.tipo || 'N/A';
  const c = s.cantidad || 0;
  if (t === 'W') return `<span class="streak-w">${{c}}V</span>`;
  if (t === 'D') return `<span class="streak-d">${{c}}E</span>`;
  if (t === 'L') return `<span class="streak-l">${{c}}D</span>`;
  return '-';
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

async function cargarHistorial(cuando) {{
  const tbody = document.querySelector('.excel-table tbody');
  tbody.innerHTML = '<tr><td colspan="14" style="text-align:center; padding:20px;">Cargando...</td></tr>';
  
  const fecha = new Date();
  if (cuando === 'ayer') fecha.setDate(fecha.getDate() - 1);
  if (cuando === 'manana') fecha.setDate(fecha.getDate() + 1);
  const yyyy = fecha.getFullYear();
  const mm = String(fecha.getMonth() + 1).padStart(2, '0');
  const dd = String(fecha.getDate()).padStart(2, '0');
  const fechaIso = yyyy + '-' + mm + '-' + dd;
  
  try {{
    const [dataRatings, allMatches] = await Promise.all([
      fetch('data/ratings_propios.json').then(r => r.json()),
      cargarTodoElHistorial()
    ]);
    const equipos = dataRatings.equipos || {{}};
    
    let partidos = [];
    
    if (cuando === 'manana') {{
      const resESPN = await fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard?dates=' + yyyy + mm + dd);
      if (!resESPN.ok) throw new Error('Error ESPN: ' + resESPN.status);
      const dataESPN = await resESPN.json();
      if (dataESPN.events) {{
        dataESPN.events.forEach(event => {{
          const comp = event.competitions?.[0];
          if (!comp) return;
          const equiposComp = comp.competitors || [];
          if (equiposComp.length < 2) return;
          const local = equiposComp.find(e => e.homeAway === 'home') || equiposComp[0];
          const visitante = equiposComp.find(e => e.homeAway === 'away') || equiposComp[1];
          partidos.push({{
            fecha: fechaIso,
            equipo_local: {{ name: local.team?.displayName || 'N/A' }},
            equipo_visitante: {{ name: visitante.team?.displayName || 'N/A' }},
            goles_local: null,
            goles_visitante: null,
            hora: new Date(event.date).toLocaleTimeString('es-EC', {{ hour: '2-digit', minute: '2-digit', timeZone: 'America/Guayaquil' }})
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
    
    function buscarElo(nombre) {{
      const nombreLower = nombre.toLowerCase();
      for (const [key, eq] of Object.entries(equipos)) {{
        if (eq.nombre && eq.nombre.toLowerCase().includes(nombreLower)) return eq;
      }}
      return null;
    }}
    
    let html = '';
    partidos.forEach(p => {{
      const nombreLocal = p.equipo_local?.name || 'N/A';
      const nombreVisitante = p.equipo_visitante?.name || 'N/A';
      const gl = p.goles_local;
      const ga = p.goles_visitante;
      const marcador = gl != null ? gl + ' - ' + ga : '?';
      const hora = p.hora || '-';
      
      const eqLocal = buscarElo(nombreLocal);
      const eqVisitante = buscarElo(nombreVisitante);
      const eloLocal = eqLocal ? eqLocal.rating.toFixed(0) : '-';
      const eloVisitante = eqVisitante ? eqVisitante.rating.toFixed(0) : '-';
      
      const statsLocal = calcularEstadisticas(nombreLocal, allMatches);
      const statsVisitante = calcularEstadisticas(nombreVisitante, allMatches);
      const formaLocal = statsLocal.form_score != null ? statsLocal.form_score : '-';
      const formaVisitante = statsVisitante.form_score != null ? statsVisitante.form_score : '-';
      
      const diff = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : '-';
      
      let acierto = '';
      if (gl != null && ga != null && eqLocal && eqVisitante) {{
        const probLocal = 50 + (eqLocal.rating - eqVisitante.rating) / 40;
        const probVisitante = 100 - probLocal - 25;
        const maxProb = Math.max(probLocal, probVisitante);
        if (maxProb > 69) {{
          if (probLocal > probVisitante) acierto = gl > ga ? '<span class="acierto-ok">&#10003;</span>' : '<span class="acierto-fail">&#10007;</span>';
          else acierto = ga > gl ? '<span class="acierto-ok">&#10003;</span>' : '<span class="acierto-fail">&#10007;</span>';
        }}
      }}
      
      html += `<tr class="excel-row" data-home="${{nombreLocal.toLowerCase()}}" data-away="${{nombreVisitante.toLowerCase()}}">
        <td class="ex-fecha">${{fechaIso}}</td>
        <td class="ex-hora">${{hora}}</td>
        <td class="ex-local">${{nombreLocal}}</td>
        <td class="ex-elo ${{claseRating(eqLocal?.rating)}}">${{eloLocal}}</td>
        <td class="ex-forma ${{claseForma(formaLocal)}}">${{formaLocal}}</td>
        <td class="ex-racha">${{streakHtml(statsLocal.streak)}}</td>
        <td class="ex-marcador">${{marcador}}</td>
        <td class="ex-visitante">${{nombreVisitante}}</td>
        <td class="ex-elo ${{claseRating(eqVisitante?.rating)}}">${{eloVisitante}}</td>
        <td class="ex-forma ${{claseForma(formaVisitante)}}">${{formaVisitante}}</td>
        <td class="ex-racha">${{streakHtml(statsVisitante.streak)}}</td>
        <td class="ex-diff">${{diff}}</td>
        <td class="ex-pred">-</td>
        <td class="ex-acierto">${{acierto}}</td>
      </tr>`;
    }});
    
    if (html === '') {{
      html = '<tr><td colspan="14" style="text-align:center; padding:20px;">No hay partidos para esta fecha</td></tr>';
    }}
    
    tbody.innerHTML = html;
  }} catch (error) {{
    console.error('[Ayer/Manana] Error:', error);
    tbody.innerHTML = `<tr><td colspan="14" style="text-align:center; padding:20px; color:#ef4444;">Error: ${{error.message}}</td></tr>`;
  }}
}}

async function cargarEnVivo() {{
  const tbody = document.querySelector('.excel-table tbody');
  tbody.innerHTML = '<tr><td colspan="14" style="text-align:center; padding:20px;">Cargando partidos en vivo...</td></tr>';
  
  try {{
    const [dataESPN, dataRatings, allMatches] = await Promise.all([
      fetch('https://site.api.espn.com/apis/site/v2/sports/soccer/all/scoreboard').then(r => {{
        if (!r.ok) throw new Error('Error ESPN: ' + r.status);
        return r.json();
      }}),
      fetch('data/ratings_propios.json').then(r => r.json()),
      cargarTodoElHistorial()
    ]);
    const equipos = dataRatings.equipos || {{}};
    
    function buscarElo(nombre) {{
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
            
            const eqLocal = buscarElo(nombreLocal);
            const eqVisitante = buscarElo(nombreVisitante);
            const eloLocal = eqLocal ? eqLocal.rating.toFixed(0) : '-';
            const eloVisitante = eqVisitante ? eqVisitante.rating.toFixed(0) : '-';
            
            const statsLocal = calcularEstadisticas(nombreLocal, allMatches);
            const statsVisitante = calcularEstadisticas(nombreVisitante, allMatches);
            const formaLocal = statsLocal.form_score != null ? statsLocal.form_score : '-';
            const formaVisitante = statsVisitante.form_score != null ? statsVisitante.form_score : '-';
            
            const diff = (eqLocal && eqVisitante) ? (eqLocal.rating - eqVisitante.rating).toFixed(0) : '-';
            
            html += `<tr class="excel-row live-row" data-home="${{nombreLocal.toLowerCase()}}" data-away="${{nombreVisitante.toLowerCase()}}">
              <td class="ex-fecha">${{fechaLocal}}</td>
              <td class="ex-hora live-indicator">${{hora}}</td>
              <td class="ex-local">${{nombreLocal}}</td>
              <td class="ex-elo ${{claseRating(eqLocal?.rating)}}">${{eloLocal}}</td>
              <td class="ex-forma ${{claseForma(formaLocal)}}">${{formaLocal}}</td>
              <td class="ex-racha">${{streakHtml(statsLocal.streak)}}</td>
              <td class="ex-marcador">${{marcador}}</td>
              <td class="ex-visitante">${{nombreVisitante}}</td>
              <td class="ex-elo ${{claseRating(eqVisitante?.rating)}}">${{eloVisitante}}</td>
              <td class="ex-forma ${{claseForma(formaVisitante)}}">${{formaVisitante}}</td>
              <td class="ex-racha">${{streakHtml(statsVisitante.streak)}}</td>
              <td class="ex-diff">${{diff}}</td>
              <td class="ex-pred">${{comp.status?.type?.shortDetail || ''}}</td>
              <td class="ex-acierto"></td>
            </tr>`;
          }}
        }});
      }});
    }}
    
    if (html === '') {{
      html = '<tr><td colspan="14" style="text-align:center; padding:20px;">No hay partidos en vivo ahora</td></tr>';
    }}
    
    tbody.innerHTML = html;
  }} catch (error) {{
    console.error('[EnVivo] Error:', error);
    tbody.innerHTML = `<tr><td colspan="14" style="text-align:center; padding:20px; color:#ef4444;">Error: ${{error.message}}</td></tr>`;
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
