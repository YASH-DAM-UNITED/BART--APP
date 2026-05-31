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
    st.stop()

# =========================
# GOOGLE CLIENT
# =========================
if "gspread_client" not in st.session_state:
    creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    st.session_state.gspread_client = gspread.authorize(creds)

master_sheet = st.session_state.gspread_client.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

ws = master_sheet.worksheet("StaffSchedule")

# =========================
# CONFIG
# =========================
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader",
                "Acting_Supervisor", "Supervisor", "Branch_Manager"]

# =========================
# STATE
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

# =========================
# CUSTOM TIME DIALOG (UNCHANGED)
# =========================
@st.dialog("⏰ Set Custom Time")
def custom_time_dialog(row_idx, row_name, day_name):
    st.write(f"Configure shift for **{row_name}** on **{day_name}**")

    col1, col2 = st.columns(2)
    with col1:
        sh = st.selectbox("Start Hour", list(range(1, 13)), index=8)
        sap = st.selectbox("AM/PM", ["AM", "PM"])
    with col2:
        eh = st.selectbox("End Hour", list(range(1, 13)), index=5)
        eap = st.selectbox("AM/PM", ["AM", "PM"])

    if st.button("Apply Shift", use_container_width=True):
        start = f"{sh} {sap}"
        end = f"{eh} {eap}"

        s = parse_hour(start)
        e = parse_hour(end)
        if e <= s:
            e += 24

        hrs = e - s

        if hrs < 9:
            st.error("❌ Minimum 9 hours required")
        else:
            ot = max(0, hrs - 9)
            value = f"{start} - {end}" + (f" (OT {ot}h)" if ot > 0 else "")

            st.session_state.shift_buffer[f"{row_idx}_{day_name}"] = value
            st.rerun()

# =========================
# HELPERS
# =========================
def parse_hour(val):
    hour, ap = val.split()
    hour = int(hour)
    if ap == "PM" and hour != 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    return hour

def calculate_row_ot(row):
    total_ot = 0
    for col in row.index:
        if "Over-Time" in col:
            val = str(row.get(col, ""))
            match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
            if match:
                total_ot += float(match.group(1))
    return f"{total_ot} hrs" if total_ot else "0 hrs"

# =========================
# LOAD DATA
# =========================
def load_data():
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame()

all_data_df = load_data()

if all_data_df.empty:
    st.stop()

# =========================
# FIX: AUTO DETECT SHIFT COLUMNS
# =========================
SHEET_HEADERS = ws.row_values(1)

SHIFT_COLS = [
    c for c in SHEET_HEADERS
    if re.search(r"\(", c) and c not in ["Branch", "Name", "Role"]
]

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

# =========================
# EDIT MODE
# =========================
edit_mode = st.toggle("Edit Mode Only")

if edit_mode:

    df_display = df[["Name", "Role"]].drop_duplicates().reset_index(drop=True)

    for d in SHIFT_COLS:
        df_display[d] = ""

    # APPLY BUFFER
    for i, row in df_display.iterrows():
        for d in SHIFT_COLS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]

    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    edited_df = st.data_editor(df_display, num_rows="dynamic", use_container_width=True)

    # =========================
    # ACTIONS (UNCHANGED)
    # =========================
    for i, row in edited_df.iterrows():
        for d in SHIFT_COLS:
            val = row.get(d)

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                st.rerun()

            if val == "➕ Custom Time":
                custom_time_dialog(i, row["Name"], d)

    # =========================
    # SUBMIT (ONLY FIX HERE - HEADER LOCK)
    # =========================
    if st.button("✅ Submit"):
        try:
            old_data = load_data()

            others = old_data[old_data["Branch"] != branch].copy()

            new_data = edited_df.copy()
            new_data["Branch"] = branch

            final = pd.concat([others, new_data], ignore_index=True)

            # 🔥 IMPORTANT FIX: MATCH SHEET HEADERS ONLY
            final = final.reindex(columns=SHEET_HEADERS, fill_value="")

            # HARD LOCK: prevent header overwrite
            if list(final.columns) != SHEET_HEADERS:
                st.error("Header mismatch detected. Aborting.")
                st.stop()

            ws.update(
                values=[SHEET_HEADERS] + final.fillna("").values.tolist()
            )

            st.session_state.cached_df = final
            st.session_state.shift_buffer = {}

            st.success("Submitted Successfully!")

        except Exception as e:
            st.error(f"❌ Submission Failed: {e}")

# =========================
# VIEW MODE (UNCHANGED)
# =========================
else:

    if st.button("🔄 Refresh Data"):
        st.rerun()

    df_display = df.copy()
    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    AgGrid(df_display, height=500)

# =========================
# BACK BUTTON
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
