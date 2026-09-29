"""
migrar_pj_reales.py
--------------------
Migracion UNICA (no forma parte del cron de cada 30 min): calcula
pj_reales retroactivo para todos los equipos que ya existen en
ratings_propios.json, antes de activar el filtro que depende de ese
campo.

- Equipo sin bootstrap_en -> pj_reales = su partidos_jugados actual
  (todos sus partidos fueron reales).
- Equipo con bootstrap_en -> pj_reales = cantidad de partidos de ese
  equipo en historial_partidos/*.json con fecha POSTERIOR a
  bootstrap_en (los que jugo de verdad desde que se le hizo bootstrap).

Uso:
    python migrar_pj_reales.py
    python migrar_pj_reales.py --dry-run   # solo imprime, no guarda
"""

import argparse
import json
from pathlib import Path

import ratings_store

DATA_DIR = Path(__file__).parent / "data"
DIR_HISTORIAL = DATA_DIR / "historial_partidos"


def _contar_partidos_reales_desde(team_id, fecha_bootstrap):
    team_id = str(team_id)
    contados = set()
    if not DIR_HISTORIAL.exists():
        return 0
    for archivo in sorted(DIR_HISTORIAL.glob("*.json")):
        if archivo.name == ".gitkeep":
            continue
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        for p in datos.get("partidos", []):
            fecha_p = p.get("fecha", "")
            if not fecha_p or fecha_p <= fecha_bootstrap:
                continue
            home = str(p.get("equipo_local", {}).get("id", ""))
            away = str(p.get("equipo_visitante", {}).get("id", ""))
            if team_id in (home, away):
                fid = p.get("fixture_id")
                if fid:
                    contados.add(fid)
    return len(contados)


def migrar(dry_run=False):
    datos = ratings_store._cargar()
    equipos = datos["equipos"]
    cambios = 0

    for llave, eq in equipos.items():
        bootstrap_en = eq.get("bootstrap_en")
        pj_total = eq.get("partidos_jugados", 0)

        if not bootstrap_en:
            nuevo_pj_reales = pj_total
        else:
            team_id = llave.split(":", 1)[1] if ":" in llave else llave
            nuevo_pj_reales = _contar_partidos_reales_desde(team_id, bootstrap_en)

        actual = eq.get("pj_reales")
        if actual != nuevo_pj_reales:
            print(f"{llave} ({eq.get('nombre', '?')}): pj_reales {actual} -> {nuevo_pj_reales} "
                  f"(pj_total={pj_total}, bootstrap_en={bootstrap_en})")
            if not dry_run:
                eq["pj_reales"] = nuevo_pj_reales
            cambios += 1

    print(f"\n{cambios} equipo(s) actualizado(s) de {len(equipos)} total.")
    if not dry_run and cambios:
        ratings_store._guardar(datos)
        print("Guardado en ratings_propios.json.")
    elif dry_run:
        print("(--dry-run: no se guardo nada)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migracion unica: calcula pj_reales retroactivo.")
    parser.add_argument("--dry-run", action="store_true", help="Solo imprime, no guarda cambios.")
    args = parser.parse_args()
    migrar(dry_run=args.dry_run)
