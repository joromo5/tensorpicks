"""ML model — train, save, load, and predict game outcomes.

Three models:
  1. Win probability (classification) — XGBoost
  2. Total points (regression) — XGBoost
  3. Spread prediction (regression) — XGBoost
"""

import logging
from pathlib import Path

import joblib
import numpy as np
from xgboost import XGBClassifier, XGBRegressor

from tensorinc.core.config import settings
from tensorinc.sports_bettor.features import (
    FEATURE_COLUMNS,
    build_features,
    build_target,
    features_to_array,
)

log = logging.getLogger(__name__)

MODEL_DIR = Path(settings.sports_bettor_model_dir)

MODEL_FILES = {
    "win_prob": MODEL_DIR / "win_prob.joblib",
    "total_points": MODEL_DIR / "total_points.joblib",
    "spread": MODEL_DIR / "spread.joblib",
}


def train(historical_games: list[dict], team_stats: dict) -> dict:
    """Train all three models on historical data.

    Returns dict with training metrics for each model.
    """
    log.info("Building training dataset from %d games...", len(historical_games))

    X_rows = []
    y_win = []
    y_total = []
    y_spread = []

    for game in historical_games:
        if game.get("status") != "STATUS_FINAL":
            continue

        feats = build_features(game, historical_games, team_stats)
        targets = build_target(game)

        if feats is None or targets is None:
            continue

        row = features_to_array(feats)
        X_rows.append(row)
        y_win.append(targets["home_win"])
        y_total.append(targets["total_points"])
        y_spread.append(targets["home_spread"])

    if len(X_rows) < 50:
        log.warning("Only %d samples — need at least 50 for training", len(X_rows))
        return {"error": "insufficient_data", "samples": len(X_rows)}

    X = np.array(X_rows, dtype=np.float32)
    log.info("Training dataset: %d samples, %d features", X.shape[0], X.shape[1])

    metrics = {}
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Win probability model
    log.info("Training win probability model...")
    win_model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="logloss",
        random_state=42,
    )
    win_model.fit(X, np.array(y_win))
    joblib.dump(win_model, MODEL_FILES["win_prob"])
    train_acc = float(win_model.score(X, np.array(y_win)))
    metrics["win_prob"] = {"accuracy": train_acc, "samples": len(y_win)}
    log.info("  Win model train accuracy: %.3f", train_acc)

    # 2. Total points model
    log.info("Training total points model...")
    total_model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    total_model.fit(X, np.array(y_total, dtype=np.float32))
    joblib.dump(total_model, MODEL_FILES["total_points"])
    total_preds = total_model.predict(X)
    mae = float(np.mean(np.abs(total_preds - np.array(y_total))))
    metrics["total_points"] = {"mae": mae, "samples": len(y_total)}
    log.info("  Total points model train MAE: %.1f", mae)

    # 3. Spread model
    log.info("Training spread model...")
    spread_model = XGBRegressor(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    spread_model.fit(X, np.array(y_spread, dtype=np.float32))
    joblib.dump(spread_model, MODEL_FILES["spread"])
    spread_preds = spread_model.predict(X)
    spread_mae = float(np.mean(np.abs(spread_preds - np.array(y_spread))))
    metrics["spread"] = {"mae": spread_mae, "samples": len(y_spread)}
    log.info("  Spread model train MAE: %.1f", spread_mae)

    # Log feature importances for the win model
    importances = win_model.feature_importances_
    top_idx = np.argsort(importances)[-10:][::-1]
    log.info("Top 10 features for win probability:")
    for i in top_idx:
        log.info("  %s: %.4f", FEATURE_COLUMNS[i], importances[i])

    return metrics


def load_models() -> dict | None:
    """Load all trained models from disk. Returns None if any missing."""
    models = {}
    for name, path in MODEL_FILES.items():
        if not path.exists():
            log.warning("Model file missing: %s", path)
            return None
        models[name] = joblib.load(path)
    log.info("Loaded all 3 models from %s", MODEL_DIR)
    return models


def predict(models: dict, features: dict) -> dict | None:
    """Run all three models on a feature set.

    Returns:
        home_win_prob: float (0-1)
        predicted_total: float
        predicted_spread: float (positive = home favored)
    """
    if not models:
        return None

    row = np.array([features_to_array(features)], dtype=np.float32)

    win_model = models["win_prob"]
    total_model = models["total_points"]
    spread_model = models["spread"]

    # Win probability
    win_proba = win_model.predict_proba(row)[0]
    home_win_prob = float(win_proba[1]) if len(win_proba) > 1 else float(win_proba[0])

    # Total points
    predicted_total = float(total_model.predict(row)[0])

    # Spread
    predicted_spread = float(spread_model.predict(row)[0])

    return {
        "home_win_prob": home_win_prob,
        "away_win_prob": 1 - home_win_prob,
        "predicted_total": predicted_total,
        "predicted_spread": predicted_spread,
    }


def models_exist() -> bool:
    """Check if trained models exist on disk."""
    return all(p.exists() for p in MODEL_FILES.values())
