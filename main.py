"""
main.py ─ Entry point · Background: SMS checker + OxaPay poller
"""
import asyncio
import logging
from datetime import datetime
from telegram.ext import Application
from core import (
    init_db, get_active_purchases_all, update_purchase,
    update_balance, get_setting, BOT_TOKEN,
    get_active_smspool_key
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
