"""
oxapay.py ─ OxaPay Payment Gateway (Advanced Fix + Icons)
"""
import aiohttp
import json
import logging

log = logging.getLogger(__name__)
OXAPAY_BASE = "https://api.oxapay.com"

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

class OxaPayError(Exception): pass

class OxaPay:
    def __init__(self, key: str = ""):
        self.key  = key
        self.base = OXAPAY_BASE
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        }

    async def _request(self, path: str, data: dict) -> dict:
        url = f"{self.base}{path}"
        # Ensure numeric values are properly handled (cast to strings/floats/ints as expected)
        payload = {"merchant": str(self.key), "key": str(self.key)}
        for k, v in data.items():
            if k in ("amount", "underPaidCover"): payload[k] = float(v)
            elif k in ("lifeTime", "feePaidByPayer"): payload[k] = int(v)
            else: payload[k] = str(v)

        async with aiohttp.ClientSession() as s:
            try:
                async with s.post(url, json=payload, headers=self.headers, timeout=20) as r:
                    resp_text = await r.text()
                    log.info(f"OxaPay Request: {path} | Status: {r.status} | Payload: {json.dumps(payload)} | Body: {resp_text[:300]}")

                    if r.status == 403: raise OxaPayError("Cloudflare 403 (Blocked)")
                    if r.status != 200: raise OxaPayError(f"HTTP {r.status}")

                    resp = json.loads(resp_text)
                    # Result 100/200/None usually means okay depending on endpoint
                    # 100/200/None usually means okay. Check result value properly.
                    res_val = resp.get("result")
                    if res_val not in (100, 200, None):
                        raise OxaPayError(f"{resp.get('message', 'API Error')} (Result: {res_val})")
                    return resp
            except Exception as e:
                if isinstance(e, OxaPayError): raise
                raise OxaPayError(f"Connection: {str(e)}")

    async def merchant_info(self) -> dict:
        for ep in ["/merchants/balance", "/merchant/balance", "/wlabel/balance", "/payout/balance"]:
            try: return await self._request(ep, {})
            except: continue
        return {"result": 404, "message": "No endpoint found"}

    async def accepted_currencies(self) -> list:
        for ep in ["/merchants/list/currencies", "/wlabel/list/currencies"]:
            try:
                resp = await self._request(ep, {})
                return resp.get("data", resp.get("result_data", []))
            except: continue
        return []

    async def create_invoice(self, amount: float, pay_currency: str, order_id: str, description: str = "Deposit", lifetime: int = 30, fee_paid_by_payer: int = 0, underpaid_cover: float = 2.5) -> dict:
        payload = {
            "amount": str(amount),
            "currency": "USD",
            "payCurrency": pay_currency,
            "lifeTime": int(lifetime),
            "feePaidByPayer": int(fee_paid_by_payer),
            "underPaidCover": float(underpaid_cover),
            "description": description,
            "orderId": order_id,
        }
        if "/" in pay_currency:
            curr, net = pay_currency.split("/", 1)
            payload["payCurrency"] = curr
            payload["network"] = net.lower()

        try:
            return await self._request("/merchants/request", payload)
        except OxaPayError as e:
            if "102" in str(e) or "merchant" in str(e).lower():
                log.info("Trying White Label endpoint...")
                return await self._request("/wlabel/create", payload)
            raise

    async def check_payment(self, track_id: str) -> dict:
        return await self._request("/merchants/inquiry", {"trackId": track_id})

    def status_icon(self, status: str) -> str: return PAYMENT_STATUS.get(status, ("❓", ""))[0]
    def coin_icon(self, coin: str) -> str: return COIN_ICONS.get(coin.upper(), "🪙")
    def format_pay_link(self, track_id: str) -> str: return f"https://oxapay.com/pay/{track_id}"

oxapay = OxaPay()
def init_oxapay(key: str):
    global oxapay
    oxapay = OxaPay(key)
