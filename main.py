"""
main.py ─ Entry point · Background: SMS checker + OxaPay poller
"""
import asyncio
import logging
from datetime import datetime, timedelta
from telegram.ext import Application, TypeHandler, ApplicationHandlerStop
from core import (
    init_db, get_active_purchases_all, update_purchase,
    update_balance, get_setting, BOT_TOKEN, SUPER_ADMIN_IDS,
    get_active_smspool_key, get_user
)
from smspool import pool, SMSError
import handlers, admin, admin_payment, payment, admin_tools

logging.basicConfig(format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


async def sms_checker(app: Application):
    log.info("SMS checker started")
    while True:
        await asyncio.sleep(15)
        try:
            purchases = await get_active_purchases_all()
            if not purchases: continue
            max_mins = int((await get_setting("auto_cancel_minutes")) or 10)
            now = datetime.now()
            for p in purchases:
                oid  = p.get("order_id"); tid = p.get("tg_id"); lang = p.get("user_lang","ar")
                try: age_s = (now - datetime.fromisoformat(p.get("created_at",""))).total_seconds()
                except: age_s = 0
                try: res = await pool.check(oid)
                except SMSError: continue
                status = res.get("status", 0)
                if status == 1:
                    code = res.get("sms",""); full = res.get("full_sms", code)
                    await update_purchase(oid, status="completed", sms_code=code, sms_full=full,
                                          completed_at=now.isoformat())
                    from core import t
                    try:
                        await app.bot.send_message(tid, t(lang,"sms_auto_notify",
                            num=p.get("phone_number",""), service=p.get("service_name",""),
                            code=code, full=full), parse_mode="HTML")
                    except: pass
                elif status == 3 or age_s > max_mins * 60:
                    amt = p.get("cost_display", 0)
                    await update_purchase(oid, status="cancelled", cancelled_at=now.isoformat())
                    await update_balance(tid, amt, "refund", f"Auto-refund {oid}", oid)
                    if status != 3:
                        from core import t
                        try: await app.bot.send_message(tid, t(lang,"auto_cancel",
                            num=p.get("phone_number",""), min=max_mins, amount=amt), parse_mode="HTML")
                        except: pass
        except Exception as e: log.error(f"SMS checker: {e}")


async def payment_poller_task(app: Application):
    from payment import payment_poller
    await payment_poller(app)


# ── Anti-Spam Middleware Logic ────────────────────────────────────────────────
# Use a simple in-memory cache for performance
SPAM_CACHE = {} # {tid: {"last_click": datetime, "spam_count": int, "banned_until": datetime}}

async def antispam_middleware(update, ctx):
    if not update.effective_user or update.effective_user.is_bot:
        return

    tid = update.effective_user.id
    if tid in SUPER_ADMIN_IDS:
        return

    from core import _q, DATABASE_PATH, t
    import aiosqlite

    now = datetime.now()

    # Check cache first
    state = SPAM_CACHE.get(tid)

    if not state:
        # Load from DB
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM user_antispam WHERE telegram_id=?", (tid,))
            row = await cur.fetchone()
            if row:
                state = {
                    "last_click": datetime.fromisoformat(row["last_click_at"]),
                    "spam_count": row["spam_count"],
                    "ban_count": row["ban_count"],
                    "banned_until": datetime.fromisoformat(row["banned_until"]) if row["banned_until"] else None
                }
            else:
                state = {
                    "last_click": now,
                    "spam_count": 0,
                    "ban_count": 0,
                    "banned_until": None
                }
                await db.execute("INSERT INTO user_antispam (telegram_id, last_click_at) VALUES (?,?)",
                                 (tid, now.isoformat()))
                await db.commit()
        SPAM_CACHE[tid] = state

    # Check ban
    if state["banned_until"]:
        if now < state["banned_until"]:
            raise ApplicationHandlerStop()
        else:
            # Ban expired
            state["banned_until"] = None
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET banned_until=NULL WHERE telegram_id=?", (tid,))
                await db.commit()

    # Check spamming
    diff = (now - state["last_click"]).total_seconds()
    state["last_click"] = now

    if diff < 0.6:
        state["spam_count"] += 1
        if state["spam_count"] >= 5:
            # Apply ban
            state["ban_count"] += 1
            durations = [10, 120, 1440]
            mins = durations[min(state["ban_count"]-1, 2)]
            state["banned_until"] = now + timedelta(minutes=mins)
            state["spam_count"] = 0

            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET banned_until=?, ban_count=?, spam_count=0, last_click_at=? WHERE telegram_id=?",
                                 (state["banned_until"].isoformat(), state["ban_count"], now.isoformat(), tid))
                await db.commit()

            # Notify user
            u = await get_user(tid)
            lang = u.get("language", "ar") if u else "ar"
            try:
                await ctx.bot.send_message(tid, t(lang, "antispam_ban", mins=mins))
            except: pass

            # Notify admins
            for aid in SUPER_ADMIN_IDS:
                try:
                    await ctx.bot.send_message(aid, f"🚫 AntiSpam: User {tid} ({update.effective_user.first_name}) banned for {mins}m")
                except: pass

            raise ApplicationHandlerStop()
        else:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET spam_count=?, last_click_at=? WHERE telegram_id=?",
                                 (state["spam_count"], now.isoformat(), tid))
                await db.commit()

            if state["spam_count"] == 3:
                u = await get_user(tid)
                lang = u.get("language", "ar") if u else "ar"
                try:
                    await ctx.bot.send_message(tid, t(lang, "antispam_warn"))
                except: pass
    else:
        # Reset spam count
        if state["spam_count"] > 0:
            state["spam_count"] = 0
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET spam_count=0, last_click_at=? WHERE telegram_id=?",
                                 (now.isoformat(), tid))
                await db.commit()
        else:
             # Just update last_click in DB
             async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET last_click_at=? WHERE telegram_id=?",
                                 (now.isoformat(), tid))
                await db.commit()


async def post_init(app: Application):
    log.info("Initialising database...")
    await init_db()
    log.info("Database ready")

    # Load OxaPay key
    key = await get_setting("oxapay_key")
    if key:
        from oxapay import init_oxapay; init_oxapay(key)
        log.info("OxaPay key loaded")

    # Load active SMSPool key (may be stored in DB)
    active_sk = await get_active_smspool_key()
    if active_sk:
        pool.key = active_sk
        log.info("SMSPool key loaded from DB")

    asyncio.create_task(sms_checker(app))
    asyncio.create_task(payment_poller_task(app))
    log.info("Background tasks started")


def build_app() -> Application:
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN not set!")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register Anti-Spam Middleware
    app.add_handler(TypeHandler(object, antispam_middleware), group=-1)

    # Priority order matters for ConversationHandlers
    admin.register(app)
    admin_payment.register(app)
    admin_tools.register(app)  # broadcast + smspool keys + msg commands
    payment.register(app)
    handlers.register(app)

    log.info("All handlers registered")
    return app


def main():
    log.info("SMS Bot Starting...")
    build_app().run_polling(
        allowed_updates=["message","callback_query","inline_query"],
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()
