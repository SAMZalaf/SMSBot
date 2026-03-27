"""
handlers.py ─ All user-facing handlers
start · language · buy · active numbers · history · balance · profile · stats
"""
import asyncio
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as KB,
    InlineQueryResultArticle, InputTextMessageContent
)
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    InlineQueryHandler
)
from core import (
    t, fmt_date, fmt_list, status_label, tx_name, tx_icon, user_display,
    get_user, upsert_user, update_user, update_balance,
    get_user_purchases, count_user_purchases, get_purchase, update_purchase,
    create_purchase, get_user_transactions, get_user_detailed_stats, is_admin,
    get_setting, get_referral_code, link_referral, get_user_referrals,
    count_user_referrals, get_user_referral_stats, get_all_referral_earnings,
    process_referral_commission,
    get_user_purchases_filtered, count_user_purchases_filtered,
    cleanup_old_purchases, get_history_summary,
    ITEMS_PER_PAGE,
    main_menu_kb, lang_kb, countries_kb, services_kb, confirm_kb,
    number_detail_kb, cancel_ask_kb, reuse_confirm_kb, paginated_kb,
    balance_kb, profile_kb, referral_menu_kb, back_kb,
    history_filter_kb, history_item_kb, history_cleanup_confirm_kb
)
from smspool import pool, SMSError

import hashlib


# ── helpers ───────────────────────────────────────────────────────────────────

async def _lang(tid):
    u = await get_user(tid)
    return u.get("language", "ar") if u else "ar"

async def _ensure_user(update: Update):
    u = update.effective_user
    return await upsert_user(u.id, u.username, u.first_name, u.last_name)

async def _check_banned(user, update: Update) -> bool:
    if user.get("is_banned"):
        lang = user.get("language", "ar")
        await update.effective_message.reply_text(t(lang, "banned"))
        return True
    return False

async def _check_maintenance(lang, update: Update) -> bool:
    if await get_setting("bot_active") == "0":
        msg_key = f"maintenance_msg_{lang}"
        extra = await get_setting(msg_key) or ""
        await update.effective_message.reply_text(t(lang, "maintenance", msg=extra), parse_mode="HTML")
        return True
    return False

async def _send_or_edit(update, text, kb=None, parse_mode="HTML"):
    kw = {"text": text, "parse_mode": parse_mode}
    if kb: kw["reply_markup"] = kb
    if update.callback_query:
        await update.callback_query.edit_message_text(**kw)
    else:
        await update.effective_message.reply_text(**kw)


# ════════════════════════════════════════════════════════════════════════════
# START / MENU
# ════════════════════════════════════════════════════════════════════════════

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # Cancel any active conversation states
    if ctx.user_data:
        for key in list(ctx.user_data.keys()):
            if not key.startswith("_"): # Convention: persistent data starts with _
                ctx.user_data.pop(key)

    user = await _ensure_user(update)
    if await _check_banned(user, update): return
    lang  = user.get("language", "ar")
    if await _check_maintenance(lang, update): return
    adm   = await is_admin(update.effective_user.id)
    name  = update.effective_user.first_name
    bal   = user.get("balance", 0.0)

    # Handle referral code in /start payload
    if update.message and update.message.text:
        args = update.message.text.split()
        if len(args) > 1 and args[1].startswith("ref_"):
            code = args[1][4:]  # strip "ref_" prefix
            referrer = await get_user_by_referral_code_safe(code)
            if referrer and referrer["telegram_id"] != update.effective_user.id:
                linked = await link_referral(update.effective_user.id, referrer["telegram_id"])
                if linked:
                    # Notify new user
                    r_name = referrer.get("first_name","") or referrer.get("username","")
                    await update.message.reply_text(
                        t(lang, "ref_welcomed", name=r_name), parse_mode="HTML"
                    )
                    # Notify referrer
                    r_lang = referrer.get("language","ar")
                    try:
                        await ctx.bot.send_message(
                            chat_id=referrer["telegram_id"],
                            text=t(r_lang, "ref_new_user_notify", name=name),
                            parse_mode="HTML"
                        )
                    except Exception: pass

    # Custom welcome message
    custom_welcome = await get_setting(f"welcome_{lang}")
    text = custom_welcome if custom_welcome else t(lang, "welcome", name=name, bal=bal)
    await _send_or_edit(update, text, main_menu_kb(lang, adm))

    from telegram.ext import ConversationHandler
    return ConversationHandler.END


async def get_user_by_referral_code_safe(code: str):
    """Wrapper to find user by referral code."""
    from core import get_referral_code, get_all_users
    users = await get_all_users(limit=50000)
    for u in users:
        if get_referral_code(u["telegram_id"]) == code.upper():
            return u
    return None

async def main_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await start_cmd(update, ctx)

async def noop_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def lang_choose_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(t("ar", "choose_lang"), reply_markup=lang_kb())

async def lang_set_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    code = q.data.split(":")[1]
    await update_user(q.from_user.id, language=code)
    await q.edit_message_text(t(code, "lang_set"))
    await start_cmd(update, ctx)


# ════════════════════════════════════════════════════════════════════════════
# BUY FLOW
# ════════════════════════════════════════════════════════════════════════════

