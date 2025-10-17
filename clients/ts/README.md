# AegisFlux TypeScript SDK

```ts
import { createClient } from "@aegisflux/sdk";

const client = createClient({
  baseUrl: "http://127.0.0.1:8000",
  apiKey: "demo",
  spkiPins: ["sha256/..."]
});

const result = await client.predict({
  event_id: "demo",
  tenant_id: "tenant",
  amount_minor: 1299,
  currency: "USD"
});

console.log(result.decision, result.headers["x-ratelimit-remaining"]);
```
