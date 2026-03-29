"""
payment.py ─ OxaPay payment flow for users
Deposit → select method → enter amount → create invoice → poll status → credit balance
"""
import asyncio
import uuid
from datetime import datetime

from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as KB
from telegram.ext import (
    ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters, CommandHandler
)
from core import (
    t, fmt_date, get_user, update_balance, start_cmd,
    get_payment_methods, get_payment_method,
    create_payment, get_payment_by_track, update_payment,
    get_user_payments, get_setting, is_admin,
    balance_kb, back_kb, paginated_kb,
    payment_invoice_kb, payment_method_select_kb
)
from oxapay import oxapay, OxaPayError, PAYMENT_STATUS, init_oxapay

# Conversation states
S_AMOUNT = "PAY_AMOUNT"
END = ConversationHandler.END


async def _lang(tid):
    u = await get_user(tid)
    return u.get("language", "ar") if u else "ar"


# ════════════════════════════════════════════════════════════════════════════
# DEPOSIT MENU
# ════════════════════════════════════════════════════════════════════════════

async def pay_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Cancel any active conversation states
    if ctx.user_data:
        for key in list(ctx.user_data.keys()):
            if not key.startswith("_"):
                ctx.user_data.pop(key)

    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    # Check OxaPay enabled
    if await get_setting("oxapay_enabled") != "1":
        await q.edit_message_text(t(lang, "pay_oxapay_off"),
                                   reply_markup=back_kb(lang, "bl:m"))
        return

    methods = await get_payment_methods(enabled_only=True)
    if not methods:
        await q.edit_message_text(t(lang, "pay_no_methods"),
                                   reply_markup=back_kb(lang, "bl:m"))
        return

    await q.edit_message_text(
        t(lang, "pay_select_method"), parse_mode="HTML",
        reply_markup=payment_method_select_kb(lang, methods)
    )


async def pay_select_method_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """pay:sel:{pm_id}"""
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    pm_id = int(q.data.split(":")[-1])
    pm    = await get_payment_method(pm_id)
    if not pm or not pm.get("is_enabled"):
        await q.edit_message_text(t(lang, "pay_no_methods"),
                                   reply_markup=back_kb(lang, "bl:m"))
        return

    ctx.user_data["pay_pm_id"]  = pm_id
    ctx.user_data["pay_coin"]   = pm.get("coin","USDT")
    ctx.user_data["pay_min"]    = pm.get("min_amount", 1.0)
    ctx.user_data["pay_max"]    = pm.get("max_amount", 10000.0)
    ctx.user_data["pay_fee"]    = pm.get("fee_paid_by", 0)
    ctx.user_data["pay_life"]   = pm.get("lifetime_min", 30)
    ctx.user_data["pay_under"]  = pm.get("underpaid_cover", 2.5)
    ctx.user_data["pay_network"]= pm.get("network","")

    await q.edit_message_text(
        t(lang, "pay_enter_amount",
          min=pm.get("min_amount",1.0), max=pm.get("max_amount",10000.0)),
        parse_mode="HTML",
        reply_markup=back_kb(lang, "pay:m")
    )
    return S_AMOUNT


