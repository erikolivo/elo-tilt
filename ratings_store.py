"""
ratings_store.py
-----------------
Guarda y actualiza el rating Glicko-2 propio de cada equipo. Es la
"memoria" persistente del sistema: cada partido nuevo ajusta el rating
de los dos equipos involucrados, siempre relativo al rating (y a la
incertidumbre RD) que tenia el rival en ese momento.

No mezcla el rating con ninguna fuente externa (ClubElo u otra semilla)
-- todo equipo arranca en 1500 (rating base de Glicko-2, ver
glicko2.py) y su valor se ajusta unicamente con resultados reales
observados por este sistema. TRAMOS_PESO queda definido por si en el
futuro se decide introducir una semilla externa, pero no se usa hoy.
"""

import json
import datetime
from pathlib import Path

import glicko2

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_RATINGS = DATA_DIR / "ratings_propios.json"

TRAMOS_PESO = [
    (0, 0.0),
    (3, 0.20),
    (8, 0.50),
    (15, 0.75),
]
PESO_MAXIMO = 1.0


def peso_rating_propio(n_partidos):
    for tope, peso in TRAMOS_PESO:
        if n_partidos <= tope:
            return peso
    return PESO_MAXIMO


def _cargar():
    if ARCHIVO_RATINGS.exists():
        try:
            return json.loads(ARCHIVO_RATINGS.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"equipos": {}}


def _guardar(datos):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVO_RATINGS.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")


def llave_equipo(team_id, pais=None, nombre=None):
    """Llave primaria del equipo (id numerico de ESPN)."""
    if team_id:
        return f"espn:{team_id}"
    return f"np:{pais or '?'}|{nombre or '?'}"


def obtener_o_crear(llave, nombre=None, pais=None, liga=None):
    datos = _cargar()
    equipo = datos["equipos"].get(llave)
    if equipo is None:
        equipo = {
            "nombre": nombre, "pais": pais, "liga": liga,
            "rating": glicko2.RATING_BASE, "rd": glicko2.RD_INICIAL, "vol": glicko2.VOL_INICIAL,
            "partidos_jugados": 0, "ultima_actualizacion": None,
        }
        datos["equipos"][llave] = equipo
        _guardar(datos)
    else:
        cambiado = False
        if nombre and not equipo.get("nombre"):
            equipo["nombre"] = nombre
            cambiado = True
        if nombre and equipo.get("nombre"):
            equipo["nombre"] = _limpiar_nombre_duplicado(equipo["nombre"])
        if pais and not equipo.get("pais"):
            equipo["pais"] = pais
            cambiado = True
        if liga and not equipo.get("liga"):
            equipo["liga"] = liga
            cambiado = True
        if cambiado:
            datos["equipos"][llave] = equipo
            _guardar(datos)
    return equipo


def _limpiar_nombre_duplicado(nombre):
    """Limpia nombres duplicados de ESPN (ej: 'LSU LSU TIGERS' -> 'LSU Tigers').
    Solo limpia cuando dos palabras consecutivas son iguales ignorando mayusculas
    (como 'LSU LSU' o 'Belmont BELMONT'), pero preserva nombres legitimos como 'Colo Colo'."""
    if not nombre:
        return nombre
    words = nombre.split()
    for i in range(len(words) - 1):
        if words[i].lower() == words[i+1].lower() and words[i] != words[i+1]:
            return ' '.join(words[:i+1]).strip()
    return nombre


def actualizar_tras_partido(llave, rating_rival, rd_rival, resultado, fecha=None):
    """Ajusta el rating del equipo 'llave' tras un partido contra un
    rival con (rating_rival, rd_rival), con 'resultado' en escala
    Glicko-2 (1.0 victoria, 0.5 empate, 0.0 derrota). Cada llamada deja
    el rating un poco mas ajustado y un poco mas seguro (RD baja segun
    cuanta informacion nueva aporto el partido) -- asi es como el
    sistema "se va afinando" solo, partido a partido, sin intervencion
    manual."""
    datos = _cargar()
    eq = datos["equipos"].get(llave)
    if eq is None:
        obtener_o_crear(llave)
        datos = _cargar()
        eq = datos["equipos"][llave]

    nuevo_rating, nuevo_rd, nuevo_vol = glicko2.actualizar_rating(
        eq["rating"], eq["rd"], eq["vol"], [(rating_rival, rd_rival, resultado)]
    )
    eq["rating"], eq["rd"], eq["vol"] = nuevo_rating, nuevo_rd, nuevo_vol
    eq["partidos_jugados"] = eq.get("partidos_jugados", 0) + 1
    eq["ultima_actualizacion"] = (fecha or datetime.date.today().isoformat())

    datos["equipos"][llave] = eq
    _guardar(datos)
    return eq


def rd_de(llave):
    eq = obtener_o_crear(llave)
    return eq["rd"]


def decaer_rd_inactivos(dias_minimos=30):
    """Incrementa el RD (incertidumbre) de equipos que no han jugado
    en los ultimos 'dias_minimos' dias. Llama a glicko2._incrementar_rd_por_inactividad
    para que aplique el decaimiento por inactividad.
    Retorna cantidad de equipos afectados."""
    datos = _cargar()
    hoy = datetime.date.today()
    afectados = 0
    for llave, eq in datos["equipos"].items():
        ultima = eq.get("ultima_actualizacion")
        if not ultima:
            continue
        try:
            fecha_ult = datetime.date.fromisoformat(ultima)
        except (ValueError, TypeError):
            continue
        dias_inactivo = (hoy - fecha_ult).days
        if dias_inactivo >= dias_minimos:
            periodos = min(dias_inactivo // 30, 12)
            if periodos > 0:
                nuevo_rd = glicko2._incrementar_rd_por_inactividad(eq["rd"], periodos, eq.get("vol", glicko2.VOL_INICIAL))
                if nuevo_rd != eq["rd"]:
                    eq["rd"] = nuevo_rd
                    afectados += 1
    if afectados:
        _guardar(datos)
    return afectados
