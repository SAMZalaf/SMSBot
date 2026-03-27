"""
admin_payment.py ─ Admin Payment Management
OxaPay config · Payment methods CRUD · Payment stats · Payment history
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
    t, fmt_date, user_display, is_admin, get_user_by_id,
    get_setting, set_setting, start_cmd,
    get_payment_methods, get_payment_method, add_payment_method,
    update_payment_method, delete_payment_method, toggle_payment_method,
    get_all_payments, get_payment_stats,
    admin_menu_kb, admin_payment_menu_kb, admin_pm_detail_kb,
    admin_oxapay_cfg_kb, back_kb, confirm_action_kb, paginated_kb
)
from oxapay import oxapay, OxaPayError, PAYMENT_STATUS, COIN_ICONS, init_oxapay

# Conversation states
(S_OPA_KEY, S_OPA_LIFE, S_OPA_FEE, S_OPA_UNDER,
 S_PM_MIN, S_PM_MAX, S_PM_LABEL, S_PM_NOTE) = range(10, 18)
END = ConversationHandler.END


async def _lang(tid):
    from core import get_user
    u = await get_user(tid)
    return u.get("language","ar") if u else "ar"

async def _require_admin(update, ctx):
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
# PAYMENT MANAGEMENT MAIN MENU
# ════════════════════════════════════════════════════════════════════════════

async def adm_pay_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pay:m"""
    q = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    enabled = await get_setting("oxapay_enabled") == "1"
    key     = await get_setting("oxapay_key") or ""
    status_s = ("🟢 مفعّل" if lang=="ar" else "🟢 Active") if enabled \
               else ("🔴 معطّل" if lang=="ar" else "🔴 Disabled")

    # Try to get balance
    balance_text = ""
    if key:
        try:
            bal_data = await oxapay.merchant_info()
            if bal_data.get("result") == 100 or bal_data.get("result") == 200:
                 # result 100 usually success. Body format: {"result":100, "message":"success", "data": {"balance":0, ...}}
                 # but docs vary. Let's look at Body v13: Body /merchant/balance: 403 (blocked)
                 # If it works, it usually has "data" or "balance"
                 bal = bal_data.get("balance", bal_data.get("data", {}).get("balance", "0"))
                 balance_text = f"\n💰 {'رصيد الحساب:' if lang=='ar' else 'Account Balance:'} <b>${bal}</b>"
        except:
            pass

    text = (
        f"{'💳 إدارة المدفوعات' if lang=='ar' else '💳 Payment Management'}\n\n"
        f"{'البوابة:' if lang=='ar' else 'Gateway:'} <b>OxaPay</b>  {status_s}\n"
        f"{'المفتاح:' if lang=='ar' else 'Key:'} <code>{'✅ مُعد' if key else '❌ غير مُعد'}</code>"
        f"{balance_text}"
    )

    rows = [
        [Btn(t(lang,"adm_pay_stats") if lang=="ar" else "📊 Payment Stats", callback_data="adm:pay:st")],
        [Btn(t(lang,"adm_pay_list_title") if lang=="ar" else "💳 All Payments", callback_data="adm:pay:l:0")],
        [Btn(t(lang,"adm_oxapay_settings"), callback_data="adm:pay:cfg")],
        [Btn(t(lang,"btn_adm_pay_methods"), callback_data="adm:pm:l")],
        [Btn(t(lang,"back"), callback_data="adm:m")],
    ]
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT STATISTICS
# ════════════════════════════════════════════════════════════════════════════

