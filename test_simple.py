import asyncio
import aiohttp
import json

async def test_simple():
    key = "YLFY1E-COXJ3G-ROJZIT-2P1CMB"
    url = "https://api.oxapay.com/merchants/request"
    payload = {
        "merchant": key,
        "amount": 1.0,
        "currency": "USD",
        "orderId": "test_simple",
    }
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, headers=headers) as r:
            print(f"Body: {await r.text()}")

if __name__ == "__main__":
    asyncio.run(test_simple())