async def buy_start_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    await q.edit_message_text(t(lang, "loading"), parse_mode="HTML")
    try:
        countries = await pool.countries()
    except SMSError as e:
        await q.edit_message_text(f"❌ {e}"); return
    if not countries:
        await q.edit_message_text(t(lang, "buy_no_countries")); return
    ctx.application.bot_data["countries"] = countries
    ctx.application.bot_data["country_map"] = {str(c.get("ID",c.get("id",""))): c.get("name","") for c in countries}
    await q.edit_message_text(t(lang, "buy_select_country"), parse_mode="HTML",
                               reply_markup=countries_kb(lang, countries, 0))

async def buy_countries_page_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[2])
    countries = ctx.application.bot_data.get("countries", [])
    if not countries:
        await buy_start_cb(update, ctx); return
    await q.edit_message_text(t(lang, "buy_select_country"), parse_mode="HTML",
                               reply_markup=countries_kb(lang, countries, page))

async def buy_country_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    cid  = q.data.split(":")[2]
    cnt_name = ctx.application.bot_data.get("country_map", {}).get(cid, cid)
    await q.edit_message_text(t(lang, "loading"), parse_mode="HTML")
    try:
        services = await pool.services(country=cid)
    except SMSError as e:
        await q.edit_message_text(f"❌ {e}"); return
    if not services:
        await q.edit_message_text(t(lang, "buy_no_services")); return
    ctx.application.bot_data[f"svc_{cid}"] = services
    ctx.application.bot_data[f"svc_map_{cid}"] = {str(s.get("ID",s.get("id",""))): s for s in services}
    await q.edit_message_text(t(lang, "buy_select_service", country=cnt_name), parse_mode="HTML",
                               reply_markup=services_kb(lang, services, cid, 0))

async def buy_services_page_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    _, _, cid, page = q.data.split(":")
    cnt_name = ctx.application.bot_data.get("country_map", {}).get(cid, cid)
    services = ctx.application.bot_data.get(f"svc_{cid}", [])
    if not services:
        await buy_country_cb(update, ctx); return
    await q.edit_message_text(t(lang, "buy_select_service", country=cnt_name), parse_mode="HTML",
                               reply_markup=services_kb(lang, services, cid, int(page)))

async def buy_service_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """b:sv:{cid}:{sid} → show confirm"""
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    _, _, cid, sid = q.data.split(":")
    cnt_name = ctx.application.bot_data.get("country_map", {}).get(cid, cid)
    svc_map  = ctx.application.bot_data.get(f"svc_map_{cid}", {})
    svc      = svc_map.get(sid, {})
    svc_name = svc.get("name", sid)
    price    = await pool.markup_async(svc.get("price", 0))
    user     = await get_user(q.from_user.id)
    bal      = user.get("balance", 0.0) if user else 0.0
    # Store in user_data for confirm step
    ctx.user_data["buy"] = {"cid": cid, "sid": sid, "cnt_name": cnt_name,
                             "svc_name": svc_name, "price": price}
    await q.edit_message_text(
        t(lang, "buy_confirm", country=cnt_name, service=svc_name, price=price, bal=bal),
        parse_mode="HTML", reply_markup=confirm_kb(lang, cid, sid)
    )

async def buy_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """b:cf:{cid}:{sid}"""
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    _, _, cid, sid = q.data.split(":")
    buy  = ctx.user_data.get("buy", {})
    cnt_name = buy.get("cnt_name") or ctx.application.bot_data.get("country_map", {}).get(cid, cid)
    svc_map  = ctx.application.bot_data.get(f"svc_map_{cid}", {})
    svc      = svc_map.get(sid, {})
    svc_name = buy.get("svc_name") or svc.get("name", sid)
    price    = buy.get("price") or await pool.markup_async(svc.get("price", 0))

    user = await get_user(q.from_user.id)
    if not user:
        await q.edit_message_text(t(lang, "error")); return
    bal = user.get("balance", 0.0)
    if bal < price:
        await q.edit_message_text(t(lang,"buy_insufficient", bal=bal, need=price), parse_mode="HTML",
                                   reply_markup=back_kb(lang,"bl:m")); return

    await q.edit_message_text(t(lang,"loading"), parse_mode="HTML")
    try:
        res = await pool.purchase(country=cid, service=sid)
    except SMSError as e:
        await q.edit_message_text(t(lang,"buy_failed",reason=str(e)),reply_markup=back_kb(lang,"mm")); return

    if not res.get("success"):
        reason = res.get("message", "Unknown error")
        await q.edit_message_text(t(lang,"buy_failed",reason=reason),reply_markup=back_kb(lang,"mm")); return

    phone    = res.get("phonenumber") or res.get("number","")
    order_id = str(res.get("order_id",""))
    cost_api = float(res.get("cost", price) or price)

    new_bal = await update_balance(q.from_user.id, -price, "purchase",
                                    f"Buy {svc_name} ({cnt_name}) {phone}", order_id)
    if new_bal is False:
        await q.edit_message_text(t(lang,"buy_insufficient",bal=bal,need=price),parse_mode="HTML"); return

    purchase = await create_purchase(q.from_user.id, order_id, sid, svc_name, cid, cnt_name, phone,
                           cost_api, price)
    # Register for auto-checker
    if "pending_orders" not in ctx.application.bot_data:
        ctx.application.bot_data["pending_orders"] = set()
    ctx.application.bot_data["pending_orders"].add(order_id)

    # ── Referral commission ──────────────────────────────────────
    if purchase:
        commission = await process_referral_commission(
            purchase_id=purchase["id"],
            referred_tid=q.from_user.id,
            purchase_amount=price,
            bot=ctx.bot
        )
        if commission:
            # Notify referrer (already done inside process_referral_commission)
            pass

    kb = number_detail_kb(lang, order_id, "active")
    await q.edit_message_text(
        t(lang,"buy_success",num=phone,country=cnt_name,service=svc_name,cost=price,oid=order_id),
        parse_mode="HTML", reply_markup=kb
    )


