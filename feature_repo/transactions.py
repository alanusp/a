from __future__ import annotations

from datetime import timedelta

from feast import Entity, FeatureService, FeatureView, Field, FileSource
from feast.types import Float32

transactions = Entity(name="transaction", join_keys=["transaction_id"])

file_source = FileSource(
    name="transactions_source",
    path="data/sample_transactions.csv",
    timestamp_field=None,
)

transaction_features = FeatureView(
    name="transaction_features",
    entities=[transactions],
    ttl=timedelta(days=1),
    schema=[
        Field(name="amount", dtype=Float32),
        Field(name="customer_tenure", dtype=Float32),
        Field(name="device_trust_score", dtype=Float32),
        Field(name="merchant_risk_score", dtype=Float32),
        Field(name="velocity_1m", dtype=Float32),
        Field(name="velocity_1h", dtype=Float32),
        Field(name="chargeback_rate", dtype=Float32),
        Field(name="account_age_days", dtype=Float32),
        Field(name="geo_distance", dtype=Float32),
    ],
    online=True,
    source=file_source,
)

transaction_feature_service = FeatureService(
    name="transaction_feature_service",
    features=[transaction_features],
)
