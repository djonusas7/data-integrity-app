import streamlit as st
import pandas as pd
from datetime import datetime

# ----------------------------------------------------------------------------------------
# Streamlit App
# ----------------------------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison", layout="wide")
st.title("Data Integrity Comparison Tool")

st.markdown("""
This application compares two datasets to detect discrepancies and ensure data integrity.
Drag and drop your CSV files for the previous and current datasets.
""")

# File upload widgets for previous and current CSV files
col1, col2 = st.columns(2)
with col1:
    previous_file = st.file_uploader("Upload Previous CSV file", type="csv", key="prev")
with col2:
    current_file = st.file_uploader("Upload Current CSV file", type="csv", key="curr")

# Proceed if both files are uploaded
if previous_file is not None and current_file is not None:
    try:
        # Read the CSV files from the uploaded file objects
        previous_df = pd.read_csv(previous_file)
        current_df = pd.read_csv(current_file)
        
        # Clean up column names by stripping whitespace
        previous_df.columns = previous_df.columns.str.strip()
        current_df.columns = current_df.columns.str.strip()
        
        # Extract column options from one of the datasets (assuming both have the same structure)
        columns_available = list(previous_df.columns)
        
        # Allow user to select key columns for matching rows
        key_cols = st.multiselect("Select the Key Column(s) for Row Identification", options=columns_available)
        if not key_cols:
            st.error("Please select at least one key column.")
            st.stop()
        
        # Confirm start of the comparison
        if st.button("Run Comparison"):
            st.write("Starting the data comparison...")

            # -----------------------------
            # 1) Detect partial mismatches by merging on all columns.
            merged_all_cols = previous_df.merge(current_df, how='left', indicator=True)
            rows_not_matching_df = merged_all_cols.loc[merged_all_cols['_merge'] == 'left_only'].drop(columns=['_merge'])

            # Function to compare rows based on key columns
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
                    if pd.isna(old_val) and pd.isna(new_val):
                        continue
                    if old_val != new_val:
                        discrepancies.append(f"{col}: {old_val} != {new_val}")
                return ", ".join(discrepancies)
            
            # Function to create a unique key string from the row
            def make_key_str(row, key_cols):
                return "||".join(str(row[col]) for col in key_cols)
            
            # Apply discrepancy detection to mismatched rows
            current_date = datetime.now().strftime("%m/%d/%Y")
            rows_not_matching_df = rows_not_matching_df.apply(
                lambda row: pd.Series({
                    **row,
                    'Discrepancy_Columns': find_discrepancies(row, current_df, key_cols),
                    'Created_Date': current_date
                }),
                axis=1
            )
            
            # -----------------------------
            # 2) Identify new rows in the current dataset
            merged_for_new = current_df.merge(previous_df, how='outer', indicator=True)
            new_rows_df = merged_for_new.loc[merged_for_new['_merge'] == 'left_only'].drop(columns=['_merge']).copy()
            
            missing_keys_set = set(rows_not_matching_df.apply(lambda r: make_key_str(r, key_cols), axis=1))
            new_rows_df_key_str = new_rows_df.apply(lambda r: make_key_str(r, key_cols), axis=1)
            new_rows_df = new_rows_df[~new_rows_df_key_str.isin(missing_keys_set)]
            new_rows_df['Discrepancy_Columns'] = 'New row in current upload'
            new_rows_df['Created_Date'] = current_date
            
            # -----------------------------
            # 3) Combine discrepancies and new rows
            combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
            
            # -----------------------------
            # 4) Provide the discrepancy report (for example, displaying the head of the DataFrame)
            st.success("Comparison complete!")
            st.write("Discrepancy report preview:")
            st.dataframe(combined_discrepancies_df.head())
            
            # Optionally, you can allow the user to download the report
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
