"""Deterministic synthetic ML tests; no network or production data required."""

import hashlib
import json

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from scipy.sparse import issparse

from ml.data_access import COHORTS, PREDICTORS, MLData
from ml.kmeans import fit_districts
from ml.logistic import choose_threshold, clean_predictors, evaluate, fit_logistic, make_pipeline
from ml.train import main, write_json
from pipeline.contract import SCHEMA
from pipeline.features import CREATION_FEATURES
from pipeline.geography import DISTRICT_CODES
from pipeline.ingest import sha256


def save_snapshot(tmp_path, frame, *, mode="synthetic"):
    path = tmp_path / "requests.parquet"
    provenance = {
        "schema_version": "1.0.0",
        "mode": mode,
        "sampling": "none",
        "extraction_cutoff": "2026-02-01T00:00:00Z",
    }
    table = pa.Table.from_pandas(frame, schema=SCHEMA, preserve_index=False)
    table = table.replace_schema_metadata({b"urbanpulse": json.dumps(provenance).encode()})
    pq.write_table(table, path)
    write_json(
        path.with_suffix(".quality.json"),
        {"processed_rows": len(frame), "parquet_sha256": sha256(path), "provenance": provenance},
    )
    return path


def test_district_denominators_exclusions_and_missing(tmp_path, raw_row, transform):
    rows = [
        raw_row,
        {**raw_row, "unique_key": "2", "closed_date": "2025-01-09T00:00:00"},
        {**raw_row, "unique_key": "3", "closed_date": None, "status": "Open"},
        {**raw_row, "unique_key": "4", "closed_date": None, "status": "Closed"},
        {**raw_row, "unique_key": "5", "community_board": "64 MANHATTAN"},
        {**raw_row, "unique_key": "6", "community_board": "Unspecified MANHATTAN"},
        {
            **raw_row,
            "unique_key": "7",
            "community_board": "02 MANHATTAN",
            "closed_date": None,
            "status": "Closed",
        },
    ]
    data = MLData(save_snapshot(tmp_path, transform(rows)))
    profiles, audit = data.district_profiles(top_n=1)
    district = profiles.set_index("boro_cd").loc["101"]
    assert len(profiles) == 59
    assert district.request_count == 4
    assert district.valid_closures == 2
    assert district.median_closure_hours == 108
    assert district.known_long_labels == 3
    assert district.long_closures == 2  # Both eventual closure and mature open case.
    assert district.long_closure_rate == pytest.approx(2 / 3)
    assert audit["geography_counts"] == {
        "ordinary": 5,
        "joint_interest_area": 1,
        "unmatched_or_invalid": 1,
    }
    assert pd.isna(profiles.set_index("boro_cd").loc["102", "long_closure_rate"])
    empty = profiles.set_index("boro_cd").loc["103"]
    assert empty.request_count == 0
    assert pd.isna(empty.median_closure_hours)
    assert pd.isna(empty.complaint_share_other)
    with pytest.raises(ValueError, match="need requests"):
        fit_districts(profiles)


def test_complaint_other_includes_null_and_rare(tmp_path, raw_row, transform):
    rows = [
        {**raw_row, "unique_key": str(i), "complaint_type": c}
        for i, c in enumerate(["A", "A", "B", None])
    ]
    profiles, audit = MLData(save_snapshot(tmp_path, transform(rows))).district_profiles(top_n=1)
    row = profiles.iloc[0]
    assert audit["complaint_categories"] == {"complaint_share_0": "A"}
    assert row.complaint_share_0 == row.complaint_share_other == 0.5


@pytest.fixture
def profiles():
    rng = np.random.default_rng(123)
    group = np.repeat([0, 1], [30, 29])
    share = 0.2 + group * 0.6 + rng.uniform(-0.03, 0.03, 59)
    return pd.DataFrame(
        {
            "boro_cd": sorted(DISTRICT_CODES),
            "request_count": 1000 + group * 4000 + rng.integers(0, 100, 59),
            "valid_closures": np.full(59, 100),
            "median_closure_hours": 10 + group * 50 + rng.uniform(0, 1, 59),
            "known_long_labels": np.full(59, 100),
            "long_closures": 10 + group * 50,
            "long_closure_rate": 0.1 + group * 0.5,
            "complaint_share_0": share,
            "complaint_share_other": 1 - share,
            "borough_mismatch_count": np.zeros(59, dtype=int),
        }
    )