# ════════════════════════════════════════════════════════════════════════════
# ACTIVE NUMBERS
# ════════════════════════════════════════════════════════════════════════════

async def active_list_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    nums = await get_user_purchases(q.from_user.id, status="active")
    if not nums:
        await q.edit_message_text(t(lang,"active_empty"), parse_mode="HTML",
                                   reply_markup=back_kb(lang,"mm")); return
    rows = [[Btn(f"📞 {n.get('phone_number','?')}  📲 {n.get('service_name','?')}",
                 callback_data=f"ac:v:{n.get('order_id','')}")] for n in nums]
    rows.append([Btn(t(lang,"refresh"), callback_data="ac:l"),
                 Btn(t(lang,"back"),    callback_data="mm")])
    await q.edit_message_text(t(lang,"active_title",count=len(nums)), parse_mode="HTML",
                               reply_markup=KB(rows))

async def active_view_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.edit_message_text(t(lang,"error")); return
    status = status_label(lang, p.get("status",""))
    text = t(lang,"num_detail",
              num=p.get("phone_number",""), country=p.get("country_name",""),
              service=p.get("service_name",""), cost=p.get("cost_display",0),
              status=status, date=fmt_date(p.get("created_at","")), oid=oid)
    if p.get("sms_code"):
        text += "\n\n" + t(lang,"sms_received",
                            num=p.get("phone_number",""), code=p.get("sms_code",""),
                            full=p.get("sms_full",""))
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=number_detail_kb(lang, oid, p.get("status","")))

async def active_check_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.answer(t(lang,"error"), show_alert=True); return
    try:
        res = await pool.check(oid)
    except SMSError as e:
        await q.answer(f"❌ {e}", show_alert=True); return

    st = res.get("status", 0)
    if st == 1:
        code = res.get("sms","")
        full = res.get("full_sms", code)
        await update_purchase(oid, status="completed", sms_code=code, sms_full=full,
                               completed_at=datetime.now().isoformat())
        text = t(lang,"sms_received", num=p.get("phone_number",""), code=code, full=full)
        await q.edit_message_text(text, parse_mode="HTML",
                                   reply_markup=number_detail_kb(lang,oid,"completed"))
    elif st == 3:
        await _auto_refund(q.from_user.id, p, lang, ctx.bot)
        await q.answer(t(lang,"cancel_ok"), show_alert=True)
        await active_list_cb(update, ctx)
    else:
        await q.answer(t(lang,"sms_waiting"), show_alert=True)

async def active_resend_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    try:
        res = await pool.resend(oid)
        if res.get("success"):
            await q.answer(t(lang,"resend_ok"), show_alert=True)
        else:
            await q.answer(t(lang,"resend_fail",reason=res.get("message","")), show_alert=True)
    except SMSError as e:
        await q.answer(t(lang,"resend_fail",reason=str(e)), show_alert=True)

async def active_cancel_prompt_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.edit_message_text(t(lang,"error")); return
    await q.edit_message_text(t(lang,"cancel_ask",num=p.get("phone_number","")),
                               parse_mode="HTML", reply_markup=cancel_ask_kb(lang, oid))

async def active_cancel_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.edit_message_text(t(lang,"error")); return
    try:
        res = await pool.cancel(oid)
    except SMSError as e:
        await q.edit_message_text(t(lang,"cancel_fail",reason=str(e))); return
    if res.get("success"):
        await _auto_refund(q.from_user.id, p, lang, ctx.bot)
        await q.edit_message_text(t(lang,"cancel_ok"), reply_markup=back_kb(lang,"ac:l"))
    else:
        await q.edit_message_text(t(lang,"cancel_fail",reason=res.get("message","")),
                                   reply_markup=back_kb(lang,f"ac:v:{oid}"))

async def _auto_refund(tid, p, lang, bot):
    await update_purchase(p["order_id"], status="cancelled",
                           cancelled_at=datetime.now().isoformat())
    amt = p.get("cost_display", 0)
    await update_balance(tid, amt, "refund",
                          f"Refund order {p['order_id']}", p["order_id"])


# ════════════════════════════════════════════════════════════════════════════
# REUSE NUMBER (Task #8) — request new SMS on a completed number
# ════════════════════════════════════════════════════════════════════════════

