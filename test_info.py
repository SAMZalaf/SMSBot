import asyncio
import aiohttp

async def get_info():
    key = "YLFY1E-COXJ3G-ROJZIT-2P1CMB"
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as s:
        # Try balance with 'merchant' field
        async with s.post("https://api.oxapay.com/merchants/balance", json={"merchant": key}, headers=headers) as r:
            print(f"Balance (merchant field): {await r.text()}")
        # Try balance with 'key' field
        async with s.post("https://api.oxapay.com/merchants/balance", json={"key": key}, headers=headers) as r:
            print(f"Balance (key field): {await r.text()}")

if __name__ == "__main__":
    asyncio.run(get_info())
