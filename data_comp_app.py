import streamlit as st
import pandas as pd
from datetime import datetime

# --------------------------------------------------------------------
# Set page configuration (must be first)
# --------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison and Validation", layout="wide")

# --------------------------------------------------------------------
# App Title and Description
# --------------------------------------------------------------------
st.title("Data Integrity Comparison and Validation Tool")
st.markdown("""
This application compares two datasets to detect discrepancies and ensure data integrity.
Please drag and drop your **Previous CSV file** and **Current CSV file** below.
""")

# --------------------------------------------------------------------
# Drag and Drop File Uploaders for CSV Files
# --------------------------------------------------------------------
col1, col2 = st.columns(2)
with col1:
    previous_file = st.file_uploader("Upload Previous CSV file", type="csv", key="prev")
with col2:
    current_file = st.file_uploader("Upload Current CSV file", type="csv", key="curr")

# --------------------------------------------------------------------
# Process files if both are uploaded
# --------------------------------------------------------------------
if previous_file is not None and current_file is not None:
    try:
        # Read CSV files
        previous_df = pd.read_csv(previous_file)
        current_df = pd.read_csv(current_file)

        # Remove extra whitespace from column names
        previous_df.columns = previous_df.columns.str.strip()
        current_df.columns = current_df.columns.str.strip()

        # Let the user select key columns from the previous CSV
        columns_available = list(previous_df.columns)
        key_cols = st.multiselect("Select the Key Column(s) for Row Identification", options=columns_available)

        if not key_cols:
            st.error("Please select at least one key column.")
        else:
            # ----------------------------------------------------------------
            # Helper functions for discrepancy detection
            # ----------------------------------------------------------------
            def find_discrepancies(row, current_data, key_cols):
                filter_condition = None
                for col in key_cols:
                    cond = current_data[col] == row[col]
                    filter_condition = cond if filter_condition is None else (filter_condition & cond)
                matching_rows = current_data[filter_condition]
                if matching_rows.empty:
                    return "Row is missing from latest upload"
                current_row = matching_rows.iloc[0]
                discrepancies = []
                for col in row.index:
                    old_val = row[col]
                    new_val = current_row.get(col, None)
                    # Treat NaN values as matching
                    if pd.isna(old_val) and pd.isna(new_val):
                        continue
                    if old_val != new_val:
                        discrepancies.append(f"{col}: {old_val} != {new_val}")
                return ", ".join(discrepancies)

            def make_key_str(row, key_cols):
                return "||".join(str(row[col]) for col in key_cols)

            # ----------------------------------------------------------------
            # Run the comparison when the button is clicked
            # ----------------------------------------------------------------
            if st.button("Run Comparison"):
                current_date = datetime.now().strftime("%m/%d/%Y")
                
                # 1) Merge on ALL columns to find rows in previous that aren't matching in current
                merged_all_cols = previous_df.merge(current_df, how='left', indicator=True)
                rows_not_matching_df = merged_all_cols.loc[merged_all_cols['_merge'] == 'left_only'].drop(columns=['_merge'])
                rows_not_matching_df = rows_not_matching_df.apply(
                    lambda row: pd.Series({
                        **row,
                        'Discrepancy_Columns': find_discrepancies(row, current_df, key_cols),
                        'Created_Date': current_date
                    }), axis=1
                )
                
                # 2) Identify new rows in the current CSV
                merged_for_new = current_df.merge(previous_df, how='outer', indicator=True)
                new_rows_df = merged_for_new.loc[merged_for_new['_merge'] == 'left_only'].drop(columns=['_merge']).copy()
                missing_keys_set = set(rows_not_matching_df.apply(lambda r: make_key_str(r, key_cols), axis=1))
                new_rows_df_key_str = new_rows_df.apply(lambda r: make_key_str(r, key_cols), axis=1)
                new_rows_df = new_rows_df[~new_rows_df_key_str.isin(missing_keys_set)]
                new_rows_df['Discrepancy_Columns'] = 'New row in current upload'
                new_rows_df['Created_Date'] = current_date
                
                # 3) Combine both sets of discrepancies
                combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
                
                st.success("Comparison complete!")
                st.write("Discrepancy Report Preview:")
                st.dataframe(combined_discrepancies_df.head())
                
                # Download button for the full report
                csv_report = combined_discrepancies_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download Full Report as CSV",
                    data=csv_report,
                    file_name=f"Rows_Not_Matching_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
    except Exception as e:
        st.error(f"An error occurred: {e}")
else:
    st.info("Please upload both CSV files to proceed.")