async def active_reuse_prompt_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ac:ru:{oid} — show confirm to reuse a completed number"""
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.edit_message_text(t(lang,"error")); return

    # Cost = 50% of original (discount for reuse), minimum $0.01
    cost = max(round(p.get("cost_display",0) * 0.5, 6), 0.01)
    ctx.user_data[f"reuse_cost_{oid}"] = cost

    await q.edit_message_text(
        t(lang,"reuse_confirm", num=p.get("phone_number",""), cost=cost),
        parse_mode="HTML",
        reply_markup=reuse_confirm_kb(lang, oid)
    )


async def active_reuse_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ac:ruc:{oid} — execute reuse"""
    q   = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    oid  = q.data.split(":",2)[2]
    p    = await get_purchase(oid)
    if not p:
        await q.edit_message_text(t(lang,"error")); return

    user = await get_user(q.from_user.id)
    cost = ctx.user_data.get(f"reuse_cost_{oid}", max(round(p.get("cost_display",0)*0.5,6), 0.01))
    bal  = user.get("balance",0) if user else 0

    if bal < cost:
        await q.edit_message_text(
            t(lang,"reuse_no_balance", need=cost),
            parse_mode="HTML",
            reply_markup=back_kb(lang,f"ac:v:{oid}")
        ); return

    # Attempt resend via SMSPool on the same order_id
    try:
        res = await pool.resend(oid)
    except SMSError as e:
        await q.edit_message_text(
            t(lang,"reuse_failed", reason=str(e)),
            reply_markup=back_kb(lang,f"ac:v:{oid}")
        ); return

    if not res.get("success"):
        reason = res.get("message","Unknown error")
        await q.edit_message_text(
            t(lang,"reuse_failed", reason=reason),
            reply_markup=back_kb(lang,f"ac:v:{oid}")
        ); return

    # Deduct cost and reset purchase status to active
    await update_balance(q.from_user.id, -cost, "purchase",
                          f"Reuse number {p.get('phone_number','')} (order {oid})", oid)
    await update_purchase(oid,
        status="active",
        sms_code=None,
        sms_full=None,
        completed_at=None
    )

    # Register in pending orders for auto-checker
    pending = ctx.application.bot_data.setdefault("pending_orders", set())
    pending.add(oid)

    num = p.get("phone_number","")
    await q.edit_message_text(
        t(lang,"reuse_success", num=num),
        parse_mode="HTML",
        reply_markup=number_detail_kb(lang, oid, "active")
    )


# ════════════════════════════════════════════════════════════════════════════
# HISTORY
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# HISTORY — Interactive, filterable, searchable, with cleanup
# ════════════════════════════════════════════════════════════════════════════

STATUS_ICONS = {"active":"🟢","completed":"✅","cancelled":"❌",
                "refunded":"💸","pending":"⏳"}

