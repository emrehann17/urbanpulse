"""Descriptive district clustering with equal feature-block weights."""

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.metrics import silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from pipeline.geography import DISTRICT_CODES


def fit_districts(profiles, *, seed=2025, min_support=30):
    if len(profiles) != 59 or set(profiles.boro_cd) != DISTRICT_CODES:
        raise ValueError("Expected exactly 59 distinct ordinary districts")
    if (profiles.request_count <= 0).any():
        raise ValueError("All 59 districts need requests; refuse to invent empty profiles")
    if min_support < 1:
        raise ValueError("min_support must be positive")
    profiles = profiles.sort_values("boro_cd").reset_index(drop=True).copy()
    composition = [c for c in profiles if c.startswith("complaint_share_")]
    features = profiles[composition].copy()
    features["log1p_request_count"] = np.log1p(profiles.request_count)
    features["log1p_median_closure_hours"] = np.log1p(
        profiles.median_closure_hours.where(profiles.valid_closures >= min_support)
    )
    features["long_closure_rate"] = profiles.long_closure_rate.where(
        profiles.known_long_labels >= min_support
    )
    if features.isna().all().any():
        raise ValueError("Cannot median-impute an entirely unsupported district feature")
    preprocessing = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    matrix = preprocessing.fit_transform(features)
    # Each of volume, composition, duration and rate has total squared weight 1.
    groups = ["composition"] * len(composition) + ["volume", "duration", "rate"]
    groups += [groups[i] for i in preprocessing["impute"].indicator_.features_]
    weights = np.array([1 / np.sqrt(groups.count(group)) for group in groups])
    matrix *= weights
    candidates, fitted = [], {}
    with threadpool_limits(limits=1):
        for k in range(2, 7):
            model = KMeans(n_clusters=k, random_state=seed, n_init=50, algorithm="lloyd")
            labels = model.fit_predict(matrix)
            sizes = np.bincount(labels, minlength=k)
            distinct = len(np.unique(labels))
            score = float(silhouette_score(matrix, labels)) if 1 < distinct < 59 else None
            accepted = bool(sizes.min() >= 3 and distinct == k and score is not None)
            candidates.append(
                {
                    "k": k,
                    "silhouette": score,
                    "cluster_sizes": sizes.tolist(),
                    "accepted": accepted,
                    "inertia": float(model.inertia_),
                }
            )
            fitted[k] = model
        eligible = [c for c in candidates if c["accepted"]]
        if not eligible:
            raise ValueError("No nondegenerate K in 2..6 (minimum cluster size is 3)")
        best = max(eligible, key=lambda c: (c["silhouette"], -c["k"]))
        model = fitted[best["k"]]
        pca = PCA(n_components=2, svd_solver="full")
        coordinates = pca.fit_transform(matrix)
    # Stable, arbitrary IDs: order clusters by their smallest district code.
    order = sorted(range(best["k"]), key=lambda i: profiles.boro_cd[model.labels_ == i].min())
    mapping = {old: new for new, old in enumerate(order)}
    export = profiles.copy()
    export["cluster_id"] = [mapping[int(label)] for label in model.labels_]
    export[["pca_x", "pca_y"]] = coordinates
    export["duration_imputed"] = features.log1p_median_closure_hours.isna()
    export["rate_imputed"] = features.long_closure_rate.isna()
    export["selected_k"] = best["k"]
    export["seed"] = seed
    summaries = []
    for cluster, group in export.groupby("cluster_id", sort=True):
        summaries.append(
            {
                "cluster_id": int(cluster),
                "districts": group.boro_cd.tolist(),
                "district_count": len(group),
                "request_count": int(group.request_count.sum()),
                "median_district_request_count": float(group.request_count.median()),
                "median_district_completed_closure_hours": float(
                    group.median_closure_hours.median()
                )
                if group.median_closure_hours.notna().any()
                else None,
                "pooled_known_long_labels": int(group.known_long_labels.sum()),
                "pooled_long_closure_rate": float(
                    group.long_closures.sum() / group.known_long_labels.sum()
                )
                if group.known_long_labels.sum()
                else None,
                "mean_district_complaint_shares": {c: float(group[c].mean()) for c in composition},
            }
        )
    metrics = {
        "selected_k": best["k"],
        "silhouette": best["silhouette"],
        "cluster_sizes": export.groupby("cluster_id").size().tolist(),
        "candidates": candidates,
        "selection_rule": "Maximum silhouette among K=2..6 with every cluster >=3; ties: lower K",
        "semantics": "Descriptive profiles, not rankings or causal conclusions; IDs are arbitrary",
        "seed": seed,
        "n_init": 50,
        "features": features.columns.tolist(),
        "min_support": min_support,
        "missing_feature_counts": features.isna().sum().to_dict(),
        "preprocessing": "log1p counts/durations; median imputation with missing indicators; "
        "standardization; each of four blocks weighted by 1/sqrt(block columns)",
        "processed_features": preprocessing.get_feature_names_out().tolist(),
        "block_weights": weights.tolist(),
        "imputation_medians": preprocessing["impute"].statistics_.tolist(),
        "pca_explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "pca_input": "Identical imputed, standardized, block-weighted matrix used by K-Means",
        "cluster_profiles": summaries,
    }
    artifacts = {
        "preprocessing": preprocessing,
        "weights": weights,
        "kmeans": model,
        "pca": pca,
        "cluster_id_mapping": mapping,
        "features": features.columns.tolist(),
    }
    return export, metrics, artifacts