async def pay_recv_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    raw  = (update.message.text or "").strip().replace(",", ".")

    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang, "pay_invalid_amount"))
        return S_AMOUNT

    pm_min = ctx.user_data.get("pay_min", 1.0)
    pm_max = ctx.user_data.get("pay_max", 10000.0)
    if amount < pm_min:
        await update.message.reply_text(t(lang, "pay_amount_low", min=pm_min))
        return S_AMOUNT
    if amount > pm_max:
        await update.message.reply_text(t(lang, "pay_amount_high", max=pm_max))
        return S_AMOUNT

    coin    = ctx.user_data.get("pay_coin", "USDT")
    network = ctx.user_data.get("pay_network","")

    pay_currency_combined = f"{coin}/{network}" if network else coin

    fee     = ctx.user_data.get("pay_fee", 0)
    life    = ctx.user_data.get("pay_life", 30)
    under   = ctx.user_data.get("pay_under", 2.5)

    loading = await update.message.reply_text(t(lang, "pay_creating"))

    # Reload oxapay with current key from settings
    key = await get_setting("oxapay_key") or ""
    if key:
        init_oxapay(key)

    order_ref = f"dep_{update.effective_user.id}_{uuid.uuid4().hex[:8]}"
    try:
        res = await oxapay.create_invoice(
            amount=float(amount),
            pay_currency=pay_currency_combined,
            order_id=order_ref,
            description=f"Deposit {amount} USD",
            lifetime=int(life),
            fee_paid_by_payer=int(fee),
            underpaid_cover=float(under),
        )
    except OxaPayError as e:
        await loading.edit_text(t(lang, "pay_error", reason=str(e)))
        return END

    track_id    = str(res.get("trackId", ""))
    pay_address = res.get("payAddress", "")
    pay_amount  = res.get("payAmount", "?")
    pay_link    = oxapay.format_pay_link(track_id)

    await create_payment(
        tid=update.effective_user.id,
        track_id=track_id,
        order_ref=order_ref,
        amount_usd=amount,
        pay_currency=coin,
        pay_amount=float(pay_amount) if pay_amount != "?" else 0,
        pay_address=pay_address,
        network=network,
        pay_link=pay_link,
        fee_paid_by=fee,
        underpaid_cover=under,
        lifetime_min=life,
        raw=str(res),
    )

    text = t(lang, "pay_invoice",
             usd=amount, coin=coin,
             network=f"({network})" if network else "",
             pay_amount=pay_amount,
             address=pay_address,
             lifetime=life,
             track_id=track_id)

    await loading.edit_text(text, parse_mode="HTML",
                             reply_markup=payment_invoice_kb(lang, track_id, pay_link))

    # Register for background polling
    pending = ctx.application.bot_data.setdefault("pending_payments", set())
    pending.add(track_id)

    return END


# ════════════════════════════════════════════════════════════════════════════
# CHECK / CANCEL INVOICE
# ════════════════════════════════════════════════════════════════════════════

async def pay_check_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """pay:chk:{track_id}"""
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    track_id = q.data.split(":", 2)[2]
    payment  = await get_payment_by_track(track_id)
    if not payment:
        await q.answer(t(lang, "error"), show_alert=True)
        return

    key = await get_setting("oxapay_key") or ""
    if key: init_oxapay(key)

    try:
        res = await oxapay.check_payment(track_id)
    except OxaPayError as e:
        await q.answer(f"❌ {e}", show_alert=True)
        return

    status = res.get("status", "Waiting")
    icon   = PAYMENT_STATUS.get(status, ("❓","?"))[0]

    await update_payment(track_id, status=status,
                          received_amount=res.get("receivedAmount"),
                          raw_response=str(res))

    if status == "Paid":
        await _confirm_payment(track_id, payment, lang, q.from_user.id, ctx.bot)
        await q.edit_message_text(
            t(lang, "pay_confirmed_notify",
              usd=payment["amount_usd"],
              coin=payment["pay_currency"],
              track_id=track_id,
              balance=(await get_user(q.from_user.id) or {}).get("balance", 0)),
            parse_mode="HTML",
            reply_markup=back_kb(lang, "bl:m")
        )
    else:
        status_key = f"pay_status_{status.lower()}" if f"pay_status_{status.lower()}" in (
            {**{k: "" for k in ["pay_status_waiting","pay_status_confirming","pay_status_paid",
                                 "pay_status_expired","pay_status_error","pay_status_cancelled"]}}
        ) else "pay_status_waiting"
        await q.answer(f"{icon} {t(lang, status_key)}", show_alert=True)


async def pay_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """pay:cxl:{track_id}"""
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    track_id = q.data.split(":", 2)[2]
    await update_payment(track_id, status="Canceled")

    # Remove from pending
    pending = ctx.application.bot_data.get("pending_payments", set())
    pending.discard(track_id)

    await q.edit_message_text(t(lang, "pay_cancelled_ok"),
                               reply_markup=back_kb(lang, "bl:m"))


# ════════════════════════════════════════════════════════════════════════════
# DEPOSIT HISTORY
# ════════════════════════════════════════════════════════════════════════════

