"""
fetch_data.py
-------------
Todo el acceso a la API no oficial de ESPN para futbol.

Tres endpoints distintos:
  - site.api.espn.com   -> scoreboard (marcador de un dia), summary
                            (boxscore detallado), y schedule (fixtures
                            futuros por equipo).
  - sports.core.api.espn.com -> catalogo de ligas que ESPN conoce.

La cobertura de ligas viene de dos fuentes fusionadas por fixture_id:
  1. El marcador GLOBAL de ESPN (".../all/scoreboard").
  2. La lista de ligas descubierta por descubrir_ligas.py.

Para partidos a jugarse, se usa el mismo scoreboard con fechas futuras
o el endpoint /teams/{id}/schedule de cada equipo.
"""

import requests

TIMEOUT = 20

BASE_ESPN_SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
BASE_ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/soccer"

# Se usa solo si data/ligas_espn.json todavia no existe (primera corrida,
# antes de que descubrir_ligas.py haya generado la lista completa) -- ver
# descubrir_ligas.cargar_ligas().
LIGAS_SEMILLA = [
    "eng.1", "esp.1", "ger.1", "ita.1", "fra.1", "ned.1", "por.1",
    "usa.1", "mex.1", "bra.1", "arg.1", "ecu.1", "col.1", "chi.1",
    "uru.1", "uefa.champions", "uefa.europa", "conmebol.libertadores",
    "conmebol.sudamericana", "concacaf.leagues.cup",
]


def _fecha_espn(fecha_iso):
    return fecha_iso.replace("-", "")


def _extraer_evento(evento, liga_slug):
    """Convierte un 'event' crudo del scoreboard de ESPN al formato
    interno que usa este proyecto. Devuelve None si el evento no trae
    la forma esperada (se salta ese partido puntual, no rompe el
    resto)."""
    try:
        comp = evento["competitions"][0]
        home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
        away = next(c for c in comp["competitors"] if c["homeAway"] == "away")
    except (KeyError, IndexError, StopIteration):
        return None

    liga = evento.get("league", {})
    status = comp.get("status", {}) or evento.get("status", {})
    estado = status.get("type", {}).get("state")  # "pre" | "in" | "post"

    def _goles(competitor):
        try:
            return int(competitor.get("score", 0))
        except (TypeError, ValueError):
            return None

    return {
        "fixture": {"id": str(evento["id"]), "date": evento.get("date")},
        "teams": {
            "home": {"id": str(home["team"]["id"]), "name": home["team"].get("displayName")},
            "away": {"id": str(away["team"]["id"]), "name": away["team"].get("displayName")},
        },
        "league": {
            "country": liga.get("country") or "",
            "name": liga.get("name") or "",
        },
        "_liga_slug": liga_slug,
        "_estado": estado,
        "_goles_local": _goles(home),
        "_goles_visitante": _goles(away),
    }


def _consultar_scoreboard(slug, fecha_iso):
    url = f"{BASE_ESPN_SITE}/{slug}/scoreboard?dates={_fecha_espn(fecha_iso)}"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def obtener_fixtures_por_fecha(fecha_iso, ligas=None):
    """
    Devuelve los fixtures de 'fecha_iso' (YYYY-MM-DD): marcador global
    + TODAS las ligas en 'ligas' (por defecto, la lista descubierta
    por descubrir_ligas.py -- ver ese modulo), fusionando por
    fixture_id sin duplicar. Cada fixture ya trae estado
    ("pre"/"in"/"post") y marcador directo del scoreboard.

    'ligas' se puede pasar explicito (ej. para pruebas o para correr
    solo un subconjunto); si se omite, se usa la lista completa
    descubierta.
    """
    if ligas is None:
        import descubrir_ligas
        ligas = descubrir_ligas.cargar_ligas()

    fixtures_por_id = {}

    try:
        data = _consultar_scoreboard("all", fecha_iso)
        for evento in data.get("events", []):
            fx = _extraer_evento(evento, "all")
            if fx:
                fixtures_por_id[fx["fixture"]["id"]] = fx
        print(f"ESPN global ({fecha_iso}): {len(fixtures_por_id)} fixtures encontrados.")
    except Exception as e:
        print(f"[AVISO] No se pudo consultar el marcador global de ESPN para {fecha_iso}: {e}")

    nuevos_de_ligas = 0
    fallidas = []
    for slug in ligas:
        try:
            data = _consultar_scoreboard(slug, fecha_iso)
        except Exception as e:
            fallidas.append(slug)
            continue

        for evento in data.get("events", []):
            if evento["id"] in fixtures_por_id:
                continue  # ya vino del global, no se duplica
            fx = _extraer_evento(evento, slug)
            if fx:
                fixtures_por_id[fx["fixture"]["id"]] = fx
                nuevos_de_ligas += 1

    print(f"ESPN ({len(ligas)} liga(s) consultada(s), {fecha_iso}): "
          f"{nuevos_de_ligas} fixture(s) adicional(es) que el global no traia.")
    if fallidas:
        print(f"[AVISO] {len(fallidas)} liga(s) fallaron al consultar y se saltaron: {fallidas[:10]}"
              f"{'...' if len(fallidas) > 10 else ''}")

    return list(fixtures_por_id.values())


