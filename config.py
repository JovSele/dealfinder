# config.py — všetky nastavenia na jednom mieste
# Nikdy nepush tento súbor s reálnymi tokenmi — použi .env alebo env premenné

import os
from dotenv import load_dotenv
load_dotenv()

# ── TELEGRAM ─────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── SCRAPING ─────────────────────────────────────────────────
SCRAPE_INTERVAL_SEC = int(os.getenv("SCRAPE_INTERVAL_SEC", "300"))  # 5 minút

# Bazos.sk — viacero miest, každé = jeden wide query (bez humkreis)
BAZOS_SEARCH_URLS = [
    # Bratislava
    "https://www.bazos.sk/search.php?hledat=byt&rubriky=reality&hlokalita=Bratislava&humkreis=25&cenaod=50000&cenado=&Submit=H%C4%BEada%C5%A5",
    # Košice
    "https://www.bazos.sk/search.php?hledat=byt&rubriky=reality&hlokalita=Ko%C5%A1ice&humkreis=25&cenaod=30000&cenado=&Submit=H%C4%BEada%C5%A5",
    # Žilina
    "https://www.bazos.sk/search.php?hledat=byt&rubriky=reality&hlokalita=%C5%BDilina&humkreis=25&cenaod=30000&cenado=&Submit=H%C4%BEada%C5%A5",
    # Nitra
    "https://www.bazos.sk/search.php?hledat=byt&rubriky=reality&hlokalita=Nitra&humkreis=25&cenaod=30000&cenado=&Submit=H%C4%BEada%C5%A5",
]

# Spätná kompatibilita — runner môže použiť oba spôsoby
BAZOS_SEARCH_URL = BAZOS_SEARCH_URLS[0]

# Requst headers — realistický prehliadač
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sk-SK,sk;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_TIMEOUT_SEC = 15
REQUEST_RETRY_COUNT = 3
REQUEST_RETRY_DELAY_SEC = 5

# ── STORAGE ───────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "dealfinder.db")

# ── DEAL SCORE ────────────────────────────────────────────────
# Minimálny % rozdiel od priemeru aby sme poslali alert
DEAL_SCORE_THRESHOLD_PCT = float(os.getenv("DEAL_SCORE_THRESHOLD_PCT", "10.0"))

# Minimálny počet inzerátov v lokalite na výpočet priemeru
DEAL_SCORE_MIN_SAMPLES = int(os.getenv("DEAL_SCORE_MIN_SAMPLES", "5"))

# ── FILTERS ───────────────────────────────────────────────────
# Inzeráty s cenou 0 alebo pod týmto limitom ignorujeme
FILTER_MIN_PRICE_EUR = int(os.getenv("FILTER_MIN_PRICE_EUR", "10000"))

# ── LOGGING ───────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")  # INFO | DEBUG
