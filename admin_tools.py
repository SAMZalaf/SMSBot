"""
admin_tools.py
Task 5 ─ SMSPool API key management (multi-key + live switch)
Task 6 ─ Advanced broadcast (all / active / depositors / specific user)
Task 7 ─ Message management commands:
            /msg_options [reply | @user | id]
            /msg_delete · /msg_edit · /msg_pin · /msg_unpin
"""
import asyncio
import warnings
from datetime import datetime

# Suppress PTBUserWarning about per_message in ConversationHandler
warnings.filterwarnings('ignore', message='.*per_message.*', category=UserWarning)

from telegram import Update, InlineKeyboardButton as Btn, InlineKeyboardMarkup as KB
from telegram.ext import (
    ContextTypes, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
from core import (
    t, fmt_date, user_display, is_admin,
    get_user, get_user_by_id, search_users, get_all_users, count_users,
    get_smspool_keys, get_active_smspool_key,
    add_smspool_key, delete_smspool_key, set_active_smspool_key,
    get_smspool_key_by_id,
    get_setting,
    admin_smspool_kb, admin_smspool_key_kb, back_kb, confirm_action_kb
)
from smspool import pool as sms_pool, SMSPool, SMSError

# ── Conversation states ────────────────────────────────────────────────────────
(S_SK_KEY, S_SK_LABEL,
 S_BC_MSG, S_BC_CONFIRM,
 S_BC_SPECIFIC_USER, S_BC_SPECIFIC_MSG,
 S_MSG_EDIT) = range(20, 27)
END = ConversationHandler.END


async def _lang(tid):
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
# TASK 5 ─ SMSPool Key Management
# ════════════════════════════════════════════════════════════════════════════

async def smspool_list_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:list"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    keys = await get_smspool_keys()
    active_key = await get_active_smspool_key()
    prev = (active_key[:6] + "..." + active_key[-4:]) if active_key else "—"

    # Try to get account balance from active key
    balance = 0.0
    try:
        balance = await sms_pool.account_balance()
    except Exception:
        pass

    text = t(lang,"adm_smspool_body",
             active_preview=prev, count=len(keys), balance=balance)
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_smspool_kb(lang, keys))