def obtener_boxscore_en_vivo(liga_slug, fixture_id):
    """
    Estadisticas detalladas de un partido (tiros, corners, posesion,
    tarjetas, etc.) via el endpoint /summary. Requiere un liga_slug
    REAL (no sirve "all", ese solo es valido para /scoreboard).

    Nunca lanza excepcion hacia arriba -- devuelve None si algo falla.
    """
    if not liga_slug or liga_slug == "all":
        return None

    url = f"{BASE_ESPN_SITE}/{liga_slug}/summary?event={fixture_id}"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[AVISO] No se pudo consultar el boxscore de {fixture_id} ({liga_slug}): {e}")
        return None

    boxscore = data.get("boxscore", {})
    equipos_stats = {}
    for equipo in boxscore.get("teams", []):
        home_away = equipo.get("homeAway")
        stats_lista = equipo.get("statistics", [])
        equipos_stats[home_away] = {s["name"]: s.get("displayValue") for s in stats_lista}

    if not equipos_stats:
        return None
    return equipos_stats


def obtener_fixtures_futuros(fecha_iso, ligas=None):
    """
    Devuelve los fixtures PROGRAMADOS para 'fecha_iso' (YYYY-MM-DD):
    partidos con estado "pre" (aun no juegan). Usa el mismo endpoint
    que obtener_fixtures_por_fecha pero filtra solo partidos futuros.

    tilde: tambien intenta consultar fechas cercanas (+1, +2 dias) por
    si hay partidos programados para esos dias que ya estan disponibles.
    """
    if ligas is None:
        import descubrir_ligas
        ligas = descubrir_ligas.cargar_ligas()

    fixtures_por_id = {}

    # Consultar el dia solicitado + 2 dias mas para cubrir findes/semanas
    from datetime import datetime, timedelta
    fecha_base = datetime.strptime(fecha_iso, "%Y-%m-%d")
    fechas_a_consultar = [
        (fecha_base + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(3)
    ]

    for fecha in fechas_a_consultar:
        try:
            data = _consultar_scoreboard("all", fecha)
            for evento in data.get("events", []):
                fx = _extraer_evento(evento, "all")
                if fx and fx["_estado"] == "pre":
                    fixtures_por_id[fx["fixture"]["id"]] = fx
        except Exception:
            pass

        for slug in ligas:
            try:
                data = _consultar_scoreboard(slug, fecha)
            except Exception:
                continue
            for evento in data.get("events", []):
                if evento["id"] in fixtures_por_id:
                    continue
                fx = _extraer_evento(evento, slug)
                if fx and fx["_estado"] == "pre":
                    fixtures_por_id[fx["fixture"]["id"]] = fx

    print(f"ESPN fixtures futuros ({len(fechas_a_consultar)} dias, {len(ligas)} ligas): "
          f"{len(fixtures_por_id)} partido(s) programado(s).")
    return list(fixtures_por_id.values())


def obtener_historial_equipo(liga_slug, team_id, limit=20):
    """
    Obtiene el historial reciente de un equipo via el endpoint
    /teams/{id}/schedule. Devuelve los ultimos 'limit' partidos
    terminados (estado "post") con marcador.

    Util para calcular forma/momentum cuando el historial local
    no tiene suficientes partidos.
    """
    if not liga_slug or not team_id:
        return []

    url = f"{BASE_ESPN_SITE}/{liga_slug}/teams/{team_id}/schedule"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[AVISO] No se pudo consultar historial de equipo {team_id} ({liga_slug}): {e}")
        return []

    partidos = []
    for evento in data.get("events", []):
        try:
            comp = evento["competitions"][0]
            status = comp.get("status", {})
            estado = status.get("type", {}).get("state")
            if estado != "post":
                continue

            home = next(c for c in comp["competitors"] if c["homeAway"] == "home")
            away = next(c for c in comp["competitors"] if c["homeAway"] == "away")

            partidos.append({
                "fixture_id": evento["id"],
                "fecha": evento.get("date", "")[:10],
                "home": {
                    "id": home["team"]["id"],
                    "name": home["team"].get("displayName"),
                    "score": int(home.get("score", 0)),
                },
                "away": {
                    "id": away["team"]["id"],
                    "name": away["team"].get("displayName"),
                    "score": int(away.get("score", 0)),
                },
            })
        except (KeyError, IndexError, StopIteration):
            continue

    return partidos[-limit:]
