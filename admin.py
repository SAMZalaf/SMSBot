"""
admin.py ─ Complete Admin Panel
Authentication · User management · Stats · Transactions · Settings · Broadcast
"""
import asyncio
import warnings
from datetime import datetime
warnings.filterwarnings('ignore', message='.*per_message.*', category=UserWarning)
from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as KB
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from core import (
    t, fmt_date, fmt_list, tx_name, tx_icon, user_display, status_label,
    get_user, get_user_by_id, update_user, update_balance, get_setting, set_setting,
    get_all_settings, get_all_users, count_users, search_users, get_top_users,
    get_user_purchases, get_user_transactions, get_user_detailed_stats,
    get_all_purchases, get_all_transactions, count_all_purchases,
    get_active_purchases_all, is_admin, add_admin_session, remove_admin_session,
    get_referral_code, get_user_referrals, count_user_referrals,
    get_user_referral_stats, get_global_referral_stats, get_all_referral_earnings,
    admin_menu_kb, admin_user_kb, admin_settings_kb, admin_referral_kb,
    admin_topsort_kb, admin_profit_kb, back_kb, confirm_action_kb,
    get_profit_stats,
    ADMIN_PASSWORD, SUPER_ADMIN_IDS, ITEMS_PER_PAGE
)

# ── Conversation states ───────────────────────────────────────────────────────
(S_PW, S_SEARCH, S_AMOUNT, S_REASON, S_BROADCAST, S_BROADCAST2,
 S_NOTE, S_MSG, S_SETTING_VAL, S_SET_BAL, S_REF_PCT, S_USEARCH2) = range(12)
END = ConversationHandler.END


async def _lang(tid):
    u = await get_user(tid)
    return u.get("language","ar") if u else "ar"

def _uname(u):
    return ("@" + u["username"]) if u.get("username") else "—"

async def _require_admin(update, ctx):
    """Returns (lang, True) if admin, sends error and returns (lang, False) otherwise."""
    tid  = update.effective_user.id
    lang = await _lang(tid)
    if not await is_admin(tid):
        if update.callback_query:
            await update.callback_query.answer(t(lang,"adm_no_auth"), show_alert=True)
        else:
            await update.message.reply_text(t(lang,"adm_no_auth"))
        return lang, False
    return lang, True


# ════════════════════════════════════════════════════════════════════════════
# AUTH
# ════════════════════════════════════════════════════════════════════════════

async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid  = update.effective_user.id
    lang = await _lang(tid)
    if tid in SUPER_ADMIN_IDS or await is_admin(tid):
        await add_admin_session(tid)
        await update.message.reply_text(t(lang,"adm_logged_in"), parse_mode="HTML",
                                         reply_markup=admin_menu_kb(lang))
        return END
    await update.message.reply_text(t(lang,"adm_enter_pw"))
    return S_PW

async def recv_pw(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    pw   = (update.message.text or "").strip()
    try: await update.message.delete()
    except: pass
    if pw == ADMIN_PASSWORD:
        await add_admin_session(update.effective_user.id)
        await update.effective_chat.send_message(t(lang,"adm_logged_in"), parse_mode="HTML",
                                                  reply_markup=admin_menu_kb(lang))
    else:
        await update.effective_chat.send_message(t(lang,"adm_wrong_pw"))
    return END

async def admin_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_menu"), parse_mode="HTML",
                               reply_markup=admin_menu_kb(lang))

async def admin_logout_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await _lang(q.from_user.id)
    await remove_admin_session(q.from_user.id)
    await q.edit_message_text(t(lang,"adm_logged_out"))


# ════════════════════════════════════════════════════════════════════════════
# GLOBAL STATS
# ════════════════════════════════════════════════════════════════════════════

async def admin_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    from core import get_global_stats
    s = await get_global_stats()
    svcs = fmt_list(s["top_services"], "service_name")
    cnts = fmt_list(s["top_countries"], "country_name")
    text = t(lang,"adm_stats_title") + "\n\n" + t(lang,"adm_stats",
        total=s["total_users"], active=s["active_users"], banned=s["banned_users"],
        new24=s["new_users_24h"], tot_p=s["total_purchases"], act_n=s["active_numbers"],
        done=s["completed"], cancel=s["cancelled"], refund=s["refunded"],
        p24=s["purchases_24h"], p7=s["purchases_7d"], rev=s["total_revenue"],
        rev24=s["revenue_24h"], refamt=s["total_refunded_amt"], bals=s["total_balances"],
        svcs=svcs, cnts=cnts)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=back_kb(lang,"adm:m"))


# ════════════════════════════════════════════════════════════════════════════
# USER LIST + VIEW
# ════════════════════════════════════════════════════════════════════════════

async def admin_users_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ul:{page}"""
    q    = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    page = int(q.data.split(":")[-1])
    per  = ITEMS_PER_PAGE
    users = await get_all_users(limit=per+1, offset=page*per)
    has_more = len(users) > per
    users    = users[:per]
    rows = []
    for u in users:
        icon = "🚫" if u.get("is_banned") else "👤"
        name = user_display(u)
        rows.append([Btn(f"{icon} {name}  |  ${u.get('balance',0):.2f}",
                          callback_data=f"adm:u:{u['id']}")])
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:ul:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"adm:ul:{page+1}"))
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
    total = await count_users()
    await q.edit_message_text(
        f"👥 <b>{'المستخدمون' if lang=='ar' else 'Users'} ({total})</b>",
        parse_mode="HTML", reply_markup=KB(rows))

async def admin_view_user_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:u:{db_id}"""
    q    = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if not user:
        await q.answer(t(lang,"adm_not_found"), show_alert=True); return
    name = user_display(user)
    text = await _full_user_text(lang, user)
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_user_kb(lang, uid, bool(user.get("is_banned"))))