async def pay_history_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """pay:h:{page}"""
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    page = int(q.data.split(":")[-1])
    per  = 5
    pays = await get_user_payments(q.from_user.id, limit=per+1, offset=page*per)
    has_more = len(pays) > per
    pays     = pays[:per]

    if not pays and page == 0:
        await q.edit_message_text(t(lang, "pay_history_empty"),
                                   reply_markup=back_kb(lang, "bl:m"))
        return

    lines = [t(lang, "pay_history_title"), ""]
    for p in pays:
        status = p.get("status","Waiting")
        icon   = PAYMENT_STATUS.get(status, ("❓","?"))[0]
        lines.append(t(lang, "pay_history_row",
                        icon=icon, coin=p.get("pay_currency","?"),
                        usd=p.get("amount_usd",0),
                        date=fmt_date(p.get("created_at","")),
                        status=f"{icon} {status}"))
        lines.append("")

    kb = paginated_kb(lang, page, has_more, "pay:h", "bl:m")
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ════════════════════════════════════════════════════════════════════════════
# INTERNAL: credit balance on paid
# ════════════════════════════════════════════════════════════════════════════

async def _confirm_payment(track_id, payment, lang, tid, bot):
    """Credit balance if not already credited."""
    pay = await get_payment_by_track(track_id)
    if not pay or pay.get("paid_at"):
        return  # already processed
    usd = payment.get("amount_usd", 0)
    now = datetime.now().isoformat()
    await update_payment(track_id, status="Paid", paid_at=now)
    new_bal = await update_balance(
        tid, usd, "deposit",
        f"OxaPay deposit {payment.get('pay_currency','')} track:{track_id}",
        ref_id=track_id, method="oxapay"
    )
    if new_bal is not False:
        try:
            await bot.send_message(
                chat_id=tid,
                text=t(lang, "pay_confirmed_notify",
                       usd=usd, coin=payment.get("pay_currency",""),
                       track_id=track_id, balance=new_bal),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ════════════════════════════════════════════════════════════════════════════
# BACKGROUND PAYMENT POLLER STEP (called by JobQueue)
# ════════════════════════════════════════════════════════════════════════════

async def payment_poller_step(bot):
    """Execution step for polling pending payments."""
    try:
        from core import get_pending_payments
        payments = await get_pending_payments()
        if not payments:
            return

        key = await get_setting("oxapay_key") or ""
        if not key:
            return
        init_oxapay(key)

        for p in payments:
            track_id = p.get("track_id")
            tid      = p.get("tg_id")
            lang     = p.get("user_lang","ar")
            if not track_id:
                continue

            # Check if expired_at has passed
            expired_at = p.get("expired_at")
            if expired_at:
                try:
                    if datetime.now() > datetime.fromisoformat(expired_at):
                        await update_payment(track_id, status="Expired")
                        continue
                except Exception:
                    pass

            try:
                res = await oxapay.check_payment(track_id)
            except OxaPayError:
                continue

            status = res.get("status", "Waiting")
            await update_payment(
                track_id,
                status=status,
                received_amount=res.get("receivedAmount"),
                raw_response=str(res)
            )

            if status == "Paid":
                await _confirm_payment(track_id, p, lang, tid, bot)
            elif status in ("Expired", "Error", "Canceled"):
                await update_payment(track_id, status=status)

    except Exception as e:
        import logging
        logging.getLogger("payment_poller").error(f"Poller error: {e}")


# ════════════════════════════════════════════════════════════════════════════
# REGISTER HANDLERS
# ════════════════════════════════════════════════════════════════════════════

def register(app):
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(pay_select_method_cb, pattern=r"^pay:sel:\d+$"),
        ],
        states={
            S_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, pay_recv_amount)],
        },
        fallbacks=[CommandHandler("start", start_cmd)],
        per_message=False, allow_reentry=True,
    )
    app.add_handler(conv)

    app.add_handler(CallbackQueryHandler(pay_menu_cb,    pattern="^pay:m$"))
    app.add_handler(CallbackQueryHandler(pay_check_cb,   pattern=r"^pay:chk:.+$"))
    app.add_handler(CallbackQueryHandler(pay_cancel_cb,  pattern=r"^pay:cxl:.+$"))
    app.add_handler(CallbackQueryHandler(pay_history_cb, pattern=r"^pay:h:\d+$"))