async def smspool_view_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:v:{key_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    key_id = int(q.data.split(":")[-1])
    sk     = await get_smspool_key_by_id(key_id)
    if not sk:
        await q.answer("❌ Not found", show_alert=True); return

    stat = "🟢 " + ("نشط" if lang=="ar" else "Active") if sk.get("is_active") \
           else "⚪ " + ("غير نشط" if lang=="ar" else "Inactive")
    prev = sk["api_key"][:8] + "..." + sk["api_key"][-6:]
    text = (
        f"🔑 <b>{'تفاصيل المفتاح' if lang=='ar' else 'Key Details'}</b>\n"
        f"─────────────────\n"
        f"🔐 <code>{prev}</code>\n"
        f"📝 {'الاسم' if lang=='ar' else 'Label'}: <b>{sk.get('label') or '—'}</b>\n"
        f"{'الحالة' if lang=='ar' else 'Status'}: {stat}\n"
        f"📅 {'أُضيف' if lang=='ar' else 'Added'}: {fmt_date(sk.get('added_at',''))}"
    )
    await q.edit_message_text(text, parse_mode="HTML",
                               reply_markup=admin_smspool_key_kb(lang, key_id, bool(sk.get("is_active"))))


async def smspool_add_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:add"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    await q.edit_message_text(t(lang,"adm_smspool_enter_key"))
    return S_SK_KEY


async def recv_sk_key(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    key  = (update.message.text or "").strip()
    # Validate key
    test = SMSPool(key)
    try:
        await test.account_balance()
        valid = True
    except SMSError:
        valid = False

    if not valid:
        await update.message.reply_text(t(lang,"adm_smspool_invalid"))
        return S_SK_KEY

    ctx.user_data["new_sk_key"] = key
    await update.message.reply_text(t(lang,"adm_smspool_enter_label"))
    return S_SK_LABEL


async def recv_sk_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang  = await _lang(update.effective_user.id)
    label = (update.message.text or "").strip()
    key   = ctx.user_data.get("new_sk_key","")

    await add_smspool_key(key, label)

    # If no active key set, auto-activate the new one
    keys = await get_smspool_keys()
    active_count = sum(1 for k in keys if k.get("is_active"))
    if active_count == 0 and keys:
        await set_active_smspool_key(keys[-1]["id"])

    await update.message.reply_text(t(lang,"adm_smspool_added"),
                                     reply_markup=back_kb(lang,"adm:sk:list"))
    return END


async def smspool_activate_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:act:{key_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    key_id = int(q.data.split(":")[-1])
    await set_active_smspool_key(key_id)
    await q.answer(t(lang,"adm_smspool_activated"), show_alert=True)
    await smspool_list_cb(update, ctx)


async def smspool_delete_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:del:{key_id}"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    key_id = int(q.data.split(":")[-1])
    await delete_smspool_key(key_id)
    await q.answer(t(lang,"adm_smspool_deleted"), show_alert=True)
    await smspool_list_cb(update, ctx)


async def smspool_balance_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:sk:bal — check live balance"""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    try:
        bal = await sms_pool.account_balance()
        await q.answer(t(lang,"adm_smspool_balance",balance=bal), show_alert=True)
    except SMSError as e:
        await q.answer(f"❌ {e}", show_alert=True)


# ════════════════════════════════════════════════════════════════════════════
# TASK 6 ─ Advanced Broadcast
# ════════════════════════════════════════════════════════════════════════════

async def broadcast_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:bc — show broadcast type menu."""
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return

    rows = [
        [Btn(t(lang,"btn_bc_all"),       callback_data="adm:bc:all")],
        [Btn(t(lang,"btn_bc_active"),     callback_data="adm:bc:active")],
        [Btn(t(lang,"btn_bc_deposited"),  callback_data="adm:bc:deposited")],
        [Btn(t(lang,"btn_bc_specific"),   callback_data="adm:bc:specific")],
        [Btn(t(lang,"back"),              callback_data="adm:m")],
    ]
    await q.edit_message_text(
        t(lang,"adm_broadcast_type_menu") + "\n\n" + t(lang,"adm_bc_html_tip"),
        parse_mode="HTML", reply_markup=KB(rows)
    )


async def _start_broadcast(update, ctx, bc_type: str):
    lang = await _lang(update.effective_user.id)
    ctx.user_data["bc_type"] = bc_type
    q = update.callback_query
    await q.edit_message_text(
        t(lang,"adm_broadcast_prompt") + "\n\n" + t(lang,"adm_bc_html_tip"),
        parse_mode="HTML",
        reply_markup=back_kb(lang,"adm:bc")
    )
    return S_BC_MSG

async def bc_all_cb(update, ctx): return await _start_broadcast(update, ctx, "all")
async def bc_active_cb(update, ctx): return await _start_broadcast(update, ctx, "active")
async def bc_deposited_cb(update, ctx): return await _start_broadcast(update, ctx, "deposited")


async def bc_specific_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return
    ctx.user_data["bc_type"] = "specific"
    await q.edit_message_text(t(lang,"adm_bc_specific_prompt"))
    return S_BC_SPECIFIC_USER


async def recv_bc_specific_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang   = await _lang(update.effective_user.id)
    query  = (update.message.text or "").strip().lstrip("@")
    users  = await search_users(query, limit=1)
    if not users:
        await update.message.reply_text(t(lang,"adm_not_found"),
                                         reply_markup=back_kb(lang,"adm:bc"))
        return END

    u = users[0]
    ctx.user_data["bc_specific_uid"] = u["id"]
    ctx.user_data["bc_specific_name"] = user_display(u)
    await update.message.reply_text(
        t(lang,"adm_bc_specific_msg_prompt", name=user_display(u)) +
        "\n\n" + t(lang,"adm_bc_html_tip"),
        parse_mode="HTML"
    )
    return S_BC_SPECIFIC_MSG


async def recv_bc_specific_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang = await _lang(update.effective_user.id)
    msg  = update.message.text or ""
    uid  = ctx.user_data.get("bc_specific_uid")
    name = ctx.user_data.get("bc_specific_name","?")
    u    = await get_user_by_id(uid)
    if not u:
        await update.message.reply_text(t(lang,"adm_not_found")); return END
    try:
        await update.effective_bot.send_message(
            chat_id=u["telegram_id"], text=msg, parse_mode="HTML"
        )
        await update.message.reply_text(
            t(lang,"adm_bc_sent_specific", name=name),
            reply_markup=back_kb(lang,"adm:bc")
        )
    except Exception as e:
        await update.message.reply_text(f"❌ {e}")
    return END


async def recv_bc_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    lang    = await _lang(update.effective_user.id)
    msg     = update.message.text or ""
    bc_type = ctx.user_data.get("bc_type","all")
    ctx.user_data["bc_msg"] = msg

    # Count target audience
    if bc_type == "all":
        count = await count_users()
    elif bc_type == "active":
        from core import _q
        r = await _q("SELECT COUNT(DISTINCT u.id) c FROM users u "
                     "JOIN purchases p ON p.user_id=u.id "
                     "WHERE u.is_banned=0", fetchone=True)
        count = r["c"] if r else 0
    elif bc_type == "deposited":
        from core import _q
        r = await _q("SELECT COUNT(DISTINCT u.id) c FROM users u "
                     "JOIN payments p ON p.user_id=u.id "
                     "WHERE p.status='Paid' AND u.is_banned=0", fetchone=True)
        count = r["c"] if r else 0
    else:
        count = 1

    # Show preview + confirm
    preview = t(lang,"adm_bc_preview", msg=msg[:300])
    rows = [
        [Btn(t(lang,"btn_bc_confirm_send"),  callback_data="adm:bc:ok"),
         Btn(t(lang,"btn_bc_edit"),          callback_data="adm:bc:edit")],
        [Btn(t(lang,"cancel"),               callback_data="adm:bc")],
    ]
    await update.message.reply_text(
        preview + "\n\n" + t(lang,"adm_broadcast_confirm", count=count),
        parse_mode="HTML",
        reply_markup=KB(rows)
    )
    return S_BC_CONFIRM


async def bc_edit_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:bc:edit — re-prompt for message."""
    q = update.callback_query; await q.answer()
    lang = await _lang(q.from_user.id)
    await q.edit_message_text(
        t(lang,"adm_broadcast_prompt") + "\n\n" + t(lang,"adm_bc_html_tip"),
        parse_mode="HTML",
        reply_markup=back_kb(lang,"adm:bc")
    )
    return S_BC_MSG


async def bc_ok_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """adm:bc:ok — execute broadcast."""
    q    = update.callback_query; await q.answer()
    lang, ok = await _require_admin(update, ctx)
    if not ok: return END

    msg     = ctx.user_data.get("bc_msg","")
    bc_type = ctx.user_data.get("bc_type","all")

    await q.edit_message_text("📤 " + ("جارٍ الإرسال..." if lang=="ar" else "Sending..."))

    # Get target users
    if bc_type == "all":
        users = await get_all_users(limit=500000)
    elif bc_type == "active":
        from core import _q
        users = await _q(
            "SELECT DISTINCT u.* FROM users u "
            "JOIN purchases p ON p.user_id=u.id "
            "WHERE u.is_banned=0", fetchall=True
        )
    elif bc_type == "deposited":
        from core import _q
        users = await _q(
            "SELECT DISTINCT u.* FROM users u "
            "JOIN payments p ON p.user_id=u.id "
            "WHERE p.status='Paid' AND u.is_banned=0", fetchall=True
        )
    else:
        users = []

    sent = failed = 0
    for u in users:
        if u.get("is_banned"): continue
        try:
            await ctx.bot.send_message(u["telegram_id"], msg, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if sent % 25 == 0:
            await asyncio.sleep(1)  # Telegram rate limit
        else:
            await asyncio.sleep(0.05)

    await q.edit_message_text(
        t(lang,"adm_broadcast_done", ok=sent, fail=failed),
        reply_markup=back_kb(lang,"adm:m")
    )
    return END


# ════════════════════════════════════════════════════════════════════════════
# TASK 7 ─ Message Management Commands
# /msg_options [reply | @user | uid]
# /msg_delete · /msg_edit · /msg_pin · /msg_unpin
# ════════════════════════════════════════════════════════════════════════════

# State storage key
MSG_OPT_KEY = "msg_options"


def _get_msg_state(ctx) -> dict | None:
    return ctx.user_data.get(MSG_OPT_KEY)

def _set_msg_state(ctx, state: dict):
    ctx.user_data[MSG_OPT_KEY] = state

def _clear_msg_state(ctx):
    ctx.user_data.pop(MSG_OPT_KEY, None)


async def msg_options_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/msg_options — must be a reply OR specify @user/id as argument."""
    if not await is_admin(update.effective_user.id):
        return
    lang = await _lang(update.effective_user.id)

    args     = ctx.args or []
    reply_to = update.message.reply_to_message

    # Case 1: already had msg_options set — second call clears it
    prev = _get_msg_state(ctx)
    if prev and not args and not reply_to:
        _clear_msg_state(ctx)
        await update.message.reply_text(t(lang,"msg_options_cleared"))
        return

    target_tid   = None
    target_msgid = None
    target_chatid = update.effective_chat.id

    # Case 2: /msg_options @username or /msg_options 123456789
    if args:
        q = args[0].lstrip("@")
        users = await search_users(q, limit=1)
        if not users:
            await update.message.reply_text(t(lang,"msg_user_not_found")); return
        u = users[0]
        target_tid = u["telegram_id"]
        # If replying too, get message id from reply
        if reply_to:
            target_msgid  = reply_to.message_id
            target_chatid = reply_to.chat.id
        _set_msg_state(ctx, {
            "target_tid":   target_tid,
            "target_msgid": target_msgid,
            "target_chatid":target_chatid,
            "user_name":    user_display(u),
            "set_at":       datetime.now().isoformat()
        })
        await update.message.reply_text(
            t(lang,"msg_options_for_user", name=user_display(u))
        )
        return

    # Case 3: must be a reply
    if not reply_to:
        await update.message.reply_text(t(lang,"msg_options_usage")); return

    _set_msg_state(ctx, {
        "target_tid":   None,
        "target_msgid": reply_to.message_id,
        "target_chatid":reply_to.chat.id,
        "user_name":    None,
        "set_at":       datetime.now().isoformat()
    })
    await update.message.reply_text(t(lang,"msg_options_set"))


async def _require_msg_options(update, ctx) -> dict | None:
    lang = await _lang(update.effective_user.id)
    state = _get_msg_state(ctx)
    if not state:
        await update.message.reply_text(t(lang,"msg_no_options")); return None
    return state


async def msg_delete_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/msg_delete"""
    if not await is_admin(update.effective_user.id): return
    lang  = await _lang(update.effective_user.id)
    state = await _require_msg_options(update, ctx)
    if not state: return

    try:
        # If targeting a specific user, try to delete via their chat
        if state.get("target_tid") and state.get("target_msgid"):
            await ctx.bot.delete_message(
                chat_id=state["target_tid"],
                message_id=state["target_msgid"]
            )
        elif state.get("target_msgid"):
            await ctx.bot.delete_message(
                chat_id=state["target_chatid"],
                message_id=state["target_msgid"]
            )
        else:
            await update.message.reply_text(t(lang,"msg_delete_fail", reason="No message selected"))
            return
        _clear_msg_state(ctx)
        await update.message.reply_text(t(lang,"msg_delete_ok"))
    except Exception as e:
        await update.message.reply_text(t(lang,"msg_delete_fail", reason=str(e)))


async def msg_edit_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/msg_edit — prompts for new text."""
    if not await is_admin(update.effective_user.id): return
    lang  = await _lang(update.effective_user.id)
    state = await _require_msg_options(update, ctx)
    if not state: return

    ctx.user_data["msg_awaiting_edit"] = True
    await update.message.reply_text(t(lang,"msg_edit_prompt"))


async def msg_edit_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Receive new text for /msg_edit."""
    if not ctx.user_data.get("msg_awaiting_edit"): return
    ctx.user_data.pop("msg_awaiting_edit", None)
    lang  = await _lang(update.effective_user.id)
    state = _get_msg_state(ctx)
    if not state:
        await update.message.reply_text(t(lang,"msg_no_options")); return

    new_text = update.message.text or ""
    try:
        chat_id  = state.get("target_tid") or state.get("target_chatid")
        msg_id   = state.get("target_msgid")
        if not msg_id:
            await update.message.reply_text(t(lang,"msg_edit_fail", reason="No message selected"))
            return
        await ctx.bot.edit_message_text(
            chat_id=chat_id, message_id=msg_id,
            text=new_text, parse_mode="HTML"
        )
        _clear_msg_state(ctx)
        await update.message.reply_text(t(lang,"msg_edit_ok"))
    except Exception as e:
        await update.message.reply_text(t(lang,"msg_edit_fail", reason=str(e)))


async def msg_pin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/msg_pin"""
    if not await is_admin(update.effective_user.id): return
    lang  = await _lang(update.effective_user.id)
    state = await _require_msg_options(update, ctx)
    if not state: return

    try:
        chat_id = state.get("target_chatid")
        msg_id  = state.get("target_msgid")
        if not msg_id:
            await update.message.reply_text(t(lang,"msg_pin_fail", reason="No message selected"))
            return
        await ctx.bot.pin_chat_message(chat_id=chat_id, message_id=msg_id,
                                        disable_notification=False)
        _clear_msg_state(ctx)
        await update.message.reply_text(t(lang,"msg_pin_ok"))
    except Exception as e:
        await update.message.reply_text(t(lang,"msg_pin_fail", reason=str(e)))


async def msg_unpin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """/msg_unpin"""
    if not await is_admin(update.effective_user.id): return
    lang  = await _lang(update.effective_user.id)
    state = await _require_msg_options(update, ctx)
    if not state: return

    try:
        chat_id = state.get("target_chatid")
        msg_id  = state.get("target_msgid")
        if msg_id:
            await ctx.bot.unpin_chat_message(chat_id=chat_id, message_id=msg_id)
        else:
            await ctx.bot.unpin_all_chat_messages(chat_id=chat_id)
        _clear_msg_state(ctx)
        await update.message.reply_text(t(lang,"msg_unpin_ok"))
    except Exception as e:
        await update.message.reply_text(t(lang,"msg_unpin_fail", reason=str(e)))


# ════════════════════════════════════════════════════════════════════════════
# REGISTER ALL HANDLERS
# ════════════════════════════════════════════════════════════════════════════

def register(app):
    # ── SMSPool key management conversation ──────────────────────────────────
    sk_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(smspool_add_cb, pattern="^adm:sk:add$"),
        ],
        states={
            S_SK_KEY:   [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_sk_key)],
            S_SK_LABEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_sk_label)],
        },
        fallbacks=[],
        per_message=False, allow_reentry=True,
    )
    app.add_handler(sk_conv)

    # ── SMSPool callbacks ─────────────────────────────────────────────────────
    for pattern, handler in [
        ("^adm:sk:list$",       smspool_list_cb),
        (r"^adm:sk:v:\d+$",     smspool_view_cb),
        (r"^adm:sk:act:\d+$",   smspool_activate_cb),
        (r"^adm:sk:del:\d+$",   smspool_delete_cb),
        ("^adm:sk:bal$",        smspool_balance_cb),
    ]:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))

    # ── Advanced broadcast conversation ───────────────────────────────────────
    bc_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(bc_all_cb,       pattern="^adm:bc:all$"),
            CallbackQueryHandler(bc_active_cb,    pattern="^adm:bc:active$"),
            CallbackQueryHandler(bc_deposited_cb, pattern="^adm:bc:deposited$"),
            CallbackQueryHandler(bc_specific_cb,  pattern="^adm:bc:specific$"),
        ],
        states={
            S_BC_MSG:           [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_bc_msg)],
            S_BC_CONFIRM:       [
                CallbackQueryHandler(bc_ok_cb,   pattern="^adm:bc:ok$"),
                CallbackQueryHandler(bc_edit_cb, pattern="^adm:bc:edit$"),
            ],
            S_BC_SPECIFIC_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_bc_specific_user)],
            S_BC_SPECIFIC_MSG:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recv_bc_specific_msg)],
        },
        fallbacks=[
            CallbackQueryHandler(broadcast_menu_cb, pattern="^adm:bc$"),
        ],
        per_message=False, allow_reentry=True,
    )
    app.add_handler(bc_conv)

    # Broadcast menu + non-conv
    app.add_handler(CallbackQueryHandler(broadcast_menu_cb, pattern="^adm:bc$"))

    # ── Message management commands ───────────────────────────────────────────
    app.add_handler(CommandHandler("msg_options", msg_options_cmd))
    app.add_handler(CommandHandler("msg_delete",  msg_delete_cmd))
    app.add_handler(CommandHandler("msg_edit",    msg_edit_cmd))
    app.add_handler(CommandHandler("msg_pin",     msg_pin_cmd))
    app.add_handler(CommandHandler("msg_unpin",   msg_unpin_cmd))

    # Text input for msg_edit (uses module-level filters import)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, msg_edit_text_handler
    ), group=6)
