from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from rolldown_engine_prototype_v4 import (
    get_possible_offsets,
    load_market_data,
    load_repo_rates,
    run_backtest,
)

st.set_page_config(
    page_title="FIXED INCOME STRATEGY - ROLLDOWN | Indian Fixed Income Analytics",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root { color-scheme: dark; }
    .stApp { background: #0b1220; color: #edf2f7; }
    [data-testid="stSidebar"] { background: #101a2b; border-right: 1px solid #24334a; }
    [data-testid="stHeader"] { background: rgba(11,18,32,0.92); }
    h1, h2, h3 { color: #f5f8fc; letter-spacing: -0.02em; }
    .hero { padding: 1.15rem 1.35rem; border: 1px solid #263a52; border-radius: 16px;
            background: linear-gradient(120deg, #14233a 0%, #0e1a2c 60%, #102b35 100%); margin-bottom: 1rem; }
    .eyebrow { color: #61d6c5; font-size: 0.76rem; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; }
    .hero h1 { margin: .25rem 0 .2rem 0; font-size: 2.15rem; }
    .hero p { margin: 0; color: #aebed1; }
    div[data-testid="stMetric"] { background: #111d30; border: 1px solid #24364d; padding: 0.85rem 1rem; border-radius: 12px; }
    div[data-testid="stMetricLabel"] { color: #aebed1; }
    div[data-testid="stMetricValue"] { color: #f4f7fb; }
    div.stButton > button { background: #42d6c3; color: #071522; border: 0; font-weight: 700; border-radius: 9px; }
    div.stButton > button:hover { background: #70e6d7; color: #071522; }
    .small-muted { color: #9aabc0; font-size: .86rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Loading the bundled G-Sec and repo datasets…")
def load_bundled_inputs(gsec_path: str, repo_path: str):
    """Load the fixed market datasets bundled with the application."""
    source = load_market_data(gsec_path)
    repo = load_repo_rates(repo_path)
    return source, repo


def fmt_pct(value: float) -> str:
    return f"{value * 100:,.2f}%"


def fmt_index(value: float) -> str:
    return f"{value:,.2f}"


st.markdown(
    """
    <div class="hero">
      <div class="eyebrow">Indian Fixed Income Analytics</div>
      <h1>FIXED INCOME STRATEGY - ROLLDOWN</h1>
      <p>Yield-curve rolldown backtesting for Government Securities — with daily portfolio, yield and TREPS analytics.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# The source datasets are bundled with the application and are not exposed to end users.
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
GSEC_DATA_PATH = DATA_DIR / "Gsec daily price data.xlsx"
REPO_DATA_PATH = DATA_DIR / "Daily_Repo.xlsx"

try:
    source, repo = load_bundled_inputs(str(GSEC_DATA_PATH), str(REPO_DATA_PATH))
except Exception as exc:
    st.error(f"The bundled market datasets could not be loaded: {exc}")
    st.info("The application package may be incomplete. Please reinstall or rebuild the ROLLOVER package.")
    st.stop()

with st.sidebar:
    st.markdown("### Strategy configuration")
    st.caption("Choose the strategy assumptions, then run the backtest.")

min_data_date = pd.Timestamp(source["Date"].min()).normalize()
max_data_date = pd.Timestamp(source["Date"].max()).normalize()

with st.sidebar:
    default_start = pd.Timestamp("2019-01-01").normalize()
    if default_start < min_data_date:
        default_start = min_data_date
    if default_start > max_data_date:
        default_start = max_data_date
    if "rollover_start_date" not in st.session_state:
        st.session_state["rollover_start_date"] = default_start.date()
    else:
        stored_start = pd.Timestamp(st.session_state["rollover_start_date"]).normalize()
        if stored_start < min_data_date or stored_start > max_data_date:
            st.session_state["rollover_start_date"] = default_start.date()
    start_date = st.date_input(
        "Investment start date",
        min_value=min_data_date.date(),
        max_value=max_data_date.date(),
        key="rollover_start_date",
        help="Portfolio formation uses the previous calendar date, as in the existing model.",
    )
    start_ts = pd.Timestamp(start_date).normalize()
    horizon = st.selectbox("Investment horizon", options=[1, 2, 3, 4, 5, 6, 7], index=0, format_func=lambda x: f"{x} year{'s' if x != 1 else ''}")
    requested_end = (start_ts + pd.DateOffset(years=int(horizon)) - pd.Timedelta(days=1)).normalize()
    horizon_valid = requested_end <= max_data_date
    if not horizon_valid:
        st.warning(f"This start date and horizon end on {requested_end:%d-%b-%Y}, beyond the available G-Sec data ending {max_data_date:%d-%b-%Y}. Choose an earlier start date or shorter horizon.")
        available_offsets = []
        offset = 0
    else:
        available_offsets = get_possible_offsets(source, start_ts, int(horizon))
        if not available_offsets:
            st.warning("No eligible maturity cases were found for this start date and horizon.")
            offset = 0
        else:
            preferred_offset_index = available_offsets.index(0) if 0 in available_offsets else 0
            def case_label(value: int) -> str:
                if value == 0:
                    return "Case 1: Held till maturity"
                return f"Case {value + 1}: {int(horizon) + value} Year to {value} Year"
            offset = st.selectbox("Maturity case", options=available_offsets, index=preferred_offset_index, format_func=case_label)
            st.caption(f"Showing {len(available_offsets)} available case(s); unavailable cases are excluded.")
    run_now = st.button("Run backtest", use_container_width=True, disabled=(not horizon_valid or not available_offsets))
    st.divider()
    st.markdown("<div class='small-muted'>Historical G-Sec and repo data are bundled with this application. Users do not need to upload files or install Excel.</div>", unsafe_allow_html=True)

# A backtest is executed only after the user explicitly clicks the button.
# If any setting changes after a prior run, do not show stale results for the new settings.
run_key = (str(start_ts.date()), int(horizon), int(offset))
previous_run_key = st.session_state.get("rollover_run_key")
if run_now:
    st.session_state.pop("rollover_comparison", None)
    try:
        with st.spinner("Running the backtest and preparing portfolio analytics…"):
            result = run_backtest(source, repo, start_ts, int(horizon), int(offset))
        st.session_state["rollover_result"] = result
        st.session_state["rollover_run_key"] = run_key
    except Exception as exc:
        st.session_state.pop("rollover_result", None)
        st.session_state.pop("rollover_run_key", None)
        st.error(f"Backtest could not be completed: {exc}")
        st.stop()

result = st.session_state.get("rollover_result")
if result is None or previous_run_key != run_key and not run_now:
    st.info("Select the start date, investment horizon and maturity case, then click **Run backtest**. Results are not generated automatically.")
    st.stop()

summary = result.summary
daily = result.daily.copy()
daily_dates = daily.drop_duplicates("Date").sort_values("Date").copy()
daily_dates["Cumulative return incl. TREPS"] = daily_dates["Final index value incl. TREPS"] / 1000.0 - 1.0
daily_dates["Cumulative return excl. TREPS"] = daily_dates["Portfolio index value"] / 1000.0 - 1.0
daily_dates["Date label"] = daily_dates["Date"].dt.strftime("%d-%b-%Y")

st.caption(
    f"Period: {summary['start_date']:%d %b %Y} – {summary['end_date']:%d %b %Y}  ·  "
    f"Portfolio formation date: {summary['formation_date']:%d %b %Y}  ·  "
    f"Data coverage: {min_data_date:%d %b %Y} – {max_data_date:%d %b %Y}"
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Cumulative return", fmt_pct(summary["cumulative_return"]))
k2.metric("Annualized return", fmt_pct(summary["annualized_return"]))
k3.metric("Final index value", fmt_index(summary["final_index_value_incl_TREPS"]))
k4.metric("Entry index YTM", fmt_pct(summary["entry_ytm"]))
k5.metric("YTM change", f"{summary['ytm_change_bps']:+,.1f} bps")

overview, performance, yields, portfolio, methodology = st.tabs(["Overview", "Performance", "Yield analysis", "Portfolio details", "Methodology & data"])

with overview:
    left, right = st.columns([1.55, 1])
    with left:
        st.subheader("Index growth")
        chart = px.line(
            daily_dates,
            x="Date",
            y=["Portfolio index value", "Final index value incl. TREPS"],
            labels={"value": "Index value", "Date": "Date", "variable": "Series"},
            template="plotly_dark",
        )
        chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="", margin=dict(l=10,r=10,t=20,b=10), height=360)
        chart.update_xaxes(showgrid=False)
        chart.update_yaxes(gridcolor="#24334a")
        st.plotly_chart(chart, use_container_width=True)
    with right:
        st.subheader("Strategy snapshot")
        snapshot = pd.DataFrame({"Metric": ["Investment horizon", "Maturity offset", "Securities selected", "Maturity window start", "Maturity window end", "Formation market date", "Calendar days"],
                                 "Value": [f"{summary['horizon_years']} year(s)", f"{summary['offset_years']} year(s)", summary["security_count"], f"{summary['maturity_window_start']:%d-%b-%Y}", f"{summary['maturity_window_end']:%d-%b-%Y}", f"{summary['formation_market_date']:%d-%b-%Y}", summary["calendar_days"]]})
        st.dataframe(snapshot, hide_index=True, use_container_width=True)
        st.subheader("Entry vs exit YTM")
        ytm_comp = pd.DataFrame({"Point": ["Entry", "Exit"], "YTM (%)": [summary["entry_ytm"] * 100, summary["exit_ytm"] * 100]})
        ytm_bar = px.bar(ytm_comp, x="Point", y="YTM (%)", text_auto=".2f", template="plotly_dark")
        ytm_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10,r=10,t=20,b=10), height=260)
        st.plotly_chart(ytm_bar, use_container_width=True)

with performance:
    st.subheader("Performance through time")
    p1, p2 = st.columns(2)
    with p1:
        perf = px.line(daily_dates, x="Date", y="Cumulative return incl. TREPS", labels={"Cumulative return incl. TREPS": "Cumulative return", "Date": "Date"}, template="plotly_dark")
        perf.update_layout(yaxis_tickformat=".1%", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10,r=10,t=20,b=10), height=340)
        st.plotly_chart(perf, use_container_width=True)
    with p2:
        daily_dates["Daily return incl. TREPS"] = daily_dates["Final index value incl. TREPS"].pct_change()
        daily_ret = px.bar(daily_dates, x="Date", y="Daily return incl. TREPS", labels={"Daily return incl. TREPS": "Daily return", "Date": "Date"}, template="plotly_dark")
        daily_ret.update_layout(yaxis_tickformat=".2%", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10,r=10,t=20,b=10), height=340)
        st.plotly_chart(daily_ret, use_container_width=True)
    st.subheader("Compare maturity offsets")
    st.caption("Runs the same start date and investment horizon for each available maturity case using the datasets bundled with this application.")
    if st.button("Calculate all available offsets", key="compare_offsets"):
        comparison_rows = []
        progress = st.progress(0, text="Calculating offsets…")
        for i, candidate_offset in enumerate(available_offsets):
            try:
                comp_result = run_backtest(source, repo, start_ts, int(horizon), int(candidate_offset))
                s = comp_result.summary
                case_name = "Case 1: Held till maturity" if candidate_offset == 0 else f"Case {candidate_offset + 1}: {int(horizon) + candidate_offset} Year to {candidate_offset} Year"
                comparison_rows.append({"Maturity case": case_name, "Securities": s["security_count"], "Cumulative return": s["cumulative_return"], "Annualized return": s["annualized_return"], "Entry YTM": s["entry_ytm"], "Exit YTM": s["exit_ytm"], "YTM change (bps)": s["ytm_change_bps"], "Final index": s["final_index_value_incl_TREPS"]})
            except Exception as exc:
                case_name = "Case 1: Held till maturity" if candidate_offset == 0 else f"Case {candidate_offset + 1}: {int(horizon) + candidate_offset} Year to {candidate_offset} Year"
                comparison_rows.append({"Maturity case": case_name, "Error": str(exc)})
            progress.progress((i + 1) / len(available_offsets), text=f"Calculated offset {candidate_offset} ({i+1}/{len(available_offsets)})")
        st.session_state["rollover_comparison"] = pd.DataFrame(comparison_rows)
    if "rollover_comparison" in st.session_state:
        comp_df = st.session_state["rollover_comparison"]
        if "Annualized return" in comp_df.columns:
            display_comp = comp_df.copy()
            for col in ["Cumulative return", "Annualized return", "Entry YTM", "Exit YTM"]:
                if col in display_comp:
                    display_comp[col] = display_comp[col].map(lambda x: f"{x:.2%}" if pd.notna(x) and isinstance(x, (int,float)) else x)
            st.dataframe(display_comp, hide_index=True, use_container_width=True)
            valid = comp_df.dropna(subset=["Annualized return"])
            if not valid.empty:
                cmp_chart = px.bar(valid, x="Maturity case", y="Annualized return", labels={"Annualized return": "Annualized return", "Maturity case": "Maturity case"}, template="plotly_dark", text_auto=".2%")
                cmp_chart.update_layout(yaxis_tickformat=".1%", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10,r=10,t=20,b=10), height=330)
                st.plotly_chart(cmp_chart, use_container_width=True)
        csv = comp_df.to_csv(index=False).encode("utf-8")
        st.download_button("Download offset comparison CSV", csv, file_name="rolldown_offset_comparison.csv", mime="text/csv")

with yields:
    st.subheader("Weighted portfolio YTM")
    ytm_line = px.line(daily_dates, x="Date", y="Index YTM", labels={"Index YTM": "Weighted YTM", "Date": "Date"}, template="plotly_dark")
    ytm_line.update_layout(yaxis_tickformat=".2%", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10,r=10,t=20,b=10), height=360)
    st.plotly_chart(ytm_line, use_container_width=True)
    st.dataframe(result.ytm_trend.assign(**{"Index YTM (%)": result.ytm_trend["Index YTM"].map(lambda x: f"{x:.2%}")})[["Date", "Index YTM (%)", "Portfolio index value", "Final index value incl. TREPS"]], hide_index=True, use_container_width=True)
    st.caption("YTM is the portfolio's daily weighted YTM from the underlying security YTMs; it is not a forecast of realized investment return.")

with portfolio:
    st.subheader("Initial portfolio composition")
    portfolio_df = result.portfolio.copy()
    portfolio_df["Initial weight (%)"] = 100.0 / len(portfolio_df)
    portfolio_view = portfolio_df.rename(columns={"ISIN": "ISIN", "Coupon": "Coupon (%)", "Maturity": "Maturity date", "Price_Rs": "Clean price", "Gross Price": "Gross price", "YTM (Annualized)": "Entry YTM", "Accrued Interest": "Accrued interest"})
    for col in ["Coupon (%)", "Entry YTM"]:
        if col in portfolio_view:
            portfolio_view[col] = portfolio_view[col].map(lambda x: f"{x:.2f}%" if pd.notna(x) and col == "Coupon (%)" else (f"{x:.2%}" if pd.notna(x) else ""))
    keep = [c for c in ["ISIN", "Coupon (%)", "Maturity date", "Clean price", "Accrued interest", "Gross price", "Entry YTM", "Initial weight (%)"] if c in portfolio_view.columns]
    st.dataframe(portfolio_view[keep], hide_index=True, use_container_width=True)
    st.download_button("Download portfolio composition CSV", portfolio_view[keep].to_csv(index=False).encode("utf-8"), file_name="rolldown_portfolio_composition.csv", mime="text/csv")
    st.subheader("Daily portfolio / security-level data")
    available_cols = ["Date", "ISIN", "Gross Price", "Final units", "Market value", "Daily weight", "YTM", "Weighted YTM", "Cash flow received", "Matured securities' weight", "Repo rate", "TREPS return contribution", "Portfolio index value", "Final index value incl. TREPS"]
    selected_cols = st.multiselect("Fields to display", options=available_cols, default=["Date", "ISIN", "Gross Price", "Market value", "Daily weight", "YTM", "Cash flow received", "Matured securities' weight", "Portfolio index value", "Final index value incl. TREPS"])
    st.dataframe(daily[selected_cols], hide_index=True, use_container_width=True, height=430)
    st.download_button("Download full daily security data CSV", daily.to_csv(index=False).encode("utf-8"), file_name="rolldown_daily_security_data.csv", mime="text/csv")

with methodology:
    st.subheader("Methodology used by this prototype")
    st.markdown(
        """
        - **Portfolio formation:** the portfolio is formed using the previous calendar date's data, subject to the original issuance-date eligibility rule.
        - **Maturity window:** securities are selected from the six-month window ending at the investment horizon plus the chosen maturity offset.
        - **Initial allocation:** selected securities receive equal initial weights; initial units are derived from the selected security's gross price.
        - **Entry YTM:** the initial portfolio's equal-weighted YTM calculated from the selected securities' formation-date YTMs, not the first backtest day's weighted YTM.
        - **Coupon cash flow:** a fall in accrued interest versus the previous calendar date is treated as a coupon cash-flow event, following the existing spreadsheet formula.
        - **Reinvestment:** coupon proceeds are allocated using previous-day weights and previous-day gross prices, consistent with the ported calculation logic.
        - **Matured securities:** the clean price, accrued interest and gross price are frozen after maturity; the matured portfolio weight contributes to the repo/TREPS adjustment.
        - **Index reporting:** the app shows both the portfolio index excluding TREPS and the final index including the repo/TREPS adjustment.
        - **Return reporting:** cumulative and annualized returns are calculated from the 1,000 base index value. No monetary investment outcome is displayed.
        """
    )
    st.warning("Prototype status: this dashboard is for research and model validation. The core calculation engine has been compared with recalculated spreadsheet formulas for selected cases, but broader regression tests and final Windows packaging are still required.")
    st.subheader("Data coverage and checks")
    diag = pd.DataFrame({"Check": ["G-Sec rows", "Unique G-Sec dates", "G-Sec first date", "G-Sec last date", "Blank YTM observations", "Duplicate date–ISIN rows", "Repo observations", "Repo first date", "Repo last date"],
                         "Value": [len(source), source["Date"].nunique(), f"{min_data_date:%d-%b-%Y}", f"{max_data_date:%d-%b-%Y}", int(source["YTM (Annualized)"].isna().sum()), int(source.duplicated(["Date", "ISIN"]).sum()), len(repo), f"{repo.index.min():%d-%b-%Y}", f"{repo.index.max():%d-%b-%Y}"]})
    st.dataframe(diag, hide_index=True, use_container_width=True)

st.markdown("<div class='small-muted'>FIXED INCOME STRATEGY - ROLLDOWN prototype · Built for Indian fixed-income research · Verify methodology and source-data permissions before publishing.</div>", unsafe_allow_html=True)
