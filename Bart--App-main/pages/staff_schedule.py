import streamlit as st
import pandas as pd
import gspread
import time
import re

from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from st_aggrid import AgGrid

st.set_page_config(layout="wide", page_title="BART Master Schedule")


st.markdown("""
<style>
[data-testid="stSidebar"] {
    display: none;
}

[data-testid="collapsedControl"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)

# =========================
# AUTH CHECK
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("⚠ Session expired. Please login again.")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("⬅ Back to Staff Login", use_container_width=True):
            st.switch_page("app.py")
    st.stop()

# =========================
# INITIALIZE GOOGLE CLIENT (FIXED)
# =========================
if "gspread_client" not in st.session_state:
    try:
        # Load credentials from st.secrets
        creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
        
        # Use modern google-auth Credentials
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        st.session_state.gspread_client = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Authentication setup error: {e}")
        st.stop()

master_sheet = st.session_state.gspread_client.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

# =========================
# CONFIG
# =========================
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
SHIFT_OPTIONS = ["➕ Straight Duty", " ➕ Break Duty", "Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader", "Acting_Supervisor", "Supervisor", "Branch_Manager"]

# =========================
# DIALOGS
# =========================
@st.dialog("✅ Submission Successful")
def success_dialog():
    st.success("Your schedule has been successfully submitted to the Master Schedule.")
    if st.button("Close", use_container_width=True):
        st.rerun()




@st.dialog(" Set Break Duty")
def break_duty_dialog(row_idx, row_name, day_name):
    st.write(f"Configure Break Duty for **{row_name}** on **{day_name}**")
    
    # Dropdowns for D1 and D2
    d1s = st.selectbox("D1 Start", [f"{h}{ap}" for h in range(1, 13) for ap in ["AM", "PM"]], key=f"d1s_{row_idx}_{day_name}")
    d1e = st.selectbox("D1 End", [f"{h}{ap}" for h in range(1, 13) for ap in ["AM", "PM"]], index=3, key=f"d1e_{row_idx}_{day_name}")
    d2s = st.selectbox("D2 Start", [f"{h}{ap}" for h in range(1, 13) for ap in ["AM", "PM"]], index=8, key=f"d2s_{row_idx}_{day_name}")
    d2e = st.selectbox("D2 End", [f"{h}{ap}" for h in range(1, 13) for ap in ["AM", "PM"]], index=11, key=f"d2e_{row_idx}_{day_name}")
    
    apply_all = st.checkbox("Apply to all working days this week")
    
    if st.button("Apply Break Duty", use_container_width=True):
        # Calculate hours using existing logic
        hrs1 = calculate_hours(d1s, d1e)
        hrs2 = calculate_hours(d2s, d2e)
        total_hrs = hrs1 + hrs2
        
        # Validation: Check if total hours meet the 9-hour requirement
        if total_hrs < 9:
            st.error(f"❌ Total duration is {total_hrs} hours. Minimum 9 hours required.")
        else:
            value = format_break_duty(d1s, d1e, d2s, d2e)
            
            if apply_all:
                for day in DAYS:
                    st.session_state.shift_buffer[f"{row_idx}_{day}"] = value
            else:
                st.session_state.shift_buffer[f"{row_idx}_{day_name}"] = value
            st.rerun()
@st.dialog("⏰ Set Custom Time")
def custom_time_dialog(row_idx, row_name, day_name):
    st.write(f"Configure shift for **{row_name}** on **{day_name}**")
    col1, col2 = st.columns(2)
    with col1:
        sh = st.selectbox("Start Hour", list(range(1, 13)), index=4)
        sap = st.selectbox("AM/PM", ["AM", "PM"], key="sap_modal")
    with col2:
        eh = st.selectbox("End Hour", list(range(1, 13)), index=4)
        eap = st.selectbox("AM/PM", ["AM", "PM"], key="eap_modal", index=1)
    apply_all = st.checkbox("Apply to all working days this week")
    if st.button("Apply Shift", use_container_width=True):
        value, hrs = format_shift(f"{sh} {sap}", f"{eh} {eap}")
        if value is None:
            st.error("❌ Minimum 9 hours required")
        else:
            if apply_all:
                for day in DAYS:
                    st.session_state.shift_buffer[f"{row_idx}_{day}"] = value
            else:
                st.session_state.shift_buffer[f"{row_idx}_{day_name}"] = value
            st.rerun()

@st.dialog("🚫 Submission Blocked")
def duplicate_submission_dialog():
    st.error("This week's schedule has already been submitted for this branch.")
    if st.button("Close", use_container_width=True):
        st.rerun()

# =========================
# LOGIC FUNCTIONS
# =========================
def load_data(force_reload=False):
    if force_reload or st.session_state.get("cached_df") is None:
        try:
            ws = master_sheet.worksheet("StaffSchedule")
            data = ws.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
            if not df.empty:
                new_cols = {}
                for col in df.columns:
                    for day in DAYS:
                        if day in col:
                            new_cols[col] = day
                            break
                df = df.rename(columns=new_cols)
            if df.empty:
                df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS + ["Over-Time"])
            st.session_state.cached_df = df
        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state.cached_df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS + ["Over-Time"])
    return st.session_state.cached_df

def parse_hour(val):
    # If there's a space, split normally. 
    # If not, use regex to separate numbers from letters.
    if " " in val:
        hour, ap = val.split()
    else:
        # Matches digits followed by non-digits
        match = re.match(r"(\d+)([a-zA-Z]+)", val)
        if match:
            hour, ap = match.groups()
        else:
            return 0 # Fallback
            
    hour = int(hour)
    ap = ap.upper() # Ensure case consistency
    
    if ap == "PM" and hour != 12: hour += 12
    if ap == "AM" and hour == 12: hour = 0
    return hour

def calculate_hours(start, end):
    s = parse_hour(start)
    e = parse_hour(end)
    if e <= s: e += 24
    return e - s

def format_shift(start, end):
    hrs = calculate_hours(start, end)
    ot = max(0, hrs - 9)
    if ot > 0:
        return (f"{start} - {end} (OT {ot}h)", hrs)
    return (f"{start} - {end}", hrs)

def format_break_duty(d1s, d1e, d2s, d2e):
    # Calculate total hours from both duties
    hrs1 = calculate_hours(d1s, d1e)
    hrs2 = calculate_hours(d2s, d2e)
    total_hrs = hrs1 + hrs2
    
    ot = max(0, total_hrs - 9)
    # The saved string format
    value = f"{d1s}-{d1e}|{d2s}-{d2e}"
    if ot > 0:
        value = f"{value} (OT {ot}h)"
    return value

def calculate_row_ot(row):
    total_ot = 0
    for day in DAYS:
        val = str(row.get(day, ""))
        match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
        if match: total_ot += float(match.group(1))
    return f"{total_ot} hrs" if total_ot > 0 else "0 hrs"

# =========================
# INITIALIZATION
# =========================
if "shift_buffer" not in st.session_state: st.session_state.shift_buffer = {}
if "previous_week" not in st.session_state: st.session_state.previous_week = None
if "deleted_staff" not in st.session_state: st.session_state.deleted_staff = set()

st.title(f"🏢 Schedule: {st.session_state.selected_branch}")
selected_date = st.date_input("📅 Select Date", value=datetime.today())
week_start = selected_date - timedelta(days=(selected_date.weekday() + 1) % 7)
week_start_str = week_start.strftime('%d %b %Y')
st.caption(f"Week starting: {week_start_str}")

if st.session_state.previous_week != week_start_str:
    st.session_state.shift_buffer = {}
    st.session_state.deleted_staff = set()
    st.session_state.previous_week = week_start_str

edit_mode = st.toggle("Edit Mode Only")
all_data_df = load_data()
df = all_data_df[all_data_df["Branch"] == st.session_state.selected_branch].copy() if not all_data_df.empty else pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)
day_labels = {d: f"{d} ({(week_start + timedelta(days=i)).strftime('%d %b')})" for i, d in enumerate(DAYS)}

existing_week_data = pd.DataFrame()
if not st.session_state.cached_df.empty:
    temp_df = st.session_state.cached_df.copy()
    week_cols = [day_labels[d] for d in DAYS]
    available_cols = [c for c in week_cols if c in temp_df.columns]
    if available_cols:
        branch_data = temp_df[temp_df["Branch"] == st.session_state.selected_branch]
        existing_week_data = branch_data[branch_data[available_cols].fillna("").astype(str).apply(lambda row: any(v.strip() != "" for v in row), axis=1)]

# =========================
# EDIT MODE
# =========================



if edit_mode:
    # 1. Prepare df_display
    df_display = (df[["Name", "Role"]].dropna(subset=["Name"]).drop_duplicates().reset_index(drop=True)) if not df.empty else pd.DataFrame(columns=["Name", "Role"] + DAYS)
    if st.session_state.deleted_staff: 
        mask = df_display.apply(lambda row: (row["Name"], row["Role"]) in st.session_state.deleted_staff, axis=1)
        df_display = df_display[~mask].reset_index(drop=True)
    
    
    
    # Ensure all days are columns
    for d in DAYS:
        if d not in df_display.columns: df_display[d] = ""
    
    # Populate display from shift_buffer (Source of Truth)
    for i, row in df_display.iterrows():
        for d in DAYS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer: 
                df_display.loc[i, d] = st.session_state.shift_buffer[key]
    
    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    # 2. Config & Editor
    all_known_shifts = set(SHIFT_OPTIONS)
    for d in DAYS:
        if d in df_display.columns:
            all_known_shifts.update(df_display[d].dropna().astype(str).unique().tolist())
    
    config = {
        "Name": st.column_config.SelectboxColumn("Name", options=(df["Name"].dropna().unique().tolist() if not df.empty else []), width=90, required=True),
        "Role": st.column_config.SelectboxColumn("Role", options=(df["Role"].dropna().unique().tolist() if not df.empty else []), width=90, required=True),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True, width=70)
    }
    for d in DAYS:
        config[d] = st.column_config.SelectboxColumn(label=day_labels[d], options=list(all_known_shifts), width=100)

    # Clear Button
    if st.button(" Clear All Shifts"):
        for i in range(len(df_display)):
            for d in DAYS:
                st.session_state.shift_buffer[f"{i}_{d}"] = ""
        st.rerun()

    if st.button("🔄 Refresh Grid"):
        st.rerun()
        
    

    # Render Editor
    edited_df = st.data_editor(df_display[["Name", "Role"] + DAYS + ["Over-Time"]], column_config=config, num_rows="dynamic", use_container_width=True, key="editor")
    
    # 3. Sync State & Handle Triggers
    # Sync edited data to buffer (handles copy-paste)
    for i, row in edited_df.iterrows():
        for d in DAYS:
            new_val = row.get(d)
            if new_val is not None and str(new_val).strip() != "":
                st.session_state.shift_buffer[f"{i}_{d}"] = new_val

    # Handle logic triggers
    trigger_rerun = False
    for i, row in edited_df.iterrows():
        for d in DAYS:
            value = row.get(d)
            if value == "Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                trigger_rerun = True
            elif value == "➕ Straight Duty":
                custom_time_dialog(row_idx=i, row_name=row["Name"], day_name=d)
            elif value == "➕ Break Duty":
                break_duty_dialog(row_idx=i, row_name=row["Name"], day_name=d)

    if trigger_rerun:
        st.rerun()

    # Sync deleted staff
    current_names = set(edited_df["Name"].dropna().tolist())
    for name in df_display["Name"].tolist():
        if name not in current_names: st.session_state.deleted_staff.add(name)

    # 4. SUBMIT BUTTON
    if st.button("✅ Submit"):
        if not existing_week_data.empty:
            duplicate_submission_dialog()
            st.stop()
            
        try:
            ws = master_sheet.worksheet("StaffSchedule")
            start_date_comparison = datetime(2026, 6, 1)
            week_start_dt = datetime.combine(week_start, datetime.min.time())
            week_diff = (week_start_dt - start_date_comparison).days // 7
            ot_header = "Over-Time" if week_diff == 0 else f"Over-Time {week_diff}"
            
            headers = ws.row_values(1)
            all_records = ws.get_all_records()
            updates = []
            
            for i, row in edited_df.iterrows():
                # Locate Row
                target_row_idx = None
                for idx, record in enumerate(all_records):
                    if record.get("Branch") == st.session_state.selected_branch and record.get("Name") == row["Name"]:
                        target_row_idx = idx + 2
                        break
                
                if not target_row_idx:
                    target_row_idx = len(all_records) + 2
                    ws.update_cell(target_row_idx, 1, st.session_state.selected_branch)
                    ws.update_cell(target_row_idx, 2, row["Name"])
                    all_records.append({"Branch": st.session_state.selected_branch, "Name": row["Name"]})

                cols_to_map = {d: day_labels[d] for d in DAYS}
                cols_to_map["Over-Time"] = ot_header
                
                for key, day_header in cols_to_map.items():
                    if day_header not in headers:
                        new_col_idx = len(headers) + 1
                        ws.update_cell(1, new_col_idx, day_header)
                        headers.append(day_header)
                        col_idx = new_col_idx
                    else:
                        col_idx = headers.index(day_header) + 1
                    
                    updates.append(gspread.Cell(row=target_row_idx, col=col_idx, value=str(row[key])))
            
            ws.update_cells(updates)
            st.session_state.shift_buffer = {}
            st.session_state.deleted_staff = set()
            success_dialog()
            
        except Exception as e:
            st.error(f"❌ Submission Failed: {e}")
# =========================
# VIEW MODE
# =========================
else:
    if st.button("🔄 Refresh Data"):
        st.session_state.cached_df = None
        st.rerun()

    # 1. Fetch raw data
    try:
        ws = master_sheet.worksheet("StaffSchedule")
        all_values = ws.get_all_values()
    except Exception as e:
        st.error(f"Error accessing sheet: {e}")
        st.stop()
    
    if not all_values or len(all_values) < 2:
        st.warning("No data found.")
        st.stop()

    headers = all_values[0]
    data_rows = all_values[1:]
    
    # 2. Identify indices for key columns
    try:
        idx_branch = headers.index("Branch")
        idx_name = headers.index("Name")
        idx_role = headers.index("Role")
    except ValueError:
        st.error("Sheet headers are missing 'Branch', 'Name', or 'Role'.")
        st.stop()
    
    # 3. Calculate target columns for the selected week
    week_cols = [day_labels[d] for d in DAYS]
    start_date_comparison = datetime(2026, 6, 1)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_diff = (week_start_dt - start_date_comparison).days // 7
    ot_col_name = "Over-Time" if week_diff == 0 else f"Over-Time {week_diff}"
    
    target_headers = ["Name", "Role","CONTACT"] + week_cols + [ot_col_name]
    
    # Map headers to indices
    header_to_idx = {h: i for i, h in enumerate(headers)}
    indices_to_extract = {h: header_to_idx[h] for h in target_headers if h in header_to_idx}
            
    # 4. Extract data ONLY for selected branch
    clean_data = []
    for row in data_rows:
        if row[idx_branch] == st.session_state.selected_branch:
            new_row = {}
            for h, idx in indices_to_extract.items():
                new_row[h] = row[idx] if idx < len(row) else ""
            clean_data.append(new_row)
        
    df_display = pd.DataFrame(clean_data)

    # 5. Render the Grid and Download Button
    if df_display.empty:
        st.info("No schedule data found for this branch this week.")
    else:
        # Prepare CSV for download
        csv = df_display.to_csv(index=False).encode('utf-8')
        
        col1, col2 = st.columns([0.8, 0.2])
        with col2:
            st.download_button(
                label="📥 Download Schedule ",
                data=csv,
                file_name=f"Schedule_{st.session_state.selected_branch}_{week_start_str}.csv",
                mime="text/csv",
                use_container_width=True
            )

        column_defs = [
            {"headerName": col, "field": col, "pinned": "left" if col in ["Name", "Role"] else None}
            for col in df_display.columns
        ]

        AgGrid(
            df_display, 
            gridOptions={
                "columnDefs": column_defs, 
                "defaultColDef": {"resizable": True}
            }, 
            height=500,
            fit_columns_on_grid_load=True
        )

# Final navigation button
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
