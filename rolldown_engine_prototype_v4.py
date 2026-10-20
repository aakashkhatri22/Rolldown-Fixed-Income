"""Python calculation engine prototype for the Indian G-Sec rolldown backtest.

This module ports the formula logic from rolldown_backtest_final_v9(3).py into
Python so a dashboard can consume results directly without Excel recalculation.
It deliberately raises a clear error when selected formation records are invalid
instead of silently excluding securities or inventing missing values.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import math
import pandas as pd
import numpy as np

DATA_COLUMNS = [
    "Date", "ISIN", "Coupon", "Maturity", "Price_Rs", "YTM (Annualized)",
    "Issuance date", "First IP date", "Prev coupon date", "Accrued Interest", "Gross Price",
]

@dataclass
class BacktestResult:
    start_date: pd.Timestamp
    formation_date: pd.Timestamp
    formation_market_date: pd.Timestamp
    end_date: pd.Timestamp
    horizon_years: int
    offset_years: int
    portfolio: pd.DataFrame
    daily: pd.DataFrame
    summary: dict
    ytm_trend: pd.DataFrame


def load_market_data(data_path: str | Path) -> pd.DataFrame:
    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(f"G-Sec data file not found: {path}")
    df = pd.read_excel(path, sheet_name="Data", usecols="B:L", engine="openpyxl")
    required = set(DATA_COLUMNS)
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"G-Sec Data sheet is missing columns: {sorted(missing)}")
    for col in ["Date", "Maturity", "Issuance date", "First IP date", "Prev coupon date"]:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.normalize()
    for col in ["Coupon", "Price_Rs", "YTM (Annualized)", "Accrued Interest", "Gross Price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["ISIN"] = df["ISIN"].astype(str).str.strip()
    df = df.dropna(subset=["Date", "ISIN"]).sort_values(["Date", "ISIN"]).reset_index(drop=True)
    duplicates = df.duplicated(["Date", "ISIN"], keep=False)
    if duplicates.any():
        sample = df.loc[duplicates, ["Date", "ISIN"]].head(10).to_dict("records")
        raise ValueError(f"Duplicate Date/ISIN observations found. Examples: {sample}")
    return df


def load_repo_rates(repo_path: str | Path) -> pd.Series:
    path = Path(repo_path)
    if not path.exists():
        raise FileNotFoundError(f"Repo-rate file not found: {path}")
    repo = pd.read_excel(path, sheet_name="Sheet1", engine="openpyxl")
    required = {"Date", "Repo_Rate_%"}
    missing = required.difference(repo.columns)
    if missing:
        raise ValueError(f"Repo file must contain {sorted(required)}; missing {sorted(missing)}")
    repo["Date"] = pd.to_datetime(repo["Date"], errors="coerce").dt.normalize()
    repo["Repo_Rate_%"] = pd.to_numeric(repo["Repo_Rate_%"], errors="coerce")
    repo = repo.dropna(subset=["Date", "Repo_Rate_%"]).sort_values("Date")
    if repo.empty:
        raise ValueError("No valid repo-rate observations were found.")
    return (repo.drop_duplicates("Date", keep="last").set_index("Date")["Repo_Rate_%"] / 100.0).sort_index()


def investor_end_date(start_date: pd.Timestamp, horizon_years: int) -> pd.Timestamp:
    return (start_date + pd.DateOffset(years=horizon_years) - pd.Timedelta(days=1)).normalize()


def select_portfolio(source: pd.DataFrame, start_date: str | pd.Timestamp, horizon_years: int, offset_years: int):
    start = pd.Timestamp(start_date).normalize()
    if horizon_years <= 0 or int(horizon_years) != horizon_years:
        raise ValueError("Investment horizon must be a positive whole number of years.")
    if offset_years < 0 or int(offset_years) != offset_years:
        raise ValueError("Offset must be a non-negative whole number of years.")

    # The portfolio is notionally formed one calendar day before the start.
    # If that date is a weekend/holiday, use the latest market-data date on or
    # before it; the output still retains the requested calendar formation date.
    formation_date = (start - pd.Timedelta(days=1)).normalize()
    available_dates = source.loc[source["Date"].le(formation_date), "Date"]
    if available_dates.empty:
        raise ValueError(f"No G-Sec market data exists on or before the required formation date {formation_date:%d-%b-%Y}.")
    formation_market_date = pd.Timestamp(available_dates.max()).normalize()
    formation = source[source["Date"].eq(formation_market_date)].copy()
    formation = formation[formation["Issuance date"] < start].copy()

    target = (start + pd.DateOffset(years=horizon_years + offset_years)).normalize()
    window_start = (target - pd.DateOffset(months=6)).normalize()
    selected = formation[formation["Maturity"].between(window_start, target, inclusive="both")].copy()
    selected = selected.sort_values(["Maturity", "ISIN"]).drop_duplicates("ISIN", keep="first").reset_index(drop=True)
    if selected.empty:
        raise ValueError(f"No eligible securities found for maturity window {window_start:%d-%b-%Y} to {target:%d-%b-%Y}.")

    required_cols = ["Coupon", "Maturity", "Price_Rs", "Gross Price", "YTM (Annualized)", "Accrued Interest"]
    invalid = selected[selected[required_cols].isna().any(axis=1) | selected["Gross Price"].le(0) | selected["Price_Rs"].le(0)]
    if not invalid.empty:
        cols = ["ISIN", "Date"] + required_cols
        raise ValueError("Selected portfolio contains invalid formation observations (missing required values or non-positive clean/gross price). Review these records; they were not silently removed: " + str(invalid[cols].to_dict("records")))
    return selected, formation_date, formation_market_date, window_start, target


def get_possible_offsets(source: pd.DataFrame, start_date: str | pd.Timestamp, horizon_years: int) -> list[int]:
    """Return every integer-year offset with at least one eligible security.

    This mirrors the existing script's dynamic offset discovery; it does not
    impose a fixed maximum such as five years.
    """
    start = pd.Timestamp(start_date).normalize()
    if horizon_years <= 0 or int(horizon_years) != horizon_years:
        raise ValueError("Investment horizon must be a positive whole number of years.")
    formation_date = start - pd.Timedelta(days=1)
    dates = source.loc[source["Date"].le(formation_date), "Date"]
    if dates.empty:
        return []
    market_date = pd.Timestamp(dates.max()).normalize()
    formation = source[source["Date"].eq(market_date)].copy()
    formation = formation[formation["Issuance date"] < start]
    if formation.empty:
        return []
    target = (start + pd.DateOffset(years=int(horizon_years))).normalize()
    max_maturity = formation["Maturity"].max()
    if pd.isna(max_maturity) or max_maturity < target:
        return []
    max_offset = max(0, int(math.floor((pd.Timestamp(max_maturity) - target).days / 365.25)))
    possible = []
    for offset in range(max_offset + 1):
        window_end = (target + pd.DateOffset(years=offset)).normalize()
        window_start = (window_end - pd.DateOffset(months=6)).normalize()
        eligible = formation[formation["Maturity"].between(window_start, window_end, inclusive="both")]
        if not eligible.empty:
            possible.append(offset)
    return possible


def _prepare_security_panel(source: pd.DataFrame, isins: list[str], formation_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    # Seed the calendar grid with the last observed market data before the
    # notional formation date, so weekend/holiday dates can be forward-filled.
    subset = source[source["ISIN"].isin(isins) & source["Date"].le(end_date)].copy()
    if subset.empty:
        raise ValueError("No source observations were found for the selected securities.")
    first_seed_date = min(pd.Timestamp(formation_date), pd.Timestamp(subset["Date"].min()))
    dates = pd.date_range(first_seed_date, end_date, freq="D")
    value_cols = ["Coupon", "Maturity", "Price_Rs", "YTM (Annualized)", "Issuance date", "First IP date", "Prev coupon date", "Accrued Interest", "Gross Price"]
    grid = pd.MultiIndex.from_product([dates, isins], names=["Date", "ISIN"]).to_frame(index=False)
    panel = grid.merge(subset[["Date", "ISIN"] + value_cols], on=["Date", "ISIN"], how="left", validate="one_to_one")
    panel = panel.sort_values(["ISIN", "Date"]).reset_index(drop=True)
    panel[value_cols] = panel.groupby("ISIN", sort=False)[value_cols].ffill()

    # Preserve the original model's rule: freeze clean price, accrued interest
    # and gross price after maturity, while the matured allocation earns repo.
    for isin, group in panel.groupby("ISIN", sort=False):
        maturities = group["Maturity"].dropna()
        if maturities.empty:
            continue
        maturity = pd.Timestamp(maturities.iloc[0]).normalize()
        before = group[group["Date"].le(maturity)]
        if before.empty:
            continue
        last = before.iloc[-1]
        mask = panel["ISIN"].eq(isin) & panel["Date"].gt(maturity)
        for col in ["Price_Rs", "Accrued Interest", "Gross Price"]:
            panel.loc[mask, col] = last[col]

    panel = panel[panel["Date"].ge(formation_date)].copy()
    formation = panel[panel["Date"].eq(formation_date)]
    if len(formation) != len(isins) or formation["Gross Price"].isna().any() or formation["Gross Price"].le(0).any():
        bad = formation.loc[formation["Gross Price"].isna() | formation["Gross Price"].le(0), ["Date", "ISIN", "Gross Price"]]
        raise ValueError("A selected security lacks a valid gross price on the required formation date after carry-forward: " + str(bad.to_dict("records")))
    return panel.sort_values(["Date", "ISIN"]).reset_index(drop=True)


def _repo_by_date(repo: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    expanded = repo.reindex(repo.index.union(dates)).sort_index().ffill().reindex(dates)
    if expanded.isna().any():
        first = expanded[expanded.isna()].index[0]
        raise ValueError(f"No repo-rate observation exists on or before {first:%d-%b-%Y}.")
    return expanded


def run_backtest(source: pd.DataFrame, repo: pd.Series, start_date: str | pd.Timestamp, horizon_years: int, offset_years: int = 0) -> BacktestResult:
    start = pd.Timestamp(start_date).normalize()
    if start < source["Date"].min() or start > source["Date"].max():
        raise ValueError(f"The selected start date {start:%d-%b-%Y} is outside the G-Sec data coverage ({source['Date'].min():%d-%b-%Y} to {source['Date'].max():%d-%b-%Y}).")
    selected, formation_date, formation_market_date, window_start, window_end = select_portfolio(source, start, int(horizon_years), int(offset_years))
    end = investor_end_date(start, int(horizon_years))
    if end > source["Date"].max():
        raise ValueError(f"The requested end date {end:%d-%b-%Y} exceeds the G-Sec data end date {source['Date'].max():%d-%b-%Y}.")
    isins = selected["ISIN"].tolist()
    panel = _prepare_security_panel(source, isins, formation_date, end)
    dates = pd.date_range(start, end, freq="D")
    repo_dates = _repo_by_date(repo, dates)
    initial_weight = 1.0 / len(selected)
    formation_rows = selected.set_index("ISIN")
    initial_units = {isin: (1000.0 * initial_weight / float(formation_rows.loc[isin, "Gross Price"])) for isin in isins}
    previous_units = initial_units.copy()
    previous_weights = {isin: initial_weight for isin in isins}
    previous_q = None
    previous_z = None
    out = []
    panel_ix = panel.set_index(["Date", "ISIN"])
    for day_i, date in enumerate(dates):
        day_rows = []
        cashflows = {}
        for isin in isins:
            cur = panel_ix.loc[(date, isin)]
            prev = panel_ix.loc[(date - pd.Timedelta(days=1), isin)]
            ai, prev_ai = float(cur["Accrued Interest"]), float(prev["Accrued Interest"])
            cashflows[isin] = (prev_ai * previous_units[isin]) if ai < prev_ai else 0.0
            day_rows.append({"Date": date, "ISIN": isin, "Coupon": cur["Coupon"], "Maturity": cur["Maturity"], "Gross Price": float(cur["Gross Price"]), "YTM": float(cur["YTM (Annualized)" ]), "Accrued Interest": ai, "Previous accrued interest": prev_ai, "Previous gross price": float(prev["Gross Price"]), "Cash flow received": cashflows[isin]})
        total_cashflow = sum(cashflows.values())
        for x in day_rows:
            isin = x["ISIN"]
            prev_weight = initial_weight if day_i == 0 else previous_weights[isin]
            add_units = (total_cashflow * prev_weight / x["Previous gross price"]) if total_cashflow > 0 else 0.0
            units = initial_units[isin] + add_units if day_i == 0 else previous_units[isin] + add_units
            x["Previous day weight"] = prev_weight
            x["Additional units"] = add_units
            x["Final units"] = units
            x["Market value"] = x["Gross Price"] * units
        q = sum(x["Market value"] for x in day_rows)
        if not np.isfinite(q) or q <= 0:
            raise ValueError(f"Invalid portfolio index value on {date:%d-%b-%Y}: {q}")
        for x in day_rows:
            x["Daily weight"] = x["Market value"] / q
            x["Weighted YTM"] = x["Daily weight"] * x["YTM"]
        index_ytm = sum(x["Weighted YTM"] for x in day_rows)
        matured_weight = sum(x["Daily weight"] for x in day_rows if pd.Timestamp(x["Maturity"]).normalize() <= date)
        repo_rate = float(repo_dates.loc[date])
        repo_contribution = matured_weight * repo_rate / 365.0
        daily_return = np.nan if previous_q is None else q / previous_q - 1.0
        z = q * (1.0 + repo_contribution) if day_i == 0 else previous_z * (q / previous_q) * (1.0 + repo_contribution)
        for x in day_rows:
            x.update({"Portfolio index value": q, "Index YTM": index_ytm, "Index return excl. TREPS": daily_return, "Matured securities' weight": matured_weight, "Repo rate": repo_rate, "TREPS return contribution": repo_contribution, "Final index value incl. TREPS": z})
            out.append(x)
        previous_units = {x["ISIN"]: x["Final units"] for x in day_rows}
        previous_weights = {x["ISIN"]: x["Daily weight"] for x in day_rows}
        previous_q, previous_z = q, z
    daily = pd.DataFrame(out)
    last_z = float(daily.loc[daily["Date"].eq(end), "Final index value incl. TREPS"].iloc[0])
    calendar_days = (end - start).days
    rm = calendar_days / 365.0
    annualized = (last_z / 1000.0) ** (1.0 / rm) - 1.0 if rm > 0 else np.nan
    # Entry YTM is the weighted YTM of the securities selected and priced
    # on the portfolio-formation date, not the first backtest day's YTM.
    # The model allocates equal initial weights, so this is the equal-weighted
    # average of the selected securities' formation-date annualized YTMs.
    ytm_start = float(selected["YTM (Annualized)"].mean())
    ytm_end = float(daily.loc[daily["Date"].eq(end), "Index YTM"].iloc[0])
    summary = {"start_date": start, "formation_date": formation_date, "formation_market_date": formation_market_date, "end_date": end, "horizon_years": int(horizon_years), "offset_years": int(offset_years), "security_count": len(selected), "maturity_window_start": window_start, "maturity_window_end": window_end, "base_index_value": 1000.0, "first_daily_index_value": float(daily.loc[daily["Date"].eq(start), "Portfolio index value"].iloc[0]), "final_index_value_excl_TREPS": float(daily.loc[daily["Date"].eq(end), "Portfolio index value"].iloc[0]), "final_index_value_incl_TREPS": last_z, "cumulative_return": last_z / 1000.0 - 1.0, "annualized_return": annualized, "entry_ytm": ytm_start, "exit_ytm": ytm_end, "ytm_change_bps": (ytm_end - ytm_start) * 10000.0, "calendar_days": calendar_days}
    trend_dates = [start]
    for yr in range(1, int(horizon_years) + 1):
        ann = (start + pd.DateOffset(years=yr)).normalize()
        if ann < end:
            trend_dates.append(ann)
    if end not in trend_dates:
        trend_dates.append(end)
    trend = daily[daily["Date"].isin(trend_dates)].drop_duplicates("Date")[["Date", "Index YTM", "Portfolio index value", "Final index value incl. TREPS"]].reset_index(drop=True)
    return BacktestResult(start, formation_date, formation_market_date, end, int(horizon_years), int(offset_years), selected.copy(), daily, summary, trend)


def run_from_files(data_path: str | Path, repo_path: str | Path, start_date: str | pd.Timestamp, horizon_years: int, offset_years: int = 0) -> BacktestResult:
    source = load_market_data(data_path)
    repo = load_repo_rates(repo_path)
    return run_backtest(source, repo, start_date, horizon_years, offset_years)
