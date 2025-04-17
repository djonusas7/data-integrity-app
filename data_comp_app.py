import streamlit as st
import pandas as pd
from datetime import datetime
from collections import Counter

# --------------------------------------------------------------------
# Page configuration
# --------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison & Validation",
                   layout="wide")
st.title("Data Integrity Comparison and Validation Tool – v1.1")

st.markdown(
    """
Upload **Previous** and **Current** CSV files.  
1. *(Optional)* Open **⚙️ Column Tools** to map differently‑named columns and/or
   fix data‑types.  
2. Select key column(s) and run the comparison.
"""
)

# --------------------------------------------------------------------
# 📖 Instructions & Guidelines
# --------------------------------------------------------------------
with st.expander("📖 Instructions & Guidelines (Click to Expand)"):
    st.subheader("Overview")
    st.write(
        """
        This tool helps compare two datasets to detect discrepancies and ensure
        data integrity. It checks for **changes**, **missing rows**, and
        **new rows** between an older dataset (“Previous”) and a newer dataset
        (“Current”).
        """
    )
    st.subheader("Preparing Your Files")
    st.write(
        """
        1. Open the export in **Excel**.  
        2. Choose **Save As → CSV (UTF‑8, comma‑delimited)** for clean input.
        """
    )
    st.subheader("Handling Date Columns")
    st.write(
        "Remove or standardize export‑timestamp columns (e.g., “Data as of:”)."
    )
    st.subheader("Selecting Key Columns")
    st.write(
        """
        Pick a **unique key** (or composite) so rows match correctly  
        e.g. `"FIN" + "ChargeID" + "Date of Service"`.
        """
    )
    st.subheader("How the Comparison Works")
    st.markdown(
        """
        1. Rows are matched on the key(s).  
        2. The tool flags:  
           • Rows **missing** from *Current* (dropped)  
           • Rows **new** in *Current* (added)  
           • Rows whose **non‑key values changed**  
        3. A summary and downloadable discrepancy report are produced.
        """
    )
    st.info("🔹 At least one key column must be selected before running.")

# --------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------
DTYPE_OPTIONS = ["string", "int", "float", "datetime", "bool"]

def infer(s: pd.Series) -> str:
    if pd.api.types.is_float_dtype(s): return "float"
    if pd.api.types.is_integer_dtype(s): return "int"
    if pd.api.types.is_datetime64_any_dtype(s): return "datetime"
    if pd.api.types.is_bool_dtype(s): return "bool"
    return "string"

def cast(s: pd.Series, kind: str) -> pd.Series:
    if kind == "string":   return s.astype(str)
    if kind == "int":      return pd.to_numeric(s, errors="coerce").astype("Int64")
    if kind == "float":    return pd.to_numeric(s, errors="coerce").astype(float)
    if kind == "datetime": return pd.to_datetime(s, errors="coerce")
    if kind == "bool":     return s.astype("boolean")
    return s

def make_key(r: pd.Series, keys): return "||".join(str(r[k]) for k in keys)

def diff_desc(r, cur, keys):
    mask = pd.Series(True, index=cur.index)
    for k in keys: mask &= cur[k] == r[k]
    if mask.sum() == 0: return "Row is missing from latest upload"
    new = cur[mask].iloc[0]
    return ", ".join(
        f"{c}: {r[c]} != {new[c]}"
        for c in r.index
        if not (pd.isna(r[c]) and pd.isna(new[c])) and r[c] != new[c]
    )

def cols_from(desc):
    if desc == "New row in current upload":      return ["NEW_ROW"]
    if desc == "Row is missing from latest upload": return ["MISSING_ROW"]
    return [p.split(":")[0].strip() for p in desc.split(",") if ":" in p]

# --------------------------------------------------------------------
# File uploaders
# --------------------------------------------------------------------
lcol, rcol = st.columns(2)
with lcol:  prev_file = st.file_uploader("Previous CSV", type="csv")
with rcol:  curr_file = st.file_uploader("Current CSV",  type="csv")

