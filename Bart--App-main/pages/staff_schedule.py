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
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)

# =========================
# AUTH CHECK
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("⚠ Session expired. Please login again.")
    col1, col2, col3 = st.columns(3)
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
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader",
                "Acting_Supervisor", "Supervisor", "Branch_Manager"]

# =========================
# INIT STATE
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

# =========================
# LOAD DATA
# =========================
def load_data(force_reload=False):
    if force_reload or st.session_state.get("cached_df") is None:
        try:
            ws = master_sheet.worksheet("StaffSchedule")
            data = ws.get_all_records()
            df = pd.DataFrame(data) if data else pd.DataFrame()
            st.session_state.cached_df = df
        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state.cached_df = pd.DataFrame()

    return st.session_state.cached_df


# =========================
# SHIFT LOGIC
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
# LOAD DATA
# =========================
all_data_df = load_data()

if all_data_df.empty:
    st.warning("No data found in Google Sheet")
    st.stop()

# =========================
# FIX: AUTO DETECT SHIFT COLUMNS
# =========================
all_columns = list(all_data_df.columns)

SHIFT_COLS = [
    col for col in all_columns
    if re.match(r"(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\s*\(", str(col))
]

# fallback safety
if not SHIFT_COLS:
    st.error("No shift columns found in sheet (check column names)")
    st.stop()

# =========================
# FILTER BRANCH
# =========================
branch = st.session_state.selected_branch
df = all_data_df[all_data_df["Branch"] == branch].copy()

st.title(f"🏢 Schedule: {branch}")

# =========================
# DATE PICKER
# =========================
selected_date = st.date_input("📅 Select Date", value=datetime.today())
week_start = selected_date - timedelta(days=(selected_date.weekday() + 1) % 7)

# =========================
# EDIT MODE
# =========================
edit_mode = st.toggle("Edit Mode Only")

if edit_mode:

    df_display = df[["Name", "Role"]].drop_duplicates().reset_index(drop=True)

    for d in SHIFT_COLS:
        df_display[d] = ""

    # apply buffer
    for i, row in df_display.iterrows():
        for d in SHIFT_COLS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]

    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    config = {
        "Name": st.column_config.SelectboxColumn(
            "Name",
            options=df["Name"].dropna().unique().tolist(),
            width=90,
            required=True
        ),
        "Role": st.column_config.SelectboxColumn(
            "Role",
            options=ROLE_OPTIONS,
            width=90
        ),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True, width=70)
    }

    for d in SHIFT_COLS:
        config[d] = st.column_config.SelectboxColumn(
            label=d,
            options=SHIFT_OPTIONS,
            width=140
        )

    edited_df = st.data_editor(
        df_display,
        column_config=config,
        num_rows="dynamic",
        use_container_width=True
    )

    # handle actions
    for i, row in edited_df.iterrows():
        for d in SHIFT_COLS:
            val = row.get(d)

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                st.rerun()

            if val == "➕ Custom Time":
                st.info(f"Custom time clicked for {row['Name']} on {d}")

    # =========================
    # SUBMIT
    # =========================
    if st.button("✅ Submit"):
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            others = st.session_state.cached_df[
                st.session_state.cached_df["Branch"] != branch
            ].copy()

            new_data = edited_df.copy()
            new_data["Branch"] = branch

            final = pd.concat([others, new_data], ignore_index=True)

            ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

            st.session_state.cached_df = final
            st.session_state.shift_buffer = {}

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

    for d in SHIFT_COLS:
        column_defs.append({"headerName": d, "field": d, "width": 150})

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