async def _show_history(query, lang, tid, flt="all", page=0, search=None):
    """Shared history display — used by all history callbacks."""
    PER = 6
    items = await get_user_purchases_filtered(
        tid, status=None if flt=="all" else flt,
        search=search, limit=PER+1, offset=page*PER
    )
    total_all = await count_user_purchases_filtered(tid)
    summary   = await get_history_summary(tid)

    has_more = len(items) > PER
    items    = items[:PER]

    done_c   = summary.get("by_status",{}).get("completed",{}).get("count",0)
    cancel_c = summary.get("by_status",{}).get("cancelled",{}).get("count",0)
    total_p  = summary.get("total",0)

    filter_names = {
        "all":       t(lang,"history_filter_all"),
        "completed": t(lang,"history_filter_completed"),
        "active":    t(lang,"history_filter_active"),
        "cancelled": t(lang,"history_filter_cancelled"),
        "refunded":  t(lang,"history_filter_refunded"),
    }
    filtered_count = await count_user_purchases_filtered(
        tid, status=None if flt=="all" else flt, search=search
    )
    pages = max(1, (filtered_count + PER - 1) // PER)

    header = t(lang,"history_header",
                total=total_p, done=done_c, cancel=cancel_c,
                filter_name=filter_names.get(flt, flt),
                page=page+1, pages=pages)

    # Build item rows as inline buttons
    from telegram import InlineKeyboardButton as Btn2, InlineKeyboardMarkup as KB2
    rows = []
    if items:
        for p in items:
            icon = STATUS_ICONS.get(p.get("status",""),"❓")
            svc  = (p.get("service_name","?") or "?")[:12]
            cnt  = (p.get("country_name","?") or "?")[:8]
            cost = p.get("cost_display",0)
            dt   = fmt_date(p.get("created_at",""))[:10]
            oid  = p.get("order_id","")
            label = t(lang,"history_row_btn",
                       icon=icon, svc=svc, cnt=cnt, cost=cost, date=dt)
            rows.append([Btn2(label, callback_data=f"hi:det:{oid}:{flt}:{page}")])
    else:
        pass  # header will show "empty" indication

    # Navigation
    nav = []
    if page > 0:  nav.append(Btn2(t(lang,"prev"), callback_data=f"hi:f:{flt}:{page-1}"))
    if has_more:  nav.append(Btn2(t(lang,"next"), callback_data=f"hi:f:{flt}:{page+1}"))
    if nav: rows.append(nav)

    # Filter + tools bar
    rows.append([
        Btn2(t(lang,"btn_history_filter"),  callback_data=f"hi:fmenu:{flt}:{page}"),
        Btn2(t(lang,"btn_history_search"),  callback_data="hi:search"),
        Btn2(t(lang,"btn_history_cleanup"), callback_data="hi:cleanup"),
    ])
    rows.append([Btn2(t(lang,"back"), callback_data="mm")])

    if not items:
        header += "\n\n" + t(lang,"history_empty")

    # Store current filter in user_data for back navigation
    return header, KB2(rows)


async def history_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:{page} — default entry, no filter"""
    q = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[1])
    text, kb = await _show_history(q, lang, q.from_user.id, "all", page)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def history_filter_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:f:{filter}:{page}"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    parts = q.data.split(":")
    flt   = parts[2]
    page  = int(parts[3])
    search = ctx.user_data.get("hi_search")
    text, kb = await _show_history(q, lang, q.from_user.id, flt, page, search)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def history_fmenu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:fmenu:{current}:{page} — show filter selector"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    parts = q.data.split(":")
    current = parts[2]
    page    = int(parts[3])
    await q.edit_message_text(
        t(lang,"history_title"), parse_mode="HTML",
        reply_markup=history_filter_kb(lang, current, page)
    )


async def history_detail_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:det:{oid}:{filter}:{page}"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    parts = q.data.split(":")
    oid   = parts[2]
    flt   = parts[3] if len(parts) > 3 else "all"
    page  = int(parts[4]) if len(parts) > 4 else 0

    p = await get_purchase(oid)
    if not p:
        await q.answer(t(lang,"error"), show_alert=True); return

    status = status_label(lang, p.get("status",""))
    text   = t(lang,"history_detail",
                num=p.get("phone_number","—"),
                country=p.get("country_name","—"),
                service=p.get("service_name","—"),
                cost=p.get("cost_display",0),
                date=fmt_date(p.get("created_at","")),
                status=status, oid=oid)

    if p.get("sms_code"):
        text += t(lang,"history_detail_sms",
                   code=p["sms_code"], full=p.get("sms_full","") or "")

    await q.edit_message_text(
        text, parse_mode="HTML",
        reply_markup=history_item_kb(lang, oid, p.get("status",""), page, flt)
    )


async def history_search_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:search — prompt user to type search query"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    ctx.user_data["hi_awaiting_search"] = True
    await q.edit_message_text(
        t(lang,"history_search_prompt"),
        reply_markup=back_kb(lang,"hi:f:all:0")
    )


async def history_cleanup_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:cleanup — show cleanup confirmation"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    days = 30  # default cleanup threshold
    count = await count_user_purchases_filtered(
        q.from_user.id, status="cancelled"
    ) + await count_user_purchases_filtered(
        q.from_user.id, status="refunded"
    )
    if count == 0:
        await q.answer(t(lang,"history_cleanup_empty"), show_alert=True); return
    await q.edit_message_text(
        t(lang,"history_cleanup_ask", days=days, count=count),
        parse_mode="HTML",
        reply_markup=history_cleanup_confirm_kb(lang, days)
    )


async def history_cleanup_ok_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:cleanup_ok:{days}"""
    q    = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    days = int(q.data.split(":")[-1])
    # Cleanup only this user's old records
    from core import _q, DATABASE_PATH, get_user as _gu
    u   = await _gu(q.from_user.id)
    uid = u["id"] if u else None
    count = 0
    if uid:
        import aiosqlite
        async with aiosqlite.connect(DATABASE_PATH) as db:
            cur = await db.execute(f"""DELETE FROM purchases
                WHERE user_id=? AND status IN ('cancelled','refunded')
                AND created_at < datetime('now','-{days} days')""", (uid,))
            count = cur.rowcount
            await db.commit()
    await q.edit_message_text(
        t(lang,"history_cleanup_done", count=count),
        reply_markup=back_kb(lang,"hi:f:all:0")
    )


# History action shortcuts (from detail view — proxy to active handlers)
async def history_act_check_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:act_check:{oid} — reuse active_check from history"""
    update.callback_query.data = f"ac:ch:{update.callback_query.data.split(':',2)[2]}"
    await active_check_cb(update, ctx)

async def history_act_resend_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:act_resend:{oid}"""
    update.callback_query.data = f"ac:rs:{update.callback_query.data.split(':',2)[2]}"
    await active_resend_cb(update, ctx)

async def history_act_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:act_cancel:{oid}"""
    update.callback_query.data = f"ac:cn:{update.callback_query.data.split(':',2)[2]}"
    await active_cancel_prompt_cb(update, ctx)

async def history_reuse_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """hi:reuse:{oid}"""
    update.callback_query.data = f"ac:ru:{update.callback_query.data.split(':',2)[2]}"
    await active_reuse_prompt_cb(update, ctx)


# ════════════════════════════════════════════════════════════════════════════
# BALANCE
# ════════════════════════════════════════════════════════════════════════════

async def balance_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    user = await get_user(q.from_user.id)
    if not user:
        await q.edit_message_text(t(lang,"error")); return
    text = t(lang,"balance_title", bal=user["balance"], spent=user["total_spent"],
              purchases=user["total_purchases"])
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=balance_kb(lang))

async def balance_deposit_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Redirect to OxaPay payment menu."""
    q    = update.callback_query
    await q.answer()
    # Trigger the payment module's menu
    from telegram import InlineKeyboardButton as Btn2, InlineKeyboardMarkup as KB2
    # Simulate a "pay:m" callback by re-routing
    q.data = "pay:m"
    from payment import pay_menu_cb
    await pay_menu_cb(update, ctx)

async def balance_txs_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[2])
    per  = 5
    txs  = await get_user_transactions(q.from_user.id, limit=per+1, offset=page*per)
    has_more = len(txs) > per
    txs      = txs[:per]
    if not txs and page == 0:
        await q.edit_message_text(t(lang,"tx_empty"), reply_markup=back_kb(lang,"bl:m")); return
    lines = [t(lang,"tx_title"),""]
    for tx in txs:
        tp = tx.get("type","")
        lines.append(t(lang,"tx_row", icon=tx_icon(tp), name=tx_name(lang,tp),
                        amount=tx.get("amount",0), desc=tx.get("description","—"),
                        after=tx.get("balance_after",0), date=fmt_date(tx.get("created_at",""))))
        lines.append("─"*18)
    kb = paginated_kb(lang, page, has_more, "bl:t", "bl:m")
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