# ════════════════════════════════════════════════════════════════════════════
# SEARCH
# ════════════════════════════════════════════════════════════════════════════

async def admin_search_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_search_prompt"))
    return S_SEARCH

async def recv_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    q    = (update.message.text or "").strip()
    users = await search_users(q)
    if not users:
        await update.message.reply_text(t(lang,"adm_not_found"),
                                         reply_markup=back_kb(lang,"adm:m"))
        return END
    if len(users) == 1:
        u = users[0]
        await _send_user_profile(update, lang, u)
    else:
        rows = []
        for u in users[:15]:
            icon = "🚫" if u.get("is_banned") else "👤"
            rows.append([Btn(f"{icon} {user_display(u)}  |  ${u.get('balance',0):.2f}",
                              callback_data=f"adm:u:{u['id']}")])
        rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
        await update.message.reply_text(
            f"👥 <b>{'نتائج البحث' if lang=='ar' else 'Search Results'}</b>",
            parse_mode="HTML", reply_markup=KB(rows))
    return END

async def _send_user_profile(update, lang, u):
    name = user_display(u)
    text = t(lang,"adm_user_profile",
              tid=u["telegram_id"], name=name, uname=_uname(u),
              bal=u["balance"], spent=u["total_spent"],
              purchases=u["total_purchases"], refunds=u["total_refunds"],
              joined=fmt_date(u.get("created_at","")),
              active=fmt_date(u.get("last_active","")),
              banned="✅" if u.get("is_banned") else "❌",
              note=u.get("note") or "—")
    await update.message.reply_text(text, parse_mode="HTML",
                                     reply_markup=admin_user_kb(lang, u["id"], bool(u.get("is_banned"))))


# ════════════════════════════════════════════════════════════════════════════
# BALANCE MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

async def _balance_op_start(update: Update, ctx, op: str, uid: int, lang: str):
    ctx.user_data["adm_op"]  = op
    ctx.user_data["adm_uid"] = uid
    if update.callback_query:
        await update.callback_query.edit_message_text(t(lang,"adm_enter_amount"))
    return S_AMOUNT

async def admin_add_bal_cb(update, ctx):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    return await _balance_op_start(update, ctx, "add", int(q.data.split(":")[-1]), lang)

async def admin_rm_bal_cb(update, ctx):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    return await _balance_op_start(update, ctx, "rm", int(q.data.split(":")[-1]), lang)

async def admin_set_bal_cb(update, ctx):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    return await _balance_op_start(update, ctx, "set", int(q.data.split(":")[-1]), lang)

async def recv_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    raw  = (update.message.text or "").strip().replace(",",".")
    try:
        amt = float(raw)
        if amt <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang,"adm_invalid_amount"))
        return S_AMOUNT
    ctx.user_data["adm_amount"] = amt
    await update.message.reply_text(t(lang,"adm_enter_reason"))
    return S_REASON

async def recv_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang   = await _lang(update.effective_user.id)
    reason = (update.message.text or "").strip()
    op     = ctx.user_data.get("adm_op","add")
    amt    = ctx.user_data.get("adm_amount",0)
    uid    = ctx.user_data.get("adm_uid")
    user   = await get_user_by_id(uid)
    if not user:
        await update.message.reply_text(t(lang,"adm_not_found")); return END

    tid = user["telegram_id"]
    if op == "set":
        # Set to exact amount: calculate diff
        diff = round(amt - user["balance"], 6)
        tx_t = "admin_set"
        tx_amt = diff
        msg_key = "adm_bal_set"
    elif op == "add":
        tx_amt = amt; tx_t = "admin_add"; msg_key = "adm_bal_added"
    else:
        tx_amt = -amt; tx_t = "admin_remove"; msg_key = "adm_bal_removed"

    new_bal = await update_balance(tid, tx_amt, tx_t, reason,
                                    admin_actor=update.effective_user.id)
    if new_bal is False:
        await update.message.reply_text(t(lang,"adm_bal_err"),
                                         reply_markup=back_kb(lang,f"adm:u:{uid}"))
        return END

    uname_d = user_display(user)
    await update.message.reply_text(
        t(lang, msg_key, amount=amt, new=new_bal),
        parse_mode="HTML", reply_markup=back_kb(lang,f"adm:u:{uid}")
    )
    # Notify user
    ulang = user.get("language","ar")
    notify_key = "notify_add" if tx_amt > 0 else "notify_rm"
    try:
        await update.effective_bot.send_message(tid,
            t(ulang, notify_key, amount=abs(tx_amt), reason=reason, bal=new_bal),
            parse_mode="HTML")
    except: pass
    return END


# ════════════════════════════════════════════════════════════════════════════
# BAN / UNBAN / DELETE / NOTE / MESSAGE
# ════════════════════════════════════════════════════════════════════════════

