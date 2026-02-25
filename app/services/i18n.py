from __future__ import annotations

from typing import Optional, Dict, Set
import re

# ============ CONFIGURATIE ============

COUNTRY_DEFAULT_LANG: Dict[str, str] = {
    "NL": "nl",
    "BE": "nl",  # TODO: later "nl" of "fr" via region detection
    "DE": "de",
    "AT": "de",  # Oostenrijk ook Duits
    "CH": "de",  # Zwitserland default (later: de/fr/it)
    "SE": "sv",  # Zweeds - nu al ondersteunen
    "NO": "no",  # Noors
    "DK": "da",  # Deens
    "FI": "fi",  # Fins
    "GB": "en",
    "US": "en",
    "CA": "en",  # TODO: later en/fr
}

# Prioriteit: land > browser > fallback
SUPPORTED: Set[str] = {"nl", "en", "de"}  # Fase 1
# SUPPORTED: Set[str] = {"nl", "en", "de", "sv", "no", "da", "fi"}  # Fase 2

# Gewichten voor Accept-Language parsing
Q_WEIGHT_PATTERN = re.compile(r"q=([0-9.]+)")


# ============ CORE FUNCTIE ============


def pick_language(
    *,
    country: Optional[str] = None,
    accept_language: Optional[str] = None,
    user_pref: Optional[str] = None,  # Uit cookie/session/URL param
    fallback: str = "nl",
) -> str:
    """
    Bepaal taal op basis van:
    1. Expliciete gebruikerskeuze (cookie/URL)
    2. Land (vanuit lead/adres)
    3. Browser Accept-Language (met q-waarden)
    4. Fallback (NL voor EU markt)
    """

    # 1) Expliciete gebruikerskeuze wint altijd
    if user_pref:
        code = _normalize_lang(user_pref)
        if code in SUPPORTED:
            return code

    # 2) Land default
    country_lang = _get_country_language(country)

    # 3) Browser preferences (gewogen!)
    browser_lang = _parse_accept_language(accept_language)

    # Prioriteit: browser > country (meestal accurater)
    # BEHALVE als land expliciet NL/BE/DE is en browser "en"
    if browser_lang:
        if country_lang in ("nl", "de") and browser_lang == "en":
            # Nederlander/Duitser met Engelse browser = toch NL/DE
            return country_lang if country_lang in SUPPORTED else fallback
        return browser_lang

    return country_lang if country_lang in SUPPORTED else fallback


# ============ HELPERS ============


def _normalize_lang(code: Optional[str]) -> Optional[str]:
    """Normaliseer taalcode naar base (nl-NL → nl)"""
    if not code:
        return None
    return code.lower().split("-")[0].split("_")[0]


def _get_country_language(country: Optional[str]) -> Optional[str]:
    """Haal default taal voor land"""
    if not country:
        return None
    c = country.upper().strip()
    return COUNTRY_DEFAULT_LANG.get(c)


def _parse_accept_language(header: Optional[str]) -> Optional[str]:
    """
    Parse Accept-Language header met q-waarden.
    Bijv: "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7"
    """
    if not header:
        return None

    # Parse alle opties met gewicht
    options = []
    for part in header.split(","):
        part = part.strip()
        if not part:
            continue

        # Split locale en q-waarde
        if ";" in part:
            locale, *params = part.split(";")
            locale = locale.strip()
            q = 1.0
            for param in params:
                match = Q_WEIGHT_PATTERN.search(param)
                if match:
                    try:
                        q = float(match.group(1))
                    except ValueError:
                        pass
        else:
            locale = part
            q = 1.0

        code = _normalize_lang(locale)
        if code and code in SUPPORTED:
            options.append((q, code))

    # Sorteer op gewicht (hoogste eerst)
    options.sort(reverse=True)

    return options[0][1] if options else None


# ============ FLASK INTEGRATIE ============


def get_request_language(country: Optional[str] = None, fallback: str = "nl") -> str:
    """Gebruik in Flask routes"""
    from flask import request, session

    # Check URL param (?lang=en)
    url_lang = request.args.get("lang")

    # Check session
    session_lang = session.get("lang")

    # Combineer
    return pick_language(
        country=country,
        accept_language=request.headers.get("Accept-Language"),
        user_pref=url_lang or session_lang,
        fallback=fallback,
    )


# ============ TEMPLATE FILTER ============


def init_i18n(app):
    """Registreer template filters"""

    @app.template_filter("t")
    def translate_filter(key: str, **kwargs) -> str:
        """Gebruik: {{ 'estimate.title' | t }}"""
        from flask import g

        return translate(key, g.get("lang", "nl"), **kwargs)

    @app.before_request
    def set_language():
        """Zet taal voor elke request"""
        from flask import g, request

        # Detecteer uit lead/company context of request
        country = g.get("lead_country") or request.args.get("country")
        g.lang = get_request_language(country=country)
