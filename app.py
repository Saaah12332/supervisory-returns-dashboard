"""Review desk for supervisory returns.

Reads the filings, runs the same checks as analysis.py, and lists every
flag with the reason a reviewer would send the return back.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from analysis import run_checks

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _label(frame: pd.DataFrame, flag_id: str) -> str:
    row = frame[frame["flag_id"] == flag_id].iloc[0]
    return f"{row['flag_id']} · {row['institution']} · {row['quarter']} · {row['check']}"

st.set_page_config(page_title="Supervisory returns", layout="wide")
st.title("Supervisory returns")
st.caption(
    "Missing values, broken identities, ratios that do not match their components, "
    "peer outliers and quarter-on-quarter jumps. A flag is a request to look, not a verdict on the institution."
)

submissions = pd.read_csv(DATA / "submissions.csv")
flags = run_checks(submissions)
if flags.empty:
    st.success("No flags on this extract.")
    st.stop()

with st.sidebar:
    st.header("Filter the queue")
    institutions = ["All institutions"] + sorted(flags["institution"].unique())
    quarters = ["All quarters"] + sorted(flags["quarter"].unique())
    checks = ["All checks"] + sorted(flags["check"].unique())
    severities = ["All severities"] + sorted(flags["severity"].unique())
    institution = st.selectbox("Institution", institutions)
    quarter = st.selectbox("Quarter", quarters)
    check = st.selectbox("Check", checks)
    severity = st.selectbox("Severity", severities)

view = flags.copy()
if institution != "All institutions":
    view = view[view["institution"] == institution]
if quarter != "All quarters":
    view = view[view["quarter"] == quarter]
if check != "All checks":
    view = view[view["check"] == check]
if severity != "All severities":
    view = view[view["severity"] == severity]

filings_flagged = view.groupby(["institution_id", "quarter"]).ngroups
c1, c2, c3, c4 = st.columns(4)
c1.metric("Filings in the extract", f"{len(submissions):,}")
c2.metric("Flags", f"{len(view):,}")
c3.metric("Filings with a flag", f"{filings_flagged:,}")
c4.metric("Institutions in the queue", f"{view['institution'].nunique():,}")

left, right = st.columns(2)
with left:
    st.subheader("Flags by quarter")
    by_quarter = view.groupby("quarter").size().rename("flags").reset_index()
    st.bar_chart(by_quarter, x="quarter", y="flags")
with right:
    st.subheader("Flags by check")
    by_check = view.groupby("check").size().rename("flags").sort_values(ascending=False).reset_index()
    st.bar_chart(by_check, x="check", y="flags")

st.subheader("Queue")
show = view[
    ["flag_id", "institution", "quarter", "check", "field", "severity", "detail"]
].sort_values(["severity", "institution", "quarter"], ascending=[True, True, True])
st.dataframe(show, use_container_width=True, hide_index=True)

st.subheader("Open a filing")
choice = st.selectbox("Flag", view["flag_id"].tolist(), format_func=lambda fid: _label(view, fid))
picked = view[view["flag_id"] == choice].iloc[0]
filing = submissions[
    (submissions["institution_id"] == picked["institution_id"]) & (submissions["quarter"] == picked["quarter"])
].iloc[0]
st.markdown(f"**{picked['institution']} · {picked['quarter']} · {picked['check']}**")
st.write(picked["detail"])
siblings = view[
    (view["institution_id"] == picked["institution_id"]) & (view["quarter"] == picked["quarter"])
]
st.caption(f"{len(siblings)} flag(s) on this filing.")
st.dataframe(
    filing.drop(labels=["institution_id"]).to_frame("value"),
    use_container_width=True,
)