# ════════════════════════════════════════════════════════════════════════════
# PROFILE
# ════════════════════════════════════════════════════════════════════════════

async def profile_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    await q.edit_message_text(t(lang,"profile_title"), parse_mode="HTML",
                               reply_markup=profile_kb(lang))

async def profile_info_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    user = await get_user(q.from_user.id)
    if not user:
        await q.edit_message_text(t(lang,"error")); return
    name  = ((user.get("first_name") or "") + " " + (user.get("last_name") or "")).strip() or "—"
    uname = ("@" + user["username"]) if user.get("username") else "—"
    lang_d = "🇸🇦 العربية" if lang == "ar" else "🇬🇧 English"
    text  = t(lang,"profile_info", tid=user["telegram_id"], name=name, uname=uname,
               bal=user["balance"], spent=user["total_spent"], purchases=user["total_purchases"],
               joined=fmt_date(user.get("created_at","")), active=fmt_date(user.get("last_active","")),
               lang=lang_d)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb(lang,"pr:m"))

async def profile_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    stats = await get_user_detailed_stats(q.from_user.id)
    if not stats:
        await q.edit_message_text(t(lang,"error")); return
    u    = stats["user"]
    by_s = stats["by_status"]
    svcs = fmt_list(stats["top_services"], "service_name")
    cnts = fmt_list(stats["top_countries"], "country_name")
    months_lines = []
    for m in stats["monthly"]:
        months_lines.append(f"  📅 {m['mo']}: {m['n']} مشتريات (${m['tot']:.2f})" if lang=="ar"
                             else f"  📅 {m['mo']}: {m['n']} purchases (${m['tot']:.2f})")
    months = "\n".join(months_lines) or "—"
    text  = t(lang,"stats_title") + "\n\n" + t(lang,"stats_body",
             bal=u["balance"], spent=u["total_spent"], total=u["total_purchases"],
             done=by_s.get("completed",{}).get("count",0),
             cancel=by_s.get("cancelled",{}).get("count",0),
             refund=by_s.get("refunded",{}).get("count",0),
             svcs=svcs, cnts=cnts, months=months)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb(lang,"pr:m"))

async def profile_history_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[2])
    per  = 5
    items = await get_user_purchases(q.from_user.id, limit=per+1, offset=page*per)
    has_more = len(items) > per
    items    = items[:per]
    if not items and page == 0:
        await q.edit_message_text(t(lang,"history_empty"), reply_markup=back_kb(lang,"pr:m")); return
    lines = [t(lang,"history_title"),""]
    for p in items:
        lines.append(t(lang,"history_row",
                        num=p.get("phone_number","—"), svc=p.get("service_name","—"),
                        cnt=p.get("country_name","—"), cost=p.get("cost_display",0),
                        status=status_label(lang,p.get("status","")),
                        date=fmt_date(p.get("created_at",""))))
        lines.append("")
    kb = paginated_kb(lang, page, has_more, "pr:h", "pr:m")
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)

async def profile_balance_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    user = await get_user(q.from_user.id)
    txs  = await get_user_transactions(q.from_user.id, limit=5)
    text = t(lang,"balance_title", bal=user["balance"], spent=user["total_spent"],
              purchases=user["total_purchases"])
    if txs:
        text += "\n\n" + t(lang,"tx_title") + "\n"
        for tx in txs:
            tp = tx.get("type","")
            text += "\n" + t(lang,"tx_row", icon=tx_icon(tp), name=tx_name(lang,tp),
                              amount=tx.get("amount",0), desc=tx.get("description","—"),
                              after=tx.get("balance_after",0), date=fmt_date(tx.get("created_at","")))
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb(lang,"pr:m"))


# ════════════════════════════════════════════════════════════════════════════
# STATS (standalone)
# ════════════════════════════════════════════════════════════════════════════

async def stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await profile_stats_cb(update, ctx)  # reuse profile stats


# ════════════════════════════════════════════════════════════════════════════
# REFERRAL SYSTEM
# ════════════════════════════════════════════════════════════════════════════

