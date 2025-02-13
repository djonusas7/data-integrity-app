import streamlit as st
import pandas as pd
import os
import glob
from datetime import datetime
import subprocess
import sys
import time
import webbrowser

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
        
        progress_bar = st.progress(0)
        
        # Merge on ALL shared columns to detect partial mismatches.
        progress_bar.progress(20)
        merged_all_cols = previous_df.merge(current_df, how='left', indicator=True)
        rows_not_matching_df = merged_all_cols.loc[merged_all_cols['_merge'] == 'left_only'].drop(columns=['_merge'])
        
        progress_bar.progress(50)
        
        current_date = datetime.now().strftime("%m/%d/%Y")
        rows_not_matching_df = rows_not_matching_df.apply(
            lambda row: pd.Series({
                **row,
                'Discrepancy_Columns': find_discrepancies(row, current_df, key_cols),
                'Created_Date': current_date
            }),
            axis=1
        )
        
        progress_bar.progress(80)
        
        dt_tm = datetime.now().strftime("%Y%m%d_%H%M%S")
        non_matching_dir = os.path.join(output_path, "Non_Matching_Records")
        os.makedirs(non_matching_dir, exist_ok=True)
        discrepancy_file = os.path.join(non_matching_dir, f"Rows_Not_Matching_{dt_tm}.csv")
        
        rows_not_matching_df.to_csv(discrepancy_file, index=False)
        
        progress_bar.progress(100)
        st.success("Comparison complete!")
        st.write(f"**Discrepancy report**: {discrepancy_file}")
    
    except Exception as e:
        st.error(f"An error occurred: {e}")

if __name__ == "__main__":
    streamlit_process = subprocess.Popen([sys.executable, "-m", "streamlit", "run", sys.argv[0]], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(3)
    webbrowser.open("http://localhost:8501")
    streamlit_process.wait()