async def admin_ban_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if not user: await q.answer(t(lang,"adm_not_found"),show_alert=True); return
    await update_user(user["telegram_id"], is_banned=1)
    try:
        await ctx.bot.send_message(user["telegram_id"],
            t(user.get("language","ar"), "notify_banned"), parse_mode="HTML")
    except: pass
    await q.edit_message_text(t(lang,"adm_ban_ok",user=user_display(user)),
                               reply_markup=back_kb(lang,f"adm:u:{uid}"))

async def admin_unban_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if not user: await q.answer(t(lang,"adm_not_found"),show_alert=True); return
    await update_user(user["telegram_id"], is_banned=0)
    try:
        await ctx.bot.send_message(user["telegram_id"],
            t(user.get("language","ar"), "notify_unbanned"), parse_mode="HTML")
    except: pass
    await q.edit_message_text(t(lang,"adm_unban_ok",user=user_display(user)),
                               reply_markup=back_kb(lang,f"adm:u:{uid}"))

async def admin_delete_ask_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if not user: return
    ctx.user_data["del_uid"] = uid
    text = t(lang,"adm_delete_ask", user=user_display(user))
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=confirm_action_kb(lang,f"adm:del_ok:{uid}",f"adm:u:{uid}"))

async def admin_delete_ok_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if user:
        import aiosqlite
        from core import DATABASE_PATH
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute("DELETE FROM transactions WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM purchases WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM payments WHERE user_id=?", (uid,))
            await db.execute("DELETE FROM admin_sessions WHERE telegram_id=?", (user["telegram_id"],))
            await db.execute("DELETE FROM users WHERE id=?", (uid,))
            await db.commit()
    await q.edit_message_text(t(lang,"adm_delete_ok"), reply_markup=back_kb(lang,"adm:ul:0"))

async def admin_note_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid = int(q.data.split(":")[-1])
    ctx.user_data["note_uid"] = uid
    await q.edit_message_text(t(lang,"adm_enter_note"))
    return S_NOTE

async def recv_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    note = (update.message.text or "").strip()
    uid  = ctx.user_data.get("note_uid")
    user = await get_user_by_id(uid)
    if user:
        await update_user(user["telegram_id"], note=note)
    await update.message.reply_text(t(lang,"adm_note_ok"),
                                     reply_markup=back_kb(lang,f"adm:u:{uid}"))
    return END

async def admin_msg_user_prompt_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:um:{uid} — message specific user from user profile"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid = int(q.data.split(":")[-1])
    ctx.user_data["msg_uid"] = uid
    await q.edit_message_text(t(lang,"adm_enter_msg"))
    return S_MSG

async def admin_msg_prompt_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:mu — message any user (admin asks for ID first)"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    ctx.user_data["msg_uid"] = None
    await q.edit_message_text("📨 " + t(lang,"adm_search_prompt"))
    return S_SEARCH

async def recv_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    msg  = (update.message.text or "").strip()
    uid  = ctx.user_data.get("msg_uid")
    user = await get_user_by_id(uid) if uid else None
    if not user:
        await update.message.reply_text(t(lang,"adm_not_found")); return END
    try:
        await update.effective_bot.send_message(user["telegram_id"],
            t(user.get("language","ar"), "notify_msg", msg=msg), parse_mode="HTML")
        await update.message.reply_text(t(lang,"adm_msg_ok"),
                                         reply_markup=back_kb(lang,f"adm:u:{uid}"))
    except:
        await update.message.reply_text(t(lang,"adm_msg_fail"),
                                         reply_markup=back_kb(lang,f"adm:u:{uid}"))
    return END


# ════════════════════════════════════════════════════════════════════════════
# USER DETAILS ─ purchases / transactions / stats
# ════════════════════════════════════════════════════════════════════════════

