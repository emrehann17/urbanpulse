"""Sparse, creation-time-only retrospective logistic baseline."""

import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder
from threadpoolctl import threadpool_limits

from ml.data_access import PREDICTORS
from pipeline.features import CREATION_FEATURES


def clean_predictors(frame):
    """Fail closed on extra/missing columns, including any audit/outcome inputs."""
    if tuple(frame.columns) != PREDICTORS or not set(PREDICTORS) <= set(CREATION_FEATURES):
        raise ValueError("Only the exact reviewed creation-time predictor schema is allowed")
    # Treat bounded calendar values as nominal categories; no ordinal distance.
    result = frame.astype("string").astype(object)
    return result.where(frame.notna(), np.nan)


def make_pipeline(seed=2025):
    return Pipeline(
        [
            ("schema", FunctionTransformer(clean_predictors, feature_names_out="one-to-one")),
            (
                "missing",
                SimpleImputer(
                    strategy="constant", fill_value="__Missing__", keep_empty_features=True
                ),
            ),
            (
                "encode",
                OneHotEncoder(
                    handle_unknown="infrequent_if_exist",
                    min_frequency=20,
                    max_categories=32,
                    sparse_output=True,
                    dtype=np.float64,
                ),
            ),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    solver="liblinear",
                    max_iter=1000,
                    tol=1e-6,
                    random_state=seed,
                ),
            ),
        ]
    )


def evaluate(y, probabilities, threshold):
    y = np.asarray(y, dtype=int)
    probabilities = np.asarray(probabilities, dtype=float)
    if not len(y):
        raise ValueError("Cannot evaluate an empty cohort")
    if y.shape != probabilities.shape or not np.isin(y, [0, 1]).all():
        raise ValueError("Metrics require aligned binary labels and probabilities")
    if not np.isfinite(probabilities).all() or ((probabilities < 0) | (probabilities > 1)).any():
        raise ValueError("Probabilities must be finite and in [0,1]")
    predictions = probabilities >= threshold
    both_classes = len(np.unique(y)) == 2
    return {
        "rows": len(y),
        "positives": int(y.sum()),
        "prevalence": float(y.mean()),
        "average_precision": float(average_precision_score(y, probabilities))
        if both_classes
        else None,
        "roc_auc": float(roc_auc_score(y, probabilities)) if both_classes else None,
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "recall": float(recall_score(y, predictions, zero_division=0)),
        "f1": float(f1_score(y, predictions, zero_division=0)),
        "confusion_matrix": confusion_matrix(y, predictions, labels=[0, 1]).tolist(),
        "brier_score": float(brier_score_loss(y, probabilities)),
        "threshold": float(threshold),
        "ranking_metrics_note": None
        if both_classes
        else "Undefined comparison: single-class cohort",
    }


def choose_threshold(y, probabilities):
    if len(np.unique(y)) != 2:
        raise ValueError("Validation needs both classes to select an F1 threshold")
    precision, recall, thresholds = precision_recall_curve(y, probabilities)
    f1 = np.divide(
        2 * precision[:-1] * recall[:-1],
        precision[:-1] + recall[:-1],
        out=np.zeros(len(thresholds)),
        where=(precision[:-1] + recall[:-1]) != 0,
    )
    # Largest threshold on an exact F1 tie; chosen only on validation labels.
    best = np.flatnonzero(f1 == f1.max())[-1]
    return float(thresholds[best])


def fit_logistic(cohorts, *, seed=2025):
    xy = {}
    for name in ("train", "validation", "test"):
        frame = cohorts[name]
        if frame.empty or frame.is_long_closure.isna().any():
            raise ValueError(f"{name} must be nonempty with known targets only")
        x = frame.loc[:, PREDICTORS]
        clean_predictors(x)
        xy[name] = (x, frame.is_long_closure.astype(int).to_numpy())
    if len(np.unique(xy["train"][1])) != 2:
        raise ValueError("Training requires both target classes")
    model = make_pipeline(seed)
    with threadpool_limits(limits=1), warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        model.fit(*xy["train"])
        validation_probability = model.predict_proba(xy["validation"][0])[:, 1]
        threshold = choose_threshold(xy["validation"][1], validation_probability)
        # Test is first scored after all fitting and threshold selection have finished.
        test_probability = model.predict_proba(xy["test"][0])[:, 1]
    prior = float(xy["train"][1].mean())
    baselines = {}
    for name, probability in (("majority_class", float(prior >= 0.5)), ("train_prevalence", prior)):
        baselines[name] = {
            partition: evaluate(y, np.full(len(y), probability), 0.5)
            for partition, (_, y) in xy.items()
            if partition != "train"
        }
    transformed = model[:-1].transform(xy["train"][0])
    feature_names = model["encode"].get_feature_names_out(PREDICTORS).tolist()
    metrics = {
        "features": list(PREDICTORS),
        "seed": seed,
        "target": "Existing nullable is_long_closure; strict >168 hours, "
        "including eventual late closures",
        "training_rows": len(xy["train"][1]),
        "training_prevalence": prior,
        "threshold": threshold,
        "threshold_rule": "Maximum validation F1; ties: largest threshold",
        "validation": evaluate(xy["validation"][1], validation_probability, threshold),
        "test": evaluate(xy["test"][1], test_probability, threshold),
        "baselines": baselines,
        "metric_notes": "PR-AUC is non-interpolated Average Precision; matrix rows=true, "
        "columns=predicted in [False,True] order; zero-division precision/recall/F1=0",
        "estimator": {
            "solver": "liblinear",
            "penalty": "l2",
            "C": 1.0,
            "class_weight": None,
            "max_iter": 1000,
            "tol": 1e-6,
            "iterations": model["model"].n_iter_.tolist(),
        },
        "preprocessing": {
            "fit_partition": "train only",
            "calendar_encoding": "nominal one-hot",
            "missing": "__Missing__",
            "min_frequency": 20,
            "max_categories_per_predictor": 32,
            "unseen": "infrequent category if learned, otherwise all-zero block",
            "encoded_features": feature_names,
            "sparse_shape": list(transformed.shape),
            "sparse_nnz": int(transformed.nnz),
            "sparse_bytes": int(
                transformed.data.nbytes + transformed.indices.nbytes + transformed.indptr.nbytes
            ),
        },
        "coefficients": dict(zip(feature_names, model["model"].coef_[0].tolist(), strict=True)),
        "interpretation": "Descriptive associations, not causal effects. "
        "Retrospective single-snapshot evaluation, not a prospective deployment backtest.",
    }
    return model, metrics
