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
# GOOGLE CLIENT
# =========================
if "gspread_client" not in st.session_state:
    try:
        creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
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
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader", "Acting_Supervisor", "Supervisor", "Branch_Manager"]

# =========================
# NORMALIZE SHEET COLUMNS
# =========================
def normalize_day_columns(df):
    day_map = {d: [] for d in DAYS}

    for col in df.columns:
        for day in DAYS:
            if str(col).startswith(day):
                day_map[day].append(col)

    return df, day_map

# =========================
# DIALOG (FIXED keys ONLY)
# =========================
@st.dialog("⏰ Set Custom Time")
def custom_time_dialog(row_idx, row_name, day_name):
    st.write(f"Configure shift for **{row_name}** on **{day_name}**")

    col1, col2 = st.columns(2)

    with col1:
        sh = st.selectbox(
            "Start Hour",
            list(range(1, 13)),
            index=8,
            key=f"sh_{row_idx}_{day_name}"
        )

        sap = st.selectbox(
            "AM/PM Start",
            ["AM", "PM"],
            key=f"sap_{row_idx}_{day_name}"
        )

    with col2:
        eh = st.selectbox(
            "End Hour",
            list(range(1, 13)),
            index=5,
            key=f"eh_{row_idx}_{day_name}"
        )

        eap = st.selectbox(
            "AM/PM End",
            ["AM", "PM"],
            key=f"eap_{row_idx}_{day_name}"
        )

    if st.button("Apply Shift", use_container_width=True):
        start = f"{sh} {sap}"
        end = f"{eh} {eap}"
        hrs = calculate_hours(start, end)

        if hrs < 9:
            st.error("❌ Minimum 9 hours required")
        else:
            ot = max(0, hrs - 9)
            value = f"{start} - {end}" + (f" (OT {ot}h)" if ot > 0 else "")

            st.session_state.shift_buffer[f"{row_idx}_{day_name}"] = value
            st.rerun()

# =========================
# LOAD DATA (FIXED)
# =========================
def load_data(force_reload=False):
    if force_reload or st.session_state.get("cached_df") is None:
        try:
            ws = master_sheet.worksheet("StaffSchedule")
            data = ws.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()

            if df.empty:
                df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)

            df, day_map = normalize_day_columns(df)

            st.session_state.cached_df = df
            st.session_state.day_map = day_map

        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state.cached_df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)
            st.session_state.day_map = {d: [] for d in DAYS}

    return st.session_state.cached_df

# =========================
# SHIFT LOGIC (UNCHANGED)
# =========================
def parse_hour(val):
    hour, ap = val.split()
    hour = int(hour)
    if ap == "PM" and hour != 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    return hour

def calculate_hours(start, end):
    s = parse_hour(start)
    e = parse_hour(end)
    if e <= s:
        e += 24
    return e - s

def calculate_row_ot(row):
    total_ot = 0
    for col in row.index:
        if "Over-Time" in col:
            val = str(row.get(col, ""))
            match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
            if match:
                total_ot += float(match.group(1))

    return f"{total_ot} hrs" if total_ot > 0 else "0 hrs"

# =========================
# SESSION INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

if "deleted_staff" not in st.session_state:
    st.session_state.deleted_staff = set()

# =========================
# HEADER
# =========================
st.title(f"🏢 Schedule: {st.session_state.selected_branch}")

selected_date = st.date_input("📅 Select Date", value=datetime.today())
week_start = selected_date - timedelta(days=(selected_date.weekday() + 1) % 7)

day_labels = {d: d for d in DAYS}

# =========================
# LOAD DATA
# =========================
all_data_df = load_data()

df = all_data_df[all_data_df["Branch"] == st.session_state.selected_branch].copy()

# SAFE FIX for dynamic columns
for d in DAYS:
    if d not in df.columns:
        df[d] = ""

# =========================
# EDIT MODE
# =========================
edit_mode = st.toggle("Edit Mode Only")

if edit_mode:

    df_display = df[["Name", "Role"]].drop_duplicates().reset_index(drop=True)

    for d in DAYS:
        df_display[d] = ""

    # apply buffer
    for i, row in df_display.iterrows():
        for d in DAYS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]

    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    config = {
        "Name": st.column_config.SelectboxColumn(
            "Name",
            options=df["Name"].dropna().unique().tolist() if not df.empty else [],
            width=90,
            required=True
        ),
        "Role": st.column_config.SelectboxColumn("Role", options=ROLE_OPTIONS, width=90),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True, width=70)
    }

    for d in DAYS:
        config[d] = st.column_config.SelectboxColumn(
            label=d,
            options=SHIFT_OPTIONS,
            width=120
        )

    edited_df = st.data_editor(
        df_display,
        column_config=config,
        num_rows="dynamic",
        use_container_width=True
    )

    # custom actions (UNCHANGED)
    for i, row in edited_df.iterrows():
        for d in DAYS:
            val = row.get(d)

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                st.rerun()

            if val == "➕ Custom Time":
                custom_time_dialog(i, row["Name"], d)

    # =========================
    # SUBMIT
    # =========================
    if st.button("✅ Submit"):
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            others = st.session_state.cached_df[
                st.session_state.cached_df["Branch"] != st.session_state.selected_branch
            ].copy()

            new_data = edited_df.copy()
            new_data["Branch"] = st.session_state.selected_branch

            final = pd.concat([others, new_data], ignore_index=True)

            ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

            st.session_state.cached_df = final
            st.session_state.shift_buffer = {}
            st.session_state.deleted_staff = set()

            st.success("Submitted Successfully!")

        except Exception as e:
            st.error(f"❌ Submission Failed: {e}")

# =========================
# VIEW MODE
# =========================
else:

    if st.button("🔄 Refresh Data"):
        st.session_state.cached_df = None
        st.rerun()

    df_display = df.copy()
    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    column_defs = [
        {"headerName": "Name", "field": "Name", "width": 120},
        {"headerName": "Role", "field": "Role", "width": 140},
    ]

    for d in DAYS:
        column_defs.append({"headerName": d, "field": d, "width": 130})

    column_defs.append({"headerName": "Over-Time", "field": "Over-Time", "width": 120})

    AgGrid(
        df_display,
        gridOptions={
            "columnDefs": column_defs,
            "defaultColDef": {"resizable": True}
        },
        height=500
    )

# =========================
# BACK BUTTON
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