def test_kmeans_pca_schema_repeatability_and_identical_matrix(profiles):
    original = profiles.copy(deep=True)
    export, metrics, artifacts = fit_districts(profiles)
    repeated, repeated_metrics, _ = fit_districts(profiles.sample(frac=1, random_state=2))
    pd.testing.assert_frame_equal(export, repeated)
    assert metrics == repeated_metrics
    pd.testing.assert_frame_equal(profiles, original)
    assert {
        "boro_cd",
        "cluster_id",
        "pca_x",
        "pca_y",
        "request_count",
        "known_long_labels",
        "long_closure_rate",
        "selected_k",
        "seed",
    } <= set(export)
    assert metrics["selected_k"] == 2
    assert sorted(metrics["cluster_sizes"]) == [29, 30]
    assert len(metrics["candidates"]) == 5
    features = profiles[["complaint_share_0", "complaint_share_other"]].copy()
    features["log1p_request_count"] = np.log1p(profiles.request_count)
    features["log1p_median_closure_hours"] = np.log1p(profiles.median_closure_hours)
    features["long_closure_rate"] = profiles.long_closure_rate
    matrix = artifacts["preprocessing"].transform(features) * artifacts["weights"]
    np.testing.assert_allclose(
        artifacts["pca"].transform(matrix), export[["pca_x", "pca_y"]], atol=1e-12
    )
    labels = artifacts["kmeans"].predict(matrix)
    assert [artifacts["cluster_id_mapping"][int(i)] for i in labels] == export.cluster_id.tolist()
    assert sum(artifacts["weights"][:2] ** 2) == pytest.approx(1)


def test_missing_district_features_imputed_explicitly(profiles):
    profiles.loc[0, ["median_closure_hours", "long_closure_rate"]] = np.nan
    profiles.loc[0, ["valid_closures", "known_long_labels"]] = 0
    export, metrics, artifacts = fit_districts(profiles)
    assert export.loc[0, "duration_imputed"] and export.loc[0, "rate_imputed"]
    assert pd.isna(export.loc[0, "long_closure_rate"])
    assert np.isfinite(export[["pca_x", "pca_y"]]).all().all()
    assert metrics["missing_feature_counts"]["long_closure_rate"] == 1
    medians = artifacts["preprocessing"]["impute"].statistics_
    assert medians[-1] == profiles.long_closure_rate.median()
    profiles["long_closure_rate"] = np.nan
    with pytest.raises(ValueError, match="entirely unsupported"):
        fit_districts(profiles)


def test_reject_degenerate_clusters(profiles):
    profiles.loc[:, profiles.columns != "boro_cd"] = profiles.iloc[0, 1:].values
    with pytest.warns(UserWarning), pytest.raises(ValueError, match="nondegenerate"):
        fit_districts(profiles)


def test_temporal_boundaries_and_unknown_exclusion(tmp_path, raw_row, transform):
    dates = [
        "2024-12-31T23:59:59",
        "2025-01-01T00:00:00",
        "2025-08-31T23:59:59",
        "2025-09-01T00:00:00",
        "2025-10-31T23:59:59",
        "2025-11-01T00:00:00",
        "2025-12-31T23:59:59",
        "2026-01-01T00:00:00",
        "bad",
    ]
    rows = [
        {
            **raw_row,
            "unique_key": str(i),
            "created_date": date,
            "closed_date": None,
            "status": "Open",
            "open_data_channel_type": str(i),
        }
        for i, date in enumerate(dates)
    ]
    rows.append({**rows[1], "unique_key": "unknown", "status": "Closed"})
    frame = transform(rows)
    data = MLData(save_snapshot(tmp_path, frame))
    audit = data.cohort_audit()
    assert audit["invalid_created_date"]["rows"] == 1
    assert audit["outside_2025"]["rows"] == 2
    assert audit["train"] == {"rows": 3, "known_labels": 2, "unknown_labels": 1, "positives": 2}
    for name, expected in zip(COHORTS, (["1", "2"], ["3", "4"], ["5", "6"]), strict=True):
        sample = data.sample(name, limit=100, seed=2025)
        assert sorted(sample.open_data_channel_type) == expected
        assert sample.is_long_closure.notna().all()
        assert tuple(sample.columns) == (*PREDICTORS, "is_long_closure")


