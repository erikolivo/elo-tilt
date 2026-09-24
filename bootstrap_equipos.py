"""
bootstrap_equipos.py
--------------------
Reset + replay del rating Glicko-2 para equipos NUEVOS o con POCOS
partidos locales (partidos_jugados < UMBRAL), usando el historial real
que ESPN ya tiene en /teams/{id}/schedule (via
fetch_data.obtener_historial_equipo).

Por qué reset+replay y no "agregar encima": Glicko-2 es secuencial —
el orden de los partidos importa para el resultado del rating. El
proceso correcto es:

  1. Traer historial de ESPN (hasta LIMITE_HISTORIAL partidos "post").
  2. Fusionar con el historial local del equipo (historial_partidos/*.json),
     deduplicando por fixture_id.
  3. Ordenar cronológicamente (del más viejo al más reciente).
  4. Resetear SOLO el registro de ESTE equipo a los valores base.
  5. Reproducir la lista fusionada completa, partido por partido, a
     través de glicko2.actualizar_rating — exactamente igual que hace
     backfill_retroactivo.py pero aislado a un solo equipo.
  6. Guardar el resultado en ratings_store, y agregar a
     historial_partidos los partidos que no estaban ya ahí (sin
     duplicar).

Por qué es seguro para el resto del sistema: el reset y replay se
aplican únicamente al registro de ESE equipo — no se toca el rating de
ningún rival. Los rivales de esos partidos viejos ya recibieron su
propia actualización cuando esos partidos se procesaron originalmente
(para ellos); no hace falta ni se debe reprocesarlos.

⚠️ Limitación documentada (no se "arregla" aquí): cuando se reproduce
un partido viejo, el cálculo usa el rating ACTUAL del rival como
aproximación del rating que tenía en esa fecha (no existe forma de
saber el rating exacto del rival en ese momento histórico sin
reprocesar todo el sistema en conjunto, que es justamente lo que hace
backfill_retroactivo.py a nivel global). Esto introduce un sesgo menor,
pero sigue siendo muchísimo mejor que dejar al equipo plano en 1500
sin ningún dato — por eso se limita a equipos con pocos partidos
(< UMBRAL), donde el beneficio compensa claramente la imperfección.

Esto NO reemplaza backfill_retroactivo.py — ese sigue sirviendo para
extender el historial general del sistema hacia atrás, procesando
TODOS los equipos juntos en orden cronológico real (la forma más
correcta de hacerlo). Este mecanismo es más liviano y automático,
pensado para no dejar a un equipo nuevo o con poco historial pelado en
1500 mientras llega la próxima corrida manual de backfill.
"""

import datetime
import json
from pathlib import Path

import glicko2
import ratings_store
import fetch_data
import historial_store

DATA_DIR = Path(__file__).parent / "data"
DIR_HISTORIAL = DATA_DIR / "historial_partidos"

# Umbral configurable: si un equipo tiene MENOS de esta cantidad de
# partidos jugados (según ratings_store), se le aplica bootstrap.
UMBRAL_PJ_BOOTSTRAP = 4

# Cuántos partidos traer de ESPN /schedule.
LIMITE_HISTORIAL_ESPN = 20


def _partidos_locales_de_equipo(team_id):
    """Escanea data/historial_partidos/*.json y devuelve todos los
    partidos donde 'team_id' figura como local o visitante."""
    team_id = str(team_id)
    partidos = []
    if not DIR_HISTORIAL.exists():
        return partidos
    for archivo in sorted(DIR_HISTORIAL.glob("*.json")):
        if archivo.name == ".gitkeep":
            continue
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for p in datos.get("partidos", []):
            home = p.get("equipo_local", {})
            away = p.get("equipo_visitante", {})
            if str(home.get("id", "")) == team_id or str(away.get("id", "")) == team_id:
                partidos.append(p)
    return partidos


def _normalizar_local(p):
    """Convierte un partido del historial local al formato interno
    {fixture_id, fecha, home_id, away_id, gh, ga}."""
    return {
        "fixture_id": str(p.get("fixture_id", "")),
        "fecha": p.get("fecha", ""),
        "home_id": str(p.get("equipo_local", {}).get("id", "")),
        "away_id": str(p.get("equipo_visitante", {}).get("id", "")),
        "home_name": p.get("equipo_local", {}).get("name") or p.get("equipo_local", {}).get("nombre", ""),
        "away_name": p.get("equipo_visitante", {}).get("name") or p.get("equipo_visitante", {}).get("nombre", ""),
        "gh": p.get("goles_local"),
        "ga": p.get("goles_visitante"),
        "_ya_en_local": True,
    }


