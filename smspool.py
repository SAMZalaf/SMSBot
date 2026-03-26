"""
smspool.py ─ SMSPool.net API wrapper
https://api.smspool.net/
"""
import aiohttp
from core import SMSPOOL_API_KEY, SMSPOOL_BASE, PRICE_MARKUP


class SMSError(Exception):
    pass


class SMSPool:
    def __init__(self, key=None):
        self.key  = key or SMSPOOL_API_KEY
        self.base = SMSPOOL_BASE

    async def _get(self, path, params=None):
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{self.base}{path}", params=params or {},
                             timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    raise SMSError(f"HTTP {r.status}")
                try:    return await r.json(content_type=None)
                except: raise SMSError(f"Bad response: {(await r.text())[:100]}")

    async def _post(self, path, data=None):
        d = dict(data or {})
        d["key"] = self.key
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{self.base}{path}", data=d,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    raise SMSError(f"HTTP {r.status}")
                try:    return await r.json(content_type=None)
                except: raise SMSError(f"Bad response: {(await r.text())[:100]}")

    # ── Account ───────────────────────────────────────────────────────────────

    async def account_balance(self) -> float:
        r = await self._post("/account/balance")
        return float(r.get("balance", 0))

    # ── Countries ─────────────────────────────────────────────────────────────

    async def countries(self) -> list:
        data = await self._get("/country/list")
        return data if isinstance(data, list) else []

    # ── Services ──────────────────────────────────────────────────────────────

    async def services(self, country=None) -> list:
        p = {"country": country} if country else {}
        data = await self._get("/service/list", p)
        return data if isinstance(data, list) else []

    # ── Purchase ──────────────────────────────────────────────────────────────

    async def purchase(self, country, service, pool="0") -> dict:
        return await self._post("/purchase/sms", {"country": country, "service": service, "pool": pool})

    # ── Check SMS ─────────────────────────────────────────────────────────────

    async def check(self, order_id) -> dict:
        """
        status 0 = waiting
        status 1 = received
        status 3 = cancelled / expired
        """
        return await self._post("/sms/check", {"orderid": order_id})

    # ── Cancel ────────────────────────────────────────────────────────────────

    async def cancel(self, order_id) -> dict:
        return await self._post("/sms/cancel", {"orderid": order_id})

    # ── Resend ────────────────────────────────────────────────────────────────

    async def resend(self, order_id) -> dict:
        return await self._post("/sms/resend", {"orderid": order_id})

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def markup_async(self, price) -> float:
        """Apply markup % reading LIVE from DB settings (correct value after admin change)."""
        try:   p = float(price)
        except: return 0.0
        from core import get_setting
        try:   pct = float(await get_setting("price_markup") or "0")
        except: pct = PRICE_MARKUP
        if pct <= 0: return round(p, 6)
        return round(p * (1 + pct / 100), 6)

    def markup(self, price, pct: float = None) -> float:
        """Sync markup — uses provided pct or env fallback."""
        try:   p = float(price)
        except: return 0.0
        use_pct = pct if pct is not None else PRICE_MARKUP
        if use_pct <= 0: return round(p, 6)
        return round(p * (1 + use_pct / 100), 6)


pool = SMSPool()
