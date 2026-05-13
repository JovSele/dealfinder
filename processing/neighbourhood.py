# processing/neighbourhood.py
# Extrahuje mestskú časť z district stringu
#
# Príklady:
#   "Silurská, Praha 5 - Smíchov"          → "Praha 5 - Smíchov"
#   "Arnošta Valenty, Praha - Černý Most"  → "Praha - Černý Most"
#   "Kolbenova, Praha 9 - Vysočany"        → "Praha 9 - Vysočany"
#   "Burešova, Brno - Veveří"              → "Brno - Veveří"
#   "Brno, okres Brno-město"               → None  (toto je okres, nie časť)
#   "Kounice, okres Nymburk"               → None
#   "Český Brod"                           → None  (žiadna ulica, žiadna časť)

import re


def extract(district: str | None) -> str | None:
    """Vráti mestskú časť alebo None ak sa nedá určiť."""
    if not district:
        return None

    d = district.strip()

    # Vylúč "okres XYZ" — to nie je mestská časť
    if re.search(r'\bokres\b', d, re.IGNORECASE):
        return None

    # Formát: "Ulica, Mesto - Časť"  alebo  "Ulica, Mesto N - Časť"
    # Čiarka oddeľuje ulicu od zvyšku
    if "," in d:
        after_comma = d.split(",", 1)[1].strip()

        # Výsledok musí obsahovať mesto (Praha/Brno/...)
        # a ideálne aj " - " ktoré oddeľuje časť
        if after_comma:
            return after_comma

    return None


def extract_district_number(neighbourhood: str | None) -> str | None:
    """
    Z neighbourhood extrahuj číslovaný district pre fallback.
    "Praha 5 - Smíchov" → "Praha 5"
    "Praha - Černý Most" → "Praha"
    "Brno - Veveří"     → "Brno"
    """
    if not neighbourhood:
        return None

    # Praha N - Časť → Praha N
    m = re.match(r'^(Praha\s*\d+)', neighbourhood, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Praha - Časť → Praha
    m = re.match(r'^(Praha)', neighbourhood, re.IGNORECASE)
    if m:
        return "Praha"

    # Brno - Časť → Brno
    m = re.match(r'^(Brno)', neighbourhood, re.IGNORECASE)
    if m:
        return "Brno"

    return None