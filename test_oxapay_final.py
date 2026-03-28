import asyncio
import aiohttp
import json
import time

async def test_all_endpoints():
    key = "YLFY1E-COXJ3G-ROJZIT-2P1CMB"
    endpoints = [
        ("https://api.oxapay.com/merchants/request", ["merchant", "key"]),
        ("https://api.oxapay.com/v1/merchants/request", ["merchant", "key"]),
        ("https://api.oxapay.com/wlabel/create", ["key"]),
        ("https://api.oxapay.com/v1/wlabel/create", ["key"]),
    ]

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    async with aiohttp.ClientSession() as s:
        for url, fields in endpoints:
            for field in fields:
                payload = {
                    field: key,
                    "amount": 1.0,
                    "currency": "USD",
                    "payCurrency": "USDT",
                    "network": "bep20",
                    "orderId": f"test_{int(time.time())}_{field}",
                    "description": "Test Deposit"
                }
                try:
                    async with s.post(url, json=payload, headers=headers, timeout=10) as r:
                        text = await r.text()
                        print(f"URL: {url}\n  Field: {field}\n  Status: {r.status}\n  Body: {text[:200]}\n")
                except Exception as e:
                    print(f"URL: {url} failed: {e}\n")

if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
