import asyncio
import aiohttp
import json

async def test_create_invoice():
    key = "YLFY1E-COXJ3G-ROJZIT-2P1CMB"
    url = "https://api.oxapay.com/merchants/request"

    payload = {
        "merchant": key,
        "amount": 1.0,
        "currency": "USD",
        "payCurrency": "USDT",
        "network": "bep20",
        "lifeTime": 30,
        "feePaidByPayer": 0,
        "underPaidCover": 2.5,
        "description": "Test Deposit",
        "orderId": "test_12345"
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, headers=headers) as r:
            print(f"Status: {r.status}")
            print(f"Body: {await r.text()}")

if __name__ == "__main__":
    asyncio.run(test_create_invoice())
