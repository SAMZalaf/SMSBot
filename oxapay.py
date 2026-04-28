"""
oxapay.py ─ OxaPay Payment Gateway

⚠️ إذا ظهر خطأ "Host not in allowlist":
  1. افتح: https://oxapay.com/dashboard → Settings → Security → IP Whitelist
  2. أضف IP السيرفر أو عطّل قيد الـ IP كلياً
"""
import asyncio
import aiohttp
import json
import logging

log = logging.getLogger(__name__)

PAYMENT_STATUS = {
    "Waiting":    ("⏳", "waiting"),
    "Confirming": ("🔄", "confirming"),
    "Paid":       ("✅", "paid"),
    "Expired":    ("❌", "expired"),
    "Error":      ("🔴", "error"),
    "Refunded":   ("💸", "refunded"),
    "Canceled":   ("🚫", "cancelled"),
}

COIN_ICONS = {
    "USDT":  "💵", "BTC":   "₿",  "ETH":  "⟠",
    "TRX":   "🔴", "BNB":   "🟡", "DOGE": "🐕",
    "LTC":   "Ł",  "XRP":   "💧", "SOL":  "☀️",
    "MATIC": "🟣", "TON":   "💎", "USDC": "🔵",
    "DAI":   "🟡", "ADA":   "🔵", "DOT":  "🔴",
}

_IP_MSGS = ("host not in allowlist", "not in allowlist", "ip not allowed")


class OxaPayError(Exception):
    pass


class OxaPayIPError(OxaPayError):
    """IP السيرفر غير مدرج في القائمة البيضاء."""
    pass


