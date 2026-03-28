import asyncio
import aiohttp

async def test_v2():
    key = "YLFY1E-COXJ3G-ROJZIT-2P1CMB"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as s:
        # Some docs use /merchants/balance, some /merchant/balance
        for ep in ["/merchant/balance", "/payout/balance", "/merchants/balance"]:
            for field in ["key", "merchant"]:
                try:
                    async with s.post(f"https://api.oxapay.com{ep}", json={field: key}, headers=headers) as r:
                        print(f"EP: {ep}, Field: {field}, Status: {r.status}, Body: {await r.text()}")
                except: pass

if __name__ == "__main__":
    asyncio.run(test_v2())