async def admin_user_purchases_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    _, _, uid_s, page_s = q.data.split(":")
    uid = int(uid_s); page = int(page_s)
    user = await get_user_by_id(uid)
    if not user: return
    per  = 5
    ps   = await get_user_purchases(user["telegram_id"], limit=per+1, offset=page*per)
    has  = len(ps) > per; ps = ps[:per]
    ICONS = {"active":"🟢","completed":"✅","cancelled":"❌","refunded":"💸","pending":"⏳"}
    lines = [f"🛒 <b>{user_display(user)}</b>\n"]
    for p in ps:
        si = ICONS.get(p.get("status",""),"❓")
        lines.append(f"📞 <code>{p.get('phone_number','—')}</code>  |  📲 {p.get('service_name','—')}  |  🌍 {p.get('country_name','—')}\n"
                     f"💰 ${p.get('cost_display',0):.4f}  {si} {p.get('status','').title()}  |  📅 {fmt_date(p.get('created_at',''))}\n"
                     f"🆔 <code>{p.get('order_id','')}</code>")
        lines.append("")
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:up:{uid}:{page-1}"))
    if has:      nav.append(Btn(t(lang,"next"), callback_data=f"adm:up:{uid}:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data=f"adm:u:{uid}")])
    await q.edit_message_text("\n".join(lines) if ps else f"No purchases for {user_display(user)}.",
                               parse_mode="HTML", reply_markup=KB(rows))

async def admin_user_txs_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    _, _, uid_s, page_s = q.data.split(":")
    uid = int(uid_s); page = int(page_s)
    user = await get_user_by_id(uid)
    if not user: return
    per  = 5
    txs  = await get_user_transactions(user["telegram_id"], limit=per+1, offset=page*per)
    has  = len(txs) > per; txs = txs[:per]
    lines = [f"💳 <b>{user_display(user)}</b>\n"]
    for tx in txs:
        tp = tx.get("type","")
        lines.append(f"{tx_icon(tp)} {tx_name('en',tp)}  <b>{tx.get('amount',0):+.4f}$</b>\n"
                     f"📝 {tx.get('description','—')}\n"
                     f"💳 ${tx.get('balance_after',0):.4f}  |  📅 {fmt_date(tx.get('created_at',''))}")
        lines.append("")
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:ut:{uid}:{page-1}"))
    if has:      nav.append(Btn(t(lang,"next"), callback_data=f"adm:ut:{uid}:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data=f"adm:u:{uid}")])
    await q.edit_message_text("\n".join(lines) if txs else "No transactions.",
                               parse_mode="HTML", reply_markup=KB(rows))

async def admin_user_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    uid  = int(q.data.split(":")[-1])
    user = await get_user_by_id(uid)
    if not user: return
    stats = await get_user_detailed_stats(user["telegram_id"])
    by_s  = stats["by_status"] if stats else {}
    svcs  = fmt_list(stats["top_services"] if stats else [], "service_name")
    cnts  = fmt_list(stats["top_countries"] if stats else [], "country_name")
    months_lines = []
    for m in (stats["monthly"] if stats else []):
        months_lines.append(f"  📅 {m['mo']}: {m['n']} × ${m['tot']:.2f}")
    text = (
        f"📊 <b>{user_display(user)}</b>\n\n"
        f"💰 Balance: <b>${user['balance']:.4f}</b>  |  Spent: <b>${user['total_spent']:.4f}</b>\n"
        f"🛒 Total: <b>{user['total_purchases']}</b>  |  ✅ Done: <b>{by_s.get('completed',{}).get('count',0)}</b>\n"
        f"❌ Cancelled: <b>{by_s.get('cancelled',{}).get('count',0)}</b>  |  💸 Refunds: <b>{user['total_refunds']}</b>\n\n"
        f"📱 Top Services:\n{svcs}\n\n🌍 Top Countries:\n{cnts}\n\n"
        f"📅 Monthly:\n{chr(10).join(months_lines) or '—'}"
    )
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,f"adm:u:{uid}"))


# ════════════════════════════════════════════════════════════════════════════
# ALL TRANSACTIONS / PURCHASES
# ════════════════════════════════════════════════════════════════════════════

async def admin_all_txs_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    page = int(q.data.split(":")[-1])
    per  = 5
    txs  = await get_all_transactions(limit=per+1, offset=page*per)
    has  = len(txs) > per; txs = txs[:per]
    lines = [f"💳 <b>{'جميع المعاملات' if lang=='ar' else 'All Transactions'}</b>\n"]
    for tx in txs:
        tp    = tx.get("type","")
        uname = tx.get("username") or tx.get("first_name") or str(tx.get("telegram_id","?"))
        lines.append(f"{tx_icon(tp)} <b>{uname}</b>  {tx_name('en',tp)}  <b>{tx.get('amount',0):+.4f}$</b>\n"
                     f"📝 {tx.get('description','—')}  |  📅 {fmt_date(tx.get('created_at',''))}")
        lines.append("")
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:t:{page-1}"))
    if has:      nav.append(Btn(t(lang,"next"), callback_data=f"adm:t:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
    await q.edit_message_text("\n".join(lines) if txs else "No transactions.",
                               parse_mode="HTML", reply_markup=KB(rows))

async def admin_all_purchases_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    page = int(q.data.split(":")[-1])
    per  = 5
    ps   = await get_all_purchases(limit=per+1, offset=page*per)
    has  = len(ps) > per; ps = ps[:per]
    ICONS= {"active":"🟢","completed":"✅","cancelled":"❌","refunded":"💸","pending":"⏳"}
    lines = [f"🛒 <b>{'جميع المشتريات' if lang=='ar' else 'All Purchases'}</b>\n"]
    for p in ps:
        si  = ICONS.get(p.get("status",""),"❓")
        un  = p.get("username") or p.get("first_name") or str(p.get("telegram_id","?"))
        lines.append(f"👤 <b>{un}</b>  📞 <code>{p.get('phone_number','—')}</code>\n"
                     f"📲 {p.get('service_name','—')}  🌍 {p.get('country_name','—')}\n"
                     f"💰 ${p.get('cost_display',0):.4f}  {si}  📅 {fmt_date(p.get('created_at',''))}")
        lines.append("")
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:ap:{page-1}"))
    if has:      nav.append(Btn(t(lang,"next"), callback_data=f"adm:ap:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
    await q.edit_message_text("\n".join(lines) if ps else "No purchases.",
                               parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# ACTIVE NUMBERS (GLOBAL ADMIN VIEW)
# ════════════════════════════════════════════════════════════════════════════

async def admin_active_nums_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    page = int(q.data.split(":")[-1])
    all_active = await get_active_purchases_all()
    per  = 8
    total = len(all_active)
    chunk = all_active[page*per:(page+1)*per]
    has   = (page+1)*per < total
    now   = datetime.now()
    lines = [t(lang,"adm_active_nums",count=total),""]
    for p in chunk:
        uname = str(p.get("tg_id","?"))
        try:
            created = datetime.fromisoformat(p.get("created_at",""))
            mins    = int((now - created).total_seconds() / 60)
        except: mins = 0
        lines.append(t(lang,"adm_active_row",
                        user=uname, num=p.get("phone_number","—"),
                        svc=p.get("service_name","—"), cnt=p.get("country_name","—"), mins=mins))
        lines.append("")
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:an:{page-1}"))
    if has:      nav.append(Btn(t(lang,"next"), callback_data=f"adm:an:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"refresh"), callback_data=f"adm:an:{page}"),
                 Btn(t(lang,"back"),    callback_data="adm:m")])
    await q.edit_message_text("\n".join(lines) if chunk else "No active numbers.",
                               parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# TOP USERS
# ════════════════════════════════════════════════════════════════════════════

async def admin_top_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    users = await get_top_users(10)
    lines = [t(lang,"adm_top_title"),""]
    for i, u in enumerate(users, 1):
        lines.append(t(lang,"adm_top_row", rank=i, name=user_display(u),
                        spent=u.get("total_spent",0), purchases=u.get("total_purchases",0)))
    await q.edit_message_text("\n".join(lines), parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:m"))


# ════════════════════════════════════════════════════════════════════════════
# BROADCAST
# ════════════════════════════════════════════════════════════════════════════

# Broadcast is handled by admin_tools.py (advanced version)
# Keeping stub for backward compat with conversation handler entry points
async def admin_broadcast_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Redirect to advanced broadcast menu in admin_tools."""
    from admin_tools import broadcast_menu_cb
    return await broadcast_menu_cb(update, ctx)

async def recv_broadcast(update, ctx): return END
async def admin_broadcast_ok_cb(update, ctx): return END


# ════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ════════════════════════════════════════════════════════════════════════════

async def admin_settings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    active     = await get_setting("bot_active") == "1"
    min_dep    = await get_setting("min_deposit") or "1.0"
    markup     = await get_setting("price_markup") or "0"
    support    = await get_setting("support_link") or "—"
    auto_c     = await get_setting("auto_cancel_minutes") or "10"
    status_s   = ("🟢 مفعّل" if lang=="ar" else "🟢 Active") if active \
                 else ("🔴 معطّل" if lang=="ar" else "🔴 Disabled")
    text = t(lang,"adm_settings_title") + "\n\n" + t(lang,"adm_settings",
             status=status_s, min_dep=min_dep, markup=markup, support=support, auto_cancel=auto_c)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=admin_settings_kb(lang))

async def admin_settings_action_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ss:{action}"""
    q      = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    action = q.data.split(":")[-1]
    if action == "toggle":
        cur = await get_setting("bot_active")
        await set_setting("bot_active", "0" if cur == "1" else "1")
        await admin_settings_cb(update, ctx)
        return
    # For other settings, ask for value
    ctx.user_data["setting_key"] = {
        "markup":      "price_markup",
        "min_dep":     "min_deposit",
        "support":     "support_link",
        "welcome":     f"welcome_{lang}",
        "auto_cancel": "auto_cancel_minutes",
    }.get(action, action)
    await q.edit_message_text(t(lang,"adm_enter_setting"))
    return S_SETTING_VAL

async def recv_setting_val(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    val  = (update.message.text or "").strip()
    key  = ctx.user_data.get("setting_key","")

    # Validate markup
    if key == "price_markup":
        try:
            v = float(val.replace(",","."))
            if v < 0 or v > 500: raise ValueError
            val = str(v)
        except ValueError:
            await update.message.reply_text(
                "❌ " + ("أدخل رقماً بين 0 و500" if lang=="ar" else "Enter a number between 0 and 500")
            )
            return S_SETTING_VAL

    if key: await set_setting(key, val)

    # Show confirmation with extra info for markup
    if key == "price_markup":
        pct   = float(val)
        extra = f"\n\n📈 {'مثال' if lang=='ar' else 'Example'}: $1.00 → ${1*(1+pct/100):.4f}"
        await update.message.reply_text(
            t(lang,"adm_setting_saved") + extra,
            parse_mode="HTML",
            reply_markup=back_kb(lang,"adm:ss")
        )
    else:
        await update.message.reply_text(t(lang,"adm_setting_saved"),
                                         reply_markup=back_kb(lang,"adm:ss"))
    return END


# ════════════════════════════════════════════════════════════════════════════
# PROFIT & SALES ANALYTICS (Tasks 3 & 4)
# ════════════════════════════════════════════════════════════════════════════

async def admin_profit_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:m — profit menu entry."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_profit_title"),
                               parse_mode="HTML",
                               reply_markup=admin_profit_kb(lang))


async def admin_profit_overview_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:overview — full profit breakdown."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    await q.edit_message_text(t(lang,"loading"), parse_mode="HTML")
    s = await get_profit_stats()

    text = t(lang,"adm_profit_overview",
        markup=s["current_markup"],
        total_sales=s["total_sales"], sales_today=s["sales_today"],
        completed=s["completed_sales"], refunded=s["refunded_sales"],
        revenue_total=s["revenue_total"], revenue_today=s["revenue_today"],
        revenue_week=s["revenue_week"], revenue_month=s["revenue_month"],
        cost_total=s["cost_total"], cost_today=s["cost_today"],
        cost_week=s["cost_week"], cost_month=s["cost_month"],
        commission_total=s["commission_total"], commission_month=s["commission_month"],
        gross_total=s["gross_profit_total"], gross_today=s["gross_profit_today"],
        gross_week=s["gross_profit_week"], gross_month=s["gross_profit_month"],
        margin=s["margin_total"],
        net_total=s["net_profit_total"], net_today=s["net_profit_today"],
        net_week=s["net_profit_week"], net_month=s["net_profit_month"],
        net_margin=s["net_margin_total"])

    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:profit:m"))


async def admin_profit_services_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:services"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_profit_stats()
    rows_lines = []
    for i, row in enumerate(s["top_services_profit"], 1):
        rows_lines.append(t(lang,"adm_profit_service_row",
            rank=i, name=row.get("service_name","?"),
            sales=row.get("sales",0),
            revenue=row.get("revenue",0),
            cost=row.get("cost_raw",0),
            profit=row.get("profit",0)))
        rows_lines.append("")

    text = t(lang,"adm_profit_services", rows="\n".join(rows_lines) or "—")
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:profit:m"))


async def admin_profit_countries_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:countries"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_profit_stats()
    rows_lines = []
    for i, row in enumerate(s["top_countries_profit"], 1):
        rows_lines.append(t(lang,"adm_profit_country_row",
            rank=i, name=row.get("country_name","?"),
            sales=row.get("sales",0),
            profit=row.get("profit",0)))

    text = t(lang,"adm_profit_countries", rows="\n".join(rows_lines) or "—")
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:profit:m"))


async def admin_profit_monthly_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:monthly"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_profit_stats()
    rows_lines = []
    for row in s["monthly_trend"]:
        rows_lines.append(t(lang,"adm_profit_month_row",
            mo=row.get("mo","?"), sales=row.get("sales",0),
            rev=row.get("revenue",0), cost=row.get("cost_raw",0),
            profit=row.get("profit",0)))

    text = t(lang,"adm_profit_monthly", rows="\n".join(rows_lines) or "—")
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:profit:m"))


async def admin_profit_deposits_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:deposits"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_profit_stats()
    text = t(lang,"adm_profit_deposits",
        deposits_total=s["deposits_total"], deposits_today=s["deposits_today"],
        deposits_week=s["deposits_week"], deposits_month=s["deposits_month"],
        deposits_pending=s["deposits_pending"],
        liabilities=s["total_liabilities"],
        refunded_amt=s["revenue_refunded"])
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:profit:m"))


async def admin_profit_markup_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:profit:markup — live markup test with examples."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    from smspool import pool as sms_pool
    try:
        pct = float(await get_setting("price_markup") or "0")
    except Exception:
        pct = 0.0

    def apply(base): return round(base * (1 + pct / 100), 4)

    text = t(lang,"adm_profit_markup_test",
        markup=pct,
        p1=apply(0.10), p2=apply(0.50), p3=apply(1.00),
        p4=apply(2.00), p5=apply(5.00))

    # Add action button to change markup directly
    rows = [
        [Btn(t(lang,"btn_set_markup"), callback_data="adm:ss:markup")],
        [Btn(t(lang,"back"), callback_data="adm:profit:m")],
    ]
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# REGISTER
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
# ADMIN ADVANCED USER SEARCH + RANKING
# ════════════════════════════════════════════════════════════════════════════

async def _full_user_text(lang, u):
    """Build rich user profile text with all stats."""
    from core import get_user_detailed_stats, get_user_referral_stats, _q
    uid   = u["id"]
    stats = await get_user_detailed_stats(u["telegram_id"])
    refs  = await get_user_referral_stats(u["telegram_id"])
    by_s  = stats["by_status"] if stats else {}
    done  = by_s.get("completed",{}).get("count",0)
    return t(lang,"adm_user_full",
        tid=u["telegram_id"],
        name=user_display(u), uname=_uname(u),
        bal=u.get("balance",0), spent=u.get("total_spent",0),
        purchases=u.get("total_purchases",0), done=done,
        refunds=u.get("total_refunds",0),
        refs=refs.get("total",0), ref_earned=refs.get("total_earned",0),
        joined=fmt_date(u.get("created_at","")),
        active=fmt_date(u.get("last_active","")),
        banned="✅" if u.get("is_banned") else "❌",
        note=u.get("note") or "—"
    )


async def admin_usearch_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:usearch — advanced user search prompt."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_usearch_prompt"))
    return S_USEARCH2


async def recv_usearch2(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive advanced search query — show full results with stats."""
    lang  = await _lang(update.effective_user.id)
    query = (update.message.text or "").strip()
    users = await search_users(query, limit=10)
    if not users:
        await update.message.reply_text(t(lang,"adm_not_found"),
                                         reply_markup=back_kb(lang,"adm:m"))
        return END

    if len(users) == 1:
        u    = users[0]
        text = await _full_user_text(lang, u)
        await update.message.reply_text(text, parse_mode="HTML",
                                         reply_markup=admin_user_kb(lang, u["id"], bool(u.get("is_banned"))))
    else:
        rows = []
        for u in users:
            icon = "🚫" if u.get("is_banned") else "👤"
            rows.append([Btn(
                f"{icon} {user_display(u)}  |  ${u.get('balance',0):.2f}  |  🛒{u.get('total_purchases',0)}",
                callback_data=f"adm:u:{u['id']}"
            )])
        rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
        await update.message.reply_text(
            t(lang,"adm_usearch_title"), parse_mode="HTML",
            reply_markup=KB(rows))
    return END


async def admin_topsort_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:topsort — show sort criteria menu."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(
        t(lang,"adm_usearch_sort_prompt"), parse_mode="HTML",
        reply_markup=admin_topsort_kb(lang)
    )


async def admin_top_sorted_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:top:{criteria}:{page}"""
    q    = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    parts    = q.data.split(":")
    criteria = parts[2]
    page     = int(parts[3])
    per      = 10

    ORDER = {
        "spent":     "total_spent DESC",
        "balance":   "balance DESC",
        "purchases": "total_purchases DESC",
        "refs":      "referral_count DESC",
    }
    order_sql = ORDER.get(criteria, "total_spent DESC")

    from core import _q as _cq
    users = await _cq(
        f"SELECT * FROM users WHERE is_banned=0 ORDER BY {order_sql} LIMIT ? OFFSET ?",
        (per+1, page*per), fetchall=True
    )
    has_more = len(users) > per
    users    = users[:per]

    TITLES = {
        "spent":     "adm_top_by_spent",
        "balance":   "adm_top_by_balance",
        "purchases": "adm_top_by_purchases",
        "refs":      "adm_top_by_refs",
    }
    lines = [t(lang, TITLES.get(criteria,"adm_top_by_spent")), ""]
    rows  = []
    for i, u in enumerate(users, page*per+1):
        lines.append(t(lang,"adm_top_row_full",
                        rank=i, name=user_display(u),
                        spent=u.get("total_spent",0),
                        purchases=u.get("total_purchases",0),
                        bal=u.get("balance",0),
                        refs=u.get("referral_count",0)))
        rows.append([Btn(
            f"{i}. {user_display(u)}",
            callback_data=f"adm:u:{u['id']}"
        )])
        lines.append("")

    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:top:{criteria}:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"adm:top:{criteria}:{page+1}"))
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="adm:topsort")])

    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# ADMIN REFERRAL MANAGEMENT
# ════════════════════════════════════════════════════════════════════════════

async def admin_referral_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ref:m"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_global_referral_stats()
    enabled = s.get("enabled", True)
    status_s = ("🟢 مفعّل" if lang=="ar" else "🟢 Active") if enabled                else ("🔴 معطّل" if lang=="ar" else "🔴 Disabled")

    top_lines = []
    for i, r in enumerate(s.get("top_referrers",[])[:5], 1):
        name = r.get("first_name","") or r.get("username","") or str(r.get("telegram_id","?"))
        top_lines.append(t(lang,"adm_ref_top_row", rank=i, name=name,
                            refs=r.get("refs",0), earned=r.get("earned",0)))

    text = t(lang,"adm_ref_title") + "\n\n" + t(lang,"adm_ref_stats",
        total=s["total_referrals"], active=s["active_referrals"],
        total_earned=s["total_earned"], today=s["today_earned"],
        week=s["week_earned"], pct=s["pct"],
        status=status_s,
        top="\n".join(top_lines) or "—")

    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_referral_kb(lang))


async def admin_ref_toggle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ref:tog"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    from core import set_setting
    cur = await get_setting("referral_enabled")
    await set_setting("referral_enabled", "0" if cur=="1" else "1")
    await q.answer(t(lang,"adm_ref_toggled"), show_alert=True)
    await admin_referral_menu_cb(update, ctx)


async def admin_ref_pct_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ref:pct"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_ref_enter_pct"))
    return S_REF_PCT


