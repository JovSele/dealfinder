import requests

TOKEN = "8443644162:AAGGfvqdkEZs4UTjkkGvmJoO5Mk99oLJt8k"          # tvoj token
ADMIN = "-1003924625158"               # tvoj admin chat ID (celé číslo)

r = requests.post(
    f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    json={"chat_id": ADMIN, "text": "test admin"},
    timeout=10,
)
print(r.status_code, r.json())