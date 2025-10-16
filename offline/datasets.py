from __future__ import annotations

from pathlib import Path
from typing import Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler

from app.core.config import get_settings


FEATURE_COLUMNS = [
    "amount",
    "customer_tenure",
    "device_trust_score",
    "merchant_risk_score",
    "velocity_1m",
    "velocity_1h",
    "chargeback_rate",
    "account_age_days",
    "geo_distance",
]
TARGET_COLUMN = "label"


def load_dataset(path: Path | None = None) -> pd.DataFrame:
    settings = get_settings()
    dataset_path = path or settings.offline_dataset_path
    return pd.read_csv(dataset_path)


def train_val_split(test_size: float = 0.2, random_state: int = 42) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    df = load_dataset()
    X = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y = df[TARGET_COLUMN].astype(np.float32).to_numpy()
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X)
    X_train, X_val, y_train, y_val = train_test_split(
        X_scaled, y, test_size=test_size, random_state=random_state, stratify=y
    )
    return X_train, X_val, y_train, y_val
