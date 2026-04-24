"""
DealFinder — Telegram Subscription Bot
Bot: @dealfinder_sk_bot

Čo robí:
- /start  → zapíše usera do DB, pošle jednorazový invite link do paid kanála
- /status → ukáže dátum expirácie
- daily job o 09:00 UTC → 3 dni pred koncom pošle upozornenie, po expirácii vyhodí z kanála

Inštalácia:
    pip install "python-telegram-bot[job-queue]" python-dotenv

.env:
    BOT_TOKEN=123456:ABC...
    CHANNEL_ID=-100xxxxxxxxxx   ← ID plateného kanála (nie bota)
    DAYS_ACCESS=30
"""

import os
import sqlite3
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
CHANNEL_ID  = int(os.getenv("CHANNEL_ID"))
DAYS_ACCESS = int(os.getenv("DAYS_ACCESS", "30"))
DB_PATH     = "members.db"

RENEWAL_LINK = "https://dealfinderalerts.gumroad.com/l/pwcgi"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS members (
            telegram_id  INTEGER PRIMARY KEY,
            username     TEXT,
            first_name   TEXT,
            joined_at    TEXT,
            expires_at   TEXT,
            warned       INTEGER DEFAULT 0,
            active       INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# /start — aktivácia prístupu
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    now  = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=DAYS_ACCESS)

    conn = get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO members
            (telegram_id, username, first_name, joined_at, expires_at, warned, active)
        VALUES (?, ?, ?, ?, ?, 0, 1)
    """, (
        user.id,
        user.username,
        user.first_name,
        now.isoformat(),
        expires_at.isoformat(),
    ))
    conn.commit()
    conn.close()

    # jednorazový invite link platný 24h
    invite = await context.bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        member_limit=1,
        expire_date=now + timedelta(hours=24),
        name=f"user_{user.id}",
    )

    await update.message.reply_text(
        f"👋 Vitaj v DealFinder Premium!\n\n"
        f"✅ Tvoj prístup je aktívny na {DAYS_ACCESS} dní.\n"
        f"📅 Platí do: {expires_at.strftime('%d.%m.%Y')}\n\n"
        f"Tu je tvoj súkromný vstup do kanála:\n"
        f"{invite.invite_link}\n\n"
        f"⚠️ Link je jednorazový a vyprší za 24 hodín."
    )


# ---------------------------------------------------------------------------
# /status — stav predplatného
# ---------------------------------------------------------------------------

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = get_conn()
    row  = conn.execute(
        "SELECT expires_at, active FROM members WHERE telegram_id = ?",
        (user.id,)
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text(
            "Nemám ťa v systéme.\n\n"
            "Ak si zaplatil na Gumroad, klikni na link z potvrdzovacieho emailu "
            "a aktivuj prístup cez /start."
        )
        return

    expires_at_str, active = row
    expires_at = datetime.fromisoformat(expires_at_str)
    now        = datetime.now(timezone.utc)
    days_left  = (expires_at - now).days

    if active and now < expires_at:
        await update.message.reply_text(
            f"✅ Predplatné: aktívne\n"
            f"📅 Platí do: {expires_at.strftime('%d.%m.%Y')}\n"
            f"⏳ Zostatok: {days_left} dní\n\n"
            f"Pre obnovu: {RENEWAL_LINK}"
        )
    else:
        await update.message.reply_text(
            f"❌ Predplatné: neaktívne\n\n"
            f"Pre obnovu prístupu: {RENEWAL_LINK}"
        )


# ---------------------------------------------------------------------------
# Daily job — upozornenia + odobratie po expirácii
# ---------------------------------------------------------------------------

async def check_expirations(context: ContextTypes.DEFAULT_TYPE):
    now  = datetime.now(timezone.utc)
    conn = get_conn()

    rows = conn.execute(
        "SELECT telegram_id, expires_at, warned FROM members WHERE active = 1"
    ).fetchall()

    for telegram_id, expires_at_raw, warned in rows:
        expires_at = datetime.fromisoformat(expires_at_raw)
        days_left  = (expires_at - now).days

        # --- upozornenie 3 dni pred koncom ---
        if 0 < days_left <= 3 and warned == 0:
            try:
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        f"⚠️ Tvoj prístup do DealFinder Premium končí o {days_left} {'deň' if days_left == 1 else 'dni'}.\n\n"
                        f"Pre obnovu predplatného:\n{RENEWAL_LINK}"
                    ),
                )
                conn.execute(
                    "UPDATE members SET warned = 1 WHERE telegram_id = ?",
                    (telegram_id,),
                )
            except Exception as e:
                print(f"[warn] Upozornenie zlyhalo pre {telegram_id}: {e}")

        # --- odobratie po expirácii ---
        if now >= expires_at:
            try:
                await context.bot.ban_chat_member(
                    chat_id=CHANNEL_ID,
                    user_id=telegram_id,
                )
                # unban hneď — ban slúži len na vyhodenie, nie trvalý zákaz
                await context.bot.unban_chat_member(
                    chat_id=CHANNEL_ID,
                    user_id=telegram_id,
                )
                conn.execute(
                    "UPDATE members SET active = 0 WHERE telegram_id = ?",
                    (telegram_id,),
                )
                await context.bot.send_message(
                    chat_id=telegram_id,
                    text=(
                        "❌ Tvoj prístup do DealFinder Premium skončil.\n\n"
                        f"Pre obnovu: {RENEWAL_LINK}"
                    ),
                )
            except Exception as e:
                print(f"[remove] Odobratie zlyhalo pre {telegram_id}: {e}")

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status))

    # kontrola každý deň o 09:00 UTC
    app.job_queue.run_daily(
        check_expirations,
        time=datetime.strptime("09:00", "%H:%M").time(),
    )

    print("[bot] DealFinder bot štartuje...")
    app.run_polling()


if __name__ == "__main__":
    main()