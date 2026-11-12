"""Member 1 aggregate contracts. No raw-row loading or chart-specific filters."""

from collections.abc import Iterable
from math import exp, isfinite, log, sqrt

import numpy as np
import pandas as pd

from config.settings import BOROUGHS
from pipeline.filters import FilterSpec
from pipeline.geography import DISTRICT_CODES, JIA_CODES, validate_geojson
from pipeline.query import ParquetQuery

KM_COLUMNS = ["borough", "hours", "survival", "lower", "upper", "at_risk", "events", "censored"]


def district_data(
    query: ParquetQuery, filters: FilterSpec, geojson: dict, *, min_known: int = 30
) -> pd.DataFrame:
    """Return all 59 districts, exact label denominators, bins, and exclusion attrs.

    Eligibility requires min_known known seven-day labels. Unknown labels never
    become negatives. Quantile cuts use eligible districts in the current cohort.
    JIAs and unmapped requests are counted separately in attrs['excluded'].
    """
    if type(min_known) is not int or min_known < 1:
        raise ValueError("min_known must be a positive integer")
    if not DISTRICT_CODES <= validate_geojson(geojson):
        raise ValueError("All 59 validated community districts are required")
    grouped = query.aggregate("boro_cd", metrics=("long_closure_rate",), filters=filters)
    codes = grouped.boro_cd
    excluded = {
        "joint_interest_area": int(grouped.loc[codes.isin(JIA_CODES), "requests"].sum()),
        "unmatched": int(grouped.loc[~codes.isin(DISTRICT_CODES | JIA_CODES), "requests"].sum()),
    }
    frame = pd.DataFrame({"boro_cd": sorted(DISTRICT_CODES)}).merge(
        grouped, on="boro_cd", how="left", validate="one_to_one"
    )
    for name in ("requests", "known_long_labels", "long_closures"):
        frame[name] = frame[name].fillna(0).astype("int64")
    frame["eligible"] = frame.known_long_labels.ge(min_known)
    frame["support"] = np.where(
        frame.requests.eq(0),
        "No matching requests",
        np.where(frame.eligible, "Eligible", "Insufficient known labels"),
    )
    cuts = {}
    for metric, output in (("requests", "volume_bin"), ("long_closure_rate", "rate_bin")):
        values = frame.loc[frame.eligible, metric].astype(float)
        thresholds = values.quantile([1 / 3, 2 / 3]).tolist() if len(values) else [None, None]
        cuts[metric] = thresholds
        frame[output] = -1
        if len(values):
            frame.loc[frame.eligible, output] = np.searchsorted(thresholds, values, side="left")
    frame["bivariate_class"] = np.where(frame.eligible, frame.rate_bin * 3 + frame.volume_bin, -1)
    frame.attrs.update(
        excluded=excluded, cuts=cuts, min_known=min_known, population=int(grouped.requests.sum())
    )
    return frame


