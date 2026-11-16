"""Build the supervisory-returns sample, the SQLite database, and the review flags.

Twenty institutions file the same return for twelve quarters. Most filings are
internally consistent. A minority have missing cells, broken accounting
identities, ratios that do not match their components, statistical outliers,
or sharp quarter-on-quarter jumps. This script writes the data and the flag
list that the Streamlit app, the SQL checks and the Power BI model all use.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
REPORTS = ROOT / "reports"
SQL = ROOT / "sql"

SEED = 11
QUARTERS = [f"{year}Q{q}" for year in (2022, 2023, 2024) for q in (1, 2, 3, 4)]
INSTITUTIONS = [
    ("INS01", "Aldermere Bank", "Commercial"),
    ("INS02", "Blackwater Commercial", "Commercial"),
    ("INS03", "Cedar & Holm", "Universal"),
    ("INS04", "Dunwich Savings", "Savings"),
    ("INS05", "Eastlane Mutual", "Mutual"),
    ("INS06", "Fairhaven Trust", "Trust"),
    ("INS07", "Greyharbour Bank", "Commercial"),
    ("INS08", "Highford Retail Bank", "Retail"),
    ("INS09", "Iverson Civic", "Civic"),
    ("INS10", "Juniper Building Society", "Building society"),
    ("INS11", "Keel & Moss", "Commercial"),
    ("INS12", "Lowridge Bank", "Retail"),
    ("INS13", "Marrowgate Savings", "Savings"),
    ("INS14", "Northglass Bank", "Universal"),
    ("INS15", "Orchard Civic", "Civic"),
    ("INS16", "Plover Mutual", "Mutual"),
    ("INS17", "Quayline Bank", "Commercial"),
    ("INS18", "Redwillow Trust", "Trust"),
    ("INS19", "Southmere Building Society", "Building society"),
    ("INS20", "Thornfield Bank", "Retail"),
]


def build_clean(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for code, name, peer in INSTITUTIONS:
        assets = float(rng.uniform(8_000, 85_000))  # £ millions
        for q in QUARTERS:
            assets = assets * float(rng.normal(1.008, 0.012))
            equity_ratio = float(np.clip(rng.normal(0.09, 0.012), 0.05, 0.16))
            equity = assets * equity_ratio
            liabilities = assets - equity
            rwa = assets * float(np.clip(rng.normal(0.62, 0.04), 0.4, 0.85))
            cet1_ratio = float(np.clip(rng.normal(0.145, 0.012), 0.09, 0.22))
            cet1 = rwa * cet1_ratio
            deposits = liabilities * float(np.clip(rng.normal(0.72, 0.04), 0.5, 0.9))
            loans = deposits * float(np.clip(rng.normal(0.84, 0.05), 0.6, 1.15))
            npl_ratio = float(np.clip(rng.normal(0.025, 0.008), 0.004, 0.07))
            npl = loans * npl_ratio
            provisions = npl * float(np.clip(rng.normal(0.62, 0.08), 0.35, 0.95))
            hqla = assets * float(np.clip(rng.normal(0.14, 0.02), 0.07, 0.25))
            outflows = hqla / float(np.clip(rng.normal(1.45, 0.1), 1.05, 2.0))
            lcr = hqla / outflows
            net_income = assets * float(np.clip(rng.normal(0.008, 0.002), -0.004, 0.02))
            rows.append(
                {
                    "institution_id": code,
                    "institution": name,
                    "peer_group": peer,
                    "quarter": q,
                    "total_assets": round(assets, 1),
                    "total_liabilities": round(liabilities, 1),
                    "total_equity": round(equity, 1),
                    "risk_weighted_assets": round(rwa, 1),
                    "cet1_capital": round(cet1, 1),
                    "cet1_ratio": round(cet1_ratio * 100, 2),
                    "gross_loans": round(loans, 1),
                    "deposits": round(deposits, 1),
                    "npl_amount": round(npl, 1),
                    "npl_ratio": round(npl_ratio * 100, 2),
                    "provisions": round(provisions, 1),
                    "hqla": round(hqla, 1),
                    "net_outflows_30d": round(outflows, 1),
                    "lcr": round(lcr * 100, 1),
                    "net_income": round(net_income, 1),
                }
            )
    return pd.DataFrame(rows)


def inject_issues(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Plant the kinds of filing errors a desk actually sees.

    The clean panel is the population. Issues are applied to specific cells
    so the checks have something to find. Nothing here is a label the model
    trains on — the checks are rules, and this function only creates work
    for them.
    """
    df = frame.copy()
    # Stable row picks so the README examples do not move between machines.
    def pick(n: int, salt: int) -> np.ndarray:
        local = np.random.default_rng(SEED + salt)
        return local.choice(df.index.to_numpy(), size=n, replace=False)

    # Missing values a clerk left blank.
    for col, salt in (("npl_amount", 1), ("provisions", 2), ("hqla", 3), ("net_income", 4)):
        for idx in pick(3, salt):
            df.loc[idx, col] = np.nan

    # Extra zero typed into assets — an outlier and an identity break.
    for idx in pick(3, 5):
        df.loc[idx, "total_assets"] = round(float(df.loc[idx, "total_assets"]) * 10, 1)

    # Equity sign error.
    for idx in pick(2, 6):
        df.loc[idx, "total_equity"] = round(-abs(float(df.loc[idx, "total_equity"])), 1)

    # NPL ratio filled in, but it does not match NPL / loans.
    for idx in pick(4, 7):
        df.loc[idx, "npl_ratio"] = round(float(df.loc[idx, "npl_ratio"]) + 6.5, 2)

    # CET1 ratio does not match CET1 / RWA.
    for idx in pick(3, 8):
        df.loc[idx, "cet1_ratio"] = round(float(df.loc[idx, "cet1_ratio"]) + 8, 2)

    # LCR outlier (components left as they were, so this is also a ratio break).
    for idx in pick(3, 9):
        df.loc[idx, "lcr"] = round(float(rng.uniform(450, 900)), 1)

    # Implausible negative loans.
    for idx in pick(2, 10):
        df.loc[idx, "gross_loans"] = round(-abs(float(df.loc[idx, "gross_loans"])) * 0.15, 1)

    return df