def test_sampling_is_deterministic_hash_order_not_first_rows(tmp_path, raw_row, transform):
    rows = [{**raw_row, "unique_key": str(i), "open_data_channel_type": str(i)} for i in range(100)]
    path = save_snapshot(tmp_path, transform(rows))
    data = MLData(path)
    a = data.sample("train", limit=20, seed=12)
    pd.testing.assert_frame_equal(a, data.sample("train", limit=20, seed=12))
    expected = sorted(
        range(100), key=lambda i: (hashlib.sha256(f"12:{i}".encode()).hexdigest(), str(i))
    )[:20]
    assert a.open_data_channel_type.tolist() == list(map(str, expected))
    assert not a.equals(data.sample("train", limit=20, seed=13))
    # Physical Parquet ordering cannot change the selected sample/order.
    save_snapshot(tmp_path, transform(rows[::-1]))
    pd.testing.assert_frame_equal(a, MLData(path).sample("train", limit=20, seed=12))
    with pytest.raises(ValueError, match="Snapshot changed"):
        data.sample("train", limit=20, seed=12)


@pytest.fixture
def cohorts():
    frame = pd.DataFrame(
        {
            "open_data_channel_type": ["PHONE", "ONLINE", None, "ONLINE"] * 30,
            "created_hour": [1, 2, 3, 4] * 30,
            "created_weekday": [1, 2, 3, 4] * 30,
            "created_month": [1, 2, 3, 4] * 30,
            "is_long_closure": [False, True, False, True] * 30,
        }
    )
    return {name: frame.copy(deep=True) for name in COHORTS}


@pytest.mark.parametrize(
    "leak",
    [
        "closed_date",
        "closure_hours",
        "observed_hours",
        "duration_bucket",
        "status",
        "closure_event",
        "extraction_cutoff",
        "is_long_closure",
        "resolution_description",
        "after_cutoff",
        "unique_key",
        "borough",
        "complaint_type",
    ],
)
def test_feature_leakage_guard(cohorts, leak):
    assert set(PREDICTORS) <= set(CREATION_FEATURES)
    frame = cohorts["train"].loc[:, PREDICTORS].copy()
    frame[leak] = 1
    with pytest.raises(ValueError, match="reviewed creation-time"):
        clean_predictors(frame)


def test_train_only_preprocessing_sparse_cardinality_and_repeatability(cohorts):
    cohorts["validation"]["open_data_channel_type"] = "VALIDATION_ONLY"
    cohorts["test"]["open_data_channel_type"] = "TEST_ONLY"
    cohorts["validation"]["created_month"] = 9
    cohorts["test"]["created_month"] = 12
    model, metrics = fit_logistic(cohorts)
    original_categories = [c.copy() for c in model["encode"].categories_]
    assert not {"VALIDATION_ONLY", "TEST_ONLY"} & set(original_categories[0])
    assert "9" not in original_categories[3] and "12" not in original_categories[3]
    for frame in cohorts.values():
        transformed = model[:-1].transform(frame.loc[:, PREDICTORS])
        assert issparse(transformed)
        assert transformed.shape[1] <= 32 * len(PREDICTORS)
    for a, b in zip(original_categories, model["encode"].categories_, strict=True):
        np.testing.assert_array_equal(a, b)
    model2, metrics2 = fit_logistic(cohorts)
    np.testing.assert_array_equal(model["model"].coef_, model2["model"].coef_)
    assert metrics == metrics2
    # Changing test labels cannot alter the model or validation-selected threshold.
    cohorts["test"]["is_long_closure"] = ~cohorts["test"].is_long_closure
    altered, altered_metrics = fit_logistic(cohorts)
    np.testing.assert_array_equal(model["model"].coef_, altered["model"].coef_)
    assert metrics["threshold"] == altered_metrics["threshold"]
    assert metrics["baselines"]["train_prevalence"]["test"]["brier_score"] == 0.25


def test_encoder_bounds_high_cardinality(cohorts):
    x = cohorts["train"].loc[:, PREDICTORS].copy()
    x["open_data_channel_type"] = [f"category_{i}" for i in range(len(x))]
    model = make_pipeline().fit(x, cohorts["train"].is_long_closure)
    assert issparse(model[:-1].transform(x))
    assert model[:-1].transform(x).shape[1] <= 128


