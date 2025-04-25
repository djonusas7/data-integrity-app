import streamlit as st
import pandas as pd
from datetime import datetime
from collections import Counter

# --------------------------------------------------------------------
# 🔧 Page configuration
# --------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison & Validation",
                   layout="wide")
st.title("Data Integrity Comparison and Validation Tool – v1.1")

st.markdown(
    """
Upload **Previous** and **Current** CSV files.  
1. *(Optional)* Open **⚙️ Column Tools** to map differently-named columns **and** fix data-types.  
2. Select key column(s) and run the comparison.
"""
)

# --------------------------------------------------------------------
# 📖 𝗜𝗻𝘀𝘁𝗿𝘂𝗰𝘁𝗶𝗼𝗻𝘀 & 𝗚𝘂𝗶𝗱𝗲𝗹𝗶𝗻𝗲𝘀
# --------------------------------------------------------------------
with st.expander("📖 Instructions & Guidelines (Click to Expand)"):
    st.subheader("Overview")
    st.write(
        """
        This tool compares two datasets to detect discrepancies and ensure
        data integrity. It checks for **changes**, **missing rows**, and
        **new rows** between an older dataset (“Previous”) and a newer dataset
        (“Current”).
        """
    )
    st.subheader("Preparing Your Files")
    st.write(
        """
        1. Open the export in **Excel** (or similar).  
        2. Choose **Save As → CSV (UTF-8, comma-delimited)** to standardise
           encoding and delimiters.
        """
    )
    st.subheader("Handling Date Columns")
    st.write(
        """
        Timestamp-style export columns—**“Data as of:”**, **"Today:"**, **"Data Through:"** and
        **“Data Downloaded on:”**—are dropped automatically to prevent false
        discrepancies.  
        Leave all genuine business-date fields (e.g., “Date of Service”)
        untouched.
        """
    )
    st.subheader("Selecting Key Columns")
    st.write(
        """
        Pick a **unique key** (or composite) so rows match correctly.  
        *Example composite:* `FIN || ChargeID || Date of Service`.
        """
    )
    st.subheader("How the Comparison Works")
    st.markdown(
        """
        1. The app loads both files and drops export timestamps.  
        2. Any column mapping / dtype fixes from **⚙️ Column Tools**
           are applied.  
        3. Rows are matched on the selected key(s).  
        4. It flags:  
           • **Missing rows** (dropped)  
           • **New rows** (added)  
           • **Value changes** in non-key columns  
        5. A summary and a downloadable CSV discrepancy report are produced.
        """
    )
    st.info("🔹 At least one key column must be selected before running.")

# --------------------------------------------------------------------
# 🛠️ Helper functions
# --------------------------------------------------------------------
DTYPE_OPTIONS = ["string", "int", "float", "datetime", "bool"]
TIMESTAMP_COLS = {"data as of:", "data downloaded on:", "today:", "data through:" }  # lower-case match

def infer(s):
    if pd.api.types.is_float_dtype(s): return "float"
    if pd.api.types.is_integer_dtype(s): return "int"
    if pd.api.types.is_datetime64_any_dtype(s): return "datetime"
    if pd.api.types.is_bool_dtype(s): return "bool"
    return "string"

def cast(s, kind):
    if kind == "string":   return s.astype(str)
    if kind == "int":      return pd.to_numeric(s, errors="coerce").astype("Int64")
    if kind == "float":    return pd.to_numeric(s, errors="coerce").astype(float)
    if kind == "datetime": return pd.to_datetime(s, errors="coerce")
    if kind == "bool":     return s.astype("boolean")
    return s

def make_key(r, keys): return "||".join(str(r[k]) for k in keys)

def diff_desc(r, cur, keys):
    rows = cur
    for k in keys: rows = rows[rows[k] == r[k]]
    if rows.empty: return "Row is missing from latest upload"
    new = rows.iloc[0]
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
# 📂 File uploaders
# --------------------------------------------------------------------
lcol, rcol = st.columns(2)
with lcol: prev_file = st.file_uploader("Previous CSV", type="csv")
with rcol: curr_file = st.file_uploader("Current CSV",  type="csv")

