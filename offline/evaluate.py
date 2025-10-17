from __future__ import annotations

from pathlib import Path

import plotly.express as px
import torch
from sklearn.metrics import PrecisionRecallDisplay, RocCurveDisplay, average_precision_score, roc_auc_score

from app.models.model_loader import FraudDetectionModel, load_model
from offline.datasets import FEATURE_COLUMNS, TARGET_COLUMN, load_dataset


def evaluate(model_path: Path | None = None, output_dir: Path | None = None) -> dict[str, float]:
    model, device = load_model(model_path)
    df = load_dataset()

    X = df[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
    y = df[TARGET_COLUMN].to_numpy(dtype=np.float32)

    with torch.no_grad():
        inputs = torch.tensor(X, device=device)
        preds = model(inputs).cpu().numpy().reshape(-1)

    roc_auc = roc_auc_score(y, preds)
    pr_auc = average_precision_score(y, preds)

    metrics = {"roc_auc": float(roc_auc), "pr_auc": float(pr_auc)}

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        RocCurveDisplay.from_predictions(y, preds).figure_.savefig(output_dir / "roc_curve.png")
        PrecisionRecallDisplay.from_predictions(y, preds).figure_.savefig(
            output_dir / "precision_recall.png"
        )
        px.histogram(x=preds, nbins=50, title="Prediction Distribution").write_html(
            output_dir / "prediction_distribution.html"
        )

    return metrics


if __name__ == "__main__":
    report = evaluate(output_dir=Path("artifacts/evaluation"))
    print(report)
