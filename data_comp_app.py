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
    """
    Compare row values between 'previous_df' row and the matching row in 'current_df',
    using the user-selected key columns to locate the matching row.
    """
    # Build a filter for the matching row in the current_data
    filter_condition = None
    for col in key_cols:
        cond = current_data[col] == row[col]
        filter_condition = cond if filter_condition is None else (filter_condition & cond)
    
    # Find the row in current_data
    matching_rows = current_data[filter_condition]
    if matching_rows.empty:
        return "Row is missing from latest download"
    
    current_row = matching_rows.iloc[0]
    
    discrepancies = []
    for col in row.index:
        # Skip the key columns themselves when checking for differences
        if col in key_cols:
            continue
        
        old_val = row[col]
        new_val = current_row.get(col, None)
        
        # Treat both NaN as identical
        if pd.isna(old_val) and pd.isna(new_val):
            continue
        
        if old_val != new_val:
            discrepancies.append(f"{col}: {old_val} != {new_val}")
    
    return ", ".join(discrepancies) if discrepancies else ""

# ----------------------------------------------------------------------------------------
# Streamlit App
# ----------------------------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison", layout="wide")
st.title("Data Integrity Comparison Tool (No Summary / No Archive)")

st.markdown("""
This version replicates your original data integrity logic while allowing you to:
- Select any column(s) as the key
- Compare the oldest vs newest CSV in the data directory
- Generate **one CSV** of discrepancies (missing or new rows)

**Note**: Steps 5 (summary stats) and 6 (archiving the old file) have been removed.
""")

# User inputs
data_path = st.text_input("Data Directory", value=r"\\your\shared\drive\data")
output_path = st.text_input("Output Directory", value=r"\\your\shared\drive\output")

# Once the user enters a valid data directory, find at least one CSV to read columns from
columns_available = []
if os.path.isdir(data_path):
    csv_files = glob.glob(os.path.join(data_path, "*.csv"))
    if csv_files:
        try:
            # Read one CSV just to grab the column names
            sample_df = pd.read_csv(csv_files[0])
            # Strip whitespace from columns, just like your original code
            sample_df.columns = sample_df.columns.str.strip()
            columns_available = list(sample_df.columns)
        except Exception as e:
            st.error(f"Error reading sample CSV for column names: {e}")
    else:
        st.warning("No CSV files found in the specified Data Directory.")
else:
    st.info("Please enter a valid Data Directory.")

# Let user select columns that form the key
key_cols = st.multiselect("Select Key Column(s) for Matching Rows", options=columns_available)

run_button = st.button("Run Comparison")

if run_button:
    # Basic validations
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
        st.write("Locating oldest and newest CSV files in data directory...")
        previous_file_path = get_oldest_file(data_path, "*.csv")
        current_file_path = get_latest_file(data_path, "*.csv")
        
        if not previous_file_path or not current_file_path:
            st.error("Could not find two or more CSV files in the data directory.")
            st.stop()
        if previous_file_path == current_file_path:
            st.error("Only one CSV file found; need at least two for comparison.")
            st.stop()
        
        st.write(f"Previous (oldest): {os.path.basename(previous_file_path)}")
        st.write(f"Current (newest): {os.path.basename(current_file_path)}")
        
        # Read CSVs
        previous_df = pd.read_csv(previous_file_path)
        current_df = pd.read_csv(current_file_path)
        
        # Strip column names
        previous_df.columns = previous_df.columns.str.strip()
        current_df.columns = current_df.columns.str.strip()
        
        # 1. Find rows in previous data that are missing in current
        rows_not_matching_df = previous_df.merge(
            current_df, 
            on=key_cols, 
            how='left', 
            indicator=True
        ).loc[lambda x: x['_merge'] == 'left_only'].drop(columns=['_merge'])
        
        # For each row, determine which columns differ (or if it's missing entirely)
        current_date = datetime.now().strftime("%m/%d/%Y")
        rows_not_matching_df = rows_not_matching_df.apply(
            lambda row: pd.Series({
                **row,
                'Discrepancy_Columns': find_discrepancies(row, current_df, key_cols),
                'Created_Date': current_date
            }),
            axis=1
        )
        
        # 2. Find new rows in current data that didn't exist in previous
        merged_df = current_df.merge(previous_df, on=key_cols, how='outer', indicator=True)
        
        # Build a composite key string for the "missing" set
        def make_key_str(row, key_cols):
            return "||".join(str(row[col]) for col in key_cols)
        
        missing_keys_set = set(rows_not_matching_df.apply(lambda r: make_key_str(r, key_cols), axis=1))
        
        new_rows_df = merged_df[merged_df['_merge'] == 'left_only'].drop(columns=['_merge']).copy()
        new_rows_df_key_str = new_rows_df.apply(lambda r: make_key_str(r, key_cols), axis=1)
        new_rows_df = new_rows_df[~new_rows_df_key_str.isin(missing_keys_set)]
        
        new_rows_df['Discrepancy_Columns'] = 'New row in current download'
        new_rows_df['Created_Date'] = current_date
        
        # 3. Combine missing/changed rows + new rows
        combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
        
        # 4. Save the combined discrepancy CSV
        dt_tm = datetime.now().strftime("%Y%m%d_%H%M%S")
        non_matching_dir = os.path.join(output_path, "Non_Matching_Records")
        os.makedirs(non_matching_dir, exist_ok=True)
        discrepancy_file = os.path.join(non_matching_dir, f"Rows_Not_Matching_{dt_tm}.csv")
        combined_discrepancies_df.to_csv(discrepancy_file, index=False)
        
        # No summary stats or archiving steps (Steps 5 & 6) in this version
        
        st.success("Comparison complete!")
        st.write(f"**Discrepancy report**: {discrepancy_file}")
    
    except Exception as e:
        st.error(f"An error occurred: {e}")