async def adm_pay_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pay:st"""
    q = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    s = await get_payment_stats()

    by_coin_lines = []
    for row in s.get("by_currency", []):
        coin = row.get("pay_currency","?")
        icon = COIN_ICONS.get(coin.upper(),"🪙")
        by_coin_lines.append(f"  {icon} {coin}: {row.get('n',0)} × ${row.get('total',0):.2f}")
    by_coin = "\n".join(by_coin_lines) or "—"

    monthly_lines = []
    for row in s.get("monthly",[]):
        monthly_lines.append(f"  📅 {row.get('mo','?')}: {row.get('n',0)} × ${row.get('tot',0):.2f}")
    monthly = "\n".join(monthly_lines) or "—"

    text = t(lang,"adm_pay_stats",
             paid=s["paid_count"], pending=s["pending_count"], expired=s["expired_count"],
             total=s["total_usd"], today=s["today_usd"], today_c=s["today_count"],
             week=s["week_usd"], by_coin=by_coin, monthly=monthly)

    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=back_kb(lang,"adm:pay:m"))


# ════════════════════════════════════════════════════════════════════════════
# ALL PAYMENTS LIST
# ════════════════════════════════════════════════════════════════════════════

async def adm_pay_list_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pay:l:{page}"""
    q = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    page = int(q.data.split(":")[-1])
    per  = 6
    pays = await get_all_payments(limit=per+1, offset=page*per)
    has_more = len(pays) > per
    pays     = pays[:per]

    lines = [f"{'💳 جميع المدفوعات' if lang=='ar' else '💳 All Payments'}\n"]
    for p in pays:
        status = p.get("status","Waiting")
        icon   = PAYMENT_STATUS.get(status, ("❓","?"))[0]
        coin   = p.get("pay_currency","?")
        uname  = p.get("username") or p.get("first_name") or str(p.get("telegram_id","?"))
        lines.append(
            f"{icon} <b>{uname}</b> — {COIN_ICONS.get(coin.upper(),'🪙')}{coin} — <b>${p.get('amount_usd',0):.2f}</b>\n"
            f"📅 {fmt_date(p.get('created_at',''))} | {status}\n"
            f"🆔 <code>{p.get('track_id','')}</code>"
        )
        lines.append("")

    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"adm:pay:l:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"adm:pay:l:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="adm:pay:m")])

    text = "\n".join(lines) if pays else ("لا توجد مدفوعات" if lang=="ar" else "No payments yet.")
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=KB(rows))


# ════════════════════════════════════════════════════════════════════════════
# OXAPAY CONFIGURATION
# ════════════════════════════════════════════════════════════════════════════

