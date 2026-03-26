"""
core.py ─ Config · Database · Languages · Keyboards
كل المكونات الأساسية المشتركة في ملف واحد
"""
# ════════════════════════════════════════════════════════════════════════════
# SECTION 1 ─ CONFIG
# ════════════════════════════════════════════════════════════════════════════
import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN        = os.getenv("BOT_TOKEN", "")
ADMIN_PASSWORD   = os.getenv("ADMIN_PASSWORD", "af")
_super_raw       = os.getenv("SUPER_ADMIN_IDS", "")
SUPER_ADMIN_IDS  = [int(x.strip()) for x in _super_raw.split(",") if x.strip()]
SMSPOOL_API_KEY  = os.getenv("SMSPOOL_API_KEY", "")
SMSPOOL_BASE     = "https://api.smspool.net"
PRICE_MARKUP     = float(os.getenv("PRICE_MARKUP", "0"))
DATABASE_PATH    = os.getenv("DATABASE_PATH", "bot.db")
MIN_DEPOSIT      = float(os.getenv("MIN_DEPOSIT", "1.0"))
ITEMS_PER_PAGE   = 8
COUNTRIES_PER    = 10
SERVICES_PER     = 10
SMS_CHECK_INTERVAL  = 15  # seconds between auto-checks
SMS_MAX_WAIT        = 600 # 10 minutes before auto-cancel
OXAPAY_API_KEY      = os.getenv("OXAPAY_API_KEY", "")
PAY_CHECK_INTERVAL  = 30  # seconds between payment polling