# --------------------------------------------------------------------
# Main workflow
# --------------------------------------------------------------------
if prev_file and curr_file:
    if "prev_raw" not in st.session_state:
        st.session_state.prev_raw = pd.read_csv(prev_file)
        st.session_state.curr_raw = pd.read_csv(curr_file)

    prev_df = st.session_state.prev_raw.copy()
    curr_df = st.session_state.curr_raw.copy()
    prev_df.columns = prev_df.columns.str.strip()
    curr_df.columns = curr_df.columns.str.strip()

    # Load or init choices
    col_map = st.session_state.get("col_map",
               {c: (c if c in curr_df.columns else None) for c in prev_df.columns})
    d_prev  = st.session_state.get("dtypes_prev", {})
    d_curr  = st.session_state.get("dtypes_curr", {})

    # ----------------------------------------------------------------
    # ⚙️ Column Tools
    # ----------------------------------------------------------------
    with st.expander("⚙️ Column Tools (click to edit)", expanded=False):
        center = st.columns([0.22, 0.56, 0.22])[1]
        with center:
            st.markdown("#### 1. Map Column Names")
            curr_cols = curr_df.columns.tolist()
            for pc in prev_df.columns:
                cprev, ceq, ccurr = st.columns([0.42, 0.02, 0.56])
                with cprev: st.markdown(f"**{pc} (Prev)**")
                with ceq:  st.markdown("＝")
                with ccurr:
                    options = [None] + curr_cols
                    idx = 0 if col_map.get(pc) is None else options.index(col_map[pc])
                    sel = st.selectbox(
                        " ",
                        options,
                        index=idx,
                        key=f"map_{pc}",
                        label_visibility="collapsed",
                        format_func=lambda x: "–– none ––" if x is None else f"{x} (Curr)",
                    )
                    col_map[pc] = sel

            st.markdown("---")
            st.markdown("#### 2. Adjust Data‑Types")
            all_cols = sorted(set(prev_df.columns).union(curr_df.columns))
            for col in all_cols:
                pcol, ccol = st.columns(2, gap="small")
                with pcol:
                    if col in prev_df.columns:
                        typ = st.selectbox(
                            f"{col} (Prev)",
                            DTYPE_OPTIONS,
                            index=DTYPE_OPTIONS.index(d_prev.get(col, infer(prev_df[col]))),
                            key=f"prev_{col}",
                        )
                        d_prev[col] = typ
                        prev_df[col] = cast(prev_df[col], typ)
                    else:
                        st.markdown(f"*{col}* not in Prev")
                with ccol:
                    if col in curr_df.columns:
                        typ = st.selectbox(
                            f"{col} (Curr)",
                            DTYPE_OPTIONS,
                            index=DTYPE_OPTIONS.index(d_curr.get(col, infer(curr_df[col]))),
                            key=f"curr_{col}",
                        )
                        d_curr[col] = typ
                        curr_df[col] = cast(curr_df[col], typ)
                    else:
                        st.markdown(f"*{col}* not in Curr")

    # Persist choices
    st.session_state.col_map     = col_map
    st.session_state.dtypes_prev = d_prev
    st.session_state.dtypes_curr = d_curr

    # Apply mapping (rename Current)
    curr_df = curr_df.rename(columns={v: k for k, v in col_map.items()
                                      if v and v in curr_df.columns})

    # ----------------------------------------------------------------
    # Key selection & guard
    # ----------------------------------------------------------------
    key_cols = st.multiselect("Select Key Column(s)", list(prev_df.columns))
    if not key_cols: st.stop()

    mism = [f"• **{k}** — Prev: *{prev_df[k].dtype}*, Curr: *{curr_df[k].dtype}*"
            for k in key_cols if k not in curr_df.columns or
            prev_df[k].dtype != curr_df[k].dtype]
    if mism:
        st.error("Key column data‑types must match:\n\n" + "\n".join(mism))
        st.stop()

    # ----------------------------------------------------------------
    # Run comparison
    # ----------------------------------------------------------------
    if st.button("Run Comparison"):
        today = datetime.now().strftime("%m/%d/%Y")

        merged = prev_df.merge(curr_df, how="left", indicator=True)
        diff = merged[merged["_merge"] == "left_only"].drop("_merge", axis=1)
        diff = diff.apply(lambda r: pd.Series({
            **r,
            "Discrepancy_Columns": diff_desc(r, curr_df, key_cols),
            "Created_Date": today,
        }), axis=1)

        outer = curr_df.merge(prev_df, how="outer", indicator=True)
        new = outer[outer["_merge"] == "left_only"].drop("_merge", axis=1)
        new["Discrepancy_Columns"], new["Created_Date"] = "New row in current upload", today

        diff_keys = set(diff.apply(lambda r: make_key(r, key_cols), axis=1))
        new = new[~new.apply(lambda r: make_key(r, key_cols), axis=1).isin(diff_keys)]

        out = pd.concat([diff, new], ignore_index=True)

        # ----- summary -----
        pc, cc = len(prev_df), len(curr_df)
        nm = len(out); pct = nm / pc * 100 if pc else 0
        pk = set(prev_df.apply(lambda r: make_key(r, key_cols), axis=1))
        ck = set(curr_df.apply(lambda r: make_key(r, key_cols), axis=1))
        dropped, added = len(pk - ck), len(ck - pk)

        br = Counter(col for s in out["Discrepancy_Columns"] for col in cols_from(s))
        br_df = pd.DataFrame({"Column": list(br.keys()),
                              "Non‑Matching Count": list(br.values())})
        br_df["% of Discrepancies"] = (
            br_df["Non‑Matching Count"] / nm * 100).round(2) if nm else 0

        # ----- display -----
        st.success("Comparison complete!")
        a,b,c,d,e,f = st.columns(6)
        a.metric("Previous Rows", f"{pc:,}")
        b.metric("Current Rows",  f"{cc:,}")
        c.metric("Rows Dropped",  f"{dropped:,}")
        d.metric("Rows Added",    f"{added:,}")
        e.metric("Non‑Matching",  f"{nm:,}")
        f.metric("% Non‑Match",   f"{pct:.2f}%")

        st.subheader("🗂️ Column Breakdown")
        st.dataframe(br_df)

        st.subheader("🔍 Discrepancy Preview (first 50 rows)")
        st.dataframe(out.head(50))

        st.download_button(
            "Download Full Report as CSV",
            data=out.to_csv(index=False).encode("utf‑8"),
            file_name=f"Rows_Not_Matching_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
        )
else:
    st.info("Please upload both CSV files to proceed.")
