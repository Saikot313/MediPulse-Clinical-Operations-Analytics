# Query performance

Synthetic data: 300,000 visits, 129,586 lab orders, 100,000 patients. PostgreSQL, median of 3 warm runs.
Reproduce: `python -m medipulse benchmark --visits 300000`.

| Query | No indexes (ms) | With indexes (ms) | Materialised (ms) | Speed-up vs baseline |
|---|---:|---:|---:|---:|
| Daily KPIs, last 90 days | 22.9 | 25.7 | - | 0.9x |
| Doctor utilisation, latest month | 14.5 | 11.1 | - | 1.3x |
| Lab turnaround by test | 92.7 | 99.5 | - | 0.9x |
| 30-day return rate (window fn) | 252.6 | 259.6 | 0.7 | 374.8x |
| Patient retention cohorts | 320.4 | 338.9 | 0.5 | 631.8x |