# ════════════════════════════════════════════════════════════════════════════
# SECTION 2 ─ DATABASE
# ════════════════════════════════════════════════════════════════════════════
import aiosqlite
from datetime import datetime

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id     INTEGER UNIQUE NOT NULL,
            username        TEXT,
            first_name      TEXT,
            last_name       TEXT,
            balance         REAL    DEFAULT 0.0,
            language        TEXT    DEFAULT 'ar',
            is_admin        INTEGER DEFAULT 0,
            is_banned       INTEGER DEFAULT 0,
            total_spent     REAL    DEFAULT 0.0,
            total_purchases INTEGER DEFAULT 0,
            total_refunds   INTEGER DEFAULT 0,
            referral_count  INTEGER DEFAULT 0,
            referred_by     INTEGER DEFAULT NULL,
            note            TEXT    DEFAULT '',
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            type            TEXT    NOT NULL,
            amount          REAL    NOT NULL,
            balance_before  REAL    NOT NULL,
            balance_after   REAL    NOT NULL,
            description     TEXT,
            reference_id    TEXT,
            payment_method  TEXT,
            status          TEXT    DEFAULT 'completed',
            admin_actor     INTEGER,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS purchases (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            order_id        TEXT    UNIQUE,
            service         TEXT    NOT NULL,
            service_name    TEXT,
            country         TEXT    NOT NULL,
            country_name    TEXT,
            phone_number    TEXT,
            cost            REAL    NOT NULL,
            cost_display    REAL    NOT NULL,
            status          TEXT    DEFAULT 'active',
            sms_code        TEXT,
            sms_full        TEXT,
            pool            TEXT,
            auto_checked    INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at    TIMESTAMP,
            cancelled_at    TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS admin_sessions (
            telegram_id     INTEGER PRIMARY KEY,
            authenticated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS payments (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            track_id        TEXT    UNIQUE,
            order_ref       TEXT,
            amount_usd      REAL    NOT NULL,
            pay_currency    TEXT    NOT NULL,
            pay_amount      REAL,
            received_amount REAL,
            pay_address     TEXT,
            network         TEXT,
            status          TEXT    DEFAULT 'Waiting',
            pay_link        TEXT,
            fee_paid_by     INTEGER DEFAULT 0,
            underpaid_cover REAL    DEFAULT 2.5,
            lifetime_min    INTEGER DEFAULT 30,
            expired_at      TIMESTAMP,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at         TIMESTAMP,
            raw_response    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS payment_methods (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            coin            TEXT    NOT NULL,
            network         TEXT    DEFAULT '',
            label           TEXT    DEFAULT '',
            min_amount      REAL    DEFAULT 1.0,
            max_amount      REAL    DEFAULT 10000.0,
            is_enabled      INTEGER DEFAULT 1,
            fee_paid_by     INTEGER DEFAULT 0,
            lifetime_min    INTEGER DEFAULT 30,
            underpaid_cover REAL    DEFAULT 2.5,
            note            TEXT    DEFAULT '',
            sort_order      INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS referrals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id     INTEGER NOT NULL,
            referred_id     INTEGER NOT NULL UNIQUE,
            purchase_id     INTEGER,
            commission_pct  REAL    NOT NULL,
            commission_usd  REAL    DEFAULT 0.0,
            is_paid         INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(id),
            FOREIGN KEY (referred_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS referral_earnings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id     INTEGER NOT NULL,
            referred_id     INTEGER NOT NULL,
            purchase_id     INTEGER,
            commission_pct  REAL    NOT NULL,
            commission_usd  REAL    NOT NULL,
            purchase_amount REAL    NOT NULL,
            created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(id),
            FOREIGN KEY (referred_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_p_user      ON purchases(user_id);
        CREATE INDEX IF NOT EXISTS idx_p_status    ON purchases(status);
        CREATE INDEX IF NOT EXISTS idx_t_user      ON transactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_pay_user    ON payments(user_id);
        CREATE INDEX IF NOT EXISTS idx_pay_status  ON payments(status);
        CREATE INDEX IF NOT EXISTS idx_pm_enabled  ON payment_methods(is_enabled);
        CREATE INDEX IF NOT EXISTS idx_ref_referrer ON referrals(referrer_id);
        CREATE TABLE IF NOT EXISTS smspool_keys (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key    TEXT    NOT NULL UNIQUE,
            label      TEXT    DEFAULT '',
            is_active  INTEGER DEFAULT 0,
            added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_sk_active ON smspool_keys(is_active);
        CREATE INDEX IF NOT EXISTS idx_re_referrer  ON referral_earnings(referrer_id);
        """)
        for k, v in [
            ("bot_active","1"),("maintenance_msg_ar","البوت تحت الصيانة"),
            ("maintenance_msg_en","Bot under maintenance"),("min_deposit","1.0"),
            ("price_markup","0"),("welcome_ar",""),("welcome_en",""),
            ("support_link",""),("auto_cancel_minutes","10"),
            ("oxapay_key",""),("oxapay_enabled","0"),
            ("pay_lifetime_min","30"),("pay_fee_payer","0"),("pay_underpaid","2.5"),
            ("referral_pct","5"),("referral_enabled","1"),
        ]:
            await db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        await db.commit()

# ── helpers ──────────────────────────────────────────────────────────────────
async def _q(sql, params=(), fetchone=False, fetchall=False, commit=False):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        if commit:
            await db.commit()
            return cur.lastrowid
        if fetchone:
            row = await cur.fetchone()
            return dict(row) if row else None
        if fetchall:
            return [dict(r) for r in await cur.fetchall()]

async def get_setting(k):
    r = await _q("SELECT value FROM settings WHERE key=?", (k,), fetchone=True)
    return r["value"] if r else None

async def set_setting(k, v):
    await _q("INSERT OR REPLACE INTO settings(key,value,updated_at) VALUES(?,?,CURRENT_TIMESTAMP)",
             (k,v), commit=True)

async def get_all_settings():
    return await _q("SELECT key,value FROM settings", fetchall=True)

# ── users ─────────────────────────────────────────────────────────────────────
async def get_user(tid):
    return await _q("SELECT * FROM users WHERE telegram_id=?", (tid,), fetchone=True)

async def get_user_by_id(uid):
    return await _q("SELECT * FROM users WHERE id=?", (uid,), fetchone=True)

async def upsert_user(tid, username, first_name, last_name=None):
    await _q("""INSERT INTO users(telegram_id,username,first_name,last_name)
                VALUES(?,?,?,?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                  username=excluded.username,
                  first_name=excluded.first_name,
                  last_name=excluded.last_name,
                  last_active=CURRENT_TIMESTAMP""",
             (tid, username, first_name, last_name), commit=True)
    return await get_user(tid)

async def update_user(tid, **kw):
    if not kw: return
    sets = ",".join(f"{k}=?" for k in kw)
    await _q(f"UPDATE users SET {sets},last_active=CURRENT_TIMESTAMP WHERE telegram_id=?",
             list(kw.values())+[tid], commit=True)

async def search_users(q, limit=15):
    p = f"%{q}%"
    return await _q("""SELECT * FROM users
        WHERE username LIKE ? OR first_name LIKE ? OR last_name LIKE ?
           OR CAST(telegram_id AS TEXT) LIKE ?
        ORDER BY last_active DESC LIMIT ?""", (p,p,p,p,limit), fetchall=True)

async def get_all_users(limit=200, offset=0, banned=None):
    if banned is None:
        return await _q("SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                         (limit, offset), fetchall=True)
    return await _q("SELECT * FROM users WHERE is_banned=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (int(banned), limit, offset), fetchall=True)

async def count_users(banned=None):
    if banned is None:
        r = await _q("SELECT COUNT(*) c FROM users", fetchone=True)
    else:
        r = await _q("SELECT COUNT(*) c FROM users WHERE is_banned=?", (int(banned),), fetchone=True)
    return r["c"] if r else 0

async def get_top_users(limit=10):
    return await _q("""SELECT * FROM users WHERE is_banned=0
        ORDER BY total_spent DESC LIMIT ?""", (limit,), fetchall=True)

# ── balance ───────────────────────────────────────────────────────────────────
async def update_balance(tid, amount, tx_type, desc, ref_id=None, method=None, actor=None):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id,balance FROM users WHERE telegram_id=?", (tid,))
        user = await cur.fetchone()
        if not user: return False
        uid, bal = user["id"], user["balance"]
        new_bal  = round(bal + amount, 6)
        if new_bal < -0.0001: return False
        new_bal = max(0.0, new_bal)
        await db.execute("UPDATE users SET balance=?,last_active=CURRENT_TIMESTAMP WHERE telegram_id=?", (new_bal, tid))
        await db.execute("""INSERT INTO transactions(user_id,type,amount,balance_before,balance_after,
            description,reference_id,payment_method,admin_actor) VALUES(?,?,?,?,?,?,?,?,?)""",
            (uid, tx_type, amount, bal, new_bal, desc, ref_id, method, actor))
        if tx_type == "purchase" and amount < 0:
            await db.execute("UPDATE users SET total_spent=total_spent+?,total_purchases=total_purchases+1 WHERE telegram_id=?",
                             (abs(amount), tid))
        if tx_type == "refund" and amount > 0:
            await db.execute("UPDATE users SET total_refunds=total_refunds+1 WHERE telegram_id=?", (tid,))
        await db.commit()
        return new_bal

# ── purchases ─────────────────────────────────────────────────────────────────
async def create_purchase(tid, order_id, service, svc_name, country, cnt_name, phone, cost, cost_d, pool=None):
    u = await get_user(tid)
    if not u: return None
    await _q("""INSERT INTO purchases(user_id,order_id,service,service_name,country,country_name,
        phone_number,cost,cost_display,pool) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (u["id"],order_id,service,svc_name,country,cnt_name,phone,cost,cost_d,pool), commit=True)
    return await get_purchase(order_id)

async def get_purchase(order_id):
    return await _q("SELECT * FROM purchases WHERE order_id=?", (order_id,), fetchone=True)

async def update_purchase(order_id, **kw):
    if not kw: return
    sets = ",".join(f"{k}=?" for k in kw)
    await _q(f"UPDATE purchases SET {sets} WHERE order_id=?", list(kw.values())+[order_id], commit=True)

async def get_user_purchases(tid, status=None, limit=20, offset=0):
    if status:
        return await _q("""SELECT p.* FROM purchases p JOIN users u ON p.user_id=u.id
            WHERE u.telegram_id=? AND p.status=? ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            (tid,status,limit,offset), fetchall=True)
    return await _q("""SELECT p.* FROM purchases p JOIN users u ON p.user_id=u.id
        WHERE u.telegram_id=? ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
        (tid,limit,offset), fetchall=True)

async def count_user_purchases(tid, status=None):
    if status:
        r = await _q("""SELECT COUNT(*) c FROM purchases p JOIN users u ON p.user_id=u.id
            WHERE u.telegram_id=? AND p.status=?""", (tid,status), fetchone=True)
    else:
        r = await _q("""SELECT COUNT(*) c FROM purchases p JOIN users u ON p.user_id=u.id
            WHERE u.telegram_id=?""", (tid,), fetchone=True)
    return r["c"] if r else 0

async def get_active_purchases_all():
    """All active purchases across all users (for background checker)."""
    return await _q("""SELECT p.*, u.telegram_id as tg_id, u.language as user_lang
        FROM purchases p JOIN users u ON p.user_id=u.id
        WHERE p.status='active' ORDER BY p.created_at ASC""", fetchall=True)

async def get_all_purchases(limit=50, offset=0):
    return await _q("""SELECT p.*, u.telegram_id, u.username, u.first_name
        FROM purchases p JOIN users u ON p.user_id=u.id
        ORDER BY p.created_at DESC LIMIT ? OFFSET ?""", (limit,offset), fetchall=True)

async def count_all_purchases(status=None):
    if status:
        r = await _q("SELECT COUNT(*) c FROM purchases WHERE status=?", (status,), fetchone=True)
    else:
        r = await _q("SELECT COUNT(*) c FROM purchases", fetchone=True)
    return r["c"] if r else 0

# ── transactions ──────────────────────────────────────────────────────────────
async def get_user_transactions(tid, limit=20, offset=0, tx_type=None):
    if tx_type:
        return await _q("""SELECT t.* FROM transactions t JOIN users u ON t.user_id=u.id
            WHERE u.telegram_id=? AND t.type=? ORDER BY t.created_at DESC LIMIT ? OFFSET ?""",
            (tid,tx_type,limit,offset), fetchall=True)
    return await _q("""SELECT t.* FROM transactions t JOIN users u ON t.user_id=u.id
        WHERE u.telegram_id=? ORDER BY t.created_at DESC LIMIT ? OFFSET ?""",
        (tid,limit,offset), fetchall=True)

async def get_all_transactions(limit=50, offset=0):
    return await _q("""SELECT t.*, u.telegram_id, u.username, u.first_name
        FROM transactions t JOIN users u ON t.user_id=u.id
        ORDER BY t.created_at DESC LIMIT ? OFFSET ?""", (limit,offset), fetchall=True)

# ── history (advanced) ───────────────────────────────────────────────────────

async def get_user_purchases_filtered(tid, status=None, search=None, limit=20, offset=0):
    """History with optional status filter and text search."""
    u = await get_user(tid)
    if not u: return []
    uid = u["id"]
    conditions = ["p.user_id=?"]
    params     = [uid]
    if status and status != "all":
        conditions.append("p.status=?"); params.append(status)
    if search:
        s = f"%{search}%"
        conditions.append("(p.phone_number LIKE ? OR p.service_name LIKE ? OR p.country_name LIKE ? OR p.order_id LIKE ?)")
        params += [s, s, s, s]
    where = " AND ".join(conditions)
    params += [limit, offset]
    return await _q(f"""SELECT * FROM purchases p WHERE {where}
        ORDER BY p.created_at DESC LIMIT ? OFFSET ?""", params, fetchall=True)

async def count_user_purchases_filtered(tid, status=None, search=None):
    u = await get_user(tid)
    if not u: return 0
    uid = u["id"]
    conditions = ["p.user_id=?"]
    params     = [uid]
    if status and status != "all":
        conditions.append("p.status=?"); params.append(status)
    if search:
        s = f"%{search}%"
        conditions.append("(p.phone_number LIKE ? OR p.service_name LIKE ? OR p.country_name LIKE ? OR p.order_id LIKE ?)")
        params += [s, s, s, s]
    where = " AND ".join(conditions)
    r = await _q(f"SELECT COUNT(*) c FROM purchases p WHERE {where}", params, fetchone=True)
    return r["c"] if r else 0

async def get_purchase_with_user(order_id):
    """Get purchase with joined user info."""
    return await _q("""SELECT p.*, u.telegram_id as tg_id, u.language as user_lang,
        u.first_name, u.username
        FROM purchases p JOIN users u ON p.user_id=u.id
        WHERE p.order_id=?""", (order_id,), fetchone=True)

async def cleanup_old_purchases(days: int, statuses=("cancelled","refunded")):
    """Delete purchases older than X days with given statuses."""
    status_ph = ",".join("?" * len(statuses))
    result = await _q(f"""DELETE FROM purchases
        WHERE status IN ({status_ph})
        AND created_at < datetime('now', '-{int(days)} days')""",
        list(statuses), commit=True)
    return result

async def cleanup_old_transactions(days: int):
    """Delete transactions older than X days (keeps deposit/refund/referral)."""
    await _q(f"""DELETE FROM transactions
        WHERE type='purchase'
        AND created_at < datetime('now', '-{int(days)} days')""", commit=True)

async def get_history_summary(tid):
    """Quick summary stats for history header."""
    u = await get_user(tid)
    if not u: return {}
    uid = u["id"]
    rows = await _q("""SELECT status, COUNT(*) cnt, COALESCE(SUM(cost_display),0) tot
        FROM purchases WHERE user_id=? GROUP BY status""", (uid,), fetchall=True)
    summary = {r["status"]: {"count": r["cnt"], "total": r["tot"]} for r in rows}
    total   = sum(v["count"] for v in summary.values())
    spent   = sum(v["total"] for v in summary.values() if v != summary.get("refunded",{}))
    return {"by_status": summary, "total": total, "spent": spent}

# ── referrals ────────────────────────────────────────────────────────────────
import hashlib as _hashlib

def get_referral_code(telegram_id: int) -> str:
    """Generate a deterministic short referral code from telegram_id."""
    h = _hashlib.md5(f"ref_{telegram_id}".encode()).hexdigest()[:8].upper()
    return h

async def get_user_by_referral_code(code: str):
    """Find user whose referral code matches."""
    # We iterate recent users — or store code in DB for scale
    # For simplicity: code = md5(ref_{tid})[:8].upper()
    # We need to check all users (acceptable for small/medium bots)
    users = await _q("SELECT * FROM users ORDER BY id ASC", fetchall=True)
    for u in users:
        if get_referral_code(u["telegram_id"]) == code.upper():
            return u
    return None

async def link_referral(referred_tid: int, referrer_tid: int) -> bool:
    """Link a new user to their referrer. Returns True if linked."""
    referrer = await get_user(referrer_tid)
    referred = await get_user(referred_tid)
    if not referrer or not referred:
        return False
    if referred.get("referred_by"):
        return False  # already has a referrer
    if referrer_tid == referred_tid:
        return False  # can't refer yourself
    # Update referred_by
    await update_user(referred_tid, referred_by=referrer["id"])
    # Insert into referrals table
    pct = float(await get_setting("referral_pct") or 5)
    await _q("""INSERT OR IGNORE INTO referrals(referrer_id,referred_id,commission_pct)
        VALUES(?,?,?)""", (referrer["id"], referred["id"], pct), commit=True)
    # Increment referral_count for referrer
    await _q("UPDATE users SET referral_count=referral_count+1 WHERE telegram_id=?",
             (referrer_tid,), commit=True)
    return True

async def process_referral_commission(purchase_id: int, referred_tid: int,
                                       purchase_amount: float, bot=None):
    """Called after a purchase. Credits referrer with commission.
    Optionally pass bot to send real-time notification."""
    referred = await get_user(referred_tid)
    if not referred or not referred.get("referred_by"):
        return None
    if await get_setting("referral_enabled") != "1":
        return None

    referrer = await get_user_by_id(referred["referred_by"])
    if not referrer:
        return None

    pct = float(await get_setting("referral_pct") or 5)
    commission = round(purchase_amount * pct / 100, 6)
    if commission <= 0:
        return None

    # Credit referrer
    desc_ar = f"عمولة إحالة: {referred.get('first_name','') or referred.get('username','')} ({pct}% من ${purchase_amount:.4f})"
    new_bal = await update_balance(
        referrer["telegram_id"], commission, "referral",
        desc_ar, ref_id=str(purchase_id), method="referral"
    )
    if new_bal is False:
        return None

    # Log earning
    await _q("""INSERT INTO referral_earnings
        (referrer_id,referred_id,purchase_id,commission_pct,commission_usd,purchase_amount)
        VALUES(?,?,?,?,?,?)""",
        (referrer["id"], referred["id"], purchase_id, pct, commission, purchase_amount),
        commit=True)

    # Notify referrer
    if bot and new_bal is not False:
        r_lang = referrer.get("language","ar")
        ref_name = referred.get("first_name","") or referred.get("username","") or "?"
        try:
            await bot.send_message(
                chat_id=referrer["telegram_id"],
                text=t(r_lang, "ref_commission_notify",
                       amount=commission,
                       name=ref_name,
                       balance=new_bal),
                parse_mode="HTML"
            )
        except Exception:
            pass

    return commission

async def get_user_referrals(tid: int, limit=20, offset=0):
    """All users referred by this user with their purchase stats."""
    u = await get_user(tid)
    if not u: return []
    return await _q("""
        SELECT r.*, u.first_name, u.username, u.telegram_id as ref_tg_id,
               u.total_purchases as ref_purchases, u.total_spent as ref_spent,
               (SELECT COALESCE(SUM(commission_usd),0) FROM referral_earnings re WHERE re.referred_id=r.referred_id) as total_earned
        FROM referrals r
        JOIN users u ON r.referred_id=u.id
        WHERE r.referrer_id=?
        ORDER BY r.created_at DESC LIMIT ? OFFSET ?
    """, (u["id"], limit, offset), fetchall=True)

async def count_user_referrals(tid: int) -> int:
    u = await get_user(tid)
    if not u: return 0
    r = await _q("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (u["id"],), fetchone=True)
    return r["c"] if r else 0

async def get_user_referral_stats(tid: int) -> dict:
    u = await get_user(tid)
    if not u: return {}
    uid = u["id"]
    total_refs = await _q("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,), fetchone=True)
    active_refs = await _q("""SELECT COUNT(DISTINCT r.referred_id) c FROM referrals r
        JOIN users u2 ON r.referred_id=u2.id WHERE r.referrer_id=? AND u2.total_purchases>0""", (uid,), fetchone=True)
    total_earned = await _q("SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE referrer_id=?", (uid,), fetchone=True)
    pending = await _q("""SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings re
        WHERE re.referrer_id=? AND re.created_at>=datetime('now','-30 days')""", (uid,), fetchone=True)
    top_refs = await _q("""SELECT u2.first_name, u2.username,
        SUM(re.commission_usd) earned, COUNT(re.id) purchases
        FROM referral_earnings re JOIN users u2 ON re.referred_id=u2.id
        WHERE re.referrer_id=? GROUP BY re.referred_id ORDER BY earned DESC LIMIT 5""", (uid,), fetchall=True)
    return {
        "total": total_refs["c"] if total_refs else 0,
        "active": active_refs["c"] if active_refs else 0,
        "total_earned": total_earned["c"] if total_earned else 0,
        "month_earned": pending["c"] if pending else 0,
        "top_refs": top_refs or [],
        "pct": float(await get_setting("referral_pct") or 5),
    }

async def get_global_referral_stats() -> dict:
    s = {}
    for k, sql in [
        ("total_referrals",  "SELECT COUNT(*) c FROM referrals"),
        ("active_referrals", "SELECT COUNT(DISTINCT referred_id) c FROM referral_earnings"),
        ("total_earned",     "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings"),
        ("today_earned",     "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE created_at>=datetime('now','-24 hours')"),
        ("week_earned",      "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE created_at>=datetime('now','-7 days')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0
    s["top_referrers"] = await _q("""SELECT u.first_name, u.username, u.telegram_id,
        COUNT(DISTINCT re.referred_id) refs, COALESCE(SUM(re.commission_usd),0) earned
        FROM referral_earnings re JOIN users u ON re.referrer_id=u.id
        GROUP BY re.referrer_id ORDER BY earned DESC LIMIT 10""", fetchall=True)
    s["pct"] = float(await get_setting("referral_pct") or 5)
    s["enabled"] = await get_setting("referral_enabled") == "1"
    return s

async def get_all_referral_earnings(limit=50, offset=0):
    return await _q("""
        SELECT re.*, ur.first_name as referrer_name, ur.username as referrer_uname,
               ud.first_name as referred_name, ud.username as referred_uname
        FROM referral_earnings re
        JOIN users ur ON re.referrer_id=ur.id
        JOIN users ud ON re.referred_id=ud.id
        ORDER BY re.created_at DESC LIMIT ? OFFSET ?
    """, (limit, offset), fetchall=True)

# ── stats ─────────────────────────────────────────────────────────────────────
# ── smspool key management ────────────────────────────────────────────────────
async def get_smspool_keys():
    return await _q("SELECT * FROM smspool_keys ORDER BY is_active DESC, added_at ASC", fetchall=True)

async def get_active_smspool_key() -> str:
    r = await _q("SELECT api_key FROM smspool_keys WHERE is_active=1 LIMIT 1", fetchone=True)
    if r: return r["api_key"]
    # Fallback to env
    return SMSPOOL_API_KEY

async def add_smspool_key(api_key: str, label: str = "") -> bool:
    try:
        await _q("INSERT OR IGNORE INTO smspool_keys(api_key,label) VALUES(?,?)",
                 (api_key, label), commit=True)
        return True
    except Exception: return False

async def delete_smspool_key(key_id: int):
    await _q("DELETE FROM smspool_keys WHERE id=?", (key_id,), commit=True)

async def set_active_smspool_key(key_id: int):
    await _q("UPDATE smspool_keys SET is_active=0", commit=True)
    await _q("UPDATE smspool_keys SET is_active=1 WHERE id=?", (key_id,), commit=True)
    # Reload the pool
    r = await _q("SELECT api_key FROM smspool_keys WHERE id=?", (key_id,), fetchone=True)
    if r:
        from smspool import SMSPool, pool as _pool
        _pool.key = r["api_key"]

async def get_smspool_key_by_id(key_id: int):
    return await _q("SELECT * FROM smspool_keys WHERE id=?", (key_id,), fetchone=True)


async def get_profit_stats() -> dict:
    """
    Full profit & sales analytics.
    Separates:
      - raw_cost     = what we paid SMSPool (cost column)
      - display_cost = what user paid us   (cost_display column)
      - gross_profit = display_cost - raw_cost
      - commission   = referral commissions paid out
      - net_profit   = gross_profit - commissions
    """
    s = {}

    # ── Sales volumes ─────────────────────────────────────────────────────────
    for k, sql in [
        ("total_sales",      "SELECT COUNT(*) c FROM purchases"),
        ("completed_sales",  "SELECT COUNT(*) c FROM purchases WHERE status='completed'"),
        ("active_sales",     "SELECT COUNT(*) c FROM purchases WHERE status='active'"),
        ("cancelled_sales",  "SELECT COUNT(*) c FROM purchases WHERE status='cancelled'"),
        ("refunded_sales",   "SELECT COUNT(*) c FROM purchases WHERE status='refunded'"),
        ("sales_today",      "SELECT COUNT(*) c FROM purchases WHERE created_at>=datetime('now','-24 hours')"),
        ("sales_week",       "SELECT COUNT(*) c FROM purchases WHERE created_at>=datetime('now','-7 days')"),
        ("sales_month",      "SELECT COUNT(*) c FROM purchases WHERE created_at>=datetime('now','-30 days')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0

    # ── Revenue (what users paid) ──────────────────────────────────────────────
    for k, sql in [
        ("revenue_total",    "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled')"),
        ("revenue_refunded", "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status='refunded'"),
        ("revenue_today",    "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-24 hours')"),
        ("revenue_week",     "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-7 days')"),
        ("revenue_month",    "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-30 days')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0.0

    # ── Capital cost (what we paid SMSPool) ────────────────────────────────────
    for k, sql in [
        ("cost_total",  "SELECT COALESCE(SUM(cost),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled')"),
        ("cost_today",  "SELECT COALESCE(SUM(cost),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-24 hours')"),
        ("cost_week",   "SELECT COALESCE(SUM(cost),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-7 days')"),
        ("cost_month",  "SELECT COALESCE(SUM(cost),0) c FROM purchases WHERE status NOT IN ('refunded','cancelled') AND created_at>=datetime('now','-30 days')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0.0

    # ── Commissions paid out ───────────────────────────────────────────────────
    for k, sql in [
        ("commission_total", "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings"),
        ("commission_today", "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE created_at>=datetime('now','-24 hours')"),
        ("commission_week",  "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE created_at>=datetime('now','-7 days')"),
        ("commission_month", "SELECT COALESCE(SUM(commission_usd),0) c FROM referral_earnings WHERE created_at>=datetime('now','-30 days')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0.0

    # ── Deposits (from payments) ───────────────────────────────────────────────
    for k, sql in [
        ("deposits_total", "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid'"),
        ("deposits_today", "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-24 hours')"),
        ("deposits_week",  "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-7 days')"),
        ("deposits_month", "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-30 days')"),
        ("deposits_pending","SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status IN ('Waiting','Confirming')"),
    ]:
        r = await _q(sql, fetchone=True)
        s[k] = r["c"] if r else 0.0

    # ── Computed profits ───────────────────────────────────────────────────────
    s["gross_profit_total"] = round(s["revenue_total"]  - s["cost_total"],  6)
    s["gross_profit_today"] = round(s["revenue_today"]  - s["cost_today"],  6)
    s["gross_profit_week"]  = round(s["revenue_week"]   - s["cost_week"],   6)
    s["gross_profit_month"] = round(s["revenue_month"]  - s["cost_month"],  6)

    s["net_profit_total"]   = round(s["gross_profit_total"] - s["commission_total"], 6)
    s["net_profit_today"]   = round(s["gross_profit_today"] - s["commission_today"], 6)
    s["net_profit_week"]    = round(s["gross_profit_week"]  - s["commission_week"],  6)
    s["net_profit_month"]   = round(s["gross_profit_month"] - s["commission_month"], 6)

    # Margins
    s["margin_total"] = round((s["gross_profit_total"] / s["revenue_total"] * 100), 2)                         if s["revenue_total"] > 0 else 0.0
    s["net_margin_total"] = round((s["net_profit_total"] / s["revenue_total"] * 100), 2)                         if s["revenue_total"] > 0 else 0.0

    # ── Best-selling services ──────────────────────────────────────────────────
    s["top_services_profit"] = await _q("""
        SELECT service_name,
               COUNT(*) sales,
               COALESCE(SUM(cost_display),0) revenue,
               COALESCE(SUM(cost),0) cost_raw,
               COALESCE(SUM(cost_display)-SUM(cost),0) profit
        FROM purchases WHERE status NOT IN ('refunded','cancelled')
        GROUP BY service_name ORDER BY profit DESC LIMIT 8
    """, fetchall=True)

    # ── Best-selling countries ─────────────────────────────────────────────────
    s["top_countries_profit"] = await _q("""
        SELECT country_name,
               COUNT(*) sales,
               COALESCE(SUM(cost_display),0) revenue,
               COALESCE(SUM(cost_display)-SUM(cost),0) profit
        FROM purchases WHERE status NOT IN ('refunded','cancelled')
        GROUP BY country_name ORDER BY profit DESC LIMIT 5
    """, fetchall=True)

    # ── Monthly trend ──────────────────────────────────────────────────────────
    s["monthly_trend"] = await _q("""
        SELECT strftime('%Y-%m', created_at) mo,
               COUNT(*) sales,
               COALESCE(SUM(cost_display),0) revenue,
               COALESCE(SUM(cost),0) cost_raw,
               COALESCE(SUM(cost_display)-SUM(cost),0) profit
        FROM purchases WHERE status NOT IN ('refunded','cancelled')
        GROUP BY mo ORDER BY mo DESC LIMIT 6
    """, fetchall=True)

    # Current markup
    try: s["current_markup"] = float(await get_setting("price_markup") or "0")
    except: s["current_markup"] = 0.0

    # User balances (liability)
    r = await _q("SELECT COALESCE(SUM(balance),0) c FROM users", fetchone=True)
    s["total_liabilities"] = r["c"] if r else 0.0

    return s


async def get_global_stats():
    s = {}
    for k, sql, p in [
        ("total_users",      "SELECT COUNT(*) c FROM users", ()),
        ("active_users",     "SELECT COUNT(*) c FROM users WHERE is_banned=0", ()),
        ("banned_users",     "SELECT COUNT(*) c FROM users WHERE is_banned=1", ()),
        ("total_purchases",  "SELECT COUNT(*) c FROM purchases", ()),
        ("active_numbers",   "SELECT COUNT(*) c FROM purchases WHERE status='active'", ()),
        ("completed",        "SELECT COUNT(*) c FROM purchases WHERE status='completed'", ()),
        ("cancelled",        "SELECT COUNT(*) c FROM purchases WHERE status='cancelled'", ()),
        ("refunded",         "SELECT COUNT(*) c FROM purchases WHERE status='refunded'", ()),
        ("total_revenue",    "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status!='refunded'", ()),
        ("total_refunded_amt","SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status='refunded'", ()),
        ("total_balances",   "SELECT COALESCE(SUM(balance),0) c FROM users", ()),
        ("purchases_24h",    "SELECT COUNT(*) c FROM purchases WHERE created_at>=datetime('now','-24 hours')", ()),
        ("new_users_24h",    "SELECT COUNT(*) c FROM users WHERE created_at>=datetime('now','-24 hours')", ()),
        ("purchases_7d",     "SELECT COUNT(*) c FROM purchases WHERE created_at>=datetime('now','-7 days')", ()),
        ("revenue_24h",      "SELECT COALESCE(SUM(cost_display),0) c FROM purchases WHERE status!='refunded' AND created_at>=datetime('now','-24 hours')", ()),
    ]:
        r = await _q(sql, p, fetchone=True)
        s[k] = r["c"] if r else 0

    s["top_services"] = await _q("""SELECT service_name,COUNT(*) n FROM purchases
        GROUP BY service_name ORDER BY n DESC LIMIT 5""", fetchall=True)
    s["top_countries"] = await _q("""SELECT country_name,COUNT(*) n FROM purchases
        GROUP BY country_name ORDER BY n DESC LIMIT 5""", fetchall=True)
    return s

async def get_user_detailed_stats(tid):
    u = await get_user(tid)
    if not u: return None
    uid = u["id"]
    by_s = {}
    rows = await _q("SELECT status,COUNT(*) cnt,COALESCE(SUM(cost_display),0) tot FROM purchases WHERE user_id=? GROUP BY status", (uid,), fetchall=True)
    for r in rows:
        by_s[r["status"]] = {"count": r["cnt"], "total": r["tot"]}
    svcs  = await _q("SELECT service_name,COUNT(*) n FROM purchases WHERE user_id=? GROUP BY service_name ORDER BY n DESC LIMIT 5", (uid,), fetchall=True)
    cnts  = await _q("SELECT country_name,COUNT(*) n FROM purchases WHERE user_id=? GROUP BY country_name ORDER BY n DESC LIMIT 5", (uid,), fetchall=True)
    txs   = await _q("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 10", (uid,), fetchall=True)
    mo    = await _q("SELECT strftime('%Y-%m',created_at) mo,COUNT(*) n,COALESCE(SUM(cost_display),0) tot FROM purchases WHERE user_id=? GROUP BY mo ORDER BY mo DESC LIMIT 6", (uid,), fetchall=True)
    return {"user": u, "by_status": by_s, "top_services": svcs, "top_countries": cnts, "recent_txs": txs, "monthly": mo}

# ── admin sessions ────────────────────────────────────────────────────────────
async def is_admin(tid):
    if tid in SUPER_ADMIN_IDS: return True
    r = await _q("SELECT 1 FROM admin_sessions WHERE telegram_id=?", (tid,), fetchone=True)
    return r is not None

async def add_admin_session(tid):
    await _q("INSERT OR REPLACE INTO admin_sessions(telegram_id,authenticated_at) VALUES(?,CURRENT_TIMESTAMP)", (tid,), commit=True)

async def remove_admin_session(tid):
    await _q("DELETE FROM admin_sessions WHERE telegram_id=?", (tid,), commit=True)

# ── payments (OxaPay) ────────────────────────────────────────────────────────
async def create_payment(tid, track_id, order_ref, amount_usd, pay_currency,
                          pay_amount, pay_address, network, pay_link,
                          fee_paid_by=0, underpaid_cover=2.5, lifetime_min=30, raw=""):
    u = await get_user(tid)
    if not u: return None
    from datetime import timedelta
    exp = (datetime.now() + timedelta(minutes=lifetime_min)).isoformat()
    await _q("""INSERT INTO payments(user_id,track_id,order_ref,amount_usd,pay_currency,
        pay_amount,pay_address,network,pay_link,fee_paid_by,underpaid_cover,lifetime_min,
        expired_at,raw_response) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (u["id"],track_id,order_ref,amount_usd,pay_currency,pay_amount,pay_address,
         network,pay_link,fee_paid_by,underpaid_cover,lifetime_min,exp,raw), commit=True)
    return await get_payment_by_track(track_id)

async def get_payment_by_track(track_id):
    return await _q("SELECT * FROM payments WHERE track_id=?", (track_id,), fetchone=True)

async def update_payment(track_id, **kw):
    if not kw: return
    sets = ",".join(f"{k}=?" for k in kw)
    await _q(f"UPDATE payments SET {sets} WHERE track_id=?", list(kw.values())+[track_id], commit=True)

async def get_user_payments(tid, limit=10, offset=0):
    u = await get_user(tid)
    if not u: return []
    return await _q("""SELECT * FROM payments WHERE user_id=?
        ORDER BY created_at DESC LIMIT ? OFFSET ?""", (u["id"],limit,offset), fetchall=True)

async def get_pending_payments():
    """All payments still pending polling (Waiting or Confirming)."""
    return await _q("""SELECT p.*, u.telegram_id as tg_id, u.language as user_lang
        FROM payments p JOIN users u ON p.user_id=u.id
        WHERE p.status IN ('Waiting','Confirming')
        ORDER BY p.created_at ASC""", fetchall=True)

async def get_all_payments(limit=50, offset=0, status=None):
    if status:
        return await _q("""SELECT p.*, u.telegram_id, u.username, u.first_name
            FROM payments p JOIN users u ON p.user_id=u.id
            WHERE p.status=? ORDER BY p.created_at DESC LIMIT ? OFFSET ?""",
            (status,limit,offset), fetchall=True)
    return await _q("""SELECT p.*, u.telegram_id, u.username, u.first_name
        FROM payments p JOIN users u ON p.user_id=u.id
        ORDER BY p.created_at DESC LIMIT ? OFFSET ?""", (limit,offset), fetchall=True)

async def get_payment_stats():
    s = {}
    for k, sql, p in [
        ("total_count",   "SELECT COUNT(*) c FROM payments", ()),
        ("paid_count",    "SELECT COUNT(*) c FROM payments WHERE status='Paid'", ()),
        ("pending_count", "SELECT COUNT(*) c FROM payments WHERE status IN ('Waiting','Confirming')", ()),
        ("expired_count", "SELECT COUNT(*) c FROM payments WHERE status IN ('Expired','Error','Canceled')", ()),
        ("total_usd",     "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid'", ()),
        ("today_count",   "SELECT COUNT(*) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-24 hours')", ()),
        ("today_usd",     "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-24 hours')", ()),
        ("week_usd",      "SELECT COALESCE(SUM(amount_usd),0) c FROM payments WHERE status='Paid' AND created_at>=datetime('now','-7 days')", ()),
    ]:
        r = await _q(sql, p, fetchone=True)
        s[k] = r["c"] if r else 0
    # by currency
    s["by_currency"] = await _q("""SELECT pay_currency, COUNT(*) n, COALESCE(SUM(amount_usd),0) total
        FROM payments WHERE status='Paid' GROUP BY pay_currency ORDER BY total DESC""", fetchall=True)
    # monthly
    s["monthly"] = await _q("""SELECT strftime('%Y-%m',created_at) mo,
        COUNT(*) n, COALESCE(SUM(amount_usd),0) tot
        FROM payments WHERE status='Paid'
        GROUP BY mo ORDER BY mo DESC LIMIT 6""", fetchall=True)
    return s

# ── payment methods ────────────────────────────────────────────────────────────
async def get_payment_methods(enabled_only=False):
    if enabled_only:
        return await _q("""SELECT * FROM payment_methods WHERE is_enabled=1
            ORDER BY sort_order ASC, id ASC""", fetchall=True)
    return await _q("SELECT * FROM payment_methods ORDER BY sort_order ASC, id ASC", fetchall=True)

async def get_payment_method(pm_id):
    return await _q("SELECT * FROM payment_methods WHERE id=?", (pm_id,), fetchone=True)

async def add_payment_method(coin, network="", label="", min_amount=1.0, max_amount=10000.0,
                              fee_paid_by=0, lifetime_min=30, underpaid_cover=2.5, note=""):
    return await _q("""INSERT INTO payment_methods
        (coin,network,label,min_amount,max_amount,is_enabled,fee_paid_by,lifetime_min,underpaid_cover,note)
        VALUES(?,?,?,?,?,1,?,?,?,?)""",
        (coin,network,label,min_amount,max_amount,fee_paid_by,lifetime_min,underpaid_cover,note),
        commit=True)

async def update_payment_method(pm_id, **kw):
    if not kw: return
    sets = ",".join(f"{k}=?" for k in kw)
    await _q(f"UPDATE payment_methods SET {sets} WHERE id=?", list(kw.values())+[pm_id], commit=True)

async def delete_payment_method(pm_id):
    await _q("DELETE FROM payment_methods WHERE id=?", (pm_id,), commit=True)

async def toggle_payment_method(pm_id):
    pm = await get_payment_method(pm_id)
    if pm:
        await update_payment_method(pm_id, is_enabled=0 if pm["is_enabled"] else 1)


# ════════════════════════════════════════════════════════════════════════════
# SECTION 3 ─ LANGUAGES
# ════════════════════════════════════════════════════════════════════════════
STRINGS = {
"ar": {
  "choose_lang": "🌐 اختر اللغة\nChoose Language",
  "lang_set":    "✅ تم تغيير اللغة إلى العربية",
  "error":       "❌ حدث خطأ، يرجى المحاولة مرة أخرى.",
  "banned":      "🚫 حسابك محظور. تواصل مع الدعم.",
  "maintenance": "🔧 البوت تحت الصيانة حالياً.\n{msg}",
  "back":        "🔙 رجوع",
  "close":       "✖️ إغلاق",
  "confirm":     "✅ تأكيد",
  "cancel":      "❌ إلغاء",
  "loading":     "⏳ جارٍ التحميل...",
  "prev":        "◀️ السابق",
  "next":        "▶️ التالي",
  "page":        "📄 {p}/{t}",
  "no_results":  "🔍 لا توجد نتائج",
  "refresh":     "🔄 تحديث",
  "yes":         "✅ نعم",
  "no":          "❌ لا",

  "welcome": "👋 أهلاً <b>{name}</b>!\n\n🤖 <b>بوت SMS</b> — شراء أرقام للتحقق\n\n💰 رصيدك: <b>${bal:.4f}</b>",
  "main_menu": "🏠 <b>القائمة الرئيسية</b>",

  "btn_buy":      "🛒 شراء رقم",
  "btn_active":   "📱 أرقامي",
  "btn_history":  "📋 السجل",
  "btn_balance":  "💰 رصيدي",
  "btn_stats":    "📊 إحصائياتي",
  "btn_profile":  "👤 ملفي",
  "btn_lang":     "🌐 اللغة",
  "btn_support":  "🆘 الدعم",
  "btn_referral": "🎁 نظام الإحالة",
  "btn_admin":    "⚙️ الإدارة",

  "ref_title": "🎁 <b>نظام الإحالة</b>",
  "ref_info": (
    "🎁 <b>نظام الإحالة</b>\n"
    "─────────────────\n"
    "شارك رابط الإحالة الخاص بك واكسب عمولة عن كل عملية شراء يجريها من تدعوه!\n\n"
    "💰 نسبة العمولة الحالية: <b>{pct}%</b> من كل عملية شراء\n\n"
    "🔗 رابط الإحالة الخاص بك:\n"
    "<code>{link}</code>\n\n"
    "📊 إجمالي من دعوتهم: <b>{total}</b>\n"
    "✅ منهم اشتروا: <b>{active}</b>\n"
    "💸 إجمالي ما كسبته: <b>${earned:.4f}</b>\n"
    "📅 هذا الشهر: <b>${month:.4f}</b>"
  ),
  "ref_list_title": "👥 <b>قائمة إحالاتي</b>",
  "ref_list_empty": "📭 لم تقم بأي إحالة حتى الآن.\n\nشارك رابطك لتبدأ الكسب!",
  "ref_row": (
    "👤 <b>{name}</b>\n"
    "🛒 مشتريات: <b>{purchases}</b> | 💸 أنفق: <b>${spent:.2f}</b>\n"
    "💰 كسبت منه: <b>${earned:.4f}</b> | 📅 {date}"
  ),
  "ref_earnings_title": "💰 <b>سجل عمولاتي</b>",
  "ref_earnings_empty": "📭 لا توجد عمولات بعد.",
  "ref_earning_row": "💰 +<b>${amount:.4f}</b> من {name} ({pct}%) | 📅 {date}",
  "ref_stats_title": "📊 <b>إحصائيات إحالاتك</b>",
  "btn_ref_list":     "👥 من دعوتهم",
  "btn_ref_earnings": "💰 عمولاتي",
  "btn_ref_stats":    "📊 إحصائيات",
  "btn_ref_share":    "🔗 مشاركة الرابط",
  "ref_new_user_notify": "🎉 انضم {name} عبر رابط إحالتك!",
  "ref_commission_notify": "💰 كسبت <b>${amount:.4f}</b> عمولة إحالة من شراء {name}!\nرصيدك: <b>${balance:.4f}</b>",
  "ref_welcomed": "👋 لقد انضممت عبر دعوة <b>{name}</b>!\nستحصل على أفضل الخدمات 🎁",

  "adm_ref_title":   "🎁 <b>إدارة نظام الإحالة</b>",
  "adm_ref_stats": (
    "🎁 <b>إحصائيات الإحالة</b>\n"
    "─────────────────\n"
    "👥 إجمالي الإحالات: <b>{total}</b>\n"
    "✅ إحالات نشطة (اشتروا): <b>{active}</b>\n\n"
    "💰 إجمالي العمولات المدفوعة: <b>${total_earned:.4f}</b>\n"
    "📅 اليوم: <b>${today:.4f}</b>\n"
    "📆 الأسبوع: <b>${week:.4f}</b>\n\n"
    "📈 النسبة الحالية: <b>{pct}%</b>\n"
    "✅ الحالة: {status}\n\n"
    "🏆 أفضل المُحيلين:\n{top}"
  ),
  "adm_ref_top_row":   "{rank}. <b>{name}</b> — {refs} إحالة — <b>${earned:.4f}</b>",
  "btn_adm_ref":       "🎁 نظام الإحالة",
  "btn_adm_ref_stats": "📊 إحصائيات الإحالة",
  "btn_adm_ref_list":  "📋 جميع الإحالات",
  "btn_adm_ref_toggle":"🔄 تفعيل/تعطيل",
  "btn_adm_ref_pct":   "📈 تغيير النسبة",
  "adm_ref_enter_pct": "📈 أدخل النسبة المئوية للعمولة (مثال: 5 يعني 5%):",
  "adm_ref_pct_saved": "✅ تم حفظ النسبة: <b>{pct}%</b>",
  "adm_ref_invalid_pct": "❌ أدخل رقماً بين 0 و50",
  "adm_ref_toggled":   "✅ تم تغيير حالة نظام الإحالة.",
  "adm_ref_all_title": "📋 <b>جميع الإحالات</b>",
  "adm_ref_all_row": (
    "👤 <b>{referrer}</b> → <b>{referred}</b>\n"
    "💰 +${earned:.4f} ({pct}%) | 📅 {date}"
  ),
  "adm_view_referrals": "👥 إحالاتي",
  "adm_usearch_prompt": "🔍 أدخل ID التيليغرام أو @username أو الاسم:",
  "adm_usearch_title":  "🔍 <b>نتائج البحث عن مستخدمين</b>",
  "adm_usearch_sort_prompt": "📊 اختر طريقة الترتيب:",
  "adm_usearch_sort_spent":  "💸 ترتيب حسب الإنفاق",
  "adm_usearch_sort_date":   "📅 ترتيب حسب التسجيل",
  "adm_usearch_sort_active": "🕐 ترتيب حسب النشاط",
  "adm_usearch_sort_bal":    "💰 ترتيب حسب الرصيد",
  "adm_user_full": (
    "👤 <b>ملف المستخدم</b>\n"
    "═══════════════════\n"
    "🆔 ID: <code>{tid}</code>\n"
    "👤 الاسم: <b>{name}</b>  {uname}\n"
    "─────────────────\n"
    "💰 الرصيد: <b>${bal:.4f}</b>\n"
    "💸 إجمالي الإنفاق: <b>${spent:.4f}</b>\n"
    "🛒 المشتريات: <b>{purchases}</b>  |  ✅ مكتملة: <b>{done}</b>\n"
    "💸 استردادات: <b>{refunds}</b>\n"
    "─────────────────\n"
    "🎁 إحالاته: <b>{refs}</b>  |  💰 عمولاته: <b>${ref_earned:.4f}</b>\n"
    "─────────────────\n"
    "📅 انضم: <b>{joined}</b>\n"
    "🕐 آخر نشاط: <b>{active}</b>\n"
    "🔴 محظور: {banned}\n"
    "📝 ملاحظة: {note}"
  ),
  "adm_top_by_spent":    "🏆 <b>الترتيب حسب الإنفاق</b>",
  "adm_top_by_balance":  "🏆 <b>الترتيب حسب الرصيد</b>",
  "adm_top_by_purchases":"🏆 <b>الترتيب حسب المشتريات</b>",
  "adm_top_by_refs":     "🏆 <b>الترتيب حسب الإحالات</b>",
  "adm_top_row_full":    "{rank}. <b>{name}</b>\n    💸 ${spent:.2f} | 🛒 {purchases} | 💰 ${bal:.2f} | 🎁 {refs}",
  "btn_adm_usearch":     "🔍 بحث متقدم",
  "btn_adm_top_sort":    "📊 ترتيب المستخدمين",
  "btn_adm_top_spent":   "💸 الأعلى إنفاقاً",
  "btn_adm_top_bal":     "💰 الأعلى رصيداً",
  "btn_adm_top_purchases":"🛒 الأكثر شراءً",
  "btn_adm_top_refs":    "🎁 الأكثر إحالات",
  "adm_user_refs_title": "👥 <b>إحالات {name}</b>",
  "adm_user_refs_empty": "📭 لا إحالات لهذا المستخدم.",
  "adm_user_ref_row": "👤 {name} | 🛒 {purchases} | 💰 ${earned:.4f} | {date}",

  "buy_select_country": "🌍 <b>اختر الدولة</b>",
  "buy_select_service": "📱 <b>اختر الخدمة</b> — {country}",
  "buy_confirm": (
    "✅ <b>تأكيد الشراء</b>\n\n"
    "🌍 الدولة: <b>{country}</b>\n"
    "📱 الخدمة: <b>{service}</b>\n"
    "💰 السعر: <b>${price:.4f}</b>\n"
    "💳 رصيدك: <b>${bal:.4f}</b>"
  ),
  "buy_insufficient": "❌ رصيد غير كافٍ\nرصيدك: <b>${bal:.4f}</b> | المطلوب: <b>${need:.4f}</b>",
  "buy_success": (
    "✅ <b>تم الشراء بنجاح!</b>\n\n"
    "📞 الرقم: <code>{num}</code>\n"
    "🌍 {country} | 📱 {service}\n"
    "💰 التكلفة: <b>${cost:.4f}</b>\n"
    "🆔 الطلب: <code>{oid}</code>\n\n"
    "⏳ جارٍ انتظار رمز التحقق... سيتم إشعارك تلقائياً"
  ),
  "buy_failed":        "❌ فشل الشراء: {reason}",
  "buy_no_countries":  "❌ لا تتوفر دول حالياً.",
  "buy_no_services":   "❌ لا تتوفر خدمات لهذه الدولة.",

  "active_title": "📱 <b>أرقامك النشطة</b> ({count})",
  "active_empty": "📭 لا أرقام نشطة.\n\nاضغط 🛒 <b>شراء رقم</b> للبدء!",
  "num_detail": (
    "📞 <b>تفاصيل الرقم</b>\n"
    "─────────────────\n"
    "📱 <code>{num}</code>\n"
    "🌍 {country} | 📲 {service}\n"
    "💰 ${cost:.4f} | {status}\n"
    "📅 {date}\n"
    "🆔 <code>{oid}</code>"
  ),
  "sms_waiting":   "⏳ لم يصل الرمز بعد...",
  "sms_received": (
    "🎉 <b>وصل رمز التحقق!</b>\n\n"
    "📞 <code>{num}</code>\n"
    "🔑 الرمز: <b><code>{code}</code></b>\n\n"
    "📩 الرسالة:\n<i>{full}</i>"
  ),
  "sms_auto_notify": (
    "🔔 <b>وصل رمز التحقق!</b>\n\n"
    "📞 <code>{num}</code> | 📲 {service}\n"
    "🔑 <b><code>{code}</code></b>\n\n"
    "📩 <i>{full}</i>"
  ),
  "btn_check":   "🔄 تحقق من الرسالة",
  "btn_cancel_num":   "❌ إلغاء الرقم",
  "btn_resend":      "📨 إعادة الإرسال",
  "btn_reuse_num":   "♻️ استخدام الرقم مجدداً",
  "reuse_title": "♻️ <b>استخدام الرقم مجدداً</b>",
  "reuse_desc": "طلب رمز تحقق جديد على نفس الرقم دون الحاجة لشراء رقم جديد.",
  "reuse_confirm": "⚠️ هل تريد طلب رمز تحقق جديد على الرقم\n<code>{num}</code>؟\n\n💰 الرصيد المطلوب: <b>${cost:.4f}</b>",
  "reuse_success": "✅ تم إعادة تفعيل الرقم <code>{num}</code>\n⏳ انتظر وصول الرمز الجديد...",
  "reuse_failed":  "❌ فشلت إعادة التفعيل: {reason}",
  "reuse_no_balance": "❌ رصيد غير كافٍ للإعادة (${need:.4f})",
  "cancel_ask":  "⚠️ تأكيد إلغاء الرقم <code>{num}</code>؟",
  "cancel_ok":   "✅ تم الإلغاء وسيُعاد الرصيد قريباً.",
  "cancel_fail": "❌ فشل الإلغاء: {reason}",
  "resend_ok":   "✅ تم طلب الإرسال مجدداً.",
  "resend_fail": "❌ فشل الإرسال: {reason}",
  "auto_cancel": "🕐 تم إلغاء الرقم <code>{num}</code> تلقائياً بعد {min} دقيقة واسترداد ${amount:.4f}",

  "status_active":    "🟢 نشط",
  "status_completed": "✅ مكتمل",
  "status_cancelled": "❌ ملغى",
  "status_refunded":  "💸 مسترد",
  "status_pending":   "⏳ انتظار",

  "history_title": "📋 <b>سجل المشتريات</b>",
  "history_empty": "📭 لا توجد مشتريات تطابق معايير البحث.",
  "history_header": (
    "📋 <b>سجل المشتريات</b>\n"
    "─────────────────\n"
    "🛒 الكل: <b>{total}</b>  ✅ مكتملة: <b>{done}</b>  ❌ ملغاة: <b>{cancel}</b>\n"
    "🔍 الفلتر: <b>{filter_name}</b>  |  الصفحة {page}/{pages}"
  ),
  "history_row_btn": "{icon} {svc} — 🌍{cnt} — ${cost:.4f} — {date}",
  "history_detail": (
    "📋 <b>تفاصيل الشراء</b>\n"
    "─────────────────\n"
    "📞 الرقم: <code>{num}</code>\n"
    "🌍 الدولة: <b>{country}</b>\n"
    "📱 الخدمة: <b>{service}</b>\n"
    "💰 التكلفة: <b>${cost:.4f}</b>\n"
    "📅 تاريخ الشراء: <b>{date}</b>\n"
    "🔄 الحالة: {status}\n"
    "🆔 رقم الطلب: <code>{oid}</code>"
  ),
  "history_detail_sms": "\n\n🔑 رمز التحقق: <b><code>{code}</code></b>\n📩 <i>{full}</i>",
  "history_filter_all":       "📋 الكل",
  "history_filter_completed": "✅ مكتملة",
  "history_filter_active":    "🟢 نشطة",
  "history_filter_cancelled": "❌ ملغاة",
  "history_filter_refunded":  "💸 مستردة",
  "btn_history_filter":  "🔽 فلترة",
  "btn_history_search":  "🔍 بحث",
  "btn_history_clear":   "🧹 مسح الفلتر",
  "btn_history_cleanup": "🗑️ تنظيف السجل",
  "history_search_prompt": "🔍 أدخل رقم الهاتف أو اسم الخدمة أو الدولة أو رقم الطلب:",
  "history_cleanup_ask":  "⚠️ ستُحذف جميع المشتريات الملغاة والمستردة الأقدم من {days} يوم.\nعدد السجلات: <b>{count}</b>\nهل تريد المتابعة؟",
  "history_cleanup_done": "✅ تم حذف <b>{count}</b> سجل قديم.",
  "history_cleanup_empty": "📭 لا توجد سجلات قديمة للحذف.",
  "history_row": "📞 <code>{num}</code> | {svc} | 🌍 {cnt}\n💰 ${cost:.4f} | {status} | {date}",

  "balance_title": (
    "💰 <b>رصيدك</b>\n"
    "─────────────────\n"
    "💵 الرصيد: <b>${bal:.4f}</b>\n"
    "💸 إجمالي الإنفاق: <b>${spent:.4f}</b>\n"
    "🛒 المشتريات: <b>{purchases}</b>"
  ),
  "btn_deposit":  "➕ إيداع رصيد",
  "btn_txs":      "📋 سجل المعاملات",
  "tx_title":     "📋 <b>سجل المعاملات</b>",
  "tx_row":       "{icon} <b>{name}</b>  {amount:+.4f}$\n📝 {desc} | 💳 ${after:.4f} | {date}",
  "tx_empty":     "📭 لا توجد معاملات.",
  "deposit_info": "💳 <b>الإيداع</b>\n\nاختر طريقة الدفع:",
  "btn_deposit_pay":    "💳 إيداع رصيد",
  "btn_pay_history":    "📋 سجل إيداعاتي",
  "pay_select_method":  "💳 <b>اختر عملة الدفع</b>\n\nاختر إحدى طرق الدفع المتاحة:",
  "pay_no_methods":     "❌ لا توجد طرق دفع متاحة حالياً.\nتواصل مع الإدارة.",
  "pay_enter_amount":   "💰 أدخل مبلغ الإيداع بالدولار الأمريكي:\n(الحد الأدنى: ${min:.2f} | الحد الأقصى: ${max:.2f})",
  "pay_amount_low":     "❌ المبلغ أقل من الحد الأدنى ${min:.2f}",
  "pay_amount_high":    "❌ المبلغ أعلى من الحد الأقصى ${max:.2f}",
  "pay_invalid_amount": "❌ مبلغ غير صالح. أدخل رقماً.",
  "pay_creating":       "⏳ جارٍ إنشاء الفاتورة...",
  "pay_invoice": (
    "📋 <b>تفاصيل الدفع</b>\n"
    "─────────────────\n"
    "💵 المبلغ بالدولار: <b>${usd:.2f}</b>\n"
    "🪙 العملة: <b>{coin} {network}</b>\n"
    "💰 المبلغ المطلوب: <b>{pay_amount} {coin}</b>\n"
    "📬 عنوان الإيداع:\n<code>{address}</code>\n\n"
    "⏰ ينتهي خلال: <b>{lifetime} دقيقة</b>\n"
    "🆔 رقم التتبع: <code>{track_id}</code>\n\n"
    "⚠️ أرسل المبلغ المحدد بالضبط إلى العنوان أعلاه"
  ),
  "pay_open_link":      "🔗 فتح صفحة الدفع",
  "pay_check_status":   "🔄 تحقق من الحالة",
  "pay_cancel_invoice": "❌ إلغاء",
  "pay_status_waiting": "⏳ في انتظار الدفع...",
  "pay_status_confirming":"🔄 جارٍ التأكيد...",
  "pay_status_paid":    "✅ تم الدفع!",
  "pay_status_expired": "❌ انتهت صلاحية الفاتورة",
  "pay_status_error":   "🔴 حدث خطأ",
  "pay_status_cancelled":"🚫 تم الإلغاء",
  "pay_confirmed_notify": (
    "🎉 <b>تم استلام دفعتك!</b>\n\n"
    "💵 <b>${usd:.2f}</b> أُضيفت لرصيدك\n"
    "🪙 {coin} — رقم التتبع: <code>{track_id}</code>\n"
    "💰 رصيدك الجديد: <b>${balance:.4f}</b>"
  ),
  "pay_history_title":  "📋 <b>سجل إيداعاتك</b>",
  "pay_history_empty":  "📭 لا توجد إيداعات سابقة.",
  "pay_history_row": (
    "{icon} <b>{coin}</b> — <b>${usd:.2f}</b>\n"
    "📅 {date} | {status}"
  ),
  "pay_cancelled_ok":   "✅ تم إلغاء الفاتورة.",
  "pay_error":          "❌ فشل إنشاء الفاتورة: {reason}",
  "pay_oxapay_off":     "❌ بوابة الدفع غير مفعّلة حالياً.",

  "stats_title": "📊 <b>إحصائياتك</b>",
  "stats_body": (
    "💰 الرصيد: <b>${bal:.4f}</b>\n"
    "💸 إجمالي الإنفاق: <b>${spent:.4f}</b>\n"
    "🛒 إجمالي المشتريات: <b>{total}</b>\n"
    "✅ مكتملة: <b>{done}</b> | ❌ ملغاة: <b>{cancel}</b> | 💸 مستردة: <b>{refund}</b>\n\n"
    "📱 الخدمات الأكثر استخداماً:\n{svcs}\n\n"
    "🌍 الدول الأكثر استخداماً:\n{cnts}\n\n"
    "📅 الأشهر الأخيرة:\n{months}"
  ),

  "profile_title": "👤 <b>ملفك الشخصي</b>",
  "profile_info": (
    "🆔 <code>{tid}</code>\n"
    "👤 <b>{name}</b>  {uname}\n"
    "💰 الرصيد: <b>${bal:.4f}</b>\n"
    "💸 إجمالي الإنفاق: <b>${spent:.4f}</b>\n"
    "🛒 المشتريات: <b>{purchases}</b>\n"
    "📅 انضم: {joined}\n"
    "🕐 آخر نشاط: {active}\n"
    "🌐 اللغة: {lang}"
  ),
  "btn_pr_info":    "👤 معلوماتي",
  "btn_pr_stats":   "📊 إحصائياتي",
  "btn_pr_history": "📋 سجلي",
  "btn_pr_balance": "💰 رصيدي",
  "btn_pr_lang":    "🌐 اللغة",

  "adm_enter_pw":   "🔐 أدخل كلمة المرور:",
  "adm_wrong_pw":   "❌ كلمة المرور خاطئة.",
  "adm_logged_in":  "✅ <b>تم الدخول كمسؤول!</b>",
  "adm_logged_out": "✅ تم تسجيل الخروج.",
  "adm_no_auth":    "🔐 يجب تسجيل الدخول أولاً. /admin",
  "adm_menu":       "⚙️ <b>لوحة الإدارة</b>",

  "btn_adm_stats":    "📊 الإحصائيات",
  "btn_adm_users":    "👥 المستخدمون",
  "btn_adm_search":   "🔍 بحث مستخدم",
  "btn_adm_txs":      "💳 المعاملات",
  "btn_adm_purchases":"🛒 المشتريات",
  "btn_adm_active":   "📱 الأرقام النشطة",
  "btn_adm_top":      "🏆 أفضل المستخدمين",
  "btn_adm_broadcast":"📢 بث رسالة",
  "btn_adm_settings": "⚙️ الإعدادات",
  "btn_adm_profits":  "📈 الأرباح والمبيعات",
  "btn_adm_smspool":  "🔑 مفاتيح SMSPool",

  "adm_smspool_title": "🔑 <b>إدارة مفاتيح SMSPool</b>",
  "adm_smspool_body": (
    "🔑 <b>إدارة مفاتيح SMSPool API</b>\n"
    "─────────────────\n"
    "المفتاح النشط الآن: <code>{active_preview}</code>\n"
    "عدد المفاتيح المحفوظة: <b>{count}</b>\n"
    "رصيد الحساب: <b>${balance:.4f}</b>"
  ),
  "adm_smspool_key_row":  "{status} <code>{preview}</code>  |  📝 {label}",
  "adm_smspool_enter_key": "🔑 أدخل مفتاح SMSPool API الجديد:",
  "adm_smspool_enter_label": "📝 أدخل اسم/وصف للمفتاح (مثال: رئيسي، احتياطي):",
  "adm_smspool_added":    "✅ تمت إضافة المفتاح.",
  "adm_smspool_deleted":  "✅ تم حذف المفتاح.",
  "adm_smspool_activated":"✅ تم تفعيل المفتاح كمفتاح نشط.",
  "adm_smspool_balance":  "💰 رصيد الحساب: <b>${balance:.4f}</b>",
  "adm_smspool_no_keys":  "📭 لا توجد مفاتيح محفوظة. أضف مفتاحاً.",
  "adm_smspool_invalid":  "❌ المفتاح غير صالح أو لم يتم التحقق منه.",
  "btn_adm_smspool_add":  "➕ إضافة مفتاح",
  "btn_adm_smspool_balance":"💰 فحص الرصيد",
  "btn_adm_payments":  "💳 المدفوعات",

  "adm_profit_title": "📈 <b>إحصائيات الأرباح والمبيعات</b>",
  "adm_profit_overview": (
    "📈 <b>نظرة عامة — الأرباح والمبيعات</b>\n"
    "═══════════════════════\n"
    "📊 نسبة الربح الحالية: <b>{markup}%</b>\n"
    "─────────────────\n"
    "🛒 إجمالي المبيعات: <b>{total_sales}</b>  |  اليوم: <b>{sales_today}</b>\n"
    "✅ مكتملة: <b>{completed}</b>  |  💸 مستردة: <b>{refunded}</b>\n"
    "─────────────────\n"
    "💵 <b>الإيرادات (ما دفعه العملاء)</b>\n"
    "الإجمالي: <b>${revenue_total:.4f}</b>\n"
    "اليوم: <b>${revenue_today:.4f}</b>  |  الأسبوع: <b>${revenue_week:.4f}</b>  |  الشهر: <b>${revenue_month:.4f}</b>\n"
    "─────────────────\n"
    "🏭 <b>التكاليف (رأس المال — ما دفعناه لـ SMSPool)</b>\n"
    "الإجمالي: <b>${cost_total:.4f}</b>\n"
    "اليوم: <b>${cost_today:.4f}</b>  |  الأسبوع: <b>${cost_week:.4f}</b>  |  الشهر: <b>${cost_month:.4f}</b>\n"
    "─────────────────\n"
    "📤 <b>العمولات المدفوعة (إحالة)</b>\n"
    "الإجمالي: <b>${commission_total:.4f}</b>  |  الشهر: <b>${commission_month:.4f}</b>\n"
    "─────────────────\n"
    "✨ <b>الربح الإجمالي (قبل العمولات)</b>\n"
    "الإجمالي: <b>${gross_total:.4f}</b>  |  اليوم: <b>${gross_today:.4f}</b>\n"
    "الأسبوع: <b>${gross_week:.4f}</b>  |  الشهر: <b>${gross_month:.4f}</b>\n"
    "هامش: <b>{margin:.2f}%</b>\n"
    "─────────────────\n"
    "💎 <b>صافي الربح (بعد العمولات)</b>\n"
    "الإجمالي: <b>${net_total:.4f}</b>  |  اليوم: <b>${net_today:.4f}</b>\n"
    "الأسبوع: <b>${net_week:.4f}</b>  |  الشهر: <b>${net_month:.4f}</b>\n"
    "صافي الهامش: <b>{net_margin:.2f}%</b>"
  ),
  "adm_profit_deposits": (
    "💳 <b>الإيداعات</b>\n"
    "─────────────────\n"
    "الإجمالي المُودَع: <b>${deposits_total:.4f}</b>\n"
    "اليوم: <b>${deposits_today:.4f}</b>  |  الأسبوع: <b>${deposits_week:.4f}</b>\n"
    "الشهر: <b>${deposits_month:.4f}</b>\n"
    "قيد الانتظار: <b>${deposits_pending:.4f}</b>\n"
    "─────────────────\n"
    "⚖️ أرصدة المستخدمين (التزامات): <b>${liabilities:.4f}</b>\n"
    "المستردة: <b>${refunded_amt:.4f}</b>"
  ),
  "adm_profit_services": (
    "📱 <b>أفضل الخدمات ربحاً</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_service_row":  "{rank}. <b>{name}</b>\n    🛒 {sales} مبيعة | 💵 ${revenue:.4f} | 🏭 ${cost:.4f} | ✨ ${profit:.4f}",
  "adm_profit_countries": (
    "🌍 <b>أفضل الدول ربحاً</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_country_row":  "{rank}. <b>{name}</b>  🛒 {sales} | ✨ ${profit:.4f}",
  "adm_profit_monthly": (
    "📅 <b>اتجاه الأشهر الأخيرة</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_month_row": "📅 <b>{mo}</b>: 🛒 {sales} | 💵 ${rev:.4f} | 🏭 ${cost:.4f} | ✨ ${profit:.4f}",
  "adm_profit_markup_test": (
    "🔢 <b>اختبار هامش الربح</b>\n"
    "─────────────────\n"
    "النسبة الحالية: <b>{markup}%</b>\n\n"
    "مثال على الأسعار:\n"
    "  $0.10 → <b>${p1:.4f}</b>\n"
    "  $0.50 → <b>${p2:.4f}</b>\n"
    "  $1.00 → <b>${p3:.4f}</b>\n"
    "  $2.00 → <b>${p4:.4f}</b>\n"
    "  $5.00 → <b>${p5:.4f}</b>"
  ),
  "btn_adm_profit_overview":  "📊 نظرة عامة",
  "btn_adm_profit_services":  "📱 الخدمات",
  "btn_adm_profit_countries": "🌍 الدول",
  "btn_adm_profit_monthly":   "📅 الشهري",
  "btn_adm_profit_deposits":  "💳 الإيداعات",
  "btn_adm_profit_markup":    "🔢 اختبار الهامش",
  "btn_adm_pay_methods":"🔧 طرق الدفع",
  "adm_pay_title":     "💳 <b>إدارة المدفوعات</b>",
  "adm_pay_stats": (
    "💳 <b>إحصائيات المدفوعات</b>\n"
    "─────────────────\n"
    "✅ مدفوعة: <b>{paid}</b> | ⏳ قيد الانتظار: <b>{pending}</b>\n"
    "❌ منتهية: <b>{expired}</b>\n\n"
    "💵 إجمالي: <b>${total:.2f}</b>\n"
    "📅 اليوم: <b>${today:.2f}</b> ({today_c})\n"
    "📆 الأسبوع: <b>${week:.2f}</b>\n\n"
    "🪙 حسب العملة:\n{by_coin}\n\n"
    "📊 الأشهر الأخيرة:\n{monthly}"
  ),
  "adm_pm_list":       "🔧 <b>طرق الدفع المتاحة</b>",
  "adm_pm_empty":      "📭 لا توجد طرق دفع. أضف طريقة جديدة.",
  "adm_pm_row":        "{status} <b>{coin}</b> {network} | حد: ${min:.1f}-${max:.1f}",
  "btn_adm_pm_add":    "➕ إضافة طريقة دفع",
  "adm_pm_select_coin":"🪙 اختر العملة من قائمة OxaPay:",
  "adm_pm_no_coins":   "❌ لا يمكن جلب العملات. تحقق من مفتاح OxaPay.",
  "adm_pm_enter_min":  "💰 أدخل الحد الأدنى للإيداع بالدولار:",
  "adm_pm_enter_max":  "💰 أدخل الحد الأقصى للإيداع بالدولار:",
  "adm_pm_enter_label":"📝 أدخل اسم العرض للعملة (أو اضغط تخطي):",
  "adm_pm_enter_note": "📝 أدخل ملاحظة (أو اضغط تخطي):",
  "adm_pm_skip":       "تخطي ←",
  "adm_pm_added":      "✅ تمت إضافة طريقة الدفع: <b>{coin}</b>",
  "adm_pm_deleted":    "✅ تم حذف طريقة الدفع.",
  "adm_pm_toggled":    "✅ تم تغيير الحالة.",
  "adm_pm_detail": (
    "🔧 <b>تفاصيل طريقة الدفع</b>\n"
    "─────────────────\n"
    "🪙 العملة: <b>{coin}</b>\n"
    "🌐 الشبكة: <b>{network}</b>\n"
    "🏷️ الاسم: <b>{label}</b>\n"
    "💰 الحدود: <b>${min:.2f} — ${max:.2f}</b>\n"
    "👤 الرسوم على: <b>{fee_payer}</b>\n"
    "⏰ مدة الفاتورة: <b>{lifetime} دقيقة</b>\n"
    "📉 تسامح القصور: <b>{underpaid}%</b>\n"
    "📝 ملاحظة: {note}\n"
    "الحالة: {status}"
  ),
  "btn_adm_pm_toggle": "🔄 تفعيل/تعطيل",
  "btn_adm_pm_delete": "🗑️ حذف",
  "btn_adm_pm_edit":   "✏️ تعديل",
  "adm_pay_list_title":"💳 <b>سجل المدفوعات</b>",
  "adm_pay_row": (
    "{icon} <b>{user}</b> — {coin} — <b>${usd:.2f}</b>\n"
    "📅 {date} | {status}"
  ),
  "adm_oxapay_settings":"⚙️ <b>إعدادات OxaPay</b>",
  "adm_oxapay_body": (
    "🔑 المفتاح: <code>{key_preview}</code>\n"
    "✅ الحالة: {enabled}\n"
    "⏰ مدة الفاتورة: {lifetime} دقيقة\n"
    "👤 الرسوم على: {fee_payer}\n"
    "📉 تسامح القصور: {underpaid}%"
  ),
  "btn_adm_oxapay_key": "🔑 تغيير المفتاح",
  "btn_adm_oxapay_toggle":"🔄 تفعيل/تعطيل",
  "btn_adm_oxapay_lifetime":"⏰ مدة الفاتورة",
  "btn_adm_oxapay_fee": "👤 من يدفع الرسوم؟",
  "btn_adm_oxapay_underpaid":"📉 تسامح القصور",
  "fee_payer_merchant": "التاجر (المتجر)",
  "fee_payer_customer": "العميل",
  "btn_adm_msg_user": "📨 راسل مستخدماً",
  "btn_adm_logout":   "🚪 خروج",

  "adm_stats_title": "📊 <b>الإحصائيات العامة</b>",
  "adm_stats": (
    "👥 <b>المستخدمون</b>\n"
    "الكل: <b>{total}</b> | نشطون: <b>{active}</b> | محظورون: <b>{banned}</b> | جدد اليوم: <b>{new24}</b>\n\n"
    "🛒 <b>المشتريات</b>\n"
    "الكل: <b>{tot_p}</b> | نشطة: <b>{act_n}</b> | مكتملة: <b>{done}</b>\n"
    "ملغاة: <b>{cancel}</b> | مستردة: <b>{refund}</b>\n"
    "اليوم: <b>{p24}</b> | الأسبوع: <b>{p7}</b>\n\n"
    "💰 <b>الأموال</b>\n"
    "الإيرادات الكلية: <b>${rev:.4f}</b>\n"
    "إيرادات اليوم: <b>${rev24:.4f}</b>\n"
    "المستردة: <b>${refamt:.4f}</b>\n"
    "أرصدة المستخدمين: <b>${bals:.4f}</b>\n\n"
    "📱 أكثر الخدمات:\n{svcs}\n\n"
    "🌍 أكثر الدول:\n{cnts}"
  ),

  "adm_user_profile": (
    "👤 <b>ملف المستخدم</b>\n"
    "─────────────────\n"
    "🆔 <code>{tid}</code>\n"
    "👤 <b>{name}</b>  {uname}\n"
    "💰 الرصيد: <b>${bal:.4f}</b>\n"
    "💸 إجمالي الإنفاق: <b>${spent:.4f}</b>\n"
    "🛒 المشتريات: <b>{purchases}</b> | 💸 استردادات: <b>{refunds}</b>\n"
    "📅 انضم: {joined}\n"
    "🕐 آخر نشاط: {active}\n"
    "🔴 محظور: {banned}\n"
    "📝 ملاحظة: {note}"
  ),
  "btn_u_add":    "➕ إضافة رصيد",
  "btn_u_rm":     "➖ خصم رصيد",
  "btn_u_set":    "💳 تحديد رصيد",
  "btn_u_p":      "🛒 مشتريات",
  "btn_u_t":      "💳 معاملات",
  "btn_u_s":      "📊 إحصائيات",
  "btn_u_ban":    "🚫 حظر",
  "btn_u_unban":  "✅ رفع الحظر",
  "btn_u_note":   "📝 إضافة ملاحظة",
  "btn_u_msg":    "📨 إرسال رسالة",
  "btn_u_delete": "🗑️ حذف المستخدم",

  "adm_enter_amount":  "💰 أدخل المبلغ بالدولار (مثال: 5.00):",
  "adm_enter_reason":  "📝 أدخل السبب:",
  "adm_enter_note":    "📝 أدخل الملاحظة للمستخدم:",
  "adm_enter_msg":     "📨 أدخل الرسالة التي ستُرسل للمستخدم:",
  "adm_invalid_amount":"❌ مبلغ غير صالح.",
  "adm_bal_added":     "✅ تمت إضافة <b>${amount:.4f}</b>\nالرصيد الجديد: <b>${new:.4f}</b>",
  "adm_bal_removed":   "✅ تم خصم <b>${amount:.4f}</b>\nالرصيد الجديد: <b>${new:.4f}</b>",
  "adm_bal_set":       "✅ تم تحديد الرصيد إلى <b>${new:.4f}</b>",
  "adm_bal_err":       "❌ لا يمكن إجراء العملية.",
  "adm_ban_ok":        "✅ تم حظر {user}",
  "adm_unban_ok":      "✅ تم رفع الحظر عن {user}",
  "adm_note_ok":       "✅ تمت إضافة الملاحظة.",
  "adm_msg_ok":        "✅ تم إرسال الرسالة للمستخدم.",
  "adm_msg_fail":      "❌ فشل الإرسال (محظور؟).",
  "adm_delete_ask":    "⚠️ هل أنت متأكد من حذف بيانات المستخدم <b>{user}</b>؟\nلا يمكن التراجع!",
  "adm_delete_ok":     "✅ تم حذف بيانات المستخدم.",
  "adm_not_found":     "❌ لم يتم العثور على المستخدم.",
  "adm_search_prompt": "🔍 أدخل الاسم أو المعرف أو ID:",

  "adm_broadcast_prompt":   "📢 أدخل الرسالة التي ستُبث:",
  "adm_broadcast_type_menu": (
    "📢 <b>نظام البث المتقدم</b>\n"
    "─────────────────\n"
    "اختر نوع البث:"
  ),
  "btn_bc_all":       "📢 بث عام (كل المستخدمين)",
  "btn_bc_active":    "✅ بث للنشطين فقط (اشتروا)",
  "btn_bc_deposited": "💰 بث للمودعين فقط",
  "btn_bc_specific":  "👤 إرسال لمستخدم محدد",
  "adm_bc_specific_prompt": "👤 أدخل ID المستخدم أو @username:",
  "adm_bc_specific_msg_prompt": "📨 أدخل الرسالة للإرسال لـ {name}:",
  "adm_bc_sent_specific": "✅ تم إرسال الرسالة إلى {name}.",
  "adm_bc_html_tip":  "💡 يمكن استخدام HTML: <b>غامق</b> <i>مائل</i> <code>كود</code>",
  "adm_bc_preview":   "👁 معاينة الرسالة:\n─────────────────\n{msg}\n─────────────────",
  "btn_bc_confirm_send":  "✅ إرسال",
  "btn_bc_edit":          "✏️ تعديل",
  "adm_broadcast_prompt":  "📢 أدخل الرسالة التي ستُبث لجميع المستخدمين:",
  "adm_broadcast_confirm": "⚠️ ستُرسل لـ <b>{count}</b> مستخدم. تأكيد؟",
  "adm_broadcast_done":    "✅ أُرسلت لـ <b>{ok}</b> مستخدم (فشل: {fail})",

  "adm_settings_title": "⚙️ <b>إعدادات البوت</b>",
  "adm_settings": (
    "🟢 الحالة: {status}\n"
    "💰 الحد الأدنى للإيداع: <b>${min_dep}</b>\n"
    "📈 نسبة الربح: <b>{markup}%</b>\n"
    "🆘 رابط الدعم: {support}\n"
    "🕐 إلغاء تلقائي بعد: <b>{auto_cancel}</b> دقيقة"
  ),
  "btn_toggle_bot":    "🔄 تفعيل/تعطيل البوت",
  "btn_set_markup":    "📈 تغيير نسبة الربح",
  "btn_set_min_dep":   "💰 تغيير الحد الأدنى",
  "btn_set_support":   "🆘 رابط الدعم",
  "btn_set_welcome":   "👋 رسالة الترحيب",
  "btn_set_auto_cancel":"🕐 مدة الإلغاء التلقائي",
  "adm_enter_setting": "أدخل القيمة الجديدة:",
  "adm_setting_saved": "✅ تم الحفظ.",

  "adm_active_nums": "📱 <b>الأرقام النشطة ({count})</b>",
  "adm_active_row":  "👤 {user} | 📞 <code>{num}</code>\n📲 {svc} | 🌍 {cnt} | ⏱️ {mins} دقيقة",
  "adm_top_title":   "🏆 <b>أفضل المستخدمين إنفاقاً</b>",
  "adm_top_row":     "{rank}. <b>{name}</b> — ${spent:.4f} | {purchases} شراء",

  "msg_options_set":    "✅ تم تحديد الرسالة. استخدم الآن:\n/msg_delete | /msg_edit | /msg_pin | /msg_unpin",
  "msg_options_cleared": "✅ تم إلغاء /msg_options",
  "msg_options_usage":   "⚠️ يجب الرد على رسالة عند استخدام /msg_options",
  "msg_delete_ok":       "✅ تم حذف الرسالة.",
  "msg_delete_fail":     "❌ فشل حذف الرسالة: {reason}",
  "msg_edit_prompt":     "✏️ أدخل النص الجديد للرسالة:",
  "msg_edit_ok":         "✅ تم تعديل الرسالة.",
  "msg_edit_fail":       "❌ فشل التعديل: {reason}",
  "msg_pin_ok":          "✅ تم تثبيت الرسالة.",
  "msg_pin_fail":        "❌ فشل التثبيت: {reason}",
  "msg_unpin_ok":        "✅ تم إلغاء تثبيت الرسالة.",
  "msg_unpin_fail":      "❌ فشل إلغاء التثبيت: {reason}",
  "msg_no_options":      "⚠️ يجب استخدام /msg_options أولاً على الرسالة المراد إدارتها.",
  "msg_user_not_found":  "❌ المستخدم غير موجود.",
  "msg_options_for_user":"✅ تم التحديد للمستخدم {name}. استخدم /msg_delete أو /msg_edit",
  "notify_add":    "💰 أُضيف <b>${amount:.4f}</b> لرصيدك\n📝 {reason}\nرصيدك: <b>${bal:.4f}</b>",
  "notify_rm":     "💸 خُصم <b>${amount:.4f}</b> من رصيدك\n📝 {reason}\nرصيدك: <b>${bal:.4f}</b>",
  "notify_banned": "🚫 تم حظر حسابك.",
  "notify_unbanned":"✅ تم رفع الحظر عن حسابك.",
  "notify_msg":    "📨 رسالة من الإدارة:\n\n{msg}",

  "inline_search_title": "🔍 ابحث عن خدمة أو دولة",
  "inline_no_key":       "أدخل اسم الخدمة أو الدولة للبحث",
},
"en": {
  "choose_lang": "🌐 اختر اللغة\nChoose Language",
  "lang_set":    "✅ Language set to English",
  "error":       "❌ An error occurred. Please try again.",
  "banned":      "🚫 Your account is banned. Contact support.",
  "maintenance": "🔧 Bot under maintenance.\n{msg}",
  "back":        "🔙 Back",
  "close":       "✖️ Close",
  "confirm":     "✅ Confirm",
  "cancel":      "❌ Cancel",
  "loading":     "⏳ Loading...",
  "prev":        "◀️ Previous",
  "next":        "▶️ Next",
  "page":        "📄 {p}/{t}",
  "no_results":  "🔍 No results",
  "refresh":     "🔄 Refresh",
  "yes":         "✅ Yes",
  "no":          "❌ No",

  "welcome": "👋 Hello <b>{name}</b>!\n\n🤖 <b>SMS Bot</b> — Buy numbers for verification\n\n💰 Balance: <b>${bal:.4f}</b>",
  "main_menu": "🏠 <b>Main Menu</b>",

  "btn_buy":      "🛒 Buy Number",
  "btn_active":   "📱 My Numbers",
  "btn_history":  "📋 History",
  "btn_balance":  "💰 Balance",
  "btn_stats":    "📊 Statistics",
  "btn_profile":  "👤 Profile",
  "btn_lang":     "🌐 Language",
  "btn_support":  "🆘 Support",
  "btn_referral": "🎁 Referral",
  "btn_admin":    "⚙️ Admin",

  "ref_title": "🎁 <b>Referral System</b>",
  "ref_info": (
    "🎁 <b>Referral System</b>\n"
    "─────────────────\n"
    "Share your referral link and earn commission on every purchase your referrals make!\n\n"
    "💰 Current commission rate: <b>{pct}%</b> per purchase\n\n"
    "🔗 Your referral link:\n"
    "<code>{link}</code>\n\n"
    "📊 Total referred: <b>{total}</b>\n"
    "✅ Active buyers: <b>{active}</b>\n"
    "💸 Total earned: <b>${earned:.4f}</b>\n"
    "📅 This month: <b>${month:.4f}</b>"
  ),
  "ref_list_title": "👥 <b>My Referrals</b>",
  "ref_list_empty": "📭 No referrals yet.\n\nShare your link to start earning!",
  "ref_row": (
    "👤 <b>{name}</b>\n"
    "🛒 Purchases: <b>{purchases}</b> | 💸 Spent: <b>${spent:.2f}</b>\n"
    "💰 Earned from them: <b>${earned:.4f}</b> | 📅 {date}"
  ),
  "ref_earnings_title": "💰 <b>My Commissions</b>",
  "ref_earnings_empty": "📭 No commissions yet.",
  "ref_earning_row": "💰 +<b>${amount:.4f}</b> from {name} ({pct}%) | 📅 {date}",
  "ref_stats_title": "📊 <b>Referral Statistics</b>",
  "btn_ref_list":     "👥 My Referrals",
  "btn_ref_earnings": "💰 My Commissions",
  "btn_ref_stats":    "📊 Statistics",
  "btn_ref_share":    "🔗 Share Link",
  "ref_new_user_notify": "🎉 {name} joined via your referral link!",
  "ref_commission_notify": "💰 You earned <b>${amount:.4f}</b> commission from {name}'s purchase!\nBalance: <b>${balance:.4f}</b>",
  "ref_welcomed": "👋 You joined via <b>{name}</b>'s invitation!\nEnjoy the best services 🎁",

  "adm_ref_title":   "🎁 <b>Referral Management</b>",
  "adm_ref_stats": (
    "🎁 <b>Referral Statistics</b>\n"
    "─────────────────\n"
    "👥 Total Referrals: <b>{total}</b>\n"
    "✅ Active (purchased): <b>{active}</b>\n\n"
    "💰 Total Commissions Paid: <b>${total_earned:.4f}</b>\n"
    "📅 Today: <b>${today:.4f}</b>\n"
    "📆 Week: <b>${week:.4f}</b>\n\n"
    "📈 Current Rate: <b>{pct}%</b>\n"
    "✅ Status: {status}\n\n"
    "🏆 Top Referrers:\n{top}"
  ),
  "adm_ref_top_row":   "{rank}. <b>{name}</b> — {refs} referrals — <b>${earned:.4f}</b>",
  "btn_adm_ref":       "🎁 Referral System",
  "btn_adm_ref_stats": "📊 Referral Stats",
  "btn_adm_ref_list":  "📋 All Referrals",
  "btn_adm_ref_toggle":"🔄 Toggle Active",
  "btn_adm_ref_pct":   "📈 Change Rate",
  "adm_ref_enter_pct": "📈 Enter commission percentage (e.g. 5 means 5%):",
  "adm_ref_pct_saved": "✅ Rate saved: <b>{pct}%</b>",
  "adm_ref_invalid_pct": "❌ Enter a number between 0 and 50",
  "adm_ref_toggled":   "✅ Referral system status changed.",
  "adm_ref_all_title": "📋 <b>All Referrals</b>",
  "adm_ref_all_row": (
    "👤 <b>{referrer}</b> → <b>{referred}</b>\n"
    "💰 +${earned:.4f} ({pct}%) | 📅 {date}"
  ),
  "adm_view_referrals": "👥 Referrals",
  "adm_usearch_prompt": "🔍 Enter Telegram ID, @username or name:",
  "adm_usearch_title":  "🔍 <b>User Search Results</b>",
  "adm_usearch_sort_prompt": "📊 Choose sort order:",
  "adm_usearch_sort_spent":  "💸 Sort by Spending",
  "adm_usearch_sort_date":   "📅 Sort by Join Date",
  "adm_usearch_sort_active": "🕐 Sort by Activity",
  "adm_usearch_sort_bal":    "💰 Sort by Balance",
  "adm_user_full": (
    "👤 <b>User Profile</b>\n"
    "═══════════════════\n"
    "🆔 ID: <code>{tid}</code>\n"
    "👤 Name: <b>{name}</b>  {uname}\n"
    "─────────────────\n"
    "💰 Balance: <b>${bal:.4f}</b>\n"
    "💸 Total Spent: <b>${spent:.4f}</b>\n"
    "🛒 Purchases: <b>{purchases}</b>  |  ✅ Done: <b>{done}</b>\n"
    "💸 Refunds: <b>{refunds}</b>\n"
    "─────────────────\n"
    "🎁 Referrals: <b>{refs}</b>  |  💰 Earned: <b>${ref_earned:.4f}</b>\n"
    "─────────────────\n"
    "📅 Joined: <b>{joined}</b>\n"
    "🕐 Last Active: <b>{active}</b>\n"
    "🔴 Banned: {banned}\n"
    "📝 Note: {note}"
  ),
  "adm_top_by_spent":    "🏆 <b>Ranked by Spending</b>",
  "adm_top_by_balance":  "🏆 <b>Ranked by Balance</b>",
  "adm_top_by_purchases":"🏆 <b>Ranked by Purchases</b>",
  "adm_top_by_refs":     "🏆 <b>Ranked by Referrals</b>",
  "adm_top_row_full":    "{rank}. <b>{name}</b>\n    💸 ${spent:.2f} | 🛒 {purchases} | 💰 ${bal:.2f} | 🎁 {refs}",
  "btn_adm_usearch":     "🔍 Advanced Search",
  "btn_adm_top_sort":    "📊 Rank Users",
  "btn_adm_top_spent":   "💸 Top Spenders",
  "btn_adm_top_bal":     "💰 Highest Balance",
  "btn_adm_top_purchases":"🛒 Most Purchases",
  "btn_adm_top_refs":    "🎁 Most Referrals",
  "adm_user_refs_title": "👥 <b>Referrals of {name}</b>",
  "adm_user_refs_empty": "📭 No referrals for this user.",
  "adm_user_ref_row": "👤 {name} | 🛒 {purchases} | 💰 ${earned:.4f} | {date}",

  "buy_select_country": "🌍 <b>Select Country</b>",
  "buy_select_service": "📱 <b>Select Service</b> — {country}",
  "buy_confirm": (
    "✅ <b>Confirm Purchase</b>\n\n"
    "🌍 Country: <b>{country}</b>\n"
    "📱 Service: <b>{service}</b>\n"
    "💰 Price: <b>${price:.4f}</b>\n"
    "💳 Balance: <b>${bal:.4f}</b>"
  ),
  "buy_insufficient": "❌ Insufficient balance\nYour: <b>${bal:.4f}</b> | Need: <b>${need:.4f}</b>",
  "buy_success": (
    "✅ <b>Purchase Successful!</b>\n\n"
    "📞 Number: <code>{num}</code>\n"
    "🌍 {country} | 📱 {service}\n"
    "💰 Cost: <b>${cost:.4f}</b>\n"
    "🆔 Order: <code>{oid}</code>\n\n"
    "⏳ Waiting for SMS code... You'll be notified automatically"
  ),
  "buy_failed":        "❌ Purchase failed: {reason}",
  "buy_no_countries":  "❌ No countries available.",
  "buy_no_services":   "❌ No services for this country.",

  "active_title": "📱 <b>Your Active Numbers</b> ({count})",
  "active_empty": "📭 No active numbers.\n\nPress 🛒 <b>Buy Number</b>!",
  "num_detail": (
    "📞 <b>Number Details</b>\n"
    "─────────────────\n"
    "📱 <code>{num}</code>\n"
    "🌍 {country} | 📲 {service}\n"
    "💰 ${cost:.4f} | {status}\n"
    "📅 {date}\n"
    "🆔 <code>{oid}</code>"
  ),
  "sms_waiting":   "⏳ No SMS yet...",
  "sms_received": (
    "🎉 <b>SMS Code Received!</b>\n\n"
    "📞 <code>{num}</code>\n"
    "🔑 Code: <b><code>{code}</code></b>\n\n"
    "📩 Full message:\n<i>{full}</i>"
  ),
  "sms_auto_notify": (
    "🔔 <b>SMS Code Received!</b>\n\n"
    "📞 <code>{num}</code> | 📲 {service}\n"
    "🔑 <b><code>{code}</code></b>\n\n"
    "📩 <i>{full}</i>"
  ),
  "btn_check":   "🔄 Check SMS",
  "btn_cancel_num":   "❌ Cancel Number",
  "btn_resend":      "📨 Resend SMS",
  "btn_reuse_num":   "♻️ Reuse Number",
  "reuse_title": "♻️ <b>Reuse Number</b>",
  "reuse_desc": "Request a new verification code on the same number without buying a new one.",
  "reuse_confirm": "⚠️ Request new code on\n<code>{num}</code>?\n\n💰 Cost: <b>${cost:.4f}</b>",
  "reuse_success": "✅ Number <code>{num}</code> reactivated\n⏳ Waiting for new code...",
  "reuse_failed":  "❌ Reactivation failed: {reason}",
  "reuse_no_balance": "❌ Insufficient balance (${need:.4f})",
  "cancel_ask":  "⚠️ Cancel number <code>{num}</code>?",
  "cancel_ok":   "✅ Cancelled. Refund will be processed.",
  "cancel_fail": "❌ Cancel failed: {reason}",
  "resend_ok":   "✅ Resend requested.",
  "resend_fail": "❌ Resend failed: {reason}",
  "auto_cancel": "🕐 Number <code>{num}</code> auto-cancelled after {min} min. Refunded ${amount:.4f}",

  "status_active":    "🟢 Active",
  "status_completed": "✅ Completed",
  "status_cancelled": "❌ Cancelled",
  "status_refunded":  "💸 Refunded",
  "status_pending":   "⏳ Pending",

  "history_title": "📋 <b>Purchase History</b>",
  "history_empty": "📭 No purchases match your search.",
  "history_header": (
    "📋 <b>Purchase History</b>\n"
    "─────────────────\n"
    "🛒 Total: <b>{total}</b>  ✅ Done: <b>{done}</b>  ❌ Cancelled: <b>{cancel}</b>\n"
    "🔍 Filter: <b>{filter_name}</b>  |  Page {page}/{pages}"
  ),
  "history_row_btn": "{icon} {svc} — 🌍{cnt} — ${cost:.4f} — {date}",
  "history_detail": (
    "📋 <b>Purchase Detail</b>\n"
    "─────────────────\n"
    "📞 Number: <code>{num}</code>\n"
    "🌍 Country: <b>{country}</b>\n"
    "📱 Service: <b>{service}</b>\n"
    "💰 Cost: <b>${cost:.4f}</b>\n"
    "📅 Date: <b>{date}</b>\n"
    "🔄 Status: {status}\n"
    "🆔 Order ID: <code>{oid}</code>"
  ),
  "history_detail_sms": "\n\n🔑 Code: <b><code>{code}</code></b>\n📩 <i>{full}</i>",
  "history_filter_all":       "📋 All",
  "history_filter_completed": "✅ Completed",
  "history_filter_active":    "🟢 Active",
  "history_filter_cancelled": "❌ Cancelled",
  "history_filter_refunded":  "💸 Refunded",
  "btn_history_filter":  "🔽 Filter",
  "btn_history_search":  "🔍 Search",
  "btn_history_clear":   "🧹 Clear Filter",
  "btn_history_cleanup": "🗑️ Cleanup",
  "history_search_prompt": "🔍 Enter phone number, service, country or order ID:",
  "history_cleanup_ask":  "⚠️ Will delete cancelled/refunded purchases older than {days} days.\nRecords: <b>{count}</b>\nProceed?",
  "history_cleanup_done": "✅ Deleted <b>{count}</b> old records.",
  "history_cleanup_empty": "📭 No old records to delete.",
  "history_row": "📞 <code>{num}</code> | {svc} | 🌍 {cnt}\n💰 ${cost:.4f} | {status} | {date}",

  "balance_title": (
    "💰 <b>Your Balance</b>\n"
    "─────────────────\n"
    "💵 Balance: <b>${bal:.4f}</b>\n"
    "💸 Total Spent: <b>${spent:.4f}</b>\n"
    "🛒 Purchases: <b>{purchases}</b>"
  ),
  "btn_deposit":  "➕ Add Funds",
  "btn_txs":      "📋 Transactions",
  "tx_title":     "📋 <b>Transaction History</b>",
  "tx_row":       "{icon} <b>{name}</b>  {amount:+.4f}$\n📝 {desc} | 💳 ${after:.4f} | {date}",
  "tx_empty":     "📭 No transactions yet.",
  "deposit_info": "💳 <b>Deposit</b>\n\nSelect payment method:",
  "btn_deposit_pay":    "💳 Deposit Funds",
  "btn_pay_history":    "📋 My Deposits",
  "pay_select_method":  "💳 <b>Select Payment Currency</b>\n\nChoose an available payment method:",
  "pay_no_methods":     "❌ No payment methods available.\nContact admin.",
  "pay_enter_amount":   "💰 Enter deposit amount in USD:\n(Min: ${min:.2f} | Max: ${max:.2f})",
  "pay_amount_low":     "❌ Amount below minimum ${min:.2f}",
  "pay_amount_high":    "❌ Amount above maximum ${max:.2f}",
  "pay_invalid_amount": "❌ Invalid amount. Enter a number.",
  "pay_creating":       "⏳ Creating invoice...",
  "pay_invoice": (
    "📋 <b>Payment Details</b>\n"
    "─────────────────\n"
    "💵 USD Amount: <b>${usd:.2f}</b>\n"
    "🪙 Currency: <b>{coin} {network}</b>\n"
    "💰 Pay Amount: <b>{pay_amount} {coin}</b>\n"
    "📬 Deposit Address:\n<code>{address}</code>\n\n"
    "⏰ Expires in: <b>{lifetime} minutes</b>\n"
    "🆔 Track ID: <code>{track_id}</code>\n\n"
    "⚠️ Send the exact amount shown to the address above"
  ),
  "pay_open_link":      "🔗 Open Payment Page",
  "pay_check_status":   "🔄 Check Status",
  "pay_cancel_invoice": "❌ Cancel",
  "pay_status_waiting": "⏳ Waiting for payment...",
  "pay_status_confirming":"🔄 Confirming...",
  "pay_status_paid":    "✅ Payment received!",
  "pay_status_expired": "❌ Invoice expired",
  "pay_status_error":   "🔴 Error occurred",
  "pay_status_cancelled":"🚫 Cancelled",
  "pay_confirmed_notify": (
    "🎉 <b>Payment Confirmed!</b>\n\n"
    "💵 <b>${usd:.2f}</b> added to your balance\n"
    "🪙 {coin} — Track: <code>{track_id}</code>\n"
    "💰 New Balance: <b>${balance:.4f}</b>"
  ),
  "pay_history_title":  "📋 <b>Your Deposit History</b>",
  "pay_history_empty":  "📭 No deposits yet.",
  "pay_history_row": (
    "{icon} <b>{coin}</b> — <b>${usd:.2f}</b>\n"
    "📅 {date} | {status}"
  ),
  "pay_cancelled_ok":   "✅ Invoice cancelled.",
  "pay_error":          "❌ Invoice creation failed: {reason}",
  "pay_oxapay_off":     "❌ Payment gateway is not enabled.",

  "stats_title": "📊 <b>Your Statistics</b>",
  "stats_body": (
    "💰 Balance: <b>${bal:.4f}</b>\n"
    "💸 Total Spent: <b>${spent:.4f}</b>\n"
    "🛒 Total Purchases: <b>{total}</b>\n"
    "✅ Done: <b>{done}</b> | ❌ Cancelled: <b>{cancel}</b> | 💸 Refunded: <b>{refund}</b>\n\n"
    "📱 Top Services:\n{svcs}\n\n"
    "🌍 Top Countries:\n{cnts}\n\n"
    "📅 Recent Months:\n{months}"
  ),

  "profile_title": "👤 <b>Your Profile</b>",
  "profile_info": (
    "🆔 <code>{tid}</code>\n"
    "👤 <b>{name}</b>  {uname}\n"
    "💰 Balance: <b>${bal:.4f}</b>\n"
    "💸 Total Spent: <b>${spent:.4f}</b>\n"
    "🛒 Purchases: <b>{purchases}</b>\n"
    "📅 Joined: {joined}\n"
    "🕐 Last Active: {active}\n"
    "🌐 Language: {lang}"
  ),
  "btn_pr_info":    "👤 My Info",
  "btn_pr_stats":   "📊 Statistics",
  "btn_pr_history": "📋 History",
  "btn_pr_balance": "💰 Balance",
  "btn_pr_lang":    "🌐 Language",

  "adm_enter_pw":   "🔐 Enter admin password:",
  "adm_wrong_pw":   "❌ Wrong password.",
  "adm_logged_in":  "✅ <b>Logged in as Admin!</b>",
  "adm_logged_out": "✅ Logged out.",
  "adm_no_auth":    "🔐 Must log in first. /admin",
  "adm_menu":       "⚙️ <b>Admin Panel</b>",

  "btn_adm_stats":    "📊 Statistics",
  "btn_adm_users":    "👥 Users",
  "btn_adm_search":   "🔍 Search User",
  "btn_adm_txs":      "💳 Transactions",
  "btn_adm_purchases":"🛒 Purchases",
  "btn_adm_active":   "📱 Active Numbers",
  "btn_adm_top":      "🏆 Top Users",
  "btn_adm_broadcast":"📢 Broadcast",
  "btn_adm_settings": "⚙️ Settings",
  "btn_adm_profits":  "📈 Profits & Sales",
  "btn_adm_smspool":  "🔑 SMSPool Keys",

  "adm_smspool_title": "🔑 <b>SMSPool API Key Management</b>",
  "adm_smspool_body": (
    "🔑 <b>SMSPool API Keys</b>\n"
    "─────────────────\n"
    "Active Key: <code>{active_preview}</code>\n"
    "Saved Keys: <b>{count}</b>\n"
    "Account Balance: <b>${balance:.4f}</b>"
  ),
  "adm_smspool_key_row":  "{status} <code>{preview}</code>  |  📝 {label}",
  "adm_smspool_enter_key": "🔑 Enter new SMSPool API key:",
  "adm_smspool_enter_label": "📝 Enter a label for this key (e.g. Main, Backup):",
  "adm_smspool_added":    "✅ Key added successfully.",
  "adm_smspool_deleted":  "✅ Key deleted.",
  "adm_smspool_activated":"✅ Key set as active.",
  "adm_smspool_balance":  "💰 Account Balance: <b>${balance:.4f}</b>",
  "adm_smspool_no_keys":  "📭 No keys saved. Add one.",
  "adm_smspool_invalid":  "❌ Key invalid or could not be verified.",
  "btn_adm_smspool_add":  "➕ Add Key",
  "btn_adm_smspool_balance":"💰 Check Balance",
  "btn_adm_payments":  "💳 Payments",

  "adm_profit_title": "📈 <b>Profit & Sales Analytics</b>",
  "adm_profit_overview": (
    "📈 <b>Overview — Profits & Sales</b>\n"
    "═══════════════════════\n"
    "📊 Current Markup: <b>{markup}%</b>\n"
    "─────────────────\n"
    "🛒 Total Sales: <b>{total_sales}</b>  |  Today: <b>{sales_today}</b>\n"
    "✅ Completed: <b>{completed}</b>  |  💸 Refunded: <b>{refunded}</b>\n"
    "─────────────────\n"
    "💵 <b>Revenue (what customers paid)</b>\n"
    "Total: <b>${revenue_total:.4f}</b>\n"
    "Today: <b>${revenue_today:.4f}</b>  |  Week: <b>${revenue_week:.4f}</b>  |  Month: <b>${revenue_month:.4f}</b>\n"
    "─────────────────\n"
    "🏭 <b>Capital Cost (paid to SMSPool)</b>\n"
    "Total: <b>${cost_total:.4f}</b>\n"
    "Today: <b>${cost_today:.4f}</b>  |  Week: <b>${cost_week:.4f}</b>  |  Month: <b>${cost_month:.4f}</b>\n"
    "─────────────────\n"
    "📤 <b>Commissions Paid (referral)</b>\n"
    "Total: <b>${commission_total:.4f}</b>  |  Month: <b>${commission_month:.4f}</b>\n"
    "─────────────────\n"
    "✨ <b>Gross Profit (before commissions)</b>\n"
    "Total: <b>${gross_total:.4f}</b>  |  Today: <b>${gross_today:.4f}</b>\n"
    "Week: <b>${gross_week:.4f}</b>  |  Month: <b>${gross_month:.4f}</b>\n"
    "Margin: <b>{margin:.2f}%</b>\n"
    "─────────────────\n"
    "💎 <b>Net Profit (after commissions)</b>\n"
    "Total: <b>${net_total:.4f}</b>  |  Today: <b>${net_today:.4f}</b>\n"
    "Week: <b>${net_week:.4f}</b>  |  Month: <b>${net_month:.4f}</b>\n"
    "Net Margin: <b>{net_margin:.2f}%</b>"
  ),
  "adm_profit_deposits": (
    "💳 <b>Deposits</b>\n"
    "─────────────────\n"
    "Total Deposited: <b>${deposits_total:.4f}</b>\n"
    "Today: <b>${deposits_today:.4f}</b>  |  Week: <b>${deposits_week:.4f}</b>\n"
    "Month: <b>${deposits_month:.4f}</b>\n"
    "Pending: <b>${deposits_pending:.4f}</b>\n"
    "─────────────────\n"
    "⚖️ User Balances (liabilities): <b>${liabilities:.4f}</b>\n"
    "Refunded Amount: <b>${refunded_amt:.4f}</b>"
  ),
  "adm_profit_services": (
    "📱 <b>Top Services by Profit</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_service_row":  "{rank}. <b>{name}</b>\n    🛒 {sales} sold | 💵 ${revenue:.4f} | 🏭 ${cost:.4f} | ✨ ${profit:.4f}",
  "adm_profit_countries": (
    "🌍 <b>Top Countries by Profit</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_country_row":  "{rank}. <b>{name}</b>  🛒 {sales} | ✨ ${profit:.4f}",
  "adm_profit_monthly": (
    "📅 <b>Monthly Trend</b>\n"
    "─────────────────\n"
    "{rows}"
  ),
  "adm_profit_month_row": "📅 <b>{mo}</b>: 🛒 {sales} | 💵 ${rev:.4f} | 🏭 ${cost:.4f} | ✨ ${profit:.4f}",
  "adm_profit_markup_test": (
    "🔢 <b>Markup Test</b>\n"
    "─────────────────\n"
    "Current rate: <b>{markup}%</b>\n\n"
    "Price examples:\n"
    "  $0.10 → <b>${p1:.4f}</b>\n"
    "  $0.50 → <b>${p2:.4f}</b>\n"
    "  $1.00 → <b>${p3:.4f}</b>\n"
    "  $2.00 → <b>${p4:.4f}</b>\n"
    "  $5.00 → <b>${p5:.4f}</b>"
  ),
  "btn_adm_profit_overview":  "📊 Overview",
  "btn_adm_profit_services":  "📱 Services",
  "btn_adm_profit_countries": "🌍 Countries",
  "btn_adm_profit_monthly":   "📅 Monthly",
  "btn_adm_profit_deposits":  "💳 Deposits",
  "btn_adm_profit_markup":    "🔢 Markup Test",
  "btn_adm_pay_methods":"🔧 Payment Methods",
  "adm_pay_title":     "💳 <b>Payment Management</b>",
  "adm_pay_stats": (
    "💳 <b>Payment Statistics</b>\n"
    "─────────────────\n"
    "✅ Paid: <b>{paid}</b> | ⏳ Pending: <b>{pending}</b>\n"
    "❌ Expired: <b>{expired}</b>\n\n"
    "💵 Total: <b>${total:.2f}</b>\n"
    "📅 Today: <b>${today:.2f}</b> ({today_c})\n"
    "📆 Week: <b>${week:.2f}</b>\n\n"
    "🪙 By Currency:\n{by_coin}\n\n"
    "📊 Recent Months:\n{monthly}"
  ),
  "adm_pm_list":       "🔧 <b>Available Payment Methods</b>",
  "adm_pm_empty":      "📭 No payment methods. Add one.",
  "adm_pm_row":        "{status} <b>{coin}</b> {network} | Limit: ${min:.1f}-${max:.1f}",
  "btn_adm_pm_add":    "➕ Add Payment Method",
  "adm_pm_select_coin":"🪙 Select currency from OxaPay:",
  "adm_pm_no_coins":   "❌ Cannot fetch currencies. Check OxaPay key.",
  "adm_pm_enter_min":  "💰 Enter minimum deposit in USD:",
  "adm_pm_enter_max":  "💰 Enter maximum deposit in USD:",
  "adm_pm_enter_label":"📝 Enter display name (or press skip):",
  "adm_pm_enter_note": "📝 Enter note (or press skip):",
  "adm_pm_skip":       "Skip →",
  "adm_pm_added":      "✅ Payment method added: <b>{coin}</b>",
  "adm_pm_deleted":    "✅ Payment method deleted.",
  "adm_pm_toggled":    "✅ Status changed.",
  "adm_pm_detail": (
    "🔧 <b>Payment Method Details</b>\n"
    "─────────────────\n"
    "🪙 Coin: <b>{coin}</b>\n"
    "🌐 Network: <b>{network}</b>\n"
    "🏷️ Label: <b>{label}</b>\n"
    "💰 Limits: <b>${min:.2f} — ${max:.2f}</b>\n"
    "👤 Fee Paid By: <b>{fee_payer}</b>\n"
    "⏰ Invoice Lifetime: <b>{lifetime} min</b>\n"
    "📉 Underpaid Cover: <b>{underpaid}%</b>\n"
    "📝 Note: {note}\n"
    "Status: {status}"
  ),
  "btn_adm_pm_toggle": "🔄 Toggle Enable",
  "btn_adm_pm_delete": "🗑️ Delete",
  "btn_adm_pm_edit":   "✏️ Edit",
  "adm_pay_list_title":"💳 <b>Payment History</b>",
  "adm_pay_row": (
    "{icon} <b>{user}</b> — {coin} — <b>${usd:.2f}</b>\n"
    "📅 {date} | {status}"
  ),
  "adm_oxapay_settings":"⚙️ <b>OxaPay Settings</b>",
  "adm_oxapay_body": (
    "🔑 Key: <code>{key_preview}</code>\n"
    "✅ Status: {enabled}\n"
    "⏰ Invoice Lifetime: {lifetime} min\n"
    "👤 Fee Paid By: {fee_payer}\n"
    "📉 Underpaid Cover: {underpaid}%"
  ),
  "btn_adm_oxapay_key": "🔑 Change API Key",
  "btn_adm_oxapay_toggle":"🔄 Toggle Active",
  "btn_adm_oxapay_lifetime":"⏰ Invoice Lifetime",
  "btn_adm_oxapay_fee": "👤 Fee Payer",
  "btn_adm_oxapay_underpaid":"📉 Underpaid Cover",
  "fee_payer_merchant": "Merchant (Store)",
  "fee_payer_customer": "Customer",
  "btn_adm_msg_user": "📨 Message User",
  "btn_adm_logout":   "🚪 Logout",

  "adm_stats_title": "📊 <b>Global Statistics</b>",
  "adm_stats": (
    "👥 <b>Users</b>\n"
    "Total: <b>{total}</b> | Active: <b>{active}</b> | Banned: <b>{banned}</b> | New Today: <b>{new24}</b>\n\n"
    "🛒 <b>Purchases</b>\n"
    "Total: <b>{tot_p}</b> | Active: <b>{act_n}</b> | Done: <b>{done}</b>\n"
    "Cancelled: <b>{cancel}</b> | Refunded: <b>{refund}</b>\n"
    "Today: <b>{p24}</b> | This Week: <b>{p7}</b>\n\n"
    "💰 <b>Financials</b>\n"
    "Total Revenue: <b>${rev:.4f}</b>\n"
    "Today Revenue: <b>${rev24:.4f}</b>\n"
    "Refunded: <b>${refamt:.4f}</b>\n"
    "User Balances: <b>${bals:.4f}</b>\n\n"
    "📱 Top Services:\n{svcs}\n\n"
    "🌍 Top Countries:\n{cnts}"
  ),

  "adm_user_profile": (
    "👤 <b>User Profile</b>\n"
    "─────────────────\n"
    "🆔 <code>{tid}</code>\n"
    "👤 <b>{name}</b>  {uname}\n"
    "💰 Balance: <b>${bal:.4f}</b>\n"
    "💸 Total Spent: <b>${spent:.4f}</b>\n"
    "🛒 Purchases: <b>{purchases}</b> | 💸 Refunds: <b>{refunds}</b>\n"
    "📅 Joined: {joined}\n"
    "🕐 Last Active: {active}\n"
    "🔴 Banned: {banned}\n"
    "📝 Note: {note}"
  ),
  "btn_u_add":    "➕ Add Balance",
  "btn_u_rm":     "➖ Remove Balance",
  "btn_u_set":    "💳 Set Balance",
  "btn_u_p":      "🛒 Purchases",
  "btn_u_t":      "💳 Transactions",
  "btn_u_s":      "📊 Statistics",
  "btn_u_ban":    "🚫 Ban",
  "btn_u_unban":  "✅ Unban",
  "btn_u_note":   "📝 Add Note",
  "btn_u_msg":    "📨 Send Message",
  "btn_u_delete": "🗑️ Delete User",

  "adm_enter_amount":  "💰 Enter amount in USD (e.g. 5.00):",
  "adm_enter_reason":  "📝 Enter reason:",
  "adm_enter_note":    "📝 Enter note for user:",
  "adm_enter_msg":     "📨 Enter message to send to user:",
  "adm_invalid_amount":"❌ Invalid amount.",
  "adm_bal_added":     "✅ Added <b>${amount:.4f}</b>\nNew balance: <b>${new:.4f}</b>",
  "adm_bal_removed":   "✅ Removed <b>${amount:.4f}</b>\nNew balance: <b>${new:.4f}</b>",
  "adm_bal_set":       "✅ Balance set to <b>${new:.4f}</b>",
  "adm_bal_err":       "❌ Cannot process operation.",
  "adm_ban_ok":        "✅ Banned {user}",
  "adm_unban_ok":      "✅ Unbanned {user}",
  "adm_note_ok":       "✅ Note saved.",
  "adm_msg_ok":        "✅ Message sent to user.",
  "adm_msg_fail":      "❌ Failed to send (blocked?).",
  "adm_delete_ask":    "⚠️ Delete all data for <b>{user}</b>? Cannot be undone!",
  "adm_delete_ok":     "✅ User data deleted.",
  "adm_not_found":     "❌ User not found.",
  "adm_search_prompt": "🔍 Enter username, name or Telegram ID:",

  "adm_broadcast_prompt":   "📢 Enter message to broadcast:",
  "adm_broadcast_type_menu": (
    "📢 <b>Advanced Broadcast</b>\n"
    "─────────────────\n"
    "Choose broadcast type:"
  ),
  "btn_bc_all":       "📢 All Users",
  "btn_bc_active":    "✅ Active Buyers Only",
  "btn_bc_deposited": "💰 Depositors Only",
  "btn_bc_specific":  "👤 Specific User",
  "adm_bc_specific_prompt": "👤 Enter Telegram ID or @username:",
  "adm_bc_specific_msg_prompt": "📨 Enter message to send to {name}:",
  "adm_bc_sent_specific": "✅ Message sent to {name}.",
  "adm_bc_html_tip":  "💡 HTML supported: <b>bold</b> <i>italic</i> <code>code</code>",
  "adm_bc_preview":   "👁 Message preview:\n─────────────────\n{msg}\n─────────────────",
  "btn_bc_confirm_send":  "✅ Send",
  "btn_bc_edit":          "✏️ Edit",
  "adm_broadcast_prompt":  "📢 Enter message to broadcast to all users:",
  "adm_broadcast_confirm": "⚠️ Will send to <b>{count}</b> users. Confirm?",
  "adm_broadcast_done":    "✅ Sent to <b>{ok}</b> users (failed: {fail})",

  "adm_settings_title": "⚙️ <b>Bot Settings</b>",
  "adm_settings": (
    "🟢 Status: {status}\n"
    "💰 Min Deposit: <b>${min_dep}</b>\n"
    "📈 Price Markup: <b>{markup}%</b>\n"
    "🆘 Support Link: {support}\n"
    "🕐 Auto-cancel after: <b>{auto_cancel}</b> min"
  ),
  "btn_toggle_bot":    "🔄 Toggle Bot Active",
  "btn_set_markup":    "📈 Change Markup %",
  "btn_set_min_dep":   "💰 Change Min Deposit",
  "btn_set_support":   "🆘 Support Link",
  "btn_set_welcome":   "👋 Welcome Message",
  "btn_set_auto_cancel":"🕐 Auto-cancel Duration",
  "adm_enter_setting": "Enter new value:",
  "adm_setting_saved": "✅ Saved.",

  "adm_active_nums": "📱 <b>Active Numbers ({count})</b>",
  "adm_active_row":  "👤 {user} | 📞 <code>{num}</code>\n📲 {svc} | 🌍 {cnt} | ⏱️ {mins} min",
  "adm_top_title":   "🏆 <b>Top Users by Spending</b>",
  "adm_top_row":     "{rank}. <b>{name}</b> — ${spent:.4f} | {purchases} purchases",

  "msg_options_set":    "✅ Message selected. Now use:\n/msg_delete | /msg_edit | /msg_pin | /msg_unpin",
  "msg_options_cleared": "✅ /msg_options cancelled",
  "msg_options_usage":   "⚠️ You must reply to a message when using /msg_options",
  "msg_delete_ok":       "✅ Message deleted.",
  "msg_delete_fail":     "❌ Delete failed: {reason}",
  "msg_edit_prompt":     "✏️ Enter the new text for the message:",
  "msg_edit_ok":         "✅ Message edited.",
  "msg_edit_fail":       "❌ Edit failed: {reason}",
  "msg_pin_ok":          "✅ Message pinned.",
  "msg_pin_fail":        "❌ Pin failed: {reason}",
  "msg_unpin_ok":        "✅ Message unpinned.",
  "msg_unpin_fail":      "❌ Unpin failed: {reason}",
  "msg_no_options":      "⚠️ Use /msg_options first by replying to the target message.",
  "msg_user_not_found":  "❌ User not found.",
  "msg_options_for_user":"✅ Targeting {name}. Use /msg_delete or /msg_edit",
  "notify_add":    "💰 <b>${amount:.4f}</b> added to your balance\n📝 {reason}\nBalance: <b>${bal:.4f}</b>",
  "notify_rm":     "💸 <b>${amount:.4f}</b> deducted\n📝 {reason}\nBalance: <b>${bal:.4f}</b>",
  "notify_banned": "🚫 Your account has been banned.",
  "notify_unbanned":"✅ Your ban has been lifted.",
  "notify_msg":    "📨 Message from Admin:\n\n{msg}",

  "inline_search_title": "🔍 Search service or country",
  "inline_no_key":       "Type a service or country name to search",
},
}

TX_NAMES = {
  "ar": {"deposit":"إيداع","withdrawal":"سحب","purchase":"شراء","refund":"استرداد","admin_add":"إضافة إدارة","admin_remove":"خصم إدارة","admin_set":"تحديد إدارة","referral":"عمولة إحالة"},
  "en": {"deposit":"Deposit","withdrawal":"Withdrawal","purchase":"Purchase","refund":"Refund","admin_add":"Admin Credit","admin_remove":"Admin Debit","admin_set":"Admin Set","referral":"Referral Commission"},
}
TX_ICONS = {"deposit":"💰","withdrawal":"💸","purchase":"🛒","refund":"💸","admin_add":"✅","admin_remove":"❌","admin_set":"💳","referral":"🎁"}

def t(lang, key, **kw):
    lang = lang if lang in STRINGS else "ar"
    text = STRINGS[lang].get(key, STRINGS["ar"].get(key, f"[{key}]"))
    return text.format(**kw) if kw else text

def tx_name(lang, tp): return TX_NAMES.get(lang, TX_NAMES["ar"]).get(tp, tp)
def tx_icon(tp): return TX_ICONS.get(tp, "💳")

def fmt_date(s):
    try: return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except: return s or "—"

def fmt_list(items, nk, ck="n"):
    return "\n".join(f"  {i+1}. {x[nk]} ({x[ck]})" for i,x in enumerate(items)) or "—"

def status_label(lang, s):
    return t(lang, f"status_{s}" if f"status_{s}" in STRINGS[lang] else "status_pending")

def user_display(u):
    n = ((u.get("first_name") or "") + " " + (u.get("last_name") or "")).strip()
    return n or u.get("username") or str(u.get("telegram_id","?"))


# ════════════════════════════════════════════════════════════════════════════
# SECTION 4 ─ KEYBOARDS
# All callback patterns use short prefixes (max 64 bytes guaranteed)
# ════════════════════════════════════════════════════════════════════════════
from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as KB

def _row(*btns): return list(btns)
def _kb(*rows): return KB(list(rows))

def back_kb(lang, cb): return _kb(_row(Btn(t(lang,"back"), callback_data=cb)))

def main_menu_kb(lang, is_admin=False):
    rows = [
        _row(Btn(t(lang,"btn_buy"),     callback_data="b:s"),
             Btn(t(lang,"btn_active"),  callback_data="ac:l")),
        _row(Btn(t(lang,"btn_history"), callback_data="hi:0"),
             Btn(t(lang,"btn_balance"), callback_data="bl:m")),
        _row(Btn(t(lang,"btn_stats"),   callback_data="st:m"),
             Btn(t(lang,"btn_profile"), callback_data="pr:m")),
        _row(Btn(t(lang,"btn_referral"), callback_data="ref:m"),
             Btn(t(lang,"btn_lang"),      callback_data="lc")),
    ]
    if is_admin:
        rows.append(_row(Btn(t(lang,"btn_admin"), callback_data="adm:m")))
    return KB(rows)

def lang_kb():
    return _kb(_row(Btn("🇸🇦 العربية", callback_data="l:ar"),
                    Btn("🇬🇧 English", callback_data="l:en")))

def countries_kb(lang, countries, page=0):
    start = page * COUNTRIES_PER
    chunk = countries[start:start+COUNTRIES_PER]
    total = (len(countries)+COUNTRIES_PER-1)//COUNTRIES_PER
    rows  = [[Btn(f"🌍 {c.get('name','?')}", callback_data=f"b:c:{c.get('ID',c.get('id',''))}")] for c in chunk]
    nav   = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"b:cp:{page-1}"))
    nav.append(Btn(t(lang,"page",p=page+1,t=total), callback_data="noop"))
    if start+COUNTRIES_PER < len(countries): nav.append(Btn(t(lang,"next"), callback_data=f"b:cp:{page+1}"))
    rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="mm")])
    return KB(rows)

def services_kb(lang, services, cid, page=0):
    start = page * SERVICES_PER
    chunk = services[start:start+SERVICES_PER]
    total = (len(services)+SERVICES_PER-1)//SERVICES_PER
    rows  = [[Btn(f"📱 {s.get('name','?')}  💲{s.get('price','?')}", callback_data=f"b:sv:{cid}:{s.get('ID',s.get('id',''))}")] for s in chunk]
    nav   = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"b:sp:{cid}:{page-1}"))
    nav.append(Btn(t(lang,"page",p=page+1,t=total), callback_data="noop"))
    if start+SERVICES_PER < len(services): nav.append(Btn(t(lang,"next"), callback_data=f"b:sp:{cid}:{page+1}"))
    rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data="b:s")])
    return KB(rows)

def confirm_kb(lang, cid, sid):
    return _kb(_row(Btn(t(lang,"confirm"), callback_data=f"b:cf:{cid}:{sid}"),
                    Btn(t(lang,"cancel"),  callback_data=f"b:c:{cid}")))

def number_detail_kb(lang, oid, status):
    rows = []
    if status == "active":
        rows.append(_row(Btn(t(lang,"btn_check"),   callback_data=f"ac:ch:{oid}"),
                         Btn(t(lang,"btn_resend"),  callback_data=f"ac:rs:{oid}")))
        rows.append(_row(Btn(t(lang,"btn_cancel_num"), callback_data=f"ac:cn:{oid}")))
    elif status == "completed":
        rows.append(_row(Btn(t(lang,"btn_reuse_num"), callback_data=f"ac:ru:{oid}")))
    rows.append(_row(Btn(t(lang,"back"), callback_data="ac:l")))
    return KB(rows)

def reuse_confirm_kb(lang, oid):
    return _kb(_row(Btn(t(lang,"confirm"), callback_data=f"ac:ruc:{oid}"),
                    Btn(t(lang,"cancel"),  callback_data=f"ac:v:{oid}")))

def cancel_ask_kb(lang, oid):
    return _kb(_row(Btn(t(lang,"yes"),    callback_data=f"ac:cc:{oid}"),
                    Btn(t(lang,"cancel"), callback_data=f"ac:v:{oid}")))

def paginated_kb(lang, page, has_more, cb_base, back_cb):
    nav = []
    if page > 0: nav.append(Btn(t(lang,"prev"), callback_data=f"{cb_base}:{page-1}"))
    if has_more: nav.append(Btn(t(lang,"next"), callback_data=f"{cb_base}:{page+1}"))
    rows = []
    if nav: rows.append(nav)
    rows.append([Btn(t(lang,"back"), callback_data=back_cb)])
    return KB(rows)

def balance_kb(lang):
    return _kb(
        _row(Btn(t(lang,"btn_deposit_pay"), callback_data="pay:m")),
        _row(Btn(t(lang,"btn_pay_history"), callback_data="pay:h:0")),
        _row(Btn(t(lang,"btn_txs"),         callback_data="bl:t:0")),
        _row(Btn(t(lang,"back"),            callback_data="mm")))

def profile_kb(lang):
    return _kb(_row(Btn(t(lang,"btn_pr_info"),    callback_data="pr:i")),
               _row(Btn(t(lang,"btn_pr_stats"),   callback_data="pr:s")),
               _row(Btn(t(lang,"btn_pr_history"), callback_data="pr:h:0")),
               _row(Btn(t(lang,"btn_pr_balance"), callback_data="pr:b")),
               _row(Btn(t(lang,"btn_pr_lang"),    callback_data="lc")),
               _row(Btn(t(lang,"back"),           callback_data="mm")))

def admin_menu_kb(lang):
    return _kb(
        _row(Btn(t(lang,"btn_adm_stats"),     callback_data="adm:st")),
        _row(Btn(t(lang,"btn_adm_users"),    callback_data="adm:ul:0"),
             Btn(t(lang,"btn_adm_search"),   callback_data="adm:sr")),
        _row(Btn(t(lang,"btn_adm_usearch"),  callback_data="adm:usearch"),
             Btn(t(lang,"btn_adm_top_sort"), callback_data="adm:topsort")),
        _row(Btn(t(lang,"btn_adm_active"),   callback_data="adm:an:0"),
             Btn(t(lang,"btn_adm_top"),      callback_data="adm:tp")),
        _row(Btn(t(lang,"btn_adm_profits"),  callback_data="adm:profit:m"),
             Btn(t(lang,"btn_adm_smspool"),  callback_data="adm:sk:list")),
        _row(Btn(t(lang,"btn_adm_txs"),       callback_data="adm:t:0"),
             Btn(t(lang,"btn_adm_purchases"), callback_data="adm:ap:0")),
        _row(Btn(t(lang,"btn_adm_payments"),  callback_data="adm:pay:m"),
             Btn(t(lang,"btn_adm_pay_methods"),callback_data="adm:pm:l")),
        _row(Btn(t(lang,"btn_adm_ref"),       callback_data="adm:ref:m")),
        _row(Btn(t(lang,"btn_adm_broadcast"), callback_data="adm:bc"),
             Btn(t(lang,"btn_adm_msg_user"),  callback_data="adm:mu")),
        _row(Btn(t(lang,"btn_adm_settings"),  callback_data="adm:ss")),
        _row(Btn(t(lang,"btn_adm_logout"),    callback_data="adm:lo"),
             Btn(t(lang,"back"),              callback_data="mm")),
    )

def admin_user_kb(lang, uid, is_banned):
    """Full interactive user management panel."""
    if is_banned:
        ban_icon = "✅ رفع الحظر" if lang=="ar" else "✅ Unban"
    else:
        ban_icon = "🚫 حظر" if lang=="ar" else "🚫 Ban"
    ban_cb   = f"adm:ub:{uid}" if is_banned else f"adm:bn:{uid}"
    return _kb(
        # Balance row
        _row(Btn(("➕ إضافة" if lang=="ar" else "➕ Add"),   callback_data=f"adm:ab:{uid}"),
             Btn(("➖ خصم"  if lang=="ar" else "➖ Remove"), callback_data=f"adm:rb:{uid}"),
             Btn(("💳 تحديد" if lang=="ar" else "💳 Set"),   callback_data=f"adm:sb:{uid}")),
        # History row
        _row(Btn(("🛒 مشتريات"   if lang=="ar" else "🛒 Purchases"),   callback_data=f"adm:up:{uid}:0"),
             Btn(("💳 معاملات"    if lang=="ar" else "💳 Transactions"), callback_data=f"adm:ut:{uid}:0")),
        # Stats + Referrals
        _row(Btn(("📊 إحصائيات"  if lang=="ar" else "📊 Stats"),        callback_data=f"adm:us:{uid}"),
             Btn(("🎁 إحالاته"    if lang=="ar" else "🎁 Referrals"),    callback_data=f"adm:uref:{uid}:0")),
        # Note + Message
        _row(Btn(("📝 ملاحظة"   if lang=="ar" else "📝 Note"),          callback_data=f"adm:nt:{uid}"),
             Btn(("📨 مراسلة"   if lang=="ar" else "📨 Message"),        callback_data=f"adm:um:{uid}")),
        # Ban toggle (single button, state-aware)
        _row(Btn(ban_icon, callback_data=ban_cb)),
        # Delete
        _row(Btn(("🗑️ حذف البيانات" if lang=="ar" else "🗑️ Delete Data"), callback_data=f"adm:del:{uid}")),
        _row(Btn(t(lang,"back"), callback_data="adm:ul:0")),
    )

def admin_settings_kb(lang):
    return _kb(
        _row(Btn(t(lang,"btn_toggle_bot"),     callback_data="adm:ss:toggle")),
        _row(Btn(t(lang,"btn_set_markup"),     callback_data="adm:ss:markup"),
             Btn(t(lang,"btn_set_min_dep"),    callback_data="adm:ss:min_dep")),
        _row(Btn(t(lang,"btn_set_support"),    callback_data="adm:ss:support"),
             Btn(t(lang,"btn_set_welcome"),    callback_data="adm:ss:welcome")),
        _row(Btn(t(lang,"btn_set_auto_cancel"),callback_data="adm:ss:auto_cancel")),
        _row(Btn(t(lang,"back"), callback_data="adm:m")),
    )

def admin_smspool_kb(lang, keys: list) -> "KB":
    rows = []
    for k in keys:
        stat  = "🟢" if k.get("is_active") else "⚪"
        prev  = k["api_key"][:6] + "..." + k["api_key"][-4:]
        lbl   = k.get("label","") or "—"
        rows.append([
            Btn(f"{stat} {prev}  {lbl}", callback_data=f"adm:sk:v:{k['id']}"),
        ])
    rows.append([Btn(t(lang,"btn_adm_smspool_add"),     callback_data="adm:sk:add"),
                 Btn(t(lang,"btn_adm_smspool_balance"),  callback_data="adm:sk:bal")])
    rows.append([Btn(t(lang,"back"), callback_data="adm:m")])
    return KB(rows)

def admin_smspool_key_kb(lang, key_id: int, is_active: bool) -> "KB":
    rows = []
    if not is_active:
        rows.append([Btn(("🟢 تفعيل" if lang=="ar" else "🟢 Set Active"),
                          callback_data=f"adm:sk:act:{key_id}")])
    rows.append([Btn(("🗑️ حذف" if lang=="ar" else "🗑️ Delete"),
                      callback_data=f"adm:sk:del:{key_id}")])
    rows.append([Btn(t(lang,"back"), callback_data="adm:sk:list")])
    return KB(rows)

def admin_profit_kb(lang):
    """Profit & Sales Analytics sub-menu."""
    return _kb(
        _row(Btn(t(lang,"btn_adm_profit_overview"),  callback_data="adm:profit:overview")),
        _row(Btn(t(lang,"btn_adm_profit_services"),  callback_data="adm:profit:services"),
             Btn(t(lang,"btn_adm_profit_countries"), callback_data="adm:profit:countries")),
        _row(Btn(t(lang,"btn_adm_profit_monthly"),   callback_data="adm:profit:monthly"),
             Btn(t(lang,"btn_adm_profit_deposits"),  callback_data="adm:profit:deposits")),
        _row(Btn(t(lang,"btn_adm_profit_markup"),    callback_data="adm:profit:markup")),
        _row(Btn(t(lang,"back"), callback_data="adm:m")),
    )

def admin_topsort_kb(lang):
    """Choose ranking criteria."""
    return _kb(
        _row(Btn(t(lang,"btn_adm_top_spent"),    callback_data="adm:top:spent:0"),
             Btn(t(lang,"btn_adm_top_bal"),       callback_data="adm:top:balance:0")),
        _row(Btn(t(lang,"btn_adm_top_purchases"), callback_data="adm:top:purchases:0"),
             Btn(t(lang,"btn_adm_top_refs"),       callback_data="adm:top:refs:0")),
        _row(Btn(t(lang,"back"), callback_data="adm:m")),
    )

def admin_payment_menu_kb(lang):
    return _kb(
        _row(Btn(t(lang,"adm_pay_title"), callback_data="adm:pay:st")),
        _row(Btn(t(lang,"adm_pay_list_title"), callback_data="adm:pay:l:0")),
        _row(Btn(t(lang,"adm_oxapay_settings"), callback_data="adm:pay:cfg")),
        _row(Btn(t(lang,"back"), callback_data="adm:m")),
    )

def admin_pm_detail_kb(lang, pm_id):
    return _kb(
        _row(Btn(t(lang,"btn_adm_pm_toggle"), callback_data=f"adm:pm:tog:{pm_id}"),
             Btn(t(lang,"btn_adm_pm_delete"), callback_data=f"adm:pm:del:{pm_id}")),
        _row(Btn(t(lang,"back"), callback_data="adm:pm:l")),
    )

def admin_oxapay_cfg_kb(lang):
    return _kb(
        _row(Btn(t(lang,"btn_adm_oxapay_key"),    callback_data="adm:opa:key")),
        _row(Btn(t(lang,"btn_adm_oxapay_toggle"), callback_data="adm:opa:tog")),
        _row(Btn(t(lang,"btn_adm_oxapay_lifetime"),callback_data="adm:opa:life"),
             Btn(t(lang,"btn_adm_oxapay_fee"),    callback_data="adm:opa:fee")),
        _row(Btn(t(lang,"btn_adm_oxapay_underpaid"),callback_data="adm:opa:underpaid")),
        _row(Btn(t(lang,"btn_adm_pay_methods"),   callback_data="adm:pm:l")),
        _row(Btn(t(lang,"back"), callback_data="adm:pay:m")),
    )

def payment_invoice_kb(lang, track_id, pay_link):
    return _kb(
        _row(Btn(t(lang,"pay_open_link"),    url=pay_link)),
        _row(Btn(t(lang,"pay_check_status"), callback_data=f"pay:chk:{track_id}"),
             Btn(t(lang,"pay_cancel_invoice"),callback_data=f"pay:cxl:{track_id}")),
    )

def payment_method_select_kb(lang, methods):
    from oxapay import COIN_ICONS
    rows = []
    for pm in methods:
        coin = pm.get("coin","?")
        net  = pm.get("network","")
        lbl  = pm.get("label") or f"{coin} {net}".strip()
        icon = COIN_ICONS.get(coin.upper(),"🪙")
        mn   = pm.get("min_amount",1)
        mx   = pm.get("max_amount",10000)
        rows.append([Btn(f"{icon} {lbl}  |  ${mn:.1f}-${mx:.1f}",
                          callback_data=f"pay:sel:{pm['id']}")])
    rows.append([Btn(t(lang,"back"), callback_data="bl:m")])
    return KB(rows)

def history_filter_kb(lang, current_filter, page=0):
    """History with filter buttons + search + cleanup."""
    filters = [
        ("all",       "history_filter_all"),
        ("completed", "history_filter_completed"),
        ("active",    "history_filter_active"),
        ("cancelled", "history_filter_cancelled"),
        ("refunded",  "history_filter_refunded"),
    ]
    rows = []
    row  = []
    for i, (fkey, fstr) in enumerate(filters):
        mark = "✦ " if fkey == current_filter else ""
        row.append(Btn(f"{mark}{t(lang,fstr)}", callback_data=f"hi:f:{fkey}:0"))
        if len(row) == 3:
            rows.append(row); row = []
    if row: rows.append(row)
    rows.append([
        Btn(t(lang,"btn_history_search"),  callback_data="hi:search"),
        Btn(t(lang,"btn_history_cleanup"), callback_data="hi:cleanup"),
    ])
    rows.append([Btn(t(lang,"back"), callback_data="mm")])
    return KB(rows)

def history_item_kb(lang, oid, status, from_page=0, current_filter="all"):
    """Buttons on a single history item."""
    rows = []
    if status == "active":
        rows.append(_row(
            Btn(t(lang,"btn_check"),      callback_data=f"hi:act_check:{oid}"),
            Btn(t(lang,"btn_resend"),     callback_data=f"hi:act_resend:{oid}"),
        ))
        rows.append(_row(Btn(t(lang,"btn_cancel_num"), callback_data=f"hi:act_cancel:{oid}")))
    elif status == "completed":
        rows.append(_row(Btn(t(lang,"btn_reuse_num"), callback_data=f"hi:reuse:{oid}")))
    rows.append(_row(
        Btn(t(lang,"back"), callback_data=f"hi:f:{current_filter}:{from_page}"),
    ))
    return KB(rows)

def history_cleanup_confirm_kb(lang, days):
    return _kb(_row(Btn(t(lang,"confirm"), callback_data=f"hi:cleanup_ok:{days}"),
                    Btn(t(lang,"cancel"),  callback_data="hi:f:all:0")))

def referral_menu_kb(lang, bot_username):
    return _kb(
        _row(Btn(t(lang,"btn_ref_list"),     callback_data="ref:l:0")),
        _row(Btn(t(lang,"btn_ref_earnings"), callback_data="ref:e:0")),
        _row(Btn(t(lang,"btn_ref_stats"),    callback_data="ref:s")),
        _row(Btn(t(lang,"back"),             callback_data="mm")),
    )

def admin_referral_kb(lang):
    return _kb(
        _row(Btn(t(lang,"btn_adm_ref_stats"),  callback_data="adm:ref:st")),
        _row(Btn(t(lang,"btn_adm_ref_list"),   callback_data="adm:ref:l:0")),
        _row(Btn(t(lang,"btn_adm_ref_toggle"), callback_data="adm:ref:tog"),
             Btn(t(lang,"btn_adm_ref_pct"),    callback_data="adm:ref:pct")),
        _row(Btn(t(lang,"back"), callback_data="adm:m")),
    )

def confirm_action_kb(lang, yes_cb, no_cb):
    return _kb(_row(Btn(t(lang,"yes"), callback_data=yes_cb),
                    Btn(t(lang,"no"),  callback_data=no_cb)))
