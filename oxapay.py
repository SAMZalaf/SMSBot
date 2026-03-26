"""
oxapay.py ─ OxaPay Payment Gateway
https://oxapay.com/
API Docs: https://docs.oxapay.com/
"""
import aiohttp
import json

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

# Well-known coin logos
COIN_ICONS = {
    "USDT":  "💵", "BTC":   "₿",  "ETH":  "⟠",
    "TRX":   "🔴", "BNB":   "🟡", "DOGE": "🐕",
    "LTC":   "Ł",  "XRP":   "💧", "SOL":  "☀️",
    "MATIC": "🟣", "TON":   "💎", "USDC": "🔵",
    "DAI":   "🟡", "ADA":   "🔵", "DOT":  "🔴",
}


class OxaPayError(Exception):
    pass


class OxaPay:
    def __init__(self, merchant_key: str = ""):
        self.key  = merchant_key
        self.base = OXAPAY_BASE

    async def _post(self, path: str, data: dict) -> dict:
        payload = {"merchant": self.key, **data}
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{self.base}{path}",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status != 200:
                    raise OxaPayError(f"HTTP {r.status}")
                try:
                    resp = await r.json(content_type=None)
                except Exception:
                    raise OxaPayError(f"Bad JSON: {(await r.text())[:200]}")
                if resp.get("result") not in (100, None) and resp.get("result") != 200:
                    # result 100 = success for most endpoints
                    raise OxaPayError(resp.get("message", str(resp.get("result", "Unknown"))))
                return resp

    async def _get(self, path: str, params: dict = None) -> dict:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                f"{self.base}{path}",
                params=params or {},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                if r.status != 200:
                    raise OxaPayError(f"HTTP {r.status}")
                try:
                    return await r.json(content_type=None)
                except Exception:
                    raise OxaPayError(f"Bad JSON: {(await r.text())[:200]}")

    # ── Merchant Info ─────────────────────────────────────────────────────────

    async def merchant_info(self) -> dict:
        """Get merchant account info."""
        try:
            return await self._post("/merchant/balance", {})
        except OxaPayError as e:
            if "404" in str(e):
                return await self._post("/merchants/balance", {})
            raise

    # ── Accepted Currencies ───────────────────────────────────────────────────

    async def accepted_currencies(self) -> list:
        """
        List of currencies accepted by this merchant account.
        Returns list of dicts with: currency, network, minAmount, maxAmount, etc.
        """
        try:
            resp = await self._post("/merchants/list/currencies", {})
            data = resp.get("data", resp.get("result_data", []))
            return data if isinstance(data, list) else []
        except OxaPayError:
            return []

    async def all_currencies(self) -> list:
        """List all supported currencies on OxaPay network."""
        try:
            resp = await self._get("/currencies")
            data = resp if isinstance(resp, list) else resp.get("data", [])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    # ── Create Invoice ────────────────────────────────────────────────────────

    async def create_invoice(
        self,
        amount: float,
        pay_currency: str,
        order_id: str,
        description: str = "Deposit",
        lifetime: int = 30,          # minutes
        fee_paid_by_payer: int = 0,  # 0=merchant pays, 1=customer pays
        underpaid_cover: float = 2.5,
        return_url: str = "",
        callback_url: str = "",
    ) -> dict:
        """
        Create a payment invoice.
        Returns: {result, trackId, payLink, payAddress, payAmount, ...}
        """
        payload = {
            "amount":          amount,
            "currency":        "USD",
            "payCurrency":     pay_currency,
            "lifeTime":        lifetime,
            "feePaidByPayer":  fee_paid_by_payer,
            "underPaidCover":  underpaid_cover,
            "description":     description,
            "orderId":         order_id,
        }
        if callback_url: payload["callbackUrl"] = callback_url
        if return_url:   payload["returnUrl"]   = return_url
        # If network is provided, add it
        if pay_currency and "/" in pay_currency:
             # some users might pass "USDT/BEP20"
             curr, net = pay_currency.split("/", 1)
             payload["payCurrency"] = curr
             payload["network"] = net
        return await self._post("/merchants/request", payload)

    # ── Check Payment ─────────────────────────────────────────────────────────

    async def check_payment(self, track_id: str) -> dict:
        """
        Check invoice status.
        Returns: {result, trackId, status, payAmount, receivedAmount, date, ...}
        Status: Waiting | Confirming | Paid | Expired | Error
        """
        return await self._post("/merchants/inquiry", {"trackId": track_id})

    # ── Exchange Rate ─────────────────────────────────────────────────────────

    async def exchange_rate(self, from_currency: str = "USD", to_currency: str = "USDT") -> float:
        """Get exchange rate from one currency to another."""
        try:
            resp = await self._get("/exchange", {"fromCurrency": from_currency, "toCurrency": to_currency})
            return float(resp.get("price", 0) or 0)
        except Exception:
            return 0.0

    # ── Helpers ───────────────────────────────────────────────────────────────

    def status_icon(self, status: str) -> str:
        return PAYMENT_STATUS.get(status, ("❓", "unknown"))[0]

    def coin_icon(self, coin: str) -> str:
        return COIN_ICONS.get(coin.upper(), "🪙")

    def format_pay_link(self, track_id: str) -> str:
        return f"https://oxapay.com/pay/{track_id}"


# ── Singleton (key set at runtime from settings) ──────────────────────────────
oxapay = OxaPay()


def init_oxapay(key: str):
    """Called at startup once merchant key is loaded from settings."""
    global oxapay
    oxapay = OxaPay(key)
