"""
oxapay.py ─ OxaPay Payment Gateway (V1 & Legacy support)
"""
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

class OxaPayError(Exception): pass

class OxaPay:
    def __init__(self, key: str = ""):
        self.key = key
        self.base = "https://api.oxapay.com"
        self.headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def _request(self, path: str, data: dict, key_type="merchant") -> dict:
        url = f"{self.base}{path}" if path.startswith("/") else f"{self.base}/{path}"
        headers = dict(self.headers)

        # Determine if V1
        is_v1 = "/v1/" in url or path.startswith("v1/")

        payload = dict(data)

        # Authentication
        if is_v1:
            # V1 uses headers
            header_key = "merchant_api_key" if key_type == "merchant" else "general_api_key"
            headers[header_key] = str(self.key)
        else:
            # Legacy uses body
            payload["merchant"] = str(self.key)
            payload["key"] = str(self.key)

        # Precise data typing for OxaPay
        for k in list(payload.keys()):
            if k in ("amount", "underPaidCover", "under_paid_coverage"):
                try: payload[k] = float(payload[k])
                except: pass
            elif k in ("lifeTime", "lifetime", "feePaidByPayer", "fee_paid_by_payer"):
                try: payload[k] = int(payload[k])
                except: pass

        async with aiohttp.ClientSession() as s:
            try:
                async with s.post(url, json=payload, headers=headers, timeout=20) as r:
                    text = await r.text()
                    log.info(f"OxaPay {path} | Status: {r.status} | Payload: {json.dumps(payload)} | Body: {text[:200]}")

                    if r.status == 403: raise OxaPayError("Cloudflare 403 Blocked")

                    try: resp = json.loads(text)
                    except: raise OxaPayError(f"Invalid JSON: {text[:50]}")

                    # Success check
                    status = resp.get("status") # V1
                    result = resp.get("result") # Legacy

                    if status is not None:
                        if int(status) != 200:
                            msg = resp.get("error", {}).get("message") or resp.get("message") or "API Error"
                            raise OxaPayError(f"{msg} (Status {status})")
                    elif result is not None:
                        if int(result) not in (100, 200):
                            raise OxaPayError(f"{resp.get('message', 'Error')} (Result {result})")

                    return resp
            except Exception as e:
                if isinstance(e, OxaPayError): raise
                raise OxaPayError(f"Request failed: {str(e)}")

    async def merchant_info(self) -> dict:
        # Try V1 merchant balance first
        try: return await self._request("/v1/merchant/balance", {})
        except: pass
        # Try V1 general balance
        try: return await self._request("/v1/general/account/balance", {}, key_type="general")
        except: pass
        # Legacy fallbacks
        for ep in ["/merchants/balance", "/merchant/balance", "/wlabel/balance"]:
            try: return await self._request(ep, {})
            except: continue
        return {"result": 404, "message": "Balance endpoint not found"}

    async def accepted_currencies(self) -> list:
        # V1
        try:
            resp = await self._request("/v1/merchant/allowed_currencies", {})
            return resp.get("data") or []
        except: pass
        # Legacy
        for ep in ["/merchants/list/currencies", "/wlabel/list/currencies"]:
            try:
                resp = await self._request(ep, {})
                return resp.get("data") or resp.get("result_data") or []
            except: continue
        return []

    async def create_invoice(self, amount: float, pay_currency: str, order_id: str, description: str = "Deposit", lifetime: int = 60, fee_paid_by_payer: int = 0, underpaid_cover: float = 2.5) -> dict:
        # V1 Payload
        v1_data = {
            "amount": float(amount),
            "currency": "USD",
            "lifetime": int(lifetime),
            "fee_paid_by_payer": int(fee_paid_by_payer),
            "under_paid_coverage": float(underpaid_cover),
            "description": description,
            "order_id": order_id
        }

        try:
            res = await self._request("/v1/payment/invoice", v1_data)
            return res.get("data") or res
        except Exception as e:
            log.warning(f"V1 Invoice failed ({e}), trying legacy...")

            # Legacy Payload
            leg_data = {
                "amount": float(amount),
                "currency": "USD",
                "lifeTime": int(lifetime),
                "feePaidByPayer": int(fee_paid_by_payer),
                "underPaidCover": float(underpaid_cover),
                "description": description,
                "orderId": order_id
            }
            curr = pay_currency.split("/")[0] if "/" in pay_currency else pay_currency
            leg_data["payCurrency"] = curr
            if "/" in pay_currency:
                leg_data["network"] = pay_currency.split("/")[1].lower()

            try:
                return await self._request("/merchants/request", leg_data)
            except OxaPayError as e2:
                if "102" in str(e2) or "merchant" in str(e2).lower():
                    return await self._request("/wlabel/create", leg_data)
                raise e2

    async def check_payment(self, track_id: str) -> dict:
        try: return await self._request("/v1/payment/inquiry", {"track_id": track_id})
        except: return await self._request("/merchants/inquiry", {"trackId": track_id})

    def status_icon(self, status: str) -> str: return PAYMENT_STATUS.get(status, ("❓", ""))[0]
    def coin_icon(self, coin: str) -> str: return COIN_ICONS.get(coin.upper(), "🪙")
    def format_pay_link(self, track_id: str) -> str: return f"https://oxapay.com/pay/{track_id}"

oxapay = OxaPay()
def init_oxapay(key: str):
    oxapay.key = key