def _normalizar_espn(p, liga_slug):
    """Convierte un partido del schedule de ESPN al mismo formato
    interno que _normalizar_local."""
    return {
        "fixture_id": str(p.get("fixture_id", "")),
        "fecha": p.get("fecha", ""),
        "home_id": str(p.get("home", {}).get("id", "")),
        "away_id": str(p.get("away", {}).get("id", "")),
        "home_name": p.get("home", {}).get("name", ""),
        "away_name": p.get("away", {}).get("name", ""),
        "gh": p.get("home", {}).get("score"),
        "ga": p.get("away", {}).get("score"),
        "_liga_slug": liga_slug,
        "_ya_en_local": False,
    }


def _resultado_desde_marcador(es_local, gh, ga):
    """Devuelve el resultado en escala Glicko-2 (1.0/0.5/0.0) desde la
    perspectiva del equipo para el que se está calculando."""
    if gh is None or ga is None:
        return None
    if gh == ga:
        return 0.5
    gana_local = gh > ga
    if es_local:
        return 1.0 if gana_local else 0.0
    return 0.0 if gana_local else 1.0


def _resultado_rival(es_local, gh, ga):
    """Resultado del RIVAL (opuesto al del equipo)."""
    r = _resultado_desde_marcador(es_local, gh, ga)
    if r is None:
        return None
    return 1.0 - r if r != 0.5 else 0.5


def _equipos_si_hace_falta(llave, team_id, nombre, liga_slug, equipos_ratings):
    """Devuelve True si este equipo necesita bootstrap (< umbral PJ, o
    aún no está en ratings) y no se le ha intentado aún. False en caso
    contrario."""
    eq = equipos_ratings.get(llave, {})
    if eq.get("bootstrap_en"):
        # Ya se intentó bootstrap en una corrida anterior — no reintentar
        # en cada corrida para no martillear a ESPN.
        return False
    pj = eq.get("partidos_jugados", 0)
    return pj < UMBRAL_PJ_BOOTSTRAP


