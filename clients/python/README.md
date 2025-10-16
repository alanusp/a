# Python Client

This directory contains the typed Python client for the Fraud API.

* Version: `0.0.0`
* Requirements: `httpx`, `pydantic`

```python
from clients.python import FraudApiClient, TransactionPayload
client = FraudApiClient(base_url="http://localhost:8000/v1")
response = client.post_v1_predict(TransactionPayload(transaction_id='t1'))
```