async def recv_ref_pct(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    raw  = (update.message.text or "").strip().replace(",",".")
    try:
        v = float(raw)
        if v < 0 or v > 50: raise ValueError
    except ValueError:
        await update.message.reply_text(t(lang,"adm_ref_invalid_pct"))
        return S_REF_PCT
    from core import set_setting
    await set_setting("referral_pct", str(v))
    await update.message.reply_text(
        t(lang,"adm_ref_pct_saved", pct=v),
        parse_mode="HTML",
        reply_markup=back_kb(lang,"adm:ref:m")
    )
    return END


async def admin_ref_all_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:ref:l:{page}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    page = int(q.data.split(":")[-1])
    per  = 6
    rows = await get_all_referral_earnings(limit=per+1, offset=page*per)
    has_more = len(rows) > per
    rows     = rows[:per]

    lines = [t(lang,"adm_ref_all_title"),""]
    for r in rows:
        referrer = r.get("referrer_name","") or r.get("referrer_uname","") or "?"
        referred = r.get("referred_name","") or r.get("referred_uname","") or "?"
        lines.append(t(lang,"adm_ref_all_row",
                        referrer=referrer, referred=referred,
                        earned=r.get("commission_usd",0),
                        pct=r.get("commission_pct",0),
                        date=fmt_date(r.get("created_at",""))))
        lines.append("")

    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:ref:l:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"adm:ref:l:{page+1}"))
    kbd_rows = []
    if nav: kbd_rows.append(nav)
    kbd_rows.append([Btn(t(lang,"back"), callback_data="adm:ref:m")])

    text = "\n".join(lines) if rows else ("لا إحالات" if lang=="ar" else "No referrals yet.")
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=KB(kbd_rows))


