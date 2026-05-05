# dealfinder
stiahnuť z GitHubu:
    git pull origin main

pushnut
    git add -A
    git commit -m "feat: telegram alerts fungujú, filter predaj 50k+"
    git push

# 3. Spusti
python runner.py --once

git pull
test5
***********
Ako spustiť kód na VPS (DealFinder)
Situácia: Slúžobný PC, firemná sieť blokuje priame spojenia na VPS.
Možnosti:

Mobil hotspot ← najrýchlejšie

Vypneš wifi na PC, zapneš hotspot z mobilu
SSH: ssh root@95.217.234.39
Spustíš čo potrebuješ


GitHub Actions — workflow_dispatch

Pridáš workflow_dispatch do deploy.yml
Na GitHube → Actions → Run workflow → zadáš príkaz
Vhodné pre opakované operácie


Webhook endpoint

Rozšíriš webhook.py o /run endpoint
Zavoláš cez Actions alebo curl



VPS info:

IP: 95.217.234.39
User: root
Projekt: /opt/dealfinder
Webhook: beží na porte 9000 ako systemd service

Bežné príkazy na VPS:
bashcd /opt/dealfinder
docker-compose logs -f scraper      # logy
docker-compose restart scraper      # reštart
git pull                            # manuálny pull

Stačí mi napísať "pripomeň si ako spustiť kód na VPS" a viem čo robiť.
************************