def kaplan_meier(
    counts: Iterable[tuple], totals: dict[str, int], *, max_points: int = 1024
) -> pd.DataFrame:
    """Exact product-limit/Greenwood estimates from sorted (borough,t,d,c) counts.

    Events precede censor removal at tied times. All times affect the estimator.
    Deterministic adaptive thinning bounds stored points per borough; retained
    probabilities and CIs are exact, but the drawn steps omit intermediate jumps.
    Endpoints are retained. Counts must exhaust totals; malformed input raises.
    """
    if type(max_points) is not int or not 4 <= max_points <= 4096:
        raise ValueError("max_points must be in 4..4096")
    if set(totals) - set(BOROUGHS):
        raise ValueError("Survival comparisons support only the five NYC boroughs")
    if any(type(n) is not int or n < 0 for n in totals.values()):
        raise ValueError("Survival totals must be nonnegative integers")
    output, seen, current, points, last = [], set(), None, [], None
    risk = 0
    seen_times = 0
    kept_times = 0
    for borough, hours, events, censored in counts:
        if borough != current:
            if current is not None:
                if risk != 0:
                    raise ValueError("Life table does not exhaust cohort")
                if points[-1] != last:
                    points.append(last)
                output.extend(points)
            if borough in seen or borough not in totals:
                raise ValueError("Life table boroughs must be contiguous and have totals")
            seen.add(borough)
            current, risk = borough, totals[borough]
            survival, greenwood, stride, index, previous = 1.0, 0.0, 1, 0, -1.0
            points = [(borough, 0.0, 1.0, 1.0, 1.0, risk, 0, 0)]
        if (
            not isfinite(hours)
            or hours < 0
            or hours <= previous
            or events < 0
            or censored < 0
            or int(events) != events
            or int(censored) != censored
            or events + censored <= 0
            or events + censored > risk
        ):
            raise ValueError("Invalid or unordered life table counts")
        previous = hours
        if events:
            survival *= 1 - events / risk
            if risk > events:
                greenwood += events / (risk * (risk - events))
        lower = upper = survival
        if 0 < survival < 1:
            transformed = log(-log(survival))
            delta = 1.959963984540054 * sqrt(greenwood) / abs(log(survival))
            # Clamp the exponent only outside the representable probability range.
            lower = exp(-exp(min(709, transformed + delta)))
            upper = exp(-exp(min(709, transformed - delta)))
        last = (borough, float(hours), survival, lower, upper, risk, int(events), int(censored))
        risk -= events + censored
        index += 1
        seen_times += 1
        if index % stride == 0:
            points.append(last)
        if len(points) >= max_points - 1:
            points = points[::2]
            stride *= 2
    if current is not None:
        if risk != 0:
            raise ValueError("Life table does not exhaust cohort")
        if points[-1] != last:
            points.append(last)
        output.extend(points)
    if any(n and b not in seen for b, n in totals.items()):
        raise ValueError("Missing life table borough")
    kept_times = len(output) - len(seen)
    result = pd.DataFrame(output, columns=KM_COLUMNS)
    result.attrs.update(
        input_time_groups=seen_times,
        plotted_time_groups=kept_times,
        display_thinned=kept_times < seen_times,
        max_points=max_points,
    )
    return result


def survival_data(
    query: ParquetQuery, filters: FilterSpec, *, max_points: int = 1024
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return bounded exact KM points and per-borough closed/censored/unknown counts."""
    outcomes = query.aggregate(
        "borough", metrics=("closed", "censored", "unknown_outcomes"), filters=filters
    )
    totals = {row.borough: int(row.closed + row.censored) for row in outcomes.itertuples()}
    with query.survival_counts(filters=filters) as counts:
        curve = kaplan_meier(counts, totals, max_points=max_points)
    return curve, outcomes


def daily_data(query: ParquetQuery, filters: FilterSpec, *, rolling_days: int = 7) -> pd.DataFrame:
    """Return a complete 2025 calendar within the filter, with exact daily medians.

    Rolling request mean includes zero days; rolling median of daily medians
    ignores days without valid closures and is NOT a pooled request-level median.
    Null creation days are reported in attrs, not assigned to a calendar date.
    """
    if type(rolling_days) is not int or not 1 <= rolling_days <= 31:
        raise ValueError("rolling_days must be in 1..31")
    grouped = query.aggregate("created_day", metrics=("closure_median_hours",), filters=filters)
    unknown = int(grouped.loc[grouped.created_day.isna(), "requests"].sum())
    start = max(filters.start_date or "2025-01-01", "2025-01-01")
    end = min(filters.end_date or "2025-12-31", "2025-12-31")
    dates = pd.date_range(start, end, freq="D")
    result = pd.DataFrame({"created_day": dates.strftime("%Y-%m-%d")}).merge(
        grouped.loc[grouped.created_day.notna()],
        on="created_day",
        how="left",
        validate="one_to_one",
    )
    for name in ("requests", "valid_closures"):
        result[name] = result[name].fillna(0).astype("int64")
    result["closure_median_hours"] = result.closure_median_hours.astype(float)
    result["request_trend"] = result.requests.rolling(rolling_days, min_periods=1).mean()
    result["closure_trend_hours"] = result.closure_median_hours.rolling(
        rolling_days, min_periods=1
    ).median()
    result["trend_valid_days"] = result.closure_median_hours.rolling(
        rolling_days, min_periods=1
    ).count()
    result.attrs.update(
        unknown_created_day=unknown,
        rolling_days=rolling_days,
        population=int(grouped.requests.sum()),
    )
    return result