async def admin_user_referrals_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:uref:{db_id}:{page} — view referrals made BY a specific user"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    parts  = q.data.split(":")
    db_id  = int(parts[2])
    page   = int(parts[3]) if len(parts) > 3 else 0
    per    = 5
    user   = await get_user_by_id(db_id)
    if not user:
        await q.answer(t(lang,"adm_not_found"), show_alert=True); return

    refs = await get_user_referrals(user["telegram_id"], limit=per+1, offset=page*per)
    has_more = len(refs) > per
    refs     = refs[:per]

    name_d = user_display(user)
    lines  = [t(lang,"adm_user_refs_title", name=name_d),""]

    if not refs and page == 0:
        lines.append(t(lang,"adm_user_refs_empty"))
    else:
        for r in refs:
            ref_name = r.get("first_name","") or r.get("username","") or str(r.get("ref_tg_id","?"))
            lines.append(t(lang,"adm_user_ref_row",
                            name=ref_name,
                            purchases=r.get("ref_purchases",0),
                            earned=r.get("total_earned",0),
                            date=fmt_date(r.get("created_at",""))))
            lines.append("")

    # Total stats for this user
    stats = await get_user_referral_stats(user["telegram_id"])
    lines.append("─" * 18)
    lines.append(f"📊 {'الإجمالي' if lang=='ar' else 'Total'}: {stats.get('total',0)} | "
                 f"💰 ${stats.get('total_earned',0):.4f} | "
                 f"{'النسبة' if lang=='ar' else 'Rate'}: {stats.get('pct',5)}%")

    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:uref:{db_id}:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"adm:uref:{db_id}:{page+1}"))
    kbd_rows = []
    if nav: kbd_rows.append(nav)
    kbd_rows.append([Btn(t(lang,"back"), callback_data=f"adm:u:{db_id}")])

    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=KB(kbd_rows))


