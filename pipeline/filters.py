"""One global filtering implementation for notebooks and every visualization."""

from datetime import date, datetime

import pandas as pd

type Selection = str | list[str] | tuple[str, ...] | None
type DateValue = str | date | datetime | pd.Timestamp | None


def _selection_mask(series: pd.Series, selection: Selection) -> pd.Series:
    if selection is None:
        return pd.Series(True, index=series.index)
    selected = [selection] if isinstance(selection, str) else list(selection)
    if "All" in selected:
        return pd.Series(True, index=series.index)
    return series.isin(selected)


def _day(value: DateValue) -> str | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Invalid filter date")
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/New_York")
    return stamp.date().isoformat()


def apply_filters(
    df: pd.DataFrame,
    *,
    borough: Selection = None,
    complaint_type: Selection = None,
    agency: Selection = None,
    start_date: DateValue = None,
    end_date: DateValue = None,
) -> pd.DataFrame:
    """Return a copy satisfying all selections and inclusive New York calendar dates.

    None or 'All' disables a categorical filter; [] selects no records. Unknown
    values produce no matches. Null dates survive only when no date bound is set.
    """
    start, end = _day(start_date), _day(end_date)
    if start and end and start > end:
        raise ValueError("start_date must not be after end_date")
    mask = pd.Series(True, index=df.index)
    for name, selected in (
        ("borough", borough),
        ("complaint_type", complaint_type),
        ("agency", agency),
    ):
        mask &= _selection_mask(df[name], selected)
    if start:
        mask &= df.created_day.ge(start).fillna(False)
    if end:
        mask &= df.created_day.le(end).fillna(False)
    return df.loc[mask].copy()


def get_filter_options(df: pd.DataFrame) -> dict:
    """Return sorted categories (without sentinels) and inclusive ISO date bounds."""
    result = {
        n: sorted(df[n].dropna().unique().tolist()) for n in ("borough", "complaint_type", "agency")
    }
    days = df.created_day.dropna()
    result["start_date"] = days.min() if len(days) else None
    result["end_date"] = days.max() if len(days) else None
    return result
