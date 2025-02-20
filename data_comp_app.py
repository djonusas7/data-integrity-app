import streamlit as st
import pandas as pd
from datetime import datetime
from PIL import Image
import base64
import io
import os

# --------------------------------------------------------------------
# Set page configuration as the very first Streamlit command
# --------------------------------------------------------------------
st.set_page_config(page_title="Data Integrity Comparison", layout="wide")

# --------------------------------------------------------------------
# Add Logo to the Top Right Corner (using a relative path)
# --------------------------------------------------------------------
# Since this file is in the "scripts" folder, the logo is one level up in "assets"
logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "MCI Logo.jpg")
try:
    logo = Image.open(logo_path)
    buffered = io.BytesIO()
    logo.save(buffered, format="JPEG")
    logo_b64 = base64.b64encode(buffered.getvalue()).decode()
    logo_html = f'''
        <style>
            .logo {{
                position: fixed;
                top: 10px;
                right: 10px;
                width: 150px;
                z-index: 1000;
            }}
        </style>
        <img class="logo" src="data:image/jpeg;base64,{logo_b64}">
    '''
    st.markdown(logo_html, unsafe_allow_html=True)
except Exception as e:
    st.error(f"Error loading logo: {e}")

# --------------------------------------------------------------------
# App Title and Description
# --------------------------------------------------------------------
st.title("Data Integrity Comparison Tool")
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

# Proceed if both files are uploaded
if previous_file is not None and current_file is not None:
    try:
        # Read the uploaded CSV files
        previous_df = pd.read_csv(previous_file)
        current_df = pd.read_csv(current_file)
        
        # Strip whitespace from column names
        previous_df.columns = previous_df.columns.str.strip()
        current_df.columns = current_df.columns.str.strip()
        
        # Use the columns from the previous file to let the user choose key columns
        columns_available = list(previous_df.columns)
        key_cols = st.multiselect("Select the Key Column(s) for Row Identification", options=columns_available)
        
        if not key_cols:
            st.error("Please select at least one key column.")
        else:
            # ----------------------------------------------------------------
            # Helper Functions for Data Comparison
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
                    # Consider both NaN values as matching
                    if pd.isna(old_val) and pd.isna(new_val):
                        continue
                    if old_val != new_val:
                        discrepancies.append(f"{col}: {old_val} != {new_val}")
                return ", ".join(discrepancies)

            def make_key_str(row, key_cols):
                return "||".join(str(row[col]) for col in key_cols)
            
            # ----------------------------------------------------------------
            # Run the Comparison When the User Clicks the Button
            # ----------------------------------------------------------------
            if st.button("Run Comparison"):
                current_date = datetime.now().strftime("%m/%d/%Y")
                
                # 1) Merge on ALL shared columns to detect mismatches
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
                
                # 3) Combine the discrepancies and new rows
                combined_discrepancies_df = pd.concat([rows_not_matching_df, new_rows_df], ignore_index=True)
                
                st.success("Comparison complete!")
                st.write("Discrepancy Report Preview:")
                st.dataframe(combined_discrepancies_df.head())
                
                # Provide a download button for the full report as CSV
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