def register(app):
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("admin", admin_cmd),
            CallbackQueryHandler(admin_search_cb,         pattern="^adm:sr$"),
            CallbackQueryHandler(admin_add_bal_cb,        pattern=r"^adm:ab:\d+$"),
            CallbackQueryHandler(admin_rm_bal_cb,         pattern=r"^adm:rb:\d+$"),
            CallbackQueryHandler(admin_set_bal_cb,        pattern=r"^adm:sb:\d+$"),
            CallbackQueryHandler(admin_note_cb,           pattern=r"^adm:nt:\d+$"),
            CallbackQueryHandler(admin_msg_user_prompt_cb,pattern=r"^adm:um:\d+$"),
            CallbackQueryHandler(admin_msg_prompt_cb,     pattern="^adm:mu$"),
            CallbackQueryHandler(admin_settings_action_cb,pattern=r"^adm:ss:\w+$"),
            CallbackQueryHandler(admin_ref_pct_cb,         pattern="^adm:ref:pct$"),
            CallbackQueryHandler(admin_usearch_cb,           pattern="^adm:usearch$"),
        ],
        states={
            S_PW:         [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pw)],
            S_SEARCH:     [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_search)],
            S_AMOUNT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_amount)],
            S_REASON:     [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_reason)],

            S_NOTE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_note)],
            S_MSG:        [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_msg)],
            S_SETTING_VAL:[MessageHandler(filters.TEXT & ~filters.COMMAND, recv_setting_val)],
            S_REF_PCT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_ref_pct)],
            S_USEARCH2:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_usearch2)],
        },
        fallbacks=[CommandHandler("start", lambda u,c: END)],
        per_message=False, allow_reentry=True,
    )
    app.add_handler(conv)

    # Auth entry point for /admin command directly
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("admin", admin_cmd)],
        states={S_PW: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pw)]},
        fallbacks=[], per_message=False, allow_reentry=True,
    ), group=1)

    # Regular callbacks
    for pattern, handler in [
        ("^adm:m$",              admin_menu_cb),
        ("^adm:lo$",             admin_logout_cb),
        ("^adm:st$",             admin_stats_cb),
        (r"^adm:ul:\d+$",        admin_users_cb),
        (r"^adm:u:\d+$",         admin_view_user_cb),
        (r"^adm:bn:\d+$",        admin_ban_cb),
        (r"^adm:ub:\d+$",        admin_unban_cb),
        (r"^adm:del:\d+$",       admin_delete_ask_cb),
        (r"^adm:del_ok:\d+$",    admin_delete_ok_cb),
        (r"^adm:up:\d+:\d+$",    admin_user_purchases_cb),
        (r"^adm:ut:\d+:\d+$",    admin_user_txs_cb),
        (r"^adm:us:\d+$",        admin_user_stats_cb),
        (r"^adm:t:\d+$",         admin_all_txs_cb),
        (r"^adm:ap:\d+$",        admin_all_purchases_cb),
        (r"^adm:an:\d+$",        admin_active_nums_cb),
        ("^adm:tp$",             admin_top_cb),
        ("^adm:ss$",             admin_settings_cb),
        ("^adm:ref:m$",          admin_referral_menu_cb),
        ("^adm:ref:tog$",        admin_ref_toggle_cb),
        (r"^adm:ref:l:\d+$",     admin_ref_all_cb),
        (r"^adm:uref:\d+:\d+$", admin_user_referrals_cb),
        ("^adm:topsort$",              admin_topsort_cb),
        (r"^adm:top:\w+:\d+$",         admin_top_sorted_cb),
        ("^adm:profit:m$",              admin_profit_menu_cb),
        ("^adm:profit:overview$",       admin_profit_overview_cb),
        ("^adm:profit:services$",       admin_profit_services_cb),
        ("^adm:profit:countries$",      admin_profit_countries_cb),
        ("^adm:profit:monthly$",        admin_profit_monthly_cb),
        ("^adm:profit:deposits$",       admin_profit_deposits_cb),
        ("^adm:profit:markup$",         admin_profit_markup_cb),
    ]:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
