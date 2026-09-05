"""
ligas_nombres.py
----------------
Mapeo de slugs de ESPN a nombres legibles en español.

ESPN solo expone slugs internos (ej. "arg.1", "uefa.champions") pero
nunca nombres legibles. Este diccionario los traduce para que el
dashboard muestre nombres comprensibles.

El nombre se usa como fallback: primero se intenta el campo "name" del
scoreboard de ESPN; si viene vacío, se usa este mapeo.
"""

NOMBRES_LIGAS = {
    # === Europa ===
    "eng.1": "Inglaterra - Premier League",
    "eng.2": "Inglaterra - Championship",
    "eng.3": "Inglaterra - League One",
    "eng.4": "Inglaterra - League Two",
    "eng.facup": "Inglaterra - FA Cup",
    "eng.leagucup": "Inglaterra - EFL Cup",
    "esp.1": "España - La Liga",
    "esp.2": "España - LaLiga2",
    "ger.1": "Alemania - Bundesliga",
    "ger.2": "Alemania - 2. Bundesliga",
    "ita.1": "Italia - Serie A",
    "ita.2": "Italia - Serie B",
    "fra.1": "Francia - Ligue 1",
    "fra.2": "Francia - Ligue 2",
    "ned.1": "Países Bajos - Eredivisie",
    "por.1": "Portugal - Primeira Liga",
    "bel.1": "Bélgica - Jupiler Pro League",
    "tur.1": "Turquía - Süper Lig",
    "gre.1": "Grecia - Super League",
    "rus.1": "Rusia - Premier League",
    "ukr.1": "Ucrania - Premier League",
    "cze.1": "República Checa - First League",
    "cro.1": "Croacia - HNL",
    "sui.1": "Suiza - Super League",
    "aut.1": "Austria - Bundesliga",
    "den.1": "Dinamarca - Superliga",
    "swe.1": "Suecia - Allsvenskan",
    "nor.1": "Noruega - Eliteserien",
    "pol.1": "Polonia - Ekstraklasa",
    "scotland.1": "Escocia - Premiership",
    "irl.1": "Irlanda - Premier Division",

    # === Copas europeas ===
    "uefa.champions": "UEFA Champions League",
    "uefa.champions_qual": "UEFA Champions League - Clasificación",
    "uefa.europa": "UEFA Europa League",
    "uefa.europa_qual": "UEFA Europa League - Clasificación",
    "uefa.europaconf": "UEFA Conference League",
    "uefa.europaconf_qual": "UEFA Conference League - Clasificación",
    "uefa.nations": "UEFA Nations League",
    "uefa.supeco": "UEFA Super Cup",

    # === América del Norte ===
    "usa.1": "EE.UU. - MLS",
    "usa.usl": "EE.UU. - USL Championship",
    "mex.1": "México - Liga MX",
    "mex.2": "México - Liga de Expansión MX",
    "can.1": "Canadá - Canadian Premier League",
    "concacaf.champions": "Concacaf Champions Cup",
    "concacaf.leagues.cup": "Leagues Cup",
    "concacaf.nations": "Concacaf Nations League",

    # === América del Sur ===
    "bra.1": "Brasil - Série A",
    "bra.2": "Brasil - Série B",
    "arg.1": "Argentina - Liga Profesional",
    "arg.2": "Argentina - Nacional B",
    "col.1": "Colombia - Liga BetPlay",
    "chi.1": "Chile - Liga Asportivo",
    "uru.1": "Uruguay - Primera División",
    "par.1": "Paraguay - Primera División",
    "per.1": "Perú - Liga 1",
    "ecu.1": "Ecuador - Serie A",
    "bol.1": "Bolivia - Liga Profesional",
    "ven.1": "Venezuela - Liga FUTVE",
    "conmebol.libertadores": "Copa Libertadores",
    "conmebol.sudamericana": "Copa Sudamericana",
    "conmebol.recopa": "Recopa Sudamericana",

    # === Asia ===
    "chn.1": "China - Super League",
    "jpn.1": "Japón - J1 League",
    "kor.1": "Corea del Sur - K League 1",
    "aus.1": "Australia - A-League",
    "ind.1": "India - ISL",
    "sau.1": "Arabia Saudita - SPL",
    "uae.1": "EAU - Pro League",
    "qat.1": "Qatar - Stars League",
    "afc.champions": "AFC Champions League Elite",
    "afc.cup": "AFC Cup",
    "afc.asian.cup": "Copa Asiática",

    # === África ===
    "mor.1": "Marruecos - Botola Pro",
    "tun.1": "Túnez - Ligue 1",
    "egy.1": "Egipto - Premier League",
    "nga.1": "Nigeria - NPFL",
    "rsa.1": "Sudáfrica - PSL",
    "caf.champions": "CAF Champions League",
    "caf.confed": "CAF Confederation Cup",
    "caf.cup": "CAF Super Cup",

    # === Internacionales ===
    "fifa.world": "Copa del Mundo FIFA",
    "fifa.world_qual": "Eliminatorias Copa del Mundo",
    "fifa.wc": "Copa del Mundo Femenina",
    "fifa.confed": "Copa Confederaciones",
    "friendlies": "Amistosos Internacionales",
    "intl": "Partidos Internacionales",

    # === Otros ===
    "eng.wsl": "Inglaterra - Women's Super League",
    "usa.ncaa": "EE.UU. - NCAA",
    "usa.ncaa.w": "EE.UU. - NCAA Femenino",
}


def nombre_liga(slug, nombre_espn=None):
    """Devuelve el nombre legible de una liga.
    Primero intenta el nombre de ESPN; si viene vacío, usa el mapeo."""
    if nombre_espn and nombre_espn.strip():
        return nombre_espn.strip()
    return NOMBRES_LIGAS.get(slug, slug or "Liga desconocida")
