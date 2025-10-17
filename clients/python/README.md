# AegisFlux Python SDK

Typed Python client for the AegisFlux API with SPKI pinning and quota headers.

```python
from aegisflux import Client

client = Client(base_url="http://127.0.0.1:8000", api_key="demo", spki_pins=["sha256/..."])
result = client.predict(event_id="demo", tenant_id="tenant", amount_minor=1299, currency="USD")
print(result.decision, result.probability, result.headers.get("x-ratelimit-remaining"))
```
