from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau

from app.core.config import get_settings
from app.models.model_loader import FraudDetectionModel
from offline.datasets import FEATURE_COLUMNS, train_val_split


def train(model: FraudDetectionModel, train_loader: DataLoader, val_loader: DataLoader, epochs: int = 30) -> None:
    criterion = nn.BCELoss()
    optimizer = Adam(model.parameters(), lr=1e-3, weight_decay=1e-5)
    scheduler = ReduceLROnPlateau(optimizer, mode="min", patience=3, factor=0.5)

    best_val_loss = float("inf")
    device = next(model.parameters()).device

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for batch_X, batch_y in train_loader:
            batch_X = batch_X.to(device)
            batch_y = batch_y.to(device)
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs.view(-1), batch_y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_norm=2.0)
            optimizer.step()
            train_loss += loss.item() * batch_X.size(0)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X = batch_X.to(device)
                batch_y = batch_y.to(device)
                outputs = model(batch_X)
                loss = criterion(outputs.view(-1), batch_y)
                val_loss += loss.item() * batch_X.size(0)

        train_loss /= len(train_loader.dataset)
        val_loss /= len(val_loader.dataset)
        scheduler.step(val_loss)
        print(f"Epoch {epoch:02d} train_loss={train_loss:.4f} val_loss={val_loss:.4f}")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            save_model(model)
            print(f"✔ Saved new best model with val_loss={val_loss:.4f}")


def save_model(model: FraudDetectionModel, path: Path | None = None) -> None:
    settings = get_settings()
    output_path = path or settings.model_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weights = {name: parameter.detach().cpu().tolist() for name, parameter in model.state_dict().items()}
    with open(output_path, "w") as fp:
        json.dump(weights, fp)


if __name__ == "__main__":
    settings = get_settings()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    X_train, X_val, y_train, y_val = train_val_split()

    train_dataset = TensorDataset(
        torch.tensor(X_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32)
    )
    val_dataset = TensorDataset(
        torch.tensor(X_val, dtype=torch.float32), torch.tensor(y_val, dtype=torch.float32)
    )

    train_loader = DataLoader(train_dataset, batch_size=256, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=512)

    model = FraudDetectionModel(len(FEATURE_COLUMNS), settings.model_hidden_dims)
    model.to(device)

    train(model, train_loader, val_loader)
