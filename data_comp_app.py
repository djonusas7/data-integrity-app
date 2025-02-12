import streamlit as st
import pandas as pd
import os
import glob
from datetime import datetime
import time

st.set_page_config(page_title="Data Integrity Comparison Tool", layout="wide")

st.title("Data Integrity Comparison Tool")
st.markdown(
    """
    This tool compares two CSV files to check that nothing has changed.
    Please provide the following:
    1. Project File Directory (optional)
    2. Data Directory (where your CSV files are stored)
    3. Output Directory (where results will be saved)
    4. Select key column(s) for matching rows.
    """
)

# Input widgets
project_dir = st.text_input("Project File Directory", value="\\\\your\\default\\project\\directory")
data_dir = st.text_input("Data Directory", value="\\\\your\\default\\data\\directory")
output_dir = st.text_input("Output Directory", value="\\\\your\\default\\output\\directory")

# Attempt to extract column names from the first CSV in data_dir
columns = []
if os.path.isdir(data_dir):
    csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
    if csv_files:
        try:
            sample_df = pd.read_csv(csv_files[0])
            sample_df.columns = sample_df.columns.str.strip()
            columns = list(sample_df.columns)
        except Exception as e:
            st.error(f"Error reading CSV: {e}")
    else:
        st.warning("No CSV files found in the Data Directory.")
else:
    st.info("Enter a valid Data Directory.")

# Let user select key columns if available
key_columns = st.multiselect("Select Key Column(s) for Matching Rows", options=columns)

# Run button to start processing
if st.button("Run"):
    if not os.path.isdir(data_dir):
        st.error("Data Directory does not exist.")
    elif not os.path.isdir(output_dir):
        st.error("Output Directory does not exist.")
    elif not key_columns:
        st.error("Select at least one key column.")
    else:
        progress_bar = st.progress(0)
        status_text = st.empty()
        try:
            # Locate CSV files
            status_text.info("Locating CSV files...")
            csv_files = glob.glob(os.path.join(data_dir, "*.csv"))
            if len(csv_files) < 2:
                st.error("At least two CSV files are required.")
                st.stop()

            previous_file_path = min(csv_files, key=os.path.getmtime)
            current_file_path = max(csv_files, key=os.path.getmtime)
            time.sleep(0.5)
            progress_bar.progress(10)

            # Read CSV files
            status_text.info("Reading CSV files...")
            previous_df = pd.read_csv(previous_file_path)
            current_df = pd.read_csv(current_file_path)
            previous_df.columns = previous_df.columns.str.strip()
            current_df.columns = current_df.columns.str.strip()
            time.sleep(0.5)
            progress_bar.progress(20)

            # Identify rows not matching based on key columns
            status_text.info("Comparing data...")
            rows_not_matching_df = previous_df.merge(
                current_df,
                on=key_columns,
                how='left',
                indicator=True
            ).loc[lambda x: x['_merge'] == 'left_only'].drop(columns=['_merge'])
            time.sleep(0.5)
            progress_bar.progress(30)

            def find_discrepancies(row, current_data, key_columns):
                filter_condition = None
                for col in key_columns:
                    cond = current_data[col] == row[col]
                    filter_condition = cond if filter_condition is None else filter_condition & cond
                current_row = current_data[filter_condition]
                if current_row.empty:
                    return "Row missing in latest download"
                current_row = current_row.iloc[0]
                discrepancies = []
                for col in row.index:
                    if col in key_columns:
                        continue
                    if pd.isna(row[col]) and pd.isna(current_row[col]):
                        continue
                    if row[col] != current_row[col]:
                        discrepancies.append(f"{col}: {row[col]} != {current_row[col]}")
                return ", ".join(discrepancies) if discrepancies else "No discrepancy"

            current_date = datetime.now().strftime("%m/%d/%Y")
            rows_not_matching_df = rows_not_matching_df.apply(
                lambda row: pd.Series({
                    **row,
                    'Discrepancy_Columns': find_discrepancies(row, current_df, key_columns),
                    'Created_Date': current_date
                }), axis=1
            )
            time.sleep(0.5)
            progress_bar.progress(50)

            # Identify new rows in current data
            status_text.info("Checking for new rows...")
            merged_df = current_df.merge(previous_df, on=key_columns, how='outer', indicator=True)
            new_rows_df = merged_df.loc[merged_df['_merge'] == 'left_only'].drop(columns=['_merge'])
            new_rows_df['Discrepancy_Columns'] = 'New row in current download'
            new_rows_df['Created_Date'] = current_date
            time.sleep(0.5)
            progress_bar.progress(60)

            # Combine discrepancy reports
            status_text.info("Combining results...")
            combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
            time.sleep(0.5)
            progress_bar.progress(70)

            dt_tm = datetime.now().strftime("%Y%m%d_%H%M%S")
            non_matching_dir = os.path.join(output_dir, "Non_Matching_Records")
            summary_dir = os.path.join(output_dir, "Percentage_Change_Results")
            os.makedirs(non_matching_dir, exist_ok=True)
            os.makedirs(summary_dir, exist_ok=True)
            output_file_path = os.path.join(non_matching_dir, f"Rows_Not_Matching_{dt_tm}.csv")
            combined_discrepancies_df.to_csv(output_file_path, index=False)

            # Create summary statistics
            total_rows_missing = len(rows_not_matching_df)
            total_rows_new = len(new_rows_df)
            total_discrepancies = total_rows_missing + total_rows_new
            total_rows_previous = len(previous_df)
            total_rows_current = len(current_df)
            percentage_change = (total_discrepancies / total_rows_previous) * 100 if total_rows_previous > 0 else 0

            result_df = pd.DataFrame({
                'Oral_Onc_Previous': [total_rows_previous],
                'Oral_Onc_Current': [total_rows_current],
                'Non_Matching_Rows': [total_discrepancies],
                'Percentage_Change': [f"{percentage_change:.2f}%"],
                'Timestamp': [current_date],
                'Missing_Rows': [total_rows_missing],
                'New_Rows': [total_rows_new]
            })

            results_file_path = os.path.join(summary_dir, f"Oral_Onc_Results_{dt_tm}.csv")
            result_df.to_csv(results_file_path, index=False)
            time.sleep(0.5)
            progress_bar.progress(90)

            # Archive the previous file
            status_text.info("Archiving previous file...")
            archive_path = os.path.join(data_dir, "Archive")
            os.makedirs(archive_path, exist_ok=True)
            os.rename(previous_file_path, os.path.join(archive_path, os.path.basename(previous_file_path)))
            time.sleep(0.5)
            progress_bar.progress(100)

            st.success("Data comparison complete!")
            st.write(f"Discrepancy report saved to: **{output_file_path}**")
            st.write(f"Summary results saved to: **{results_file_path}**")

        except Exception as e:
            st.error(f"An error occurred: {e}")
        finally:
            status_text.empty()
