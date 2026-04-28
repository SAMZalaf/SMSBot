"""
smspool.py ─ SMSPool.net API wrapper
https://api.smspool.net/

⚠️ إذا ظهر خطأ "Host not in allowlist":
  1. اذهب إلى: https://smspool.net/my-account → API Settings
  2. أضف IP السيرفر في قائمة الـ Allowed IPs
  3. أو تواصل مع دعم SMSPool لفتح IP السيرفر
"""
import aiohttp
import logging
from core import SMSPOOL_API_KEY, SMSPOOL_BASE, PRICE_MARKUP

log = logging.getLogger(__name__)

IP_BLOCK_MSG = "host not in allowlist"


class SMSError(Exception):
    pass


class SMSPool:
    def __init__(self, key=None):
        self.key  = key or SMSPOOL_API_KEY
        self.base = SMSPOOL_BASE

    def _check_ip_block(self, text: str):
        if IP_BLOCK_MSG in text.lower():
            raise SMSError(
                "🚫 SMSPool: IP السيرفر غير مسموح به.\n"
                "الحل: smspool.net → My Account → API → Allowed IPs → أضف IP السيرفر"
            )

    async def _get(self, path, params=None):
        """GET request — يُرسل المفتاح دائماً لاسترجاع الأسعار."""
        p = dict(params or {})
        if self.key:
            p["key"] = self.key          # ← الإصلاح الرئيسي: المفتاح مطلوب للأسعار
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self.base}{path}", params=p,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                text = await r.text()
                self._check_ip_block(text)
                if r.status != 200:
                    raise SMSError(f"HTTP {r.status}: {text[:100]}")
                try:
                    return await r.json(content_type=None)
                except:
                    raise SMSError(f"Bad JSON: {text[:100]}")

    async def _post(self, path, data=None):
        d = dict(data or {})
        d["key"] = self.key
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base}{path}", data=d,
                timeout=aiohttp.ClientTimeout(total=20)
            ) as r:
                text = await r.text()
                self._check_ip_block(text)
                if r.status != 200:
                    raise SMSError(f"HTTP {r.status}: {text[:100]}")
                try:
                    return await r.json(content_type=None)
                except:
                    raise SMSError(f"Bad JSON: {text[:100]}")

    # ── Account ───────────────────────────────────────────────────────────────

    async def account_balance(self) -> float:
        r = await self._post("/request/balance")
        return float(r.get("balance", 0))

    # ── Countries ─────────────────────────────────────────────────────────────

    async def countries(self) -> list:
        data = await self._get("/country/retrieve_all")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for k in ("data", "countries", "result"):
                if isinstance(data.get(k), list):
                    return data[k]
        return []

    # ── Services ──────────────────────────────────────────────────────────────

    async def services(self, country=None) -> list:
        """جلب الخدمات مع الأسعار — المفتاح يُرسل تلقائياً في _get."""
        p = {}
        if country:
            p["country"] = country

        try:
            data = await self._get("/service/retrieve_all", p)
        except SMSError as e:
            log.warning(f"retrieve_all failed: {e}")
            try:
                data = await self._get("/service/list", p)
            except SMSError as e2:
                raise e2

        # توحيد الرد
        raw = []
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict):
            for k in ("data", "services", "result"):
                if isinstance(data.get(k), list):
                    raw = data[k]
                    break

        # توحيد أسماء الحقول بين إصدارات الـ API
        normalized = []
        for svc in raw:
            if not isinstance(svc, dict):
                continue
            price = float(
                svc.get("price") or
                svc.get("cost") or
                svc.get("success_price") or
                0
            )
            normalized.append({
                "ID":    str(svc.get("ID") or svc.get("id") or svc.get("service_id", "")),
                "name":  svc.get("name") or svc.get("service_name", "?"),
                "price": price,
                "amount": int(svc.get("amount") or svc.get("count") or 0),
            })
        return normalized

    # ── Purchase ──────────────────────────────────────────────────────────────

    async def purchase(self, country, service, pool="0") -> dict:
        return await self._post("/purchase/sms", {
            "country": country,
            "service": service,
            "pool": pool,
        })

    # ── Check SMS ─────────────────────────────────────────────────────────────

    async def check(self, order_id) -> dict:
        return await self._post("/sms/check", {"orderid": order_id})

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel(self, order_id) -> dict:
        return await self._post("/sms/cancel", {"orderid": order_id})

    # ── Resend ────────────────────────────────────────────────────────────────

    async def resend(self, order_id) -> dict:
        return await self._post("/sms/resend", {"orderid": order_id})

    # ── Markup helpers ────────────────────────────────────────────────────────

    async def markup_async(self, price) -> float:
        try:
            p = float(price)
        except:
            return 0.0
        from core import get_setting
        try:
            pct = float(await get_setting("price_markup") or "0")
        except:
            pct = PRICE_MARKUP
        if pct <= 0:
            return round(p, 6)
        return round(p * (1 + pct / 100), 6)

    def markup(self, price, pct: float = None) -> float:
        try:
            p = float(price)
        except:
            return 0.0
        use_pct = pct if pct is not None else PRICE_MARKUP
        if use_pct <= 0:
            return round(p, 6)
        return round(p * (1 + use_pct / 100), 6)


pool = SMSPool()