def test_metrics_and_validation_threshold():
    y, scores = [0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]
    result = evaluate(y, scores, 0.5)
    assert result["average_precision"] == pytest.approx(5 / 6)
    assert result["roc_auc"] == 0.75
    assert result["precision"] == 1
    assert result["recall"] == 0.5
    assert result["f1"] == pytest.approx(2 / 3)
    assert result["confusion_matrix"] == [[2, 0], [1, 1]]
    assert result["brier_score"] == pytest.approx(0.158125)
    assert choose_threshold(y, scores) == 0.35
    assert evaluate([1, 1], [0.1, 0.9], 0.5)["roc_auc"] is None
    assert evaluate([0, 0], [0.1, 0.9], 0.5)["average_precision"] is None
    with pytest.raises(ValueError, match="empty"):
        evaluate([], [], 0.5)
    with pytest.raises(ValueError, match="both classes"):
        choose_threshold([1, 1], [0.1, 0.9])


@pytest.mark.parametrize("partition", list(COHORTS))
def test_empty_and_unknown_cohorts_fail(cohorts, partition):
    original = cohorts[partition].copy()
    cohorts[partition] = original.iloc[:0]
    with pytest.raises(ValueError, match="nonempty"):
        fit_logistic(cohorts)
    cohorts[partition] = original.astype({"is_long_closure": "boolean"})
    cohorts[partition].loc[0, "is_long_closure"] = pd.NA
    with pytest.raises(ValueError, match="known targets"):
        fit_logistic(cohorts)


@pytest.mark.parametrize("partition", ["train", "validation"])
def test_single_class_fitting_fails(cohorts, partition):
    cohorts[partition]["is_long_closure"] = True
    with pytest.raises(ValueError, match="both.*classes"):
        fit_logistic(cohorts)


def test_snapshot_verification_and_no_contract_mutation(tmp_path, frame):
    schema_before, features_before = SCHEMA.serialize().to_pybytes(), tuple(CREATION_FEATURES)
    original = frame.copy(deep=True)
    path = save_snapshot(tmp_path, frame, mode="full")
    digest = sha256(path)
    data = MLData(path)
    source = data.verify_full()
    assert source["columns"] == 52 and source["rows"] == 3
    data.district_profiles()
    data.cohort_audit()
    data.sample("train", limit=20, seed=1)
    assert sha256(path) == digest
    pd.testing.assert_frame_equal(frame, original)
    assert SCHEMA.serialize().to_pybytes() == schema_before
    assert tuple(CREATION_FEATURES) == features_before
    quality = path.with_suffix(".quality.json")
    report = json.loads(quality.read_text())
    report["parquet_sha256"] = "wrong"
    write_json(quality, report)
    with pytest.raises(ValueError, match="checksum"):
        data.verify_full()
    save_snapshot(tmp_path, frame, mode="demo")
    with pytest.raises(ValueError, match="unsampled full"):
        MLData(path).verify_full()


def test_cli_rejects_demo_and_invalid_limits():
    with pytest.raises(SystemExit):
        main(["--dataset", "demo"])
    with pytest.raises(SystemExit):
        main(["--dataset", "full", "--train-limit", "0"])


def test_single_class_test_is_reported_without_retuning(cohorts):
    _, original = fit_logistic(cohorts)
    cohorts["test"]["is_long_closure"] = False
    _, result = fit_logistic(cohorts)
    assert result["test"]["roc_auc"] is None
    assert result["test"]["average_precision"] is None
    assert result["test"]["confusion_matrix"][1] == [0, 0]
    assert result["threshold"] == original["threshold"]


def test_empty_sql_cohorts_and_all_missing_complaints(tmp_path, raw_row, transform):
    frame = transform([{**raw_row, "complaint_type": None}])
    data = MLData(save_snapshot(tmp_path, frame))
    profiles, audit = data.district_profiles()
    assert not audit["complaint_categories"]
    assert profiles.loc[0, "complaint_share_other"] == 1.0
    assert data.cohort_audit()["test"]["rows"] == 0
    assert data.sample("test", limit=10, seed=1).empty


def test_saved_model_roundtrip(tmp_path, cohorts):
    import joblib

    model, metrics = fit_logistic(cohorts)
    path = tmp_path / "model.joblib"
    joblib.dump({"pipeline": model, "threshold": metrics["threshold"]}, path)
    loaded = joblib.load(path)
    x = cohorts["test"].loc[:, PREDICTORS]
    np.testing.assert_array_equal(model.predict_proba(x), loaded["pipeline"].predict_proba(x))
    assert loaded["threshold"] == metrics["threshold"]
