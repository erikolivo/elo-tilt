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
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import glicko2

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_RATINGS = DATA_DIR / "ratings_propios.json"
ARCHIVO_ALIAS = DATA_DIR / "alias_equipos.json"

SUFIJOS_EQUIPO = {"fc", "cf", "fk", "ff", "sc", "afc", "ac"}
# Palabras que indican variante (cantera/reserva/seleccion) — nunca
# deben matchear contra el equipo senior.
VARIANTES_EQUIPO = {
    "u15", "u16", "u17", "u18", "u19", "u20", "u21", "u22", "u23",
    "women", "femenina", "femenino", "ii", "iii", "reserve", "reserves",
}
# Alias fijados a mano (nombre normalizado -> nombre normalizado).
ALIAS_EQUIPOS = {
    "wolves": "wolverhampton wanderers",
    "aarhus": "agf",
}

TRAMOS_PESO = [
    (0, 0.0),
    (3, 0.20),
    (8, 0.50),
    (15, 0.75),
]
PESO_MAXIMO = 1.0

# Cache en memoria del alias-file (se carga una vez por proceso).
_alias_memoria = None


def peso_rating_propio(n_partidos):
    for tope, peso in TRAMOS_PESO:
        if n_partidos <= tope:
            return peso
    return PESO_MAXIMO


def _cargar_alias():
    global _alias_memoria
    if _alias_memoria is None:
        if ARCHIVO_ALIAS.exists():
            try:
                _alias_memoria = json.loads(ARCHIVO_ALIAS.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                _alias_memoria = {}
        else:
            _alias_memoria = {}
    return _alias_memoria


def _guardar_alias(cache):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVO_ALIAS.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _normalizar_nombre(nombre):
    """Normaliza un nombre de equipo para comparar sin acentos ni
    suficjos tipo FC/CF."""
    texto = unicodedata.normalize("NFKD", str(nombre or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()
    palabras = [p for p in texto.split() if p not in SUFIJOS_EQUIPO]
    return ALIAS_EQUIPOS.get(" ".join(palabras), " ".join(palabras))


def _es_variante_protegida(nombre_norm):
    """True si el nombre normalizado parece una variante (cantera,
    reserva, seleccion) — no debe matchear contra el equipo senior."""
    tokens = set(nombre_norm.split())
    return bool(tokens & VARIANTES_EQUIPO)


def _nombres_coinciden(nombre_a, nombre_b):
    a = _normalizar_nombre(nombre_a)
    b = _normalizar_nombre(nombre_b)
    if not a or not b:
        return False
    if a == b:
        return True
    # Nunca matchear si alguno es variante protegida (u21, women, ii...)
    if _es_variante_protegida(a) or _es_variante_protegida(b):
        return False
    # Subcadena clara (como el fallback de buscarElo del dashboard)
    if (a in b or b in a) and min(len(a), len(b)) >= 4:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.85


def resolver_llave(llave, nombre=None, equipos=None):
    """Resuelve la llave canónica de un equipo, siguiendo el alias-cache
    (data/alias_equipos.json) y, si el equipo aún no existe, un
    fuzzy-match de nombre contra los ya registrados.

    - Si `llave` ya está en ratings → se devuelve tal cual.
    - Si hay alias guardado para ese team_id → se devuelve el canónico.
    - Si no, y se pasa `nombre`, se busca un equipo existente con nombre
      muy similar → se registra el alias y se devuelve ese.
    - Si no hay match → se devuelve la llave original (equipo nuevo).
    """
    if not isinstance(llave, str) or not llave.startswith("espn:"):
        return llave

    team_id = llave[5:]
    alias = _cargar_alias()

    # 1) Alias ya aprendido para este team_id
    if team_id in alias:
        canonico = alias[team_id]
        if not canonico.startswith("espn:"):
            canonico = f"espn:{canonico}"
        return canonico

    if equipos is None:
        equipos = _cargar().get("equipos", {})

    # 2) La llave ya existe en ratings → no hay nada que resolver
    if llave in equipos:
        return llave

    # 3) Sin nombre no se puede fuzzy-matchear
    if not nombre:
        return llave

    # 4) Buscar el mejor candidato existente por nombre similar
    mejor_llave = None
    mejor_pj = -1
    for otra_llave, eq in equipos.items():
        if not otra_llave.startswith("espn:"):
            continue
        otro_nombre = eq.get("nombre")
        if not otro_nombre:
            continue
        if _nombres_coinciden(nombre, otro_nombre):
            pj = eq.get("partidos_jugados", 0)
            if pj > mejor_pj:
                mejor_pj = pj
                mejor_llave = otra_llave

    if mejor_llave:
        # Registrar el alias para que la próxima vez sea directo
        alias[team_id] = mejor_llave[5:]
        _guardar_alias(alias)
        return mejor_llave

    return llave


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
    # Tarea 2: resolver alias/fuzzy antes de tratar como "nuevo"
    llave = resolver_llave(llave, nombre=nombre)
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
    # Tarea 2: resolver alias/fuzzy en el LADO DE ESCRITURA también
    # (si solo se resuelve al leer, se puede leer el registro correcto
    # pero escribir en uno nuevo, reintroduciendo el bug).
    llave = resolver_llave(llave)
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


def guardar_bootstrap(llave, rating, rd, vol, partidos_jugados, fecha=None, nombre=None, liga=None):
    """Guarda el estado resultante de un reset+replay de bootstrap
    (ver bootstrap_equipos.py) sobre el registro del equipo 'llave'.
    Solo toca ESTE equipo — no se procesa a ningún rival."""
    llave = resolver_llave(llave, nombre=nombre)
    datos = _cargar()
    eq = datos["equipos"].get(llave)
    if eq is None:
        eq = {
            "nombre": nombre, "pais": None, "liga": liga,
            "rating": glicko2.RATING_BASE, "rd": glicko2.RD_INICIAL,
            "vol": glicko2.VOL_INICIAL, "partidos_jugados": 0,
            "ultima_actualizacion": None,
        }
    eq["rating"] = round(float(rating), 2)
    eq["rd"] = round(float(rd), 2)
    eq["vol"] = round(float(vol), 6)
    eq["partidos_jugados"] = int(partidos_jugados)
    eq["ultima_actualizacion"] = fecha or datetime.date.today().isoformat()
    # Marca que ya se intentó bootstrap (evita re-llamar a ESPN en cada corrida)
    eq["bootstrap_en"] = datetime.date.today().isoformat()
    if nombre and not eq.get("nombre"):
        eq["nombre"] = nombre
    if liga and not eq.get("liga"):
        eq["liga"] = liga
    datos["equipos"][llave] = eq
    _guardar(datos)
    return eq


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