class OxaPay:
    def __init__(self, key: str = ""):
        self.key  = key
        self.base = "https://api.oxapay.com"
        self._headers = {
            "Content-Type":  "application/json",
            "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept":        "application/json",
            "Accept-Language": "en-US,en;q=0.9",
        }

    # ── internal ──────────────────────────────────────────────────────────────

    async def _ensure_key(self):
        if not self.key:
            from core import get_setting, OXAPAY_API_KEY
            db_key = await get_setting("oxapay_key")
            self.key = db_key if (db_key and len(db_key) > 5) else OXAPAY_API_KEY

    def _raise_if_ip_block(self, text: str):
        tl = text.lower()
        if any(m in tl for m in _IP_MSGS):
            raise OxaPayIPError(
                "🚫 OxaPay: IP السيرفر غير مسموح به.\n\n"
                "الحل:\n"
                "oxapay.com → Dashboard → Settings → Security → IP Whitelist\n"
                "→ أضف IP السيرفر أو عطّل قيود الـ IP"
            )

    async def _request(self, path: str, payload: dict, header_auth: bool = False) -> dict:
        await self._ensure_key()
        url  = f"{self.base}{path}"
        hdrs = dict(self._headers)
        body = dict(payload)

        if header_auth:
            hdrs["merchant_api_key"] = str(self.key)
        else:
            body["merchant"] = str(self.key)
            body["key"]      = str(self.key)

        # OxaPay strict typing
        for k in list(body):
            if k in ("amount", "underPaidCover", "under_paid_coverage"):
                try: body[k] = float(body[k])
                except: pass
            elif k in ("lifeTime", "lifetime", "feePaidByPayer", "fee_paid_by_payer"):
                try: body[k] = int(body[k])
                except: pass

        async with aiohttp.ClientSession() as sess:
            try:
                async with sess.post(url, json=body, headers=hdrs, timeout=25) as r:
                    text = await r.text()
                    log.info(f"OxaPay {path} | {r.status} | {text[:180]}")

                    self._raise_if_ip_block(text)

                    if r.status in (401, 403):
                        raise OxaPayError(f"Auth error {r.status}: {text[:100]}")

                    try:
                        resp = json.loads(text)
                    except:
                        raise OxaPayError(f"Invalid JSON: {text[:100]}")

                    # V1 → "status", legacy → "result"
                    if "status" in resp:
                        if int(resp["status"]) != 200:
                            msg = resp.get("error", {}).get("message") or resp.get("message", "API Error")
                            raise OxaPayError(f"{msg} (status={resp['status']})")
                    elif "result" in resp:
                        if int(resp["result"]) not in (100, 200):
                            raise OxaPayError(f"{resp.get('message','Error')} (result={resp['result']})")

                    return resp

            except OxaPayError:
                raise
            except Exception as e:
                raise OxaPayError(f"Connection error: {e}")

    # ── public methods ────────────────────────────────────────────────────────

    async def merchant_info(self) -> dict:
        try:
            return await self._request("/v1/merchant/balance", {}, header_auth=True)
        except OxaPayIPError:
            raise
        except OxaPayError:
            pass
        for ep in ("/merchants/balance", "/merchant/balance"):
            try:
                return await self._request(ep, {})
            except OxaPayIPError:
                raise
            except OxaPayError:
                continue
        return {"result": 404, "message": "Balance endpoint not found"}

    async def accepted_currencies(self) -> list:
        try:
            r = await self._request("/v1/merchant/allowed_currencies", {}, header_auth=True)
            return r.get("data") or []
        except OxaPayIPError:
            raise
        except OxaPayError:
            pass
        for ep in ("/merchants/list/currencies", "/wlabel/list/currencies"):
            try:
                r = await self._request(ep, {})
                return r.get("data") or r.get("result_data") or []
            except OxaPayIPError:
                raise
            except OxaPayError:
                continue
        return []

    async def create_invoice(
        self,
        amount: float,
        pay_currency: str,
        order_id: str,
        description: str = "Deposit",
        lifetime: int = 60,
        fee_paid_by_payer: int = 0,
        underpaid_cover: float = 2.5,
    ) -> dict:
        # Try V1
        try:
            r = await self._request("/v1/payment/invoice", {
                "amount":               float(amount),
                "currency":             "USD",
                "lifetime":             int(lifetime),
                "fee_paid_by_payer":    int(fee_paid_by_payer),
                "under_paid_coverage":  float(underpaid_cover),
                "description":          description,
                "order_id":             order_id,
            }, header_auth=True)
            return r.get("data") or r
        except OxaPayIPError:
            raise
        except OxaPayError as e:
            log.warning(f"V1 invoice failed ({e}), trying legacy…")

        # Legacy fallback
        coin, _, network = pay_currency.partition("/")
        leg = {
            "amount":           float(amount),
            "currency":         "USD",
            "lifeTime":         int(lifetime),
            "feePaidByPayer":   int(fee_paid_by_payer),
            "underPaidCover":   float(underpaid_cover),
            "description":      description,
            "orderId":          order_id,
            "payCurrency":      coin,
        }
        if network:
            leg["network"] = network.lower()

        try:
            return await self._request("/merchants/request", leg)
        except OxaPayIPError:
            raise
        except OxaPayError:
            try:
                return await self._request("/wlabel/create", leg)
            except OxaPayIPError:
                raise
            except OxaPayError as final:
                raise final

    async def check_payment(self, track_id: str) -> dict:
        try:
            return await self._request(
                "/v1/payment/inquiry", {"track_id": track_id}, header_auth=True
            )
        except OxaPayIPError:
            raise
        except OxaPayError:
            return await self._request("/merchants/inquiry", {"trackId": track_id})

    # ── utils ─────────────────────────────────────────────────────────────────

    def status_icon(self, status: str) -> str:
        return PAYMENT_STATUS.get(status, ("❓", ""))[0]

    def coin_icon(self, coin: str) -> str:
        return COIN_ICONS.get(coin.upper(), "🪙")

    def format_pay_link(self, track_id: str) -> str:
        return f"https://oxapay.com/pay/{track_id}"


oxapay = OxaPay()


def init_oxapay(key: str):
    oxapay.key = key
