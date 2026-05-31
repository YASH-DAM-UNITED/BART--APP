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
    col1, col2, col3 = st.columns(3)
    with col2:
        if st.button("⬅ Back to Staff Login", use_container_width=True):
            st.switch_page("app.py")
    st.stop()

# =========================
# GOOGLE AUTH
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
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader", "Acting_Supervisor", "Supervisor", "Branch_Manager"]

BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# WEEK BLOCK ENGINE
# =========================
def build_week_blocks(columns):
    blocks = []
    cols = columns[len(BASE_COLS):]

    i = 0
    while i < len(cols):
        chunk = cols[i:i+8]
        if len(chunk) < 8:
            break

        blocks.append({
            "days": chunk[:7],
            "ot": chunk[7]
        })
        i += 8

    return blocks


def find_week_index(blocks, selected_date):
    target = selected_date.strftime("%d %b")

    for idx, b in enumerate(blocks):
        for col in b["days"]:
            if target in col:
                return idx
    return 0


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


def calculate_row_ot(row, ot_col):
    val = str(row.get(ot_col, ""))
    match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
    return f"{match.group(1)} hrs" if match else "0 hrs"


# =========================
# LOAD DATA
# =========================
def load_data(force_reload=False):
    if force_reload or st.session_state.get("cached_df") is None:
        ws = master_sheet.worksheet("StaffSchedule")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        st.session_state.cached_df = df
    return st.session_state.cached_df


# =========================
# SESSION INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

st.title(f"🏢 Schedule: {st.session_state.selected_branch}")

selected_date = st.date_input("📅 Select Date", value=datetime.today())

edit_mode = st.toggle("Edit Mode Only")

# =========================
# LOAD + WEEK DETECTION
# =========================
all_data_df = load_data()
df = all_data_df[all_data_df["Branch"] == st.session_state.selected_branch].copy()

columns = list(all_data_df.columns)
week_blocks = build_week_blocks(columns)

active_week = find_week_index(week_blocks, selected_date)
active_block = week_blocks[active_week]

ACTIVE_DAYS = active_block["days"]
ACTIVE_OT = active_block["ot"]

# =========================
# DISPLAY LABELS
# =========================
day_labels = {d: d for d in ACTIVE_DAYS}

# =========================
# EDIT MODE
# =========================
if edit_mode:

    df_display = df[["Name", "Role"]].copy()

    for d in ACTIVE_DAYS:
        df_display[d] = ""

    for i, row in df_display.iterrows():
        for d in ACTIVE_DAYS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]

    df_display["Over-Time"] = df_display.apply(
        lambda r: calculate_row_ot(r, ACTIVE_OT),
        axis=1
    )

    config = {
        "Name": st.column_config.SelectboxColumn(
            "Name",
            options=df["Name"].dropna().unique().tolist(),
            width=100
        ),
        "Role": st.column_config.SelectboxColumn(
            "Role",
            options=ROLE_OPTIONS,
            width=120
        ),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True)
    }

    for d in ACTIVE_DAYS:
        config[d] = st.column_config.SelectboxColumn(
            label=d,
            options=SHIFT_OPTIONS,
            width=130
        )

    edited_df = st.data_editor(
        df_display,
        column_config=config,
        num_rows="dynamic",
        use_container_width=True
    )

    # handle shifts
    for i, row in edited_df.iterrows():
        for d in ACTIVE_DAYS:
            val = row.get(d)

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                st.rerun()

            if val == "➕ Custom Time":
                st.session_state.shift_buffer[f"{i}_{d}"] = "CUSTOM"

    # =========================
    # SUBMIT
    # =========================
    if st.button("✅ Submit"):
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            others = all_data_df[all_data_df["Branch"] != st.session_state.selected_branch]

            new_data = edited_df.copy()
            new_data["Branch"] = st.session_state.selected_branch

            final = pd.concat([others, new_data], ignore_index=True)

            ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

            st.success("Submitted successfully!")
            st.session_state.shift_buffer = {}

        except Exception as e:
            st.error(f"Submit failed: {e}")

# =========================
# VIEW MODE
# =========================
else:
    df_display = df.copy()

    df_display["Over-Time"] = df_display.apply(
        lambda r: calculate_row_ot(r, ACTIVE_OT),
        axis=1
    )

    column_defs = [
        {"headerName": "Name", "field": "Name"},
        {"headerName": "Role", "field": "Role"}
    ]

    for d in ACTIVE_DAYS:
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
# BACK BUTTON
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
