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

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

async def sms_checker_job(ctx):
    try:
        purchases = await get_active_purchases_all()
        if not purchases: return
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
                await update_purchase(oid, status="completed", sms_code=code, sms_full=full, completed_at=now.isoformat())
                from core import t
                try: await ctx.bot.send_message(tid, t(lang,"sms_auto_notify", num=p.get("phone_number",""), service=p.get("service_name",""), code=code, full=full), parse_mode="HTML")
                except: pass
            elif status == 3 or age_s > max_mins * 60:
                amt = p.get("cost_display", 0)
                await update_purchase(oid, status="cancelled", cancelled_at=now.isoformat())
                await update_balance(tid, amt, "refund", f"Auto-refund {oid}", oid)
                if status != 3:
                    from core import t
                    try: await ctx.bot.send_message(tid, t(lang,"auto_cancel", num=p.get("phone_number",""), min=max_mins, amount=amt), parse_mode="HTML")
                    except: pass
    except Exception as e: log.error(f"SMS checker: {e}")

async def payment_poller_job(ctx):
    from payment import payment_poller_step
    await payment_poller_step(ctx.bot)

# ── Anti-Spam Middleware Logic ────────────────────────────────────────────────
SPAM_CACHE = {}

async def antispam_middleware(update, ctx):
    if not update or not update.effective_user or update.effective_user.is_bot: return
    tid = update.effective_user.id
    if tid in SUPER_ADMIN_IDS: return
    from core import DATABASE_PATH, t
    import aiosqlite
    now = datetime.now()
    state = SPAM_CACHE.get(tid)
    if not state:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM user_antispam WHERE telegram_id=?", (tid,))
            row = await cur.fetchone()
            if row:
                state = {
                    "last_click": datetime.fromisoformat(row["last_click_at"]),
                    "series_start": datetime.fromisoformat(row["series_start_at"]) if row["series_start_at"] else now,
                    "spam_count": row["spam_count"], "ban_count": row["ban_count"],
                    "banned_until": datetime.fromisoformat(row["banned_until"]) if row["banned_until"] else None
                }
            else:
                state = {"last_click": now, "series_start": now, "spam_count": 0, "ban_count": 0, "banned_until": None}
                await db.execute("INSERT INTO user_antispam (telegram_id, last_click_at, series_start_at) VALUES (?,?,?)", (tid, now.isoformat(), now.isoformat()))
                await db.commit()
        SPAM_CACHE[tid] = state

    if state["banned_until"]:
        if now < state["banned_until"]: raise ApplicationHandlerStop()
        else:
            state["banned_until"] = None
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute("UPDATE user_antispam SET banned_until=NULL WHERE telegram_id=?", (tid,))
                await db.commit()

    if (now - state["last_click"]).total_seconds() > 10.0:
        state["spam_count"] = 0
        state["series_start"] = now
    state["last_click"] = now
    state["spam_count"] += 1
    duration = (now - state["series_start"]).total_seconds()
    is_banned = False
    is_warned = False
    if state["ban_count"] == 0:
        if state["spam_count"] == 9 and duration <= 2.0: is_warned = True
        if state["spam_count"] >= 17 and duration <= 7.0: is_banned = True
    else:
        if state["spam_count"] >= 9 and duration <= 2.0: is_banned = True

    if is_banned:
        state["ban_count"] += 1
        durations = [10, 120, 1440]
        mins = durations[min(state["ban_count"]-1, 2)]
        state["banned_until"] = now + timedelta(minutes=mins)
        state["spam_count"] = 0
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("UPDATE user_antispam SET banned_until=?, ban_count=?, spam_count=0, last_click_at=?, series_start_at=? WHERE telegram_id=?",
                             (state["banned_until"].isoformat(), state["ban_count"], now.isoformat(), now.isoformat(), tid))
            await db.commit()
        u = await get_user(tid)
        lang = u.get("language", "ar") if u else "ar"
        try: await ctx.bot.send_message(tid, t(lang, "antispam_ban", mins=mins))
        except: pass
        for aid in SUPER_ADMIN_IDS:
            try: await ctx.bot.send_message(aid, f"🚫 AntiSpam: User {tid} banned for {mins}m")
            except: pass
        raise ApplicationHandlerStop()

    if is_warned:
        u = await get_user(tid)
        lang = u.get("language", "ar") if u else "ar"
        try: await ctx.bot.send_message(tid, t(lang, "antispam_warn"))
        except: pass

    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("UPDATE user_antispam SET spam_count=?, last_click_at=?, series_start_at=? WHERE telegram_id=?",
                         (state["spam_count"], state["last_click"].isoformat(), state["series_start"].isoformat(), tid))
        await db.commit()

async def post_init(app: Application):
    log.info("Initialising database...")
    await init_db()
    from core import OXAPAY_API_KEY
    db_key = await get_setting("oxapay_key")
    key = db_key if (db_key and len(db_key) > 5) else OXAPAY_API_KEY
    if key:
        from oxapay import init_oxapay
        init_oxapay(key)
    active_sk = await get_active_smspool_key()
    if active_sk: pool.key = active_sk

    # Start Jobs
    app.job_queue.run_repeating(sms_checker_job, interval=15, first=5)
    app.job_queue.run_repeating(payment_poller_job, interval=30, first=10)

    log.info("Background jobs started via JobQueue")

def build_app() -> Application:
    if not BOT_TOKEN: raise RuntimeError("BOT_TOKEN not set!")
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    app.add_handler(TypeHandler(object, antispam_middleware), group=-1)
    admin.register(app)
    admin_payment.register(app)
    admin_tools.register(app)
    payment.register(app)
    handlers.register(app)
    return app

if __name__ == "__main__":
    build_app().run_polling(allowed_updates=["message","callback_query","inline_query"], drop_pending_updates=True)
