"""
oxapay.py ─ OxaPay Payment Gateway (Modern V1 + Legacy Support)
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
        is_v1 = path.startswith("/v1") or "/payment/" in path
        url = f"{self.base}{path}" if path.startswith("/") else f"{self.base}/{path}"

        headers = dict(self.headers)
        payload = dict(data)

        if is_v1:
            headers["merchant_api_key"] = str(self.key)
        else:
            payload["merchant"] = str(self.key)
            payload["key"] = str(self.key)

        # Precise data typing to avoid "Validating problem"
        for k in list(payload.keys()):
            if k in ("amount", "underPaidCover", "under_paid_coverage"):
                payload[k] = float(payload[k])
            elif k in ("lifeTime", "lifetime", "feePaidByPayer", "fee_paid_by_payer"):
                payload[k] = int(payload[k])

        async with aiohttp.ClientSession() as s:
            try:
                async with s.post(url, json=payload, headers=headers, timeout=20) as r:
                    resp_text = await r.text()
                    log.info(f"OxaPay Request: {path} | Status: {r.status} | Payload: {json.dumps(payload)} | Body: {resp_text[:300]}")

                    if r.status == 403: raise OxaPayError("Cloudflare 403 (Blocked)")

                    try:
                        resp = json.loads(resp_text)
                    except:
                        raise OxaPayError(f"Invalid JSON response: {resp_text[:100]}")

                    status_code = resp.get("status")
                    result_code = resp.get("result")

                    if status_code is not None:
                        if int(status_code) != 200:
                            err = resp.get("error", {}).get("message") or resp.get("message") or "API Error"
                            raise OxaPayError(f"{err} (Status: {status_code})")
                    elif result_code is not None:
                        if int(result_code) not in (100, 200):
                            raise OxaPayError(f"{resp.get('message', 'API Error')} (Result: {result_code})")

                    return resp
            except Exception as e:
                if isinstance(e, OxaPayError): raise
                raise OxaPayError(f"Connection: {str(e)}")

    async def merchant_info(self) -> dict:
        # Try V1 first
        try: return await self._request("/v1/merchant/balance", {})
        except: pass

        for ep in ["/merchants/balance", "/merchant/balance", "/wlabel/balance"]:
            try: return await self._request(ep, {})
            except: continue
        return {"result": 404, "message": "No endpoint found"}

    async def accepted_currencies(self) -> list:
        for ep in ["/v1/merchant/allowed_currencies", "/merchants/list/currencies", "/wlabel/list/currencies"]:
            try:
                resp = await self._request(ep, {})
                return resp.get("data") or resp.get("result_data") or []
            except: continue
        return []

    async def create_invoice(self, amount: float, pay_currency: str, order_id: str, description: str = "Deposit", lifetime: int = 60, fee_paid_by_payer: int = 0, underpaid_cover: float = 2.5) -> dict:
        # Modern V1 Payload
        v1_payload = {
            "amount": float(amount),
            "currency": "USD",
            "lifetime": int(lifetime),
            "fee_paid_by_payer": int(fee_paid_by_payer),
            "under_paid_coverage": float(underpaid_cover),
            "description": description,
            "order_id": order_id,
        }

        try:
            res = await self._request("/v1/payment/invoice", v1_payload)
            # If successful, V1 returns data in 'data' field
            if "data" in res: return res["data"]
            return res
        except Exception as e:
            log.warning(f"OxaPay V1 Invoice failed: {e}. Falling back to legacy...")

            # Legacy Payload
            curr = pay_currency.split("/")[0] if "/" in pay_currency else pay_currency
            leg_payload = {
                "amount": float(amount),
                "currency": "USD",
                "payCurrency": curr,
                "lifeTime": int(lifetime),
                "feePaidByPayer": int(fee_paid_by_payer),
                "underPaidCover": float(underpaid_cover),
                "description": description,
                "orderId": order_id,
            }
            if "/" in pay_currency:
                leg_payload["network"] = pay_currency.split("/")[1].lower()

            try:
                return await self._request("/merchants/request", leg_payload)
            except OxaPayError as e2:
                if "102" in str(e2) or "merchant" in str(e2).lower():
                    return await self._request("/wlabel/create", leg_payload)
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