async def referral_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ref:m"""
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)

    stats = await get_user_referral_stats(q.from_user.id)
    pct   = stats.get("pct", 5)

    # Build referral link using bot username
    bot_info = await ctx.bot.get_me()
    code     = get_referral_code(q.from_user.id)
    link     = f"https://t.me/{bot_info.username}?start=ref_{code}"

    text = t(lang,"ref_info",
              pct=pct, link=link,
              total=stats.get("total",0), active=stats.get("active",0),
              earned=stats.get("total_earned",0), month=stats.get("month_earned",0))

    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=referral_menu_kb(lang, bot_info.username))


async def referral_list_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ref:l:{page}"""
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[-1])
    per  = 5
    refs = await get_user_referrals(q.from_user.id, limit=per+1, offset=page*per)
    has_more = len(refs) > per
    refs     = refs[:per]

    if not refs and page == 0:
        await q.edit_message_text(t(lang,"ref_list_empty"), parse_mode="HTML",
                                   reply_markup=back_kb(lang,"ref:m")); return

    lines = [t(lang,"ref_list_title"),""]
    for r in refs:
        name = r.get("first_name","") or r.get("username","") or str(r.get("ref_tg_id","?"))
        lines.append(t(lang,"ref_row",
                        name=name,
                        purchases=r.get("ref_purchases",0),
                        spent=r.get("ref_spent",0),
                        earned=r.get("total_earned",0),
                        date=fmt_date(r.get("created_at",""))))
        lines.append("")

    kb = paginated_kb(lang, page, has_more, "ref:l", "ref:m")
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


async def referral_earnings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ref:e:{page}"""
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    page = int(q.data.split(":")[-1])
    per  = 5

    from core import get_user
    u    = await get_user(q.from_user.id)
    if not u:
        await q.edit_message_text(t(lang,"error")); return

    from core import _q, DATABASE_PATH
    uid  = u["id"]
    earnings = await _q("""
        SELECT re.*, ud.first_name, ud.username
        FROM referral_earnings re JOIN users ud ON re.referred_id=ud.id
        WHERE re.referrer_id=?
        ORDER BY re.created_at DESC LIMIT ? OFFSET ?
    """, (uid, per+1, page*per), fetchall=True)

    has_more = len(earnings) > per
    earnings = earnings[:per]

    if not earnings and page == 0:
        await q.edit_message_text(t(lang,"ref_earnings_empty"), parse_mode="HTML",
                                   reply_markup=back_kb(lang,"ref:m")); return

    lines = [t(lang,"ref_earnings_title"),""]
    for e in earnings:
        name = e.get("first_name","") or e.get("username","") or "?"
        lines.append(t(lang,"ref_earning_row",
                        amount=e.get("commission_usd",0),
                        name=name,
                        pct=e.get("commission_pct",0),
                        date=fmt_date(e.get("created_at",""))))

    kb = paginated_kb(lang, page, has_more, "ref:e", "ref:m")
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


async def referral_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """ref:s"""
    q    = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    stats = await get_user_referral_stats(q.from_user.id)

    top_lines = []
    for i, r in enumerate(stats.get("top_refs",[]), 1):
        name = r.get("first_name","") or r.get("username","") or "?"
        top_lines.append(f"  {i}. <b>{name}</b> — {r.get('purchases',0)} × ${r.get('earned',0):.4f}")

    text = (
        f"{t(lang,'ref_stats_title')}\n\n"
        f"{'👥 الكل' if lang=='ar' else '👥 Total'}: <b>{stats.get('total',0)}</b>\n"
        f"{'✅ اشتروا' if lang=='ar' else '✅ Active buyers'}: <b>{stats.get('active',0)}</b>\n\n"
        f"{'💰 الإجمالي' if lang=='ar' else '💰 Total earned'}: <b>${stats.get('total_earned',0):.4f}</b>\n"
        f"{'📅 هذا الشهر' if lang=='ar' else '📅 This month'}: <b>${stats.get('month_earned',0):.4f}</b>\n"
        f"{'📈 النسبة' if lang=='ar' else '📈 Rate'}: <b>{stats.get('pct',5)}%</b>\n\n"
        f"{'🏆 الأفضل' if lang=='ar' else '🏆 Top referrals'}:\n" +
        ("\n".join(top_lines) or "—")
    )
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb(lang,"ref:m"))


# ════════════════════════════════════════════════════════════════════════════
# INLINE QUERY ─ search countries/services
# ════════════════════════════════════════════════════════════════════════════

async def inline_query_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query  = update.inline_query.query.strip().lower()
    user   = await get_user(update.effective_user.id)
    lang   = user.get("language","ar") if user else "ar"
    results = []

    if not query:
        results.append(InlineQueryResultArticle(
            id="noop", title=t(lang,"inline_search_title"),
            description=t(lang,"inline_no_key"),
            input_message_content=InputTextMessageContent(t(lang,"inline_no_key"))
        ))
        await update.inline_query.answer(results, cache_time=1)
        return

    # Search countries
    countries = ctx.application.bot_data.get("countries", [])
    for c in countries:
        if query in c.get("name","").lower():
            cid   = str(c.get("ID",c.get("id","")))
            cname = c.get("name","")
            results.append(InlineQueryResultArticle(
                id=f"c_{cid}",
                title=f"🌍 {cname}",
                description="Country",
                input_message_content=InputTextMessageContent(
                    f"🌍 {cname} (ID: {cid})\n\nPress /start to buy a number"
                )
            ))
    await update.inline_query.answer(results[:10], cache_time=5)


# ── history search text handler ──────────────────────────────────────────────
async def history_search_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Intercept text input when user is in history search mode."""
    if not ctx.user_data.get("hi_awaiting_search"):
        return  # not in search mode, ignore
    ctx.user_data["hi_awaiting_search"] = False
    query  = (update.message.text or "").strip()
    lang   = await _lang(update.effective_user.id)
    if not query:
        await update.message.reply_text(t(lang,"history_empty"))
        return
    ctx.user_data["hi_search"] = query
    # Show filtered results
    text, kb = await _show_history(None, lang, update.effective_user.id,
                                    "all", 0, query)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