# --------------------------------------------------------------------
# 🚦 Main workflow
# --------------------------------------------------------------------
if prev_file and curr_file:
    # ---------- load files once per upload ----------
    new_upload = (
        "prev_raw" not in st.session_state
        or st.session_state.get("prev_file_name") != prev_file.name
        or st.session_state.get("curr_file_name") != curr_file.name
    )
    if new_upload:
        st.session_state.prev_raw = pd.read_csv(prev_file)
        st.session_state.curr_raw = pd.read_csv(curr_file)
        st.session_state.prev_file_name = prev_file.name
        st.session_state.curr_file_name = curr_file.name
        for k in ("cmp_out", "cmp_br", "cmp_stats", "selected_keys"):
            st.session_state.pop(k, None)

    prev_df = st.session_state.prev_raw.copy()
    curr_df = st.session_state.curr_raw.copy()

    # ----- drop timestamp columns -----
    prev_df.columns = prev_df.columns.str.strip()
    curr_df.columns = curr_df.columns.str.strip()
    prev_df = prev_df.drop(
        columns=[c for c in prev_df.columns if c.lower() in TIMESTAMP_COLS],
        errors="ignore",
    )
    curr_df = curr_df.drop(
        columns=[c for c in curr_df.columns if c.lower() in TIMESTAMP_COLS],
        errors="ignore",
    )

    # ---------- mapping / dtype state ----------
    col_map = st.session_state.get(
        "col_map", {c: (c if c in curr_df.columns else None) for c in prev_df.columns}
    )
    d_prev = st.session_state.get("dtypes_prev", {})
    d_curr = st.session_state.get("dtypes_curr", {})

    # ----------------------------------------------------------------
    # ⚙️ Column Tools
    # ----------------------------------------------------------------
    with st.expander("⚙️ Column Tools (click to edit)", expanded=False):
        st.markdown("#### Map Columns & Set Data-Types")
        curr_cols = [None] + curr_df.columns.tolist()
        all_cols = sorted(set(prev_df.columns).union(curr_df.columns))

        hdr1, hdr2, hdr3, hdr4 = st.columns([0.28, 0.28, 0.22, 0.22], gap="small")
        hdr1.markdown("**Prev Column**")
        hdr2.markdown("**Map → Curr Column**")
        hdr3.markdown("**Prev dtype**")
        hdr4.markdown("**Curr dtype**")

        for pc in all_cols:
            c1, c2, c3, c4 = st.columns([0.28, 0.28, 0.22, 0.22], gap="small")
            c1.markdown(f"**{pc}**" if pc in prev_df.columns else "*missing*")

            map_idx = 0 if col_map.get(pc) is None else curr_cols.index(col_map[pc])
            col_map[pc] = c2.selectbox(
                "Current column dropdown", curr_cols, index=map_idx,
                key=f"map_{pc}", format_func=lambda x: "–– none ––" if x is None else x,
                label_visibility="collapsed"
            )

            if pc in prev_df.columns:
                d_prev[pc] = c3.selectbox(
                    "Prev dtype dropdown", DTYPE_OPTIONS,
                    index=DTYPE_OPTIONS.index(d_prev.get(pc, infer(prev_df[pc]))),
                    key=f"prev_dtype_{pc}", label_visibility="collapsed"
                )
                prev_df[pc] = cast(prev_df[pc], d_prev[pc])
            else:
                c3.markdown(" ")

            if pc in curr_df.columns:
                d_curr[pc] = c4.selectbox(
                    "Curr dtype dropdown", DTYPE_OPTIONS,
                    index=DTYPE_OPTIONS.index(d_curr.get(pc, infer(curr_df[pc]))),
                    key=f"curr_dtype_{pc}", label_visibility="collapsed"
                )
                curr_df[pc] = cast(curr_df[pc], d_curr[pc])
            else:
                c4.markdown(" ")

    st.session_state.col_map = col_map
    st.session_state.dtypes_prev = d_prev
    st.session_state.dtypes_curr = d_curr

    curr_df = curr_df.rename(
        columns={v: k for k, v in col_map.items() if v and v in curr_df.columns}
    )

    # ----------------------------------------------------------------
    # 🔑 Key selection
    # ----------------------------------------------------------------
    key_cols = st.multiselect("Select Key Column(s)", list(prev_df.columns))

    # Reset comparison caches when key selection changes
    if key_cols != st.session_state.get("selected_keys", []):
        for k in ("cmp_out", "cmp_br", "cmp_stats"):
            st.session_state.pop(k, None)
        st.session_state.selected_keys = key_cols

    if not key_cols:
        st.stop()

    mism = [
        f"• **{k}** — Prev *{prev_df[k].dtype}*, Curr *{curr_df[k].dtype}*"
        for k in key_cols
        if k not in curr_df.columns or prev_df[k].dtype != curr_df[k].dtype
    ]
    if mism:
        st.error("Key column data-types must match:\n\n" + "\n".join(mism))
        st.stop()

    # ----------------------------------------------------------------
    # ▶️ Run / show comparison  (cached)
    # ----------------------------------------------------------------
    run_clicked = st.button("Run Comparison", key="run_btn")

    if run_clicked or "cmp_out" in st.session_state:
        if run_clicked:
            today = datetime.now().strftime("%m/%d/%Y")

            merged = prev_df.merge(curr_df, how="left", indicator=True)
            diff = merged[merged["_merge"] == "left_only"].drop("_merge", axis=1)
            diff["Discrepancy_Columns"] = diff.apply(
                lambda r: diff_desc(r, curr_df, key_cols), axis=1
            )
            diff["Created_Date"] = today

            outer = curr_df.merge(prev_df, how="outer", indicator=True)
            new = outer[outer["_merge"] == "left_only"].drop("_merge", axis=1)
            new["Discrepancy_Columns"] = "New row in current upload"
            new["Created_Date"] = today

            diff_keys = set(diff.apply(lambda r: make_key(r, key_cols), axis=1))
            new = new[
                ~new.apply(lambda r: make_key(r, key_cols), axis=1).isin(diff_keys)
            ]

            out = pd.concat([diff, new], ignore_index=True)

            pc, cc = len(prev_df), len(curr_df)
            nm = len(out)
            pct = nm / pc * 100 if pc else 0
            pk = set(prev_df.apply(lambda r: make_key(r, key_cols), axis=1))
            ck = set(curr_df.apply(lambda r: make_key(r, key_cols), axis=1))
            dropped, added = len(pk - ck), len(ck - pk)

            br = Counter(col for s in out["Discrepancy_Columns"] for col in cols_from(s))
            br_df = (
                pd.DataFrame(
                    {"Column": list(br.keys()), "Non-Matching Count": list(br.values())}
                )
                .assign(**{"% of Discrepancies": lambda d: (d["Non-Matching Count"] / nm * 100).round(2)})
                .sort_values("Non-Matching Count", ascending=False)
            )

            st.session_state.update(
                cmp_out=out,
                cmp_br=br_df,
                cmp_stats=(pc, cc, dropped, added, nm, pct),
            )

        pc, cc, dropped, added, nm, pct = st.session_state.cmp_stats
        br_df = st.session_state.cmp_br
        out = st.session_state.cmp_out

        st.success("✅ Comparison complete")
        a, b, c, d, e, f = st.columns(6)
        a.metric("Previous Rows", f"{pc:,}")
        b.metric("Current Rows",  f"{cc:,}")
        c.metric("Rows Dropped",  f"{dropped:,}")
        d.metric("Rows Added",    f"{added:,}")
        e.metric("Non-Matching",  f"{nm:,}")
        f.metric("% Non-Match",   f"{pct:.2f}%")

        st.subheader("🗂️ Column Breakdown")
        st.dataframe(br_df)

        st.subheader("🔍 Discrepancy Preview (first 50 rows)")
        st.dataframe(out.head(50), use_container_width=True)

        st.download_button(
            "Download Full Report as CSV",
            data=out.to_csv(index=False).encode("utf-8"),
            file_name=f"Rows_Not_Matching_{datetime.now():%Y%m%d_%H%M%S}.csv",
            mime="text/csv",
            key="dl_btn",
        )
else:
    st.info("Please upload both CSV files to proceed.")
