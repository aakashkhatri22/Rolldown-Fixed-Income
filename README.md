# ROLLOVER — Indian Fixed Income Analytics

### Can investors earn additional returns by investing beyond their investment horizon without taking additional credit risk?

## Overview

ROLLOVER is an interactive backtesting application that evaluates whether investing in longer-maturity Indian Government Securities (G-Secs) and selling them at the end of a defined investment horizon could generate higher returns than a conventional hold-to-maturity strategy.

The project explores whether investors can benefit from yield-curve rolldown and bond price movements by investing beyond their intended investment horizon.

## Credit Risk Versus Interest-Rate Risk

The project uses Government Securities to focus on interest-rate and market-price risk without introducing the additional credit risk associated with corporate bonds. However, avoiding corporate credit risk does not eliminate investment risk. Longer-maturity G-Secs can be more sensitive to interest-rate changes, and selling before maturity can result in capital losses.

ROLLOVER investigates whether investing beyond the investment horizon could generate incremental returns while maintaining exposure to Government Securities rather than moving into lower-credit-quality securities.

## Key Features

- Select an investment start date and investment horizon.
- Compare alternative security-maturity strategies.
- Analyse historical portfolio returns and yield movements.
- Explore index performance, portfolio details and strategy outcomes through an interactive dashboard.

## Methodology

The backtesting framework uses historical G-Sec prices, yields and repo-rate data to evaluate strategies across different investment horizons and maturity profiles. It examines whether potential rolldown benefits outweigh the risks arising from changes in market yields.

## Technology Stack

Python · Streamlit · Pandas · NumPy · Plotly

## How to Use

Open the application, select the investment start date, investment horizon and maturity case, then click **Run Backtest** to explore the results.

## Disclaimer

This project is intended for research and educational purposes only and does not constitute investment advice. Historical returns do not guarantee future performance. Government Securities are subject to interest-rate and market-price risk, particularly when sold before maturity.
