import streamlit as st
import pandas as pd
import os
import glob
from datetime import datetime

def get_latest_file(path, pattern):
    files = glob.glob(os.path.join(path, pattern))
    return max(files, key=os.path.getmtime) if files else None

def get_oldest_file(path, pattern):
    files = glob.glob(os.path.join(path, pattern))
    return min(files, key=os.path.getmtime) if files else None

def find_discrepancies(row, current_data, key_cols):
    filter_condition = None
    for col in key_cols:
        cond = current_data[col] == row[col]
        filter_condition = cond if filter_condition is None else (filter_condition & cond)
    
    matching_rows = current_data[filter_condition]
    if matching_rows.empty:
        return "Row is missing from latest download"
    
    current_row = matching_rows.iloc[0]
    
    discrepancies = []
    for col in row.index:
        old_val = row[col]
        new_val = current_row.get(col, None)
        # Treat both NaN as identical
        if pd.isna(old_val) and pd.isna(new_val):
            continue
        if old_val != new_val:
            discrepancies.append(f"{col}: {old_val} != {new_val}")
    
    return ", ".join(discrepancies)

def make_key_str(row, key_cols):
    """
    Creates a string that uniquely identifies a row based on the chosen key columns.
    Example: if key_cols = ['FIN / ECD', 'Order ID'], the key might be '12345||67890'.
    """
    return "||".join(str(row[col]) for col in key_cols)

# ----------------------------------------------------------------------------------------
# Streamlit App
# ----------------------------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison", layout="wide")
st.title("Data Integrity Comparison Tool")

st.markdown("""
This application compares two datasets to detect discrepancies and ensure data integrity.
Upload or specify the paths for the latest and previous versions of your dataset, and the tool will identify any missing, changed, or newly added rows.
""")

# User inputs for directories
data_path = st.text_input("Data Directory", value=r"\\your\shared\drive\data")
output_path = st.text_input("Output Directory", value=r"\\your\shared\drive\output")

columns_available = []
# If the data_path is valid, try to read at least one CSV to gather columns
if os.path.isdir(data_path):
    csv_files = glob.glob(os.path.join(data_path, "*.csv"))
    if csv_files:
        try:
            sample_df = pd.read_csv(csv_files[0])
            sample_df.columns = sample_df.columns.str.strip()
            columns_available = list(sample_df.columns)
        except Exception as e:
            st.error(f"Error reading sample CSV for column names: {e}")
    else:
        st.warning("No CSV files found in the Data Directory.")
else:
    st.info("Enter a valid Data Directory.")

key_cols = st.multiselect("Select the Key Column(s) for Row Identification", options=columns_available)

run_button = st.button("Run Comparison")

if run_button:
    if not os.path.isdir(data_path):
        st.error("Data Directory is invalid or does not exist.")
        st.stop()
    if not os.path.isdir(output_path):
        st.error("Output Directory is invalid or does not exist.")
        st.stop()
    if len(key_cols) == 0:
        st.error("Please select at least one key column.")
        st.stop()
    
    try:
        st.write("Locating the oldest (previous) and newest (current) CSV files...")
        previous_file_path = get_oldest_file(data_path, "*.csv")
        current_file_path = get_latest_file(data_path, "*.csv")
        
        if not previous_file_path or not current_file_path:
            st.error("Could not find at least two CSV files in the data directory.")
            st.stop()
        if previous_file_path == current_file_path:
            st.error("Only one CSV file found; need two or more for comparison.")
            st.stop()
        
        st.write(f"Previous (oldest): {os.path.basename(previous_file_path)}")
        st.write(f"Current (newest): {os.path.basename(current_file_path)}")
        
        # Read the CSV files
        previous_df = pd.read_csv(previous_file_path)
        current_df = pd.read_csv(current_file_path)
        
        # Strip column names
        previous_df.columns = previous_df.columns.str.strip()
        current_df.columns = current_df.columns.str.strip()
        
        # ----------------------------------------------------------------
        # 1) Use your original approach: Merge on ALL shared columns to detect partial mismatches.
        #    Rows in previous_df that differ in any column become left_only.
        # ----------------------------------------------------------------
        st.write("Merging on ALL columns to detect partial mismatches...")
        merged_all_cols = previous_df.merge(current_df, how='left', indicator=True)
        rows_not_matching_df = merged_all_cols.loc[merged_all_cols['_merge'] == 'left_only'].drop(columns=['_merge'])
        
        # ----------------------------------------------------------------
        # 2) For each mismatched row, see if there's a row with the same key in current_df
        #    - If not, "Row is missing"
        #    - If yes, note the discrepancies in non-key columns
        # ----------------------------------------------------------------
        current_date = datetime.now().strftime("%m/%d/%Y")
        rows_not_matching_df = rows_not_matching_df.apply(
            lambda row: pd.Series({
                **row,
                'Discrepancy_Columns': find_discrepancies(row, current_df, key_cols),
                'Created_Date': current_date
            }),
            axis=1
        )
        
        # ----------------------------------------------------------------
        # 3) Identify new rows in current_df
        #    - Also exclude rows that match keys of already-flagged discrepancies
        # ----------------------------------------------------------------
        st.write("Checking for NEW rows in current that didn't match exactly in previous...")
        merged_for_new = current_df.merge(previous_df, how='outer', indicator=True)
        
        # Basic "new row" check
        new_rows_df = merged_for_new.loc[merged_for_new['_merge'] == 'left_only'].drop(columns=['_merge']).copy()
        
        # Build a set of keys that were flagged as discrepancies in 'rows_not_matching_df'
        missing_keys_set = set(rows_not_matching_df.apply(lambda r: make_key_str(r, key_cols), axis=1))
        
        # Build a composite key for each "new" row
        new_rows_df_key_str = new_rows_df.apply(lambda r: make_key_str(r, key_cols), axis=1)
        
        # Exclude new rows that have the same key as something in rows_not_matching_df
        new_rows_df = new_rows_df[~new_rows_df_key_str.isin(missing_keys_set)]
        
        # Mark them as "New row in current download"
        new_rows_df['Discrepancy_Columns'] = 'New row in current download'
        new_rows_df['Created_Date'] = current_date
        
        # ----------------------------------------------------------------
        # 4) Combine the "missing/changed" rows and the "new" rows
        # ----------------------------------------------------------------
        combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
        
        # ----------------------------------------------------------------
        # 5) Output the combined discrepancies to a single CSV
        # ----------------------------------------------------------------
        dt_tm = datetime.now().strftime("%Y%m%d_%H%M%S")
        non_matching_dir = os.path.join(output_path, "Non_Matching_Records")
        os.makedirs(non_matching_dir, exist_ok=True)
        discrepancy_file = os.path.join(non_matching_dir, f"Rows_Not_Matching_{dt_tm}.csv")
        
        combined_discrepancies_df.to_csv(discrepancy_file, index=False)
        
        st.success("Comparison complete!")
        st.write(f"**Discrepancy report**: {discrepancy_file}")
    
    except Exception as e:
        st.error(f"An error occurred: {e}")