# ════════════════════════════════════════════════════════════════════════════
# REGISTER HANDLERS
# ════════════════════════════════════════════════════════════════════════════

def register(app):
    from telegram.ext import CommandHandler, CallbackQueryHandler, InlineQueryHandler

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help",  start_cmd))
    app.add_handler(InlineQueryHandler(inline_query_handler))

    cb = app.add_handler

    cb(CallbackQueryHandler(main_menu_cb,               pattern="^mm$"))
    cb(CallbackQueryHandler(noop_cb,                    pattern="^noop$"))
    cb(CallbackQueryHandler(lang_choose_cb,             pattern="^lc$"))
    cb(CallbackQueryHandler(lang_set_cb,                pattern=r"^l:(ar|en)$"))

    cb(CallbackQueryHandler(buy_start_cb,               pattern="^b:s$"))
    cb(CallbackQueryHandler(buy_countries_page_cb,      pattern=r"^b:cp:\d+$"))
    cb(CallbackQueryHandler(buy_country_cb,             pattern=r"^b:c:\w+$"))
    cb(CallbackQueryHandler(buy_services_page_cb,       pattern=r"^b:sp:\w+:\d+$"))
    cb(CallbackQueryHandler(buy_service_cb,             pattern=r"^b:sv:\w+:\w+$"))
    cb(CallbackQueryHandler(buy_confirm_cb,             pattern=r"^b:cf:\w+:\w+$"))

    cb(CallbackQueryHandler(active_list_cb,             pattern="^ac:l$"))
    cb(CallbackQueryHandler(active_view_cb,             pattern=r"^ac:v:.+$"))
    cb(CallbackQueryHandler(active_check_cb,            pattern=r"^ac:ch:.+$"))
    cb(CallbackQueryHandler(active_resend_cb,           pattern=r"^ac:rs:.+$"))
    cb(CallbackQueryHandler(active_cancel_prompt_cb,    pattern=r"^ac:cn:.+$"))
    cb(CallbackQueryHandler(active_cancel_confirm_cb,   pattern=r"^ac:cc:.+$"))

    cb(CallbackQueryHandler(history_cb,              pattern=r"^hi:\d+$"))
    cb(CallbackQueryHandler(history_filter_cb,       pattern=r"^hi:f:\w+:\d+$"))
    cb(CallbackQueryHandler(history_fmenu_cb,        pattern=r"^hi:fmenu:\w+:\d+$"))
    cb(CallbackQueryHandler(history_detail_cb,       pattern=r"^hi:det:.+$"))
    cb(CallbackQueryHandler(history_search_cb,       pattern="^hi:search$"))
    cb(CallbackQueryHandler(history_cleanup_cb,      pattern="^hi:cleanup$"))
    cb(CallbackQueryHandler(history_cleanup_ok_cb,   pattern=r"^hi:cleanup_ok:\d+$"))
    cb(CallbackQueryHandler(history_act_check_cb,    pattern=r"^hi:act_check:.+$"))
    cb(CallbackQueryHandler(history_act_resend_cb,   pattern=r"^hi:act_resend:.+$"))
    cb(CallbackQueryHandler(history_act_cancel_cb,   pattern=r"^hi:act_cancel:.+$"))
    cb(CallbackQueryHandler(history_reuse_cb,        pattern=r"^hi:reuse:.+$"))

    cb(CallbackQueryHandler(balance_menu_cb,            pattern="^bl:m$"))
    cb(CallbackQueryHandler(balance_deposit_cb,         pattern="^bl:d$"))
    cb(CallbackQueryHandler(balance_txs_cb,             pattern=r"^bl:t:\d+$"))

    cb(CallbackQueryHandler(profile_menu_cb,            pattern="^pr:m$"))
    cb(CallbackQueryHandler(profile_info_cb,            pattern="^pr:i$"))
    cb(CallbackQueryHandler(profile_stats_cb,           pattern="^pr:s$"))
    cb(CallbackQueryHandler(profile_history_cb,         pattern=r"^pr:h:\d+$"))
    cb(CallbackQueryHandler(profile_balance_cb,         pattern="^pr:b$"))

    cb(CallbackQueryHandler(stats_cb,                   pattern="^st:m$"))

    # History search text input
    from telegram.ext import MessageHandler, filters as F
    app.add_handler(MessageHandler(
        F.TEXT & ~F.COMMAND,
        history_search_text_handler
    ), group=5)

    # Reuse number (Task #8)
    cb(CallbackQueryHandler(active_reuse_prompt_cb,  pattern=r"^ac:ru:.+$"))
    cb(CallbackQueryHandler(active_reuse_confirm_cb, pattern=r"^ac:ruc:.+$"))

    # Referral system
    cb(CallbackQueryHandler(referral_menu_cb,       pattern="^ref:m$"))
    cb(CallbackQueryHandler(referral_list_cb,       pattern=r"^ref:l:\d+$"))
    cb(CallbackQueryHandler(referral_earnings_cb,   pattern=r"^ref:e:\d+$"))
    cb(CallbackQueryHandler(referral_stats_cb,      pattern="^ref:s$"))
