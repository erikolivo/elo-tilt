"""
generar_dashboard.py
--------------------
Genera el dashboard HTML autocontenido con las predicciones
y datos de tilt/momentum de los partidos a jugarse.

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


def _clase_forma(score):
    if score >= 70:
        return "forma-alta"
    elif score >= 40:
        return "forma-media"
    return "forma-baja"


def _icono_momentum(direccion):
    if direccion == "up":
        return '<span class="momentum-up">&#9650;</span>'
    elif direccion == "down":
        return '<span class="momentum-down">&#9660;</span>'
    return '<span class="momentum-stable">&#9644;</span>'


def _streak_html(streak):
    tipo = streak.get("tipo", "N/A")
    cant = streak.get("cantidad", 0)
    if tipo == "W":
        return f'<span class="streak-w">{cant}V</span>'
    elif tipo == "D":
        return f'<span class="streak-d">{cant}E</span>'
    elif tipo == "L":
        return f'<span class="streak-l">{cant}D</span>'
    return '<span class="streak-na">-</span>'


def _barra_prob(valor):
    if valor >= 50:
        return f'<div class="barra barra-alta" style="width:{valor}%">{valor:.0f}%</div>'
    elif valor >= 30:
        return f'<div class="barra barra-media" style="width:{valor}%">{valor:.0f}%</div>'
    return f'<div class="barra barra-baja" style="width:{valor}%">{valor:.0f}%</div>'


def _sparkline_html(form_score):
    width = 60
    height = 20
    fill = int(form_score / 100 * width)
    color = "#22c55e" if form_score >= 70 else "#eab308" if form_score >= 40 else "#ef4444"
    return (f'<svg width="{width}" height="{height}" class="sparkline">'
            f'<rect x="0" y="0" width="{fill}" height="{height}" fill="{color}" rx="3"/>'
            f'<rect x="{fill}" y="0" width="{width - fill}" height="{height}" fill="#374151" rx="3"/>'
            f'</svg>')


def _agrupar_por_liga(predicciones):
    ligas = {}
    for p in predicciones:
        liga_key = p.get("liga_slug") or p.get("liga", "Desconocida")
        liga_nombre = p.get("liga", liga_key)
        if liga_key not in ligas:
            ligas[liga_key] = {"nombre": liga_nombre, "partidos": []}
        ligas[liga_key]["partidos"].append(p)
    return ligas


def generar_html(predicciones, titulo="ELO + Tilt Tracker"):
    ligas = _agrupar_por_liga(predicciones)

    todos_equipos = []
    for p in predicciones:
        for lado in ["equipo_local", "equipo_visitante"]:
            eq = p[lado]
            todos_equipos.append(eq)

    equipos_unicos = {}
    for eq in todos_equipos:
        eid = eq["id"]
        if eid not in equipos_unicos:
            equipos_unicos[eid] = eq

    ranking = sorted(equipos_unicos.values(), key=lambda x: x["form_score"], reverse=True)

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{titulo}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       background: #0f172a; color: #e2e8f0; padding: 20px; }}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ text-align: center; font-size: 1.8em; margin-bottom: 5px; color: #38bdf8; }}
.subtitle {{ text-align: center; color: #94a3b8; margin-bottom: 20px; font-size: 0.9em; }}
.section {{ margin-bottom: 30px; }}
.section-title {{ font-size: 1.2em; color: #38bdf8; margin-bottom: 10px;
                  border-bottom: 1px solid #1e293b; padding-bottom: 5px; }}
.liga-header {{ background: #1e293b; padding: 10px 15px; border-radius: 8px 8px 0 0;
                font-weight: bold; color: #38bdf8; margin-top: 15px; }}
.match-card {{ background: #1e293b; padding: 15px; margin-bottom: 2px; display: grid;
               grid-template-columns: 1fr auto 1fr; gap: 10px; align-items: center; }}
.match-card:last-child {{ border-radius: 0 0 8px 8px; }}
.team {{ display: flex; flex-direction: column; gap: 4px; }}
.team-name {{ font-weight: 600; font-size: 1em; }}
.team-small {{ font-size: 0.8em; color: #94a3b8; }}
.team-right {{ text-align: right; }}
.predicciones {{ display: flex; flex-direction: column; gap: 4px; min-width: 120px; }}
.pred-row {{ display: flex; align-items: center; gap: 6px; font-size: 0.85em; }}
.pred-label {{ width: 16px; text-align: center; font-weight: bold; }}
.pred-label.home {{ color: #38bdf8; }}
.pred-label.draw {{ color: #94a3b8; }}
.pred-label.away {{ color: #f97316; }}
.barra {{ height: 18px; border-radius: 4px; display: flex; align-items: center;
          padding: 0 6px; font-size: 0.75em; font-weight: bold; color: white;
          min-width: 30px; transition: width 0.3s; }}
.barra-alta {{ background: linear-gradient(90deg, #22c55e, #16a34a); }}
.barra-media {{ background: linear-gradient(90deg, #eab308, #ca8a04); }}
.barra-baja {{ background: linear-gradient(90deg, #ef4444, #dc2626); }}
.tilt-info {{ display: flex; gap: 8px; font-size: 0.8em; color: #94a3b8;
              flex-wrap: wrap; margin-top: 4px; }}
.tilt-item {{ display: flex; align-items: center; gap: 3px; }}
.forma-alta {{ color: #22c55e; }}
.forma-media {{ color: #eab308; }}
.forma-baja {{ color: #ef4444; }}
.momentum-up {{ color: #22c55e; }}
.momentum-down {{ color: #ef4444; }}
.momentum-stable {{ color: #94a3b8; }}
.streak-w {{ color: #22c55e; font-weight: bold; }}
.streak-d {{ color: #94a3b8; font-weight: bold; }}
.streak-l {{ color: #ef4444; font-weight: bold; }}
.streak-na {{ color: #64748b; }}
.elo-badge {{ background: #334155; padding: 2px 8px; border-radius: 12px;
              font-size: 0.8em; font-weight: bold; color: #38bdf8; }}
.sparkline {{ border-radius: 3px; }}
.ranking-table {{ width: 100%; border-collapse: collapse; }}
.ranking-table th {{ text-align: left; padding: 8px 12px; background: #1e293b;
                     color: #38bdf8; font-size: 0.85em; }}
.ranking-table td {{ padding: 8px 12px; border-bottom: 1px solid #1e293b; font-size: 0.9em; }}
.ranking-table tr:hover {{ background: #1e293b; }}
.rank-num {{ color: #64748b; font-weight: bold; width: 30px; }}
.confianza {{ font-size: 0.75em; color: #64748b; }}
.filters {{ display: flex; gap: 10px; margin-bottom: 15px; flex-wrap: wrap; }}
.filter-btn {{ background: #1e293b; border: 1px solid #334155; color: #e2e8f0;
               padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85em; }}
.filter-btn:hover, .filter-btn.active {{ background: #38bdf8; color: #0f172a; border-color: #38bdf8; }}
.updated {{ text-align: center; color: #475569; font-size: 0.8em; margin-top: 20px; }}
</style>
</head>
<body>
<div class="container">
<h1>{titulo}</h1>
<p class="subtitle">Partidos a jugarse | Rating Glicko-2 + Tilt/Momentum</p>

<div class="filters">
<button class="filter-btn active" onclick="filtrarLiga('todas')">Todas</button>
'''

    for liga_key in sorted(ligas.keys()):
        nombre = ligas[liga_key]["nombre"]
        html += f'<button class="filter-btn" onclick="filtrarLiga(\'{liga_key}\')">{nombre}</button>\n'

    html += '</div>\n<div class="section" id="partidos">\n'

    for liga_key, liga_data in sorted(ligas.items()):
        html += f'<div class="liga-header" data-liga="{liga_key}">{liga_data["nombre"]}</div>\n'
        for p in liga_data["partidos"]:
            h = p["equipo_local"]
            a = p["equipo_visitante"]
            pred = p["prediccion"]

            html += f'''<div class="match-card" data-liga="{liga_key}">
<div class="team">
  <div class="team-name">{h["nombre"]}</div>
  <div class="team-small">
    <span class="elo-badge">{h["rating"]:.0f}</span>
    {_streak_html(h["streak"])}
  </div>
  <div class="tilt-info">
    <span class="tilt-item {_clase_forma(h["form_score"])}">Forma: {h["form_score"]:.0f}</span>
    <span class="tilt-item">{_icono_momentum(h["momentum"])}</span>
    {_sparkline_html(h["form_score"])}
  </div>
</div>
<div class="predicciones">
  <div class="pred-row">
    <span class="pred-label home">L</span>
    {_barra_prob(pred["prob_local"])}
  </div>
  <div class="pred-row">
    <span class="pred-label draw">E</span>
    {_barra_prob(pred["prob_empate"])}
  </div>
  <div class="pred-row">
    <span class="pred-label away">V</span>
    {_barra_prob(pred["prob_visitante"])}
  </div>
</div>
<div class="team team-right">
  <div class="team-name">{a["nombre"]}</div>
  <div class="team-small">
    {_streak_html(a["streak"])}
    <span class="elo-badge">{a["rating"]:.0f}</span>
  </div>
  <div class="tilt-info">
    {_sparkline_html(a["form_score"])}
    <span class="tilt-item">{_icono_momentum(a["momentum"])}</span>
    <span class="tilt-item {_clase_forma(a["form_score"])}">Forma: {a["form_score"]:.0f}</span>
  </div>
</div>
</div>
'''

    html += '</div>\n'

    html += '''<div class="section">
<div class="section-title">Ranking de Forma</div>
<table class="ranking-table">
<thead><tr><th>#</th><th>Equipo</th><th>Rating</th><th>Forma</th><th>Tendencia</th><th>Racha</th></tr></thead>
<tbody>
'''

    for i, eq in enumerate(ranking[:30], 1):
        html += f'''<tr>
<td class="rank-num">{i}</td>
<td>{eq["nombre"]}</td>
<td><span class="elo-badge">{eq["rating"]:.0f}</span></td>
<td class="{_clase_forma(eq["form_score"])}">{eq["form_score"]:.0f}</td>
<td>{_icono_momentum(eq["momentum"])}</td>
<td>{_streak_html(eq["streak"])}</td>
</tr>
'''

    html += '</tbody></table></div>\n'

    html += f'''<p class="updated">Ultima actualizacion: {predicciones[0]["fecha"] if predicciones else "N/A"}</p>
</div>

<script>
function filtrarLiga(liga) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.liga-header, .match-card').forEach(el => {{
    if (liga === 'todas') {{
      el.style.display = '';
    }} else {{
      el.style.display = el.dataset.liga === liga ? '' : 'none';
    }}
  }});
}}
</script>
</body>
</html>'''

    return html


def generar(predicciones=None, archivo_entrada=None, archivo_salida=None):
    if predicciones is None:
        archivo_entrada = archivo_entrada or ARCHIVO_PREDICCIONES
        if not archivo_entrada.exists():
            print(f"[ERROR] No existe {archivo_entrada}. Ejecuta predict.py primero.")
            return None
        data = json.loads(archivo_entrada.read_text(encoding="utf-8"))
        predicciones = data.get("predicciones", [])

    if not predicciones:
        print("[AVISO] No hay predicciones para generar el dashboard.")
        return None

    html = generar_html(predicciones)
    salida = archivo_salida or ARCHIVO_SALIDA
    Path(salida).write_text(html, encoding="utf-8")
    print(f"Dashboard generado: {salida}")
    return str(salida)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera el dashboard HTML.")
    parser.add_argument("--entrada", help="Archivo JSON de predicciones")
    parser.add_argument("--salida", help="Archivo HTML de salida")
    args = parser.parse_args()
    generar(archivo_entrada=args.entrada, archivo_salida=args.salida)
