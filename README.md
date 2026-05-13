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
commit
cd /opt/dealfinder
git add -A
git commit -m "fix free alerts count"
git push origin main

run once
git pull
docker-compose down
docker-compose up -d --build
docker-compose exec scraper python -u runner.py --once

docker-compose restart scraper

run check.py
docker cp check.py dealfinder_scraper_1:/app/check.py
docker-compose exec scraper python /app/check.py

docker cp check.py dealfinder_scraper_1:/app/check.py && docker-compose exec scraper python /app/check.py

Sprav zmeny a commitni:
bashdocker cp processing/deal_score.py dealfinder_scraper_1:/app/processing/deal_score.py
docker cp outputs/telegram.py dealfinder_scraper_1:/app/outputs/telegram.py
docker-compose exec scraper python /app/check.py
Po overení:
bashgit add processing/deal_score.py outputs/telegram.py
git commit -m "refactor: rename avg_per_m2 -> median_per_m2, confidence on separate line, n= -> porovnaní"
docker-compose restart scraper

docker stop dealfinder_scraper_1
docker rm dealfinder_scraper_1
docker build -t dealfinder_scraper .
docker run -d --name dealfinder_scraper_1 --network dealfinder_default --env-file .env dealfinder_scraper python -u runner.py --loop