def run_checks(df: pd.DataFrame) -> pd.DataFrame:
    """Same rules as sql/checks.sql. Kept in Python so Streamlit can run offline."""
    flags: list[dict] = []
    work = df.copy()
    work["quarter_idx"] = work["quarter"].map({q: i for i, q in enumerate(QUARTERS)})

    def add(row, check, field, severity, detail, value):
        flags.append(
            {
                "institution_id": row.institution_id,
                "institution": row.institution,
                "peer_group": row.peer_group,
                "quarter": row.quarter,
                "check": check,
                "field": field,
                "severity": severity,
                "value": None if pd.isna(value) else round(float(value), 4),
                "detail": detail,
            }
        )

    for row in work.itertuples(index=False):
        for field, label in (
            ("total_assets", "Total assets"),
            ("total_liabilities", "Total liabilities"),
            ("total_equity", "Total equity"),
            ("cet1_capital", "CET1 capital"),
            ("risk_weighted_assets", "Risk-weighted assets"),
            ("gross_loans", "Gross loans"),
            ("deposits", "Deposits"),
            ("npl_amount", "NPL amount"),
            ("npl_ratio", "NPL ratio"),
            ("provisions", "Provisions"),
            ("hqla", "High-quality liquid assets"),
            ("net_outflows_30d", "30-day net outflows"),
            ("lcr", "LCR"),
            ("net_income", "Net income"),
            ("cet1_ratio", "CET1 ratio"),
        ):
            value = getattr(row, field)
            if pd.isna(value):
                add(row, "Missing value", label, "High", f"{label} was left blank.", value)

        if pd.notna(row.total_assets) and pd.notna(row.total_liabilities) and pd.notna(row.total_equity):
            gap = row.total_assets - (row.total_liabilities + row.total_equity)
            if abs(gap) > max(50, 0.02 * abs(row.total_assets)):
                add(
                    row,
                    "Accounting identity",
                    "Total assets",
                    "High",
                    f"Assets minus liabilities minus equity is {gap:,.1f}. Tolerance is 2% of assets.",
                    gap,
                )

        if pd.notna(row.gross_loans) and row.gross_loans < 0:
            add(row, "Sign error", "Gross loans", "High", "Gross loans are negative.", row.gross_loans)
        if pd.notna(row.total_equity) and row.total_equity < 0:
            add(row, "Sign error", "Total equity", "High", "Total equity is negative.", row.total_equity)
        if pd.notna(row.total_assets) and row.total_assets <= 0:
            add(row, "Sign error", "Total assets", "High", "Total assets are not positive.", row.total_assets)

        if pd.notna(row.cet1_capital) and pd.notna(row.risk_weighted_assets) and row.risk_weighted_assets > 0 and pd.notna(row.cet1_ratio):
            implied = 100 * row.cet1_capital / row.risk_weighted_assets
            if abs(implied - row.cet1_ratio) > 1.0:
                add(
                    row,
                    "Ratio does not match components",
                    "CET1 ratio",
                    "High",
                    f"Reported CET1 ratio is {row.cet1_ratio:.2f}%. CET1 / RWA is {implied:.2f}%.",
                    row.cet1_ratio,
                )

        if pd.notna(row.npl_amount) and pd.notna(row.gross_loans) and row.gross_loans > 0 and pd.notna(row.npl_ratio):
            implied = 100 * row.npl_amount / row.gross_loans
            if abs(implied - row.npl_ratio) > 1.0:
                add(
                    row,
                    "Ratio does not match components",
                    "NPL ratio",
                    "High",
                    f"Reported NPL ratio is {row.npl_ratio:.2f}%. NPL / loans is {implied:.2f}%.",
                    row.npl_ratio,
                )

        if (
            pd.notna(row.hqla)
            and pd.notna(row.net_outflows_30d)
            and row.net_outflows_30d > 0
            and pd.notna(row.lcr)
        ):
            implied = 100 * row.hqla / row.net_outflows_30d
            if abs(implied - row.lcr) > 5:
                add(
                    row,
                    "Ratio does not match components",
                    "LCR",
                    "Medium",
                    f"Reported LCR is {row.lcr:.1f}%. HQLA / net outflows is {implied:.1f}%.",
                    row.lcr,
                )

        # Hard plausibility bounds. These catch typos even when there is no peer history yet.
        bounds = {
            "cet1_ratio": (4, 35, "CET1 ratio"),
            "npl_ratio": (0, 25, "NPL ratio"),
            "lcr": (40, 350, "LCR"),
        }
        for field, (lo, hi, label) in bounds.items():
            value = getattr(row, field)
            if pd.notna(value) and (value < lo or value > hi):
                add(
                    row,
                    "Outside plausibility bound",
                    label,
                    "High",
                    f"{label} is {value:.2f}, outside {lo}–{hi}.",
                    value,
                )

    # Peer outliers within quarter, robust z-score on a few stock ratios.
    # Computed only where the cell is present. A ratio already flagged as a
    # component break can also be an outlier; both reasons are kept.
    for field, label in (
        ("cet1_ratio", "CET1 ratio"),
        ("npl_ratio", "NPL ratio"),
        ("lcr", "LCR"),
        ("total_assets", "Total assets"),
    ):
        for quarter, g in work.groupby("quarter"):
            series = g[field].dropna()
            if len(series) < 8:
                continue
            median = series.median()
            mad = np.median(np.abs(series - median))
            if mad == 0:
                continue
            for row in g.itertuples(index=False):
                value = getattr(row, field)
                if pd.isna(value):
                    continue
                robust_z = 0.6745 * (value - median) / mad
                if abs(robust_z) >= 4.5:
                    add(
                        row,
                        "Peer outlier",
                        label,
                        "Medium",
                        f"{label} robust z-score versus the other filings this quarter is {robust_z:.1f}.",
                        value,
                    )

    # Own-history jump. Compare each institution with its previous quarter.
    work = work.sort_values(["institution_id", "quarter_idx"])
    for field, label, limit in (
        ("cet1_ratio", "CET1 ratio", 4.0),
        ("npl_ratio", "NPL ratio", 3.0),
        ("lcr", "LCR", 60.0),
        ("total_assets", "Total assets", None),
    ):
        previous = work.groupby("institution_id")[field].shift(1)
        current = work[field]
        if field == "total_assets":
            jump = (current - previous).abs() / previous.abs()
            mask = jump > 0.35
        else:
            jump = (current - previous).abs()
            mask = jump > limit
        for row, delta, prev in zip(
            work[mask.fillna(False)].itertuples(index=False),
            jump[mask.fillna(False)],
            previous[mask.fillna(False)],
        ):
            if pd.isna(getattr(row, field)):
                continue
            if field == "total_assets":
                detail = f"Total assets moved {delta:.0%} versus the previous quarter ({prev:,.1f} → {getattr(row, field):,.1f})."
            else:
                detail = f"{label} moved by {delta:.2f} versus the previous quarter ({prev:.2f} → {getattr(row, field):.2f})."
            add(row, "Quarter-on-quarter jump", label, "Medium", detail, getattr(row, field))

    flag_frame = pd.DataFrame(flags)
    if flag_frame.empty:
        return flag_frame
    flag_frame.insert(0, "flag_id", [f"F{i:04d}" for i in range(1, len(flag_frame) + 1)])
    return flag_frame


def write_sql() -> None:
    SQL.mkdir(parents=True, exist_ok=True)
    (SQL / "checks.sql").write_text(
        """-- Supervisory return checks.
-- The database is data/returns.db. Tables: submissions, institutions.
-- These queries are the same rules as analysis.py and the Streamlit app.
-- Amounts are in £ millions. Ratios are in percent.

-- 1. Blank cells that a reviewer has to send back.
SELECT institution_id, institution, quarter, 'Missing value' AS check_name, 'NPL amount' AS field
FROM submissions WHERE npl_amount IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'Provisions'
FROM submissions WHERE provisions IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'HQLA'
FROM submissions WHERE hqla IS NULL
UNION ALL
SELECT institution_id, institution, quarter, 'Missing value', 'Net income'
FROM submissions WHERE net_income IS NULL;

-- 2. Assets should equal liabilities + equity, within 2% of assets (and at least 50).
SELECT institution_id, institution, quarter,
       total_assets - (total_liabilities + total_equity) AS gap
FROM submissions
WHERE total_assets IS NOT NULL
  AND total_liabilities IS NOT NULL
  AND total_equity IS NOT NULL
  AND ABS(total_assets - (total_liabilities + total_equity))
        > MAX(50, 0.02 * ABS(total_assets));

-- 3. Reported CET1 ratio should match CET1 capital / risk-weighted assets.
SELECT institution_id, institution, quarter, cet1_ratio AS reported,
       ROUND(100.0 * cet1_capital / risk_weighted_assets, 2) AS implied
FROM submissions
WHERE risk_weighted_assets > 0
  AND cet1_capital IS NOT NULL
  AND cet1_ratio IS NOT NULL
  AND ABS(cet1_ratio - (100.0 * cet1_capital / risk_weighted_assets)) > 1.0;

-- 4. Reported NPL ratio should match NPL amount / gross loans.
SELECT institution_id, institution, quarter, npl_ratio AS reported,
       ROUND(100.0 * npl_amount / gross_loans, 2) AS implied
FROM submissions
WHERE gross_loans > 0
  AND npl_amount IS NOT NULL
  AND npl_ratio IS NOT NULL
  AND ABS(npl_ratio - (100.0 * npl_amount / gross_loans)) > 1.0;

-- 5. Reported LCR should match HQLA / 30-day net outflows.
SELECT institution_id, institution, quarter, lcr AS reported,
       ROUND(100.0 * hqla / net_outflows_30d, 1) AS implied
FROM submissions
WHERE net_outflows_30d > 0
  AND hqla IS NOT NULL
  AND lcr IS NOT NULL
  AND ABS(lcr - (100.0 * hqla / net_outflows_30d)) > 5;

-- 6. Sign errors.
SELECT institution_id, institution, quarter, 'Gross loans' AS field, gross_loans AS value
FROM submissions WHERE gross_loans < 0
UNION ALL
SELECT institution_id, institution, quarter, 'Total equity', total_equity
FROM submissions WHERE total_equity < 0;

-- 7. Plausibility bounds (percent).
SELECT institution_id, institution, quarter, 'CET1 ratio' AS field, cet1_ratio AS value
FROM submissions WHERE cet1_ratio < 4 OR cet1_ratio > 35
UNION ALL
SELECT institution_id, institution, quarter, 'NPL ratio', npl_ratio
FROM submissions WHERE npl_ratio < 0 OR npl_ratio > 25
UNION ALL
SELECT institution_id, institution, quarter, 'LCR', lcr
FROM submissions WHERE lcr < 40 OR lcr > 350;

-- Peer outliers and quarter-on-quarter jumps are easier to express with window
-- functions. SQLite supports both.

-- 8. Peer outlier: robust z-score of at least 4.5 within the quarter.
WITH stats AS (
  SELECT quarter,
         AVG(lcr) AS mean_lcr -- placeholder, robust stats are computed in analysis.py
  FROM submissions
  GROUP BY quarter
)
SELECT * FROM stats LIMIT 0;

-- The robust (median / MAD) z-score is computed in analysis.py because SQLite
-- has no MEDIAN aggregate until very recent builds. The query below is the
-- mean/stddev version a reviewer can run anywhere; the app uses the robust one.
WITH stats AS (
  SELECT quarter,
         AVG(npl_ratio) AS mu,
         -- sample stddev
         SQRT(AVG(npl_ratio * npl_ratio) - AVG(npl_ratio) * AVG(npl_ratio)) AS sigma
  FROM submissions
  WHERE npl_ratio IS NOT NULL
  GROUP BY quarter
)
SELECT s.institution_id, s.institution, s.quarter, s.npl_ratio,
       ROUND((s.npl_ratio - stats.mu) / stats.sigma, 2) AS z_score
FROM submissions s
JOIN stats ON stats.quarter = s.quarter
WHERE stats.sigma > 0
  AND ABS(s.npl_ratio - stats.mu) / stats.sigma >= 3;
""",
        encoding="utf-8",
    )


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    clean = build_clean(rng)
    filings = inject_issues(clean, rng)
    filings.to_csv(DATA / "submissions.csv", index=False)

    institutions = pd.DataFrame(INSTITUTIONS, columns=["institution_id", "institution", "peer_group"])
    institutions.to_csv(DATA / "institutions.csv", index=False)
    pd.DataFrame({"quarter": QUARTERS, "quarter_idx": range(len(QUARTERS))}).to_csv(
        DATA / "quarters.csv", index=False
    )

    flags = run_checks(filings)
    flags.to_csv(DATA / "flags.csv", index=False)

    db_path = DATA / "returns.db"
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as con:
        filings.to_sql("submissions", con, index=False)
        institutions.to_sql("institutions", con, index=False)
        flags.to_sql("flags", con, index=False)

    by_check = (
        flags.groupby("check").size().rename("count").reset_index().sort_values("count", ascending=False)
    )
    by_quarter = flags.groupby("quarter").size().rename("count").reset_index()
    by_quarter["quarter_idx"] = by_quarter["quarter"].map({q: i for i, q in enumerate(QUARTERS)})
    by_quarter = by_quarter.sort_values("quarter_idx")
    by_severity = flags.groupby("severity").size().rename("count").reset_index()

    # One row per filing with how many flags landed on it, for the queue.
    key = ["institution_id", "quarter"]
    counts = flags.groupby(key).size().rename("flag_count")
    queue = filings.merge(counts, on=key, how="left")
    queue["flag_count"] = queue["flag_count"].fillna(0).astype(int)

    payload = {
        "submissions": int(len(filings)),
        "institutions": int(filings["institution_id"].nunique()),
        "quarters": QUARTERS,
        "flag_count": int(len(flags)),
        "filings_with_flags": int((queue["flag_count"] > 0).sum()),
        "by_check": by_check.to_dict(orient="records"),
        "by_quarter": by_quarter[["quarter", "count"]].to_dict(orient="records"),
        "by_severity": by_severity.to_dict(orient="records"),
        "flags": json.loads(flags.to_json(orient="records")),
        "queue": json.loads(
            queue.sort_values(["flag_count", "institution"], ascending=[False, True]).to_json(orient="records")
        ),
    }
    (REPORTS / "metrics.json").write_text(
        json.dumps(
            {
                "submissions": payload["submissions"],
                "institutions": payload["institutions"],
                "flag_count": payload["flag_count"],
                "filings_with_flags": payload["filings_with_flags"],
                "by_check": payload["by_check"],
                "by_quarter": payload["by_quarter"],
                "by_severity": payload["by_severity"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    web = ROOT.parents[1] / "src" / "data"
    web.mkdir(parents=True, exist_ok=True)
    (web / "returns.json").write_text(json.dumps(payload), encoding="utf-8")
    write_sql()
    print(
        json.dumps(
            {
                "submissions": payload["submissions"],
                "flags": payload["flag_count"],
                "filings_with_flags": payload["filings_with_flags"],
                "by_check": payload["by_check"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
