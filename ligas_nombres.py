"""
ligas_nombres.py
----------------
Mapeo de slugs de ESPN a nombres legibles en español y países.
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
    """Devuelve el nombre legible de una liga."""
    if nombre_espn and nombre_espn.strip():
        return nombre_espn.strip()
    return NOMBRES_LIGAS.get(slug, slug or "Liga desconocida")


PAIS_POR_SLUG = {
    "eng.1": "Inglaterra", "eng.2": "Inglaterra", "eng.3": "Inglaterra", "eng.4": "Inglaterra",
    "eng.facup": "Inglaterra", "eng.leagucup": "Inglaterra", "eng.wsl": "Inglaterra",
    "esp.1": "España", "esp.2": "España",
    "ger.1": "Alemania", "ger.2": "Alemania",
    "ita.1": "Italia", "ita.2": "Italia",
    "fra.1": "Francia", "fra.2": "Francia",
    "ned.1": "Países Bajos",
    "por.1": "Portugal",
    "bel.1": "Bélgica",
    "tur.1": "Turquía",
    "gre.1": "Grecia",
    "rus.1": "Rusia",
    "ukr.1": "Ucrania",
    "cze.1": "República Checa",
    "cro.1": "Croacia",
    "sui.1": "Suiza",
    "aut.1": "Austria",
    "den.1": "Dinamarca",
    "swe.1": "Suecia",
    "nor.1": "Noruega",
    "pol.1": "Polonia",
    "scotland.1": "Escocia",
    "irl.1": "Irlanda",
    "usa.1": "EE.UU.", "usa.usl": "EE.UU.", "usa.ncaa": "EE.UU.", "usa.ncaa.w": "EE.UU.",
    "mex.1": "México", "mex.2": "México",
    "can.1": "Canadá",
    "bra.1": "Brasil", "bra.2": "Brasil",
    "arg.1": "Argentina", "arg.2": "Argentina",
    "col.1": "Colombia",
    "chi.1": "Chile",
    "uru.1": "Uruguay",
    "par.1": "Paraguay",
    "per.1": "Perú",
    "ecu.1": "Ecuador",
    "bol.1": "Bolivia",
    "ven.1": "Venezuela",
    "chn.1": "China",
    "jpn.1": "Japón",
    "kor.1": "Corea del Sur",
    "aus.1": "Australia",
    "ind.1": "India",
    "sau.1": "Arabia Saudita",
    "uae.1": "EAU",
    "qat.1": "Qatar",
    "mor.1": "Marruecos",
    "tun.1": "Túnez",
    "egy.1": "Egipto",
    "nga.1": "Nigeria",
    "rsa.1": "Sudáfrica",
}

PAISES_ORDER = sorted(set(PAIS_POR_SLUG.values()))


def pais_por_slug(slug):
    """Devuelve el país de un slug de liga."""
    return PAIS_POR_SLUG.get(slug, "")
