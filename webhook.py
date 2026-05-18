from flask import Flask, request, jsonify, render_template_string
import subprocess
import json
import os

app = Flask(__name__)

@app.route('/deploy', methods=['POST'])
def deploy():
    if request.headers.get("X-Deploy-Token") != os.getenv("DEPLOY_TOKEN"):
        return "Forbidden", 403
    subprocess.run(['git', 'pull'], cwd='/opt/dealfinder')
    subprocess.run(['docker', 'build', '--no-cache', '-t', 'dealfinder-scraper', '/opt/dealfinder'])
    subprocess.run(['docker', 'stop', 'dealfinder_scraper_1'], check=False)
    subprocess.run(['docker', 'rm', 'dealfinder_scraper_1'], check=False)
    subprocess.run(['docker', 'run', '-d', '--name', 'dealfinder_scraper_1',
                    '--env-file', '/opt/dealfinder/.env',
                    '--network', 'dealfinder_default',
                    'dealfinder-scraper'])
    return 'OK'

@app.route('/deal')
def deal_detail():
    try:
        with open('/var/www/vamuo/deal.json', 'r', encoding='utf-8') as f:
            deal = json.load(f)
    except:
        deal = None
    return render_template_string(DEAL_TEMPLATE, deal=deal)


DEAL_TEMPLATE = '''<!DOCTYPE html>
<html lang="cs">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>VAMUO Signal — Detail</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #F7F6F3; --anthracite: #1C1C1E; --gold: #B8972A; --gold-l: #C9A84C;
      --text: #111; --muted: #6B7280; --green: #15803D; --border: #E0DDD8;
      --surface: #fff; --r: 14px;
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); -webkit-font-smoothing: antialiased; }
    nav {
      background: var(--anthracite); padding: 0 40px; height: 60px;
      display: flex; align-items: center; justify-content: space-between;
    }
    .logo { display: flex; align-items: center; gap: 10px; text-decoration: none; }
    .logo-mark { width: 30px; height: 30px; background: var(--gold); border-radius: 7px; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 14px; color: #fff; }
    .logo-name { font-weight: 700; font-size: 16px; letter-spacing: 0.08em; color: #fff; text-transform: uppercase; }
    .back { color: rgba(255,255,255,0.5); text-decoration: none; font-size: 13px; }
    .back:hover { color: white; }
    .container { max-width: 680px; margin: 0 auto; padding: 48px 24px; }
    .delay-banner {
      background: rgba(184,151,42,0.08); border: 1px solid rgba(184,151,42,0.25);
      border-radius: 8px; padding: 12px 16px; margin-bottom: 32px;
      font-size: 13px; color: var(--gold-l); display: flex; align-items: center; gap: 8px;
    }
    .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: 32px; margin-bottom: 16px; }
    .pct-big { font-size: 56px; font-weight: 800; color: var(--text); letter-spacing: -0.04em; line-height: 1; margin-bottom: 4px; }
    .pct-sub { font-size: 15px; color: var(--muted); margin-bottom: 24px; }
    .title { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
    .price { font-size: 32px; font-weight: 800; letter-spacing: -0.04em; margin-bottom: 4px; }
    .savings { font-size: 14px; color: var(--green); font-weight: 600; margin-bottom: 24px; }
    .divider { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
    .row { display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px; }
    .row:last-child { border-bottom: none; }
    .row-label { color: var(--muted); }
    .row-value { font-weight: 600; }
    .meter-wrap { margin: 20px 0; }
    .meter-labels { display: flex; justify-content: space-between; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .meter-bar { height: 6px; border-radius: 999px; background: var(--border); overflow: hidden; }
    .meter-fill { height: 100%; border-radius: 999px; background: var(--gold); }
    .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 16px; }
    .tag { font-size: 12px; padding: 4px 10px; border-radius: 4px; font-weight: 500; }
    .tag-good { background: rgba(21,128,61,0.08); color: #15803D; }
    .tag-warn { background: rgba(180,83,9,0.08); color: #B45309; }
    .conf { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--green); margin-top: 16px; }
    .conf-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
    .btn-original {
      display: block; text-align: center;
      background: var(--anthracite); color: white;
      padding: 16px 24px; border-radius: 8px;
      font-weight: 700; font-size: 15px; text-decoration: none;
      margin-top: 8px; transition: background 0.2s;
    }
    .btn-original:hover { background: #2C2C2E; }
    .disclaimer { font-size: 12px; color: var(--muted); text-align: center; margin-top: 16px; line-height: 1.6; }
    footer { background: #111; border-top: 1px solid rgba(255,255,255,0.06); padding: 24px 40px; text-align: center; }
    footer p { font-size: 12px; color: rgba(255,255,255,0.3); }
  </style>
</head>
<body>
<nav>
  <a class="logo" href="/">
    <div class="logo-mark">V</div>
    <div class="logo-name">VAMUO</div>
  </a>
  <a class="back" href="/">← Zpět na hlavní stránku</a>
</nav>

{% if deal %}
<div class="container">
  <div class="delay-banner">
    🕐 Veřejné ukázky jsou publikovány se zpožděním. Členové dostávají signály okamžitě.
  </div>

  <div class="card">
    <div class="pct-big">−{{ "%.1f"|format(deal.pct_below) }}%</div>
    <div class="pct-sub">pod mediánem srovnatelných nemovitostí</div>
    <div class="title">{{ deal.title }}</div>
    <div class="price">{{ "{:,.0f}".format(deal.price).replace(",", " ") }} Kč</div>
    <div class="savings">↓ odchylka od mediánu ~{{ "{:,.0f}".format(deal.savings).replace(",", " ") }} Kč</div>

    <div class="meter-wrap">
      <div class="meter-labels">
        <span>{{ "{:,.0f}".format(deal.price_per_m2).replace(",", " ") }} Kč/m²</span>
        <span>medián {{ "{:,.0f}".format(deal.median_per_m2).replace(",", " ") }} Kč/m²</span>
      </div>
      <div class="meter-bar">
        <div class="meter-fill" style="width:{{ (deal.price_per_m2 / deal.median_per_m2 * 100)|round|int }}%"></div>
      </div>
    </div>

    <div class="tags">
      {% for t in deal.tags_good %}<span class="tag tag-good">✅ {{ t }}</span>{% endfor %}
      {% for t in deal.tags_warn %}<span class="tag tag-warn">⚠️ {{ t }}</span>{% endfor %}
    </div>

    <div class="conf"><span class="conf-dot"></span>{{ deal.conf_label }}</div>
  </div>

  <div class="card">
    <div class="row"><span class="row-label">Lokalita</span><span class="row-value">📍 {{ deal.locality }}</span></div>
    <div class="row"><span class="row-label">Dispozice</span><span class="row-value">{{ deal.rooms }}</span></div>
    <div class="row"><span class="row-label">Plocha</span><span class="row-value">{{ deal.area_m2 }} m²</span></div>
    <div class="row"><span class="row-label">Zachyceno</span><span class="row-value">{{ deal.captured_at[:16].replace("T", " ") }}</span></div>
    <div class="row"><span class="row-label">Počet srovnání</span><span class="row-value">{{ deal.sample_size }} nemovitostí</span></div>
    <div class="row"><span class="row-label">Okres</span><span class="row-value">{{ deal.district }}</span></div>
    <div class="row"><span class="row-label">Cena/m²</span><span class="row-value">{{ "{:,.0f}".format(deal.price_per_m2).replace(",", " ") }} Kč/m²</span></div>
    <div class="row"><span class="row-label">Medián lokality</span><span class="row-value">{{ "{:,.0f}".format(deal.median_per_m2).replace(",", " ") }} Kč/m²</span></div>
    <div class="row"><span class="row-label">Odchylka od mediánu</span><span class="row-value" style="color:var(--green)">~{{ "{:,.0f}".format(deal.savings).replace(",", " ") }} Kč</span></div>
  </div>

  <a class="btn-original" href="{{ deal.url }}" target="_blank" rel="noopener">
    Zobrazit původní inzerát →
  </a>
  <div class="disclaimer">
    Odkaz vede na veřejný inzerát třetí strany. VAMUO provádí pouze cenovou analýzu.
  </div>
</div>
{% else %}
<div class="container" style="text-align:center;padding-top:80px">
  <p style="color:var(--muted)">Signal není momentálně dostupný.</p>
</div>
{% endif %}

<footer><p>© 2026 VAMUO — Realtime cenová analýza</p></footer>
</body>
</html>'''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9000)