async def adm_oxapay_cfg_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pay:cfg"""
    q = update.callback_query
    await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    key      = await get_setting("oxapay_key") or ""
    enabled  = await get_setting("oxapay_enabled") == "1"
    lifetime = await get_setting("pay_lifetime_min") or "30"
    fee_payer= await get_setting("pay_fee_payer") or "0"
    underpaid= await get_setting("pay_underpaid") or "2.5"

    key_preview = (key[:6] + "..." + key[-4:]) if len(key) > 10 else ("✅" if key else "❌ غير مُعد")
    en_s        = ("🟢 " + t(lang,"fee_payer_merchant")) if enabled else ("🔴 " + ("معطّل" if lang=="ar" else "Disabled"))
    fp_s        = t(lang,"fee_payer_customer") if fee_payer=="1" else t(lang,"fee_payer_merchant")

    text = t(lang,"adm_oxapay_settings") + "\n\n" + t(lang,"adm_oxapay_body",
             key_preview=key_preview, enabled=en_s,
             lifetime=lifetime, fee_payer=fp_s, underpaid=underpaid)

    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_oxapay_cfg_kb(lang))


async def adm_oxapay_key_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:opa:key"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(
        ("🔑 أدخل مفتاح OxaPay API الجديد:" if lang=="ar" else "🔑 Enter your OxaPay API key:") +
        "\n\nhttps://oxapay.com → Settings → API Keys"
    )
    return S_OPA_KEY

async def recv_oxapay_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    key  = (update.message.text or "").strip()
    try: await update.message.delete()
    except: pass
    # Test the key
    test_opa = type('OxaPay', (), {})()
    from oxapay import OxaPay
    test = OxaPay(key)
    valid = False
    try:
        bal = await test.merchant_info()
        valid = True
    except OxaPayError:
        valid = False

    if valid:
        await set_setting("oxapay_key", key)
        init_oxapay(key)
        await update.effective_chat.send_message(
            ("✅ تم حفظ المفتاح وتحققنا منه!" if lang=="ar" else "✅ Key saved and verified!"),
            reply_markup=back_kb(lang,"adm:pay:cfg")
        )
    else:
        # Save anyway but warn
        await set_setting("oxapay_key", key)
        await update.effective_chat.send_message(
            ("⚠️ تم حفظ المفتاح لكن لم يتم التحقق منه. تأكد من صحته." if lang=="ar"
             else "⚠️ Key saved but could not verify. Please double-check it."),
            reply_markup=back_kb(lang,"adm:pay:cfg")
        )
    return END

async def adm_oxapay_toggle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:opa:tog"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    cur = await get_setting("oxapay_enabled")
    await set_setting("oxapay_enabled", "0" if cur=="1" else "1")
    await adm_oxapay_cfg_cb(update, ctx)

async def adm_oxapay_lifetime_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(
        ("⏰ أدخل مدة صلاحية الفاتورة بالدقائق (مثال: 30):" if lang=="ar"
         else "⏰ Enter invoice lifetime in minutes (e.g. 30):")
    )
    return S_OPA_LIFE

async def recv_oxapay_lifetime(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    val  = (update.message.text or "").strip()
    try:
        v = int(val)
        if v < 5 or v > 10080: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ " + ("أدخل رقماً بين 5 و10080 دقيقة" if lang=="ar"
                                                  else "Enter a number between 5 and 10080"))
        return S_OPA_LIFE
    await set_setting("pay_lifetime_min", str(v))
    await update.message.reply_text(t(lang,"adm_setting_saved"),
                                     reply_markup=back_kb(lang,"adm:pay:cfg"))
    return END

async def adm_oxapay_fee_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    cur = await get_setting("pay_fee_payer") or "0"
    await set_setting("pay_fee_payer", "1" if cur=="0" else "0")
    await adm_oxapay_cfg_cb(update, ctx)

async def adm_oxapay_underpaid_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(
        ("📉 أدخل نسبة تسامح القصور % (مثال: 2.5):" if lang=="ar"
         else "📉 Enter underpaid cover percentage (e.g. 2.5):")
    )
    return S_OPA_UNDER

async def recv_oxapay_underpaid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    val  = (update.message.text or "").strip().replace(",",".")
    try:
        v = float(val)
        if v < 0 or v > 50: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ " + ("أدخل رقماً بين 0 و50" if lang=="ar"
                                                  else "Enter a number between 0 and 50"))
        return S_OPA_UNDER
    await set_setting("pay_underpaid", str(v))
    await update.message.reply_text(t(lang,"adm_setting_saved"),
                                     reply_markup=back_kb(lang,"adm:pay:cfg"))
    return END


# ════════════════════════════════════════════════════════════════════════════
# PAYMENT METHODS (CRUD)
# ════════════════════════════════════════════════════════════════════════════

async def adm_pm_list_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:l"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    methods = await get_payment_methods()
    lines   = [t(lang,"adm_pm_list"),""]
    for pm in methods:
        stat = "🟢" if pm.get("is_enabled") else "🔴"
        net  = f"({pm.get('network','')})" if pm.get("network") else ""
        lines.append(t(lang,"adm_pm_row", status=stat, coin=pm["coin"], network=net,
                        min=pm.get("min_amount",1), max=pm.get("max_amount",10000)))

    rows = []
    for pm in methods:
        stat  = "🟢" if pm.get("is_enabled") else "🔴"
        label = pm.get("label") or pm["coin"]
        net   = f"({pm.get('network','')})" if pm.get("network") else ""
        rows.append([Btn(f"{stat} {COIN_ICONS.get(pm['coin'].upper(),'🪙')} {label} {net}",
                          callback_data=f"adm:pm:v:{pm['id']}")])

    rows.append([Btn(t(lang,"btn_adm_pm_add"),  callback_data="adm:pm:add")])
    rows.append([Btn(t(lang,"back"), callback_data="adm:pay:m")])

    text = "\n".join(lines) if methods else t(lang,"adm_pm_empty")
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=KB(rows))


async def adm_pm_view_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:v:{pm_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    pm_id = int(q.data.split(":")[-1])
    pm    = await get_payment_method(pm_id)
    if not pm:
        await q.answer("❌ Not found", show_alert=True); return

    stat      = ("🟢 مفعّل" if lang=="ar" else "🟢 Active") if pm.get("is_enabled") else ("🔴 معطّل" if lang=="ar" else "🔴 Disabled")
    fee_payer = t(lang,"fee_payer_customer") if pm.get("fee_paid_by") else t(lang,"fee_payer_merchant")
    text = t(lang,"adm_pm_detail",
             coin=pm["coin"],
             network=pm.get("network","—") or "—",
             label=pm.get("label","—") or "—",
             min=pm.get("min_amount",1),
             max=pm.get("max_amount",10000),
             fee_payer=fee_payer,
             lifetime=pm.get("lifetime_min",30),
             underpaid=pm.get("underpaid_cover",2.5),
             note=pm.get("note","—") or "—",
             status=stat)
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_pm_detail_kb(lang, pm_id))


async def adm_pm_toggle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:tog:{pm_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    pm_id = int(q.data.split(":")[-1])
    await toggle_payment_method(pm_id)
    await q.answer(t(lang,"adm_pm_toggled"), show_alert=True)
    await adm_pm_view_cb(update, ctx)


async def adm_pm_delete_ask_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:del:{pm_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    pm_id = int(q.data.split(":")[-1])
    ctx.user_data["del_pm_id"] = pm_id
    await q.edit_message_text(
        ("⚠️ هل أنت متأكد من حذف طريقة الدفع هذه؟" if lang=="ar"
         else "⚠️ Delete this payment method?"),
        reply_markup=confirm_action_kb(lang, f"adm:pm:delok:{pm_id}", "adm:pm:l")
    )

async def adm_pm_delete_ok_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:delok:{pm_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    pm_id = int(q.data.split(":")[-1])
    await delete_payment_method(pm_id)
    await q.edit_message_text(t(lang,"adm_pm_deleted"),
                               reply_markup=back_kb(lang,"adm:pm:l"))

async def _pm_conv_end(u, c): return END

# ── ADD PAYMENT METHOD WIZARD ─────────────────────────────────────────────────

async def adm_pm_add_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:add — start add wizard"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    # Fetch available currencies from OxaPay
    key = await get_setting("oxapay_key") or ""
    if key: init_oxapay(key)

    await q.edit_message_text(t(lang,"loading"), parse_mode="HTML")
    try:
        currencies = await oxapay.accepted_currencies()
    except OxaPayError:
        currencies = []

    if not currencies:
        # Fallback: show manual common coins
        currencies = [
            {"currency":"USDT","network":"TRX"},{"currency":"USDT","network":"BEP20"},
            {"currency":"USDT","network":"ERC20"},{"currency":"BTC","network":"BTC"},
            {"currency":"ETH","network":"ERC20"},{"currency":"TRX","network":"TRX"},
            {"currency":"BNB","network":"BEP20"},{"currency":"LTC","network":"LTC"},
            {"currency":"TON","network":"TON"},{"currency":"DOGE","network":"DOGE"},
        ]

    # Build coin selection keyboard
    rows = []
    seen = set()
    for cur in currencies:
        coin = cur.get("currency","?")
        net  = cur.get("network","")
        key_ = f"{coin}_{net}"
        if key_ in seen: continue
        seen.add(key_)
        icon = COIN_ICONS.get(coin.upper(),"🪙")
        label = f"{icon} {coin}"
        if net: label += f" ({net})"
        rows.append([Btn(label, callback_data=f"adm:pm:coin:{coin}:{net}")])
        if len(rows) >= 15: break

    rows.append([Btn(t(lang,"back"), callback_data="adm:pm:l")])
    await q.edit_message_text(t(lang,"adm_pm_select_coin"), parse_mode="HTML",
                               reply_markup=KB(rows))


async def adm_pm_coin_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:pm:coin:{coin}:{network}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    parts   = q.data.split(":")
    coin    = parts[3]
    network = parts[4] if len(parts) > 4 else ""

    ctx.user_data["new_pm_coin"]    = coin
    ctx.user_data["new_pm_network"] = network
    ctx.user_data["new_pm_label"]   = ""
    ctx.user_data["new_pm_note"]    = ""

    await q.edit_message_text(t(lang,"adm_pm_enter_min"))
    return S_PM_MIN

async def recv_pm_min(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    raw  = (update.message.text or "").strip().replace(",",".")
    try:
        v = float(raw)
        if v <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ " + ("أدخل رقماً موجباً" if lang=="ar" else "Enter a positive number"))
        return S_PM_MIN
    ctx.user_data["new_pm_min"] = v
    await update.message.reply_text(t(lang,"adm_pm_enter_max"))
    return S_PM_MAX

async def recv_pm_max(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    raw  = (update.message.text or "").strip().replace(",",".")
    try:
        v = float(raw)
        if v <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("❌ " + ("أدخل رقماً موجباً" if lang=="ar" else "Enter a positive number"))
        return S_PM_MAX
    ctx.user_data["new_pm_max"] = v

    skip_btn = KB([[Btn(t(lang,"adm_pm_skip"), callback_data="adm:pm:skip_label")]])
    await update.message.reply_text(t(lang,"adm_pm_enter_label"), reply_markup=skip_btn)
    return S_PM_LABEL

async def recv_pm_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    ctx.user_data["new_pm_label"] = (update.message.text or "").strip()
    skip_btn = KB([[Btn(t(lang,"adm_pm_skip"), callback_data="adm:pm:skip_note")]])
    await update.message.reply_text(t(lang,"adm_pm_enter_note"), reply_markup=skip_btn)
    return S_PM_NOTE

async def skip_pm_label_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    ctx.user_data["new_pm_label"] = ""
    skip_btn = KB([[Btn(t(lang,"adm_pm_skip"), callback_data="adm:pm:skip_note")]])
    await q.edit_message_text(t(lang,"adm_pm_enter_note"), reply_markup=skip_btn)
    return S_PM_NOTE

async def recv_pm_note(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    ctx.user_data["new_pm_note"] = (update.message.text or "").strip()
    return await _save_new_pm(update, ctx, lang)

async def skip_pm_note_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    ctx.user_data["new_pm_note"] = ""
    return await _save_new_pm(update, ctx, lang, via_query=q)

async def _save_new_pm(update, ctx, lang, via_query=None):
    coin    = ctx.user_data.get("new_pm_coin","USDT")
    network = ctx.user_data.get("new_pm_network","")
    label   = ctx.user_data.get("new_pm_label","")
    note    = ctx.user_data.get("new_pm_note","")
    mn      = ctx.user_data.get("new_pm_min", 1.0)
    mx      = ctx.user_data.get("new_pm_max", 10000.0)

    lifetime = int(await get_setting("pay_lifetime_min") or 30)
    fee      = int(await get_setting("pay_fee_payer") or 0)
    underpaid= float(await get_setting("pay_underpaid") or 2.5)

    await add_payment_method(
        coin=coin, network=network, label=label,
        min_amount=mn, max_amount=mx,
        fee_paid_by=fee, lifetime_min=lifetime,
        underpaid_cover=underpaid, note=note
    )

    text = t(lang,"adm_pm_added", coin=f"{coin} {f'({network})' if network else ''}".strip())
    kb   = back_kb(lang,"adm:pm:l")
    if via_query:
        await via_query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
    return END


# ════════════════════════════════════════════════════════════════════════════
# REGISTER
# ════════════════════════════════════════════════════════════════════════════

def register(app):
    # Payment method add wizard (ConversationHandler)
    pm_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(adm_pm_add_cb,      pattern="^adm:pm:add$"),
            CallbackQueryHandler(adm_pm_coin_cb,     pattern=r"^adm:pm:coin:.+:.+$"),
            CallbackQueryHandler(adm_oxapay_key_cb,  pattern="^adm:opa:key$"),
            CallbackQueryHandler(adm_oxapay_lifetime_cb, pattern="^adm:opa:life$"),
            CallbackQueryHandler(adm_oxapay_underpaid_cb, pattern="^adm:opa:underpaid$"),
        ],
        states={
            S_OPA_KEY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_oxapay_key)],
            S_OPA_LIFE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_oxapay_lifetime)],
            S_OPA_UNDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_oxapay_underpaid)],
            S_PM_MIN:    [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pm_min)],
            S_PM_MAX:    [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pm_max)],
            S_PM_LABEL:  [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pm_label),
                CallbackQueryHandler(skip_pm_label_cb, pattern="^adm:pm:skip_label$"),
            ],
            S_PM_NOTE:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, recv_pm_note),
                CallbackQueryHandler(skip_pm_note_cb, pattern="^adm:pm:skip_note$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(_pm_conv_end, pattern="^adm:pm:l$"),
            CommandHandler("start", start_cmd),
            MessageHandler(filters.COMMAND, _pm_conv_end),
        ],
        per_message=False, allow_reentry=True,
    )
    app.add_handler(pm_conv)

    # Regular callbacks
    for pattern, handler in [
        ("^adm:pay:m$",           adm_pay_menu_cb),
        ("^adm:pay:st$",          adm_pay_stats_cb),
        (r"^adm:pay:l:\d+$",      adm_pay_list_cb),
        ("^adm:pay:cfg$",         adm_oxapay_cfg_cb),
        ("^adm:opa:tog$",         adm_oxapay_toggle_cb),
        ("^adm:opa:fee$",         adm_oxapay_fee_cb),
        ("^adm:pm:l$",            adm_pm_list_cb),
        (r"^adm:pm:v:\d+$",       adm_pm_view_cb),
        (r"^adm:pm:tog:\d+$",     adm_pm_toggle_cb),
        (r"^adm:pm:del:\d+$",     adm_pm_delete_ask_cb),
        (r"^adm:pm:delok:\d+$",   adm_pm_delete_ok_cb),
    ]:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