def bootstrap_si_hace_falta(llave, team_id, nombre, liga_slug, equipos_ratings):
    """
    Ejecuta el reset+replay para 'llave' si cumple las condiciones
    (PJ < UMBRAL y aún no intentado). Devuelve True si se hizo
    bootstrap (o se marcó como intentado sin datos), False si se omitió.

    Modifica 'equipos_ratings' en memoria para que el llamador pueda
    seguir usando el estado fresco sin recargar el archivo.
    """
    team_id = str(team_id)
    if not _equipos_si_hace_falta(llave, team_id, nombre, liga_slug, equipos_ratings):
        return False

    # 1) Historial de ESPN
    partidos_espn = fetch_data.obtener_historial_equipo(liga_slug, team_id, limit=LIMITE_HISTORIAL_ESPN)

    # 2) Fusionar con local, deduplicando por fixture_id
    locales = [_normalizar_local(p) for p in _partidos_locales_de_equipo(team_id)]
    por_fixture = {}
    for p in locales:
        if p["fixture_id"]:
            por_fixture[p["fixture_id"]] = p
    for p in partidos_espn:
        n = _normalizar_espn(p, liga_slug)
        fid = n["fixture_id"]
        if fid and fid not in por_fixture:
            por_fixture[fid] = n

    fusionados = list(por_fixture.values())
    # Filtrar los que no tienen marcador válido
    fusionados = [p for p in fusionados if p["gh"] is not None and p["ga"] is not None]

    if not fusionados:
        # No hay datos ni locales ni de ESPN — marcar como intentado
        # para no reintentar en cada corrida, sin tocar el rating.
        ratings_store.guardar_bootstrap(
            llave,
            ratings_store._cargar()["equipos"].get(llave, {}).get("rating", glicko2.RATING_BASE),
            ratings_store._cargar()["equipos"].get(llave, {}).get("rd", glicko2.RD_INICIAL),
            ratings_store._cargar()["equipos"].get(llave, {}).get("vol", glicko2.VOL_INICIAL),
            ratings_store._cargar()["equipos"].get(llave, {}).get("partidos_jugados", 0),
            nombre=nombre, liga=liga_slug,
        )
        print(f"[BOOTSTRAP] {nombre} ({llave}): sin historial local ni de ESPN — marcado como intentado.")
        return False

    # 3) Ordenar cronológicamente
    fusionados.sort(key=lambda p: p["fecha"])

    # 4) Resetear el registro de ESTE equipo a los valores base
    rating, rd, vol = glicko2.RATING_BASE, glicko2.RD_INICIAL, glicko2.VOL_INICIAL
    pj = 0

    # Ratings de rivales (aproximación: rating ACTUAL del rival, no
    # histórico — ver limitación en el docstring).
    for p in fusionados:
        es_local = p["home_id"] == team_id
        rival_id = p["away_id"] if es_local else p["home_id"]
        r_equipo = _resultado_desde_marcador(es_local, p["gh"], p["ga"])
        if r_equipo is None:
            continue

        rival_llave = f"espn:{rival_id}"
        rival_eq = ratings_store._cargar()["equipos"].get(rival_llave, {})
        rating_rival = rival_eq.get("rating", glicko2.RATING_BASE)
        rd_rival = rival_eq.get("rd", glicko2.RD_INICIAL)

        # 5) Reproducir a través de glicko2
        rating, rd, vol = glicko2.actualizar_rating(
            rating, rd, vol, [(rating_rival, rd_rival, r_equipo)]
        )
        pj += 1

    # 6) Guardar resultado en ratings_store
    ratings_store.guardar_bootstrap(
        llave, rating, rd, vol, pj, nombre=nombre, liga=liga_slug
    )

    # Reflejar en memoria para el llamador
    equipos_ratings[llave] = {
        **equipos_ratings.get(llave, {}),
        "nombre": nombre or equipos_ratings.get(llave, {}).get("nombre"),
        "liga": liga_slug or equipos_ratings.get(llave, {}).get("liga"),
        "rating": round(rating, 2),
        "rd": round(rd, 2),
        "vol": round(vol, 6),
        "partidos_jugados": pj,
        "bootstrap_en": datetime.date.today().isoformat(),
        "ultima_actualizacion": datetime.date.today().isoformat(),
    }

    # Agregar a historial_store los partidos que no estaban ya ahí
    # (para que _obtener_historial de predict.py los encuentre y la
    # Forma/Racha/Momentum también arranquen con datos reales).
    agregados = 0
    for p in fusionados:
        if p.get("_ya_en_local"):
            continue
        if not p["fecha"]:
            continue
        ya_en_mes = historial_store.fixture_ids_guardados(p["fecha"])
        if p["fixture_id"] in ya_en_mes:
            continue
        # Reconstruir el registro en formato historial_store
        registro = {
            "fixture_id": p["fixture_id"],
            "fecha": p["fecha"],
            "fecha_hora_espn": None,
            "liga_pais": None,
            "liga_nombre": None,
            "liga_slug": p.get("_liga_slug", liga_slug),
            "equipo_local": {"id": p["home_id"], "name": p["home_name"]},
            "equipo_visitante": {"id": p["away_id"], "name": p["away_name"]},
            "goles_local": p["gh"],
            "goles_visitante": p["ga"],
            "estadisticas": None,
            "prediccion_previa": None,
        }
        historial_store.guardar_partido(p["fecha"], registro)
        agregados += 1

    print(
        f"[BOOTSTRAP] {nombre} ({llave}): reset+replay de {pj} partido(s) "
        f"(rating final {rating:.0f}, RD {rd:.0f}, {agregados} partido(s) nuevo(s) en historial)."
    )
    return True


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python bootstrap_equipos.py <llave> [liga_slug]")
        print("Ej:  python bootstrap_equipos.py espn:19436 caf.champions")
        sys.exit(1)
    _llave = sys.argv[1]
    _liga = sys.argv[2] if len(sys.argv) > 2 else "all"
    _datos = ratings_store._cargar()
    _eq = _datos["equipos"].get(_llave, {})
    bootstrap_si_hace_falta(
        _llave, _llave.split(":", 1)[1],
        _eq.get("nombre", ""), _liga, _datos["equipos"]
    )
