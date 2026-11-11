"""One global filtering implementation for notebooks and every visualization."""

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

type Selection = str | list[str] | tuple[str, ...] | None
type DateValue = str | date | datetime | pd.Timestamp | None


def normalize_selection(selection: Selection) -> tuple[str, ...] | None:
    """Normalize global category values once for Pandas and SQL consumers."""
    if selection is None:
        return None
    selected = (selection,) if isinstance(selection, str) else tuple(selection)
    if any(not isinstance(value, str) for value in selected):
        raise ValueError("Category selections must contain strings")
    return None if "All" in selected else selected


def _day(value: DateValue) -> str | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("Invalid filter date")
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("America/New_York")
    return stamp.date().isoformat()


@dataclass(frozen=True)
class FilterSpec:
    """Immutable normalized global filters, with inclusive New York calendar days."""

    borough: Selection = None
    complaint_type: Selection = None
    agency: Selection = None
    start_date: DateValue = None
    end_date: DateValue = None

    def __post_init__(self):
        for name in ("borough", "complaint_type", "agency"):
            object.__setattr__(self, name, normalize_selection(getattr(self, name)))
        object.__setattr__(self, "start_date", _day(self.start_date))
        object.__setattr__(self, "end_date", _day(self.end_date))
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date")


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
    spec = FilterSpec(borough, complaint_type, agency, start_date, end_date)
    mask = pd.Series(True, index=df.index)
    for name in ("borough", "complaint_type", "agency"):
        selected = getattr(spec, name)
        if selected is not None:
            mask &= df[name].isin(selected)
    if spec.start_date:
        mask &= df.created_day.ge(spec.start_date).fillna(False)
    if spec.end_date:
        mask &= df.created_day.le(spec.end_date).fillna(False)
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
