"""
descubrir_ligas.py
-------------------
Descubre TODAS las ligas de futbol que ESPN tiene catalogadas (ligas
nacionales de cualquier division, copas domesticas, torneos
continentales, futbol femenino, amistosos, etc.) via el catalogo de
la Core API -- en vez de mantener a mano una lista fija que
inevitablemente se queda corta.

Confirmado EN VIVO (02-sep-2026): el catalogo trae 218 ligas de
futbol en este momento.

Se corre por separado de la recopilacion diaria (ver
.github/workflows/descubrir_ligas.yml, semanal) porque el catalogo de
ligas cambia muy poco de un dia a otro -- no tiene sentido pagar 9
peticiones de paginacion en cada corrida diaria cuando alcanza con
refrescarlo una vez por semana. recopilar_dia.py simplemente lee el
resultado ya guardado (ver cargar_ligas()).

Uso:
    python descubrir_ligas.py
"""

import json
from pathlib import Path

import requests

TIMEOUT = 20
BASE_ESPN_CORE = "https://sports.core.api.espn.com/v2/sports/soccer"

DATA_DIR = Path(__file__).parent / "data"
ARCHIVO_LIGAS = DATA_DIR / "ligas_espn.json"


def _slug_desde_ref(ref_url):
    # ref_url es del tipo:
    # "http://sports.core.api.espn.com/v2/sports/soccer/leagues/eng.1?lang=en&region=us"
    sin_query = ref_url.split("?")[0]
    return sin_query.rstrip("/").split("/")[-1]


def descubrir():
    """Recorre el catalogo paginado de la Core API y devuelve la lista
    completa (ordenada) de slugs de liga."""
    slugs = []
    pagina = 1
    while True:
        url = f"{BASE_ESPN_CORE}/leagues?page={pagina}&limit=100"
        try:
            r = requests.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[AVISO] Fallo consultando pagina {pagina} del catalogo de ligas: {e}")
            break

        items = data.get("items", [])
        for item in items:
            ref = item.get("$ref")
            if ref:
                slugs.append(_slug_desde_ref(ref))

        page_count = data.get("pageCount", pagina)
        print(f"  pagina {pagina}/{page_count}: {len(items)} liga(s)")
        if pagina >= page_count:
            break
        pagina += 1

    return sorted(set(slugs))


def guardar(slugs):
    import datetime
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVO_LIGAS.write_text(json.dumps({
        "actualizado": datetime.datetime.utcnow().isoformat() + "Z",
        "total": len(slugs),
        "slugs": slugs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_ligas():
    """Lee la lista de ligas ya descubierta. Si todavia no existe
    (primera vez que se corre este proyecto, antes de la primera
    corrida de descubrir_ligas.py), cae a una lista semilla pequena
    para que recopilar_dia.py no se quede sin nada que consultar."""
    if ARCHIVO_LIGAS.exists():
        try:
            datos = json.loads(ARCHIVO_LIGAS.read_text(encoding="utf-8"))
            slugs = datos.get("slugs")
            if slugs:
                return slugs
        except Exception:
            pass

    import fetch_data
    print("[AVISO] data/ligas_espn.json no existe todavia -- usando lista semilla. "
          "Corre 'python descubrir_ligas.py' para tener la cobertura completa.")
    return fetch_data.LIGAS_SEMILLA


if __name__ == "__main__":
    print("Descubriendo catalogo completo de ligas de futbol en ESPN...")
    slugs = descubrir()
    guardar(slugs)
    print(f"\n{len(slugs)} liga(s) guardada(s) en {ARCHIVO_LIGAS}")
