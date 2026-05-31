import streamlit as st
import pandas as pd
import gspread
import time
import re

from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from st_aggrid import AgGrid

# =========================
# CONFIG
# =========================
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
    if st.button("⬅ Back to Staff Login"):
        st.switch_page("app.py")
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

# =========================
# CONFIG
# =========================
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = [
    "Team-Member", "Acting_Team_Leader", "Team_Leader",
    "Acting_Supervisor", "Supervisor", "Branch_Manager"
]

# =========================
# SESSION INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

if "pending_dialog" not in st.session_state:
    st.session_state.pending_dialog = None

# =========================
# LOAD DATA
# =========================
def load_data():
    if "cached_df" not in st.session_state or st.session_state.cached_df is None:
        ws = master_sheet.worksheet("StaffSchedule")
        data = ws.get_all_records()
        st.session_state.cached_df = pd.DataFrame(data)
    return st.session_state.cached_df


# =========================
# TIME LOGIC
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


def format_shift(start, end):
    hrs = calculate_hours(start, end)
    if hrs < 9:
        return None, hrs
    ot = max(0, hrs - 9)
    if ot > 0:
        return (f"{start} - {end} (OT {ot}h)", hrs)
    return (f"{start} - {end}", hrs)


# =========================
# OT CALC
# =========================
def calculate_row_ot(row):
    total_ot = 0
    for d in DAYS:
        val = str(row.get(d, ""))
        match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
        if match:
            total_ot += float(match.group(1))
    return f"{total_ot} hrs" if total_ot > 0 else "0 hrs"


# =========================
# CUSTOM TIME DIALOG (FIXED SAFE VERSION)
# =========================
@st.dialog("⏰ Set Custom Time")
def custom_time_dialog(row_idx, row_name, day_name):
    st.write(f"Configure shift for **{row_name}** on **{day_name}**")

    col1, col2 = st.columns(2)

    with col1:
        sh = st.selectbox("Start Hour", list(range(1, 13)), index=8, key=f"sh_{row_idx}_{day_name}")
        sap = st.selectbox("AM/PM", ["AM", "PM"], key=f"sap_{row_idx}_{day_name}")

    with col2:
        eh = st.selectbox("End Hour", list(range(1, 13)), index=5, key=f"eh_{row_idx}_{day_name}")
        eap = st.selectbox("AM/PM", ["AM", "PM"], index=1, key=f"eap_{row_idx}_{day_name}")

    apply_all = st.checkbox("Apply to all working days this week", key=f"all_{row_idx}_{day_name}")

    if st.button("Apply Shift", use_container_width=True):
        value, hrs = format_shift(f"{sh} {sap}", f"{eh} {eap}")

        if value is None:
            st.error("❌ Minimum 9 hours required")
        else:
            if apply_all:
                for d in DAYS:
                    st.session_state.shift_buffer[f"{row_idx}_{d}"] = value
            else:
                st.session_state.shift_buffer[f"{row_idx}_{day_name}"] = value

            st.session_state.pending_dialog = None
            st.rerun()


# =========================
# UI HEADER
# =========================
st.title(f"🏢 Schedule: {st.session_state.selected_branch}")
selected_date = st.date_input("📅 Select Date", value=datetime.today())

edit_mode = st.toggle("Edit Mode Only")

# =========================
# LOAD DATA
# =========================
df_all = load_data()

if df_all.empty:
    st.error("No data found")
    st.stop()

df = df_all[df_all["Branch"] == st.session_state.selected_branch].copy()

# =========================
# DISPLAY TABLE
# =========================
df_display = df[["Name", "Role"] + DAYS].copy()

# apply buffer
for i, row in df_display.iterrows():
    for d in DAYS:
        key = f"{i}_{d}"
        if key in st.session_state.shift_buffer:
            df_display.loc[i, d] = st.session_state.shift_buffer[key]

df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

# =========================
# 🔥 FIX: OPEN DIALOG OUTSIDE LOOP
# =========================
if st.session_state.pending_dialog:
    d = st.session_state.pending_dialog
    custom_time_dialog(d["row_idx"], d["row_name"], d["day_name"])

# =========================
# EDIT MODE
# =========================
if edit_mode:

    config = {
        "Name": st.column_config.SelectboxColumn(
            "Name",
            options=df["Name"].dropna().unique().tolist(),
            width=120
        ),
        "Role": st.column_config.SelectboxColumn(
            "Role",
            options=ROLE_OPTIONS,
            width=120
        ),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True)
    }

    for d in DAYS:
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

    # =========================
    # TRIGGER CUSTOM TIME (FIXED)
    # =========================
    for i, row in edited_df.iterrows():
        for d in DAYS:
            val = row.get(d)

            if val == "➕ Custom Time":
                st.session_state.pending_dialog = {
                    "row_idx": i,
                    "row_name": row["Name"],
                    "day_name": d
                }
                st.rerun()

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"

    # =========================
    # SUBMIT
    # =========================
    if st.button("✅ Submit"):
        ws = master_sheet.worksheet("StaffSchedule")

        others = df_all[df_all["Branch"] != st.session_state.selected_branch]

        new_data = edited_df.copy()
        new_data["Branch"] = st.session_state.selected_branch

        final = pd.concat([others, new_data], ignore_index=True)

        ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

        st.success("Submitted successfully!")

# =========================
# VIEW MODE
# =========================
else:

    column_defs = [
        {"headerName": "Name", "field": "Name"},
        {"headerName": "Role", "field": "Role"}
    ]

    for d in DAYS:
        column_defs.append({"headerName": d, "field": d})

    column_defs.append({"headerName": "Over-Time", "field": "Over-Time"})

    AgGrid(
        df_display,
        gridOptions={
            "columnDefs": column_defs,
            "defaultColDef": {"resizable": True}
        },
        height=500
    )

# =========================
# BACK
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
