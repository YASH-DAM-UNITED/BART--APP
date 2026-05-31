import streamlit as st
import pandas as pd
import gspread
import re

from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from st_aggrid import AgGrid

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(layout="wide", page_title="BART Master Schedule")

st.markdown("""
<style>
[data-testid="stSidebar"] { display: none; }
[data-testid="collapsedControl"] { display: none; }
</style>
""", unsafe_allow_html=True)

# =========================
# AUTH
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("⚠ Session expired. Please login again.")
    if st.button("⬅ Back to Staff Login"):
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
ROLE_OPTIONS = [
    "Team-Member", "Acting_Team_Leader", "Team_Leader",
    "Acting_Supervisor", "Supervisor", "Branch_Manager"
]

BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# SAFE LOAD
# =========================
def load_data():
    if "cached_df" not in st.session_state or st.session_state.cached_df is None:
        ws = master_sheet.worksheet("StaffSchedule")
        data = ws.get_all_records()
        st.session_state.cached_df = pd.DataFrame(data)
    return st.session_state.cached_df


# =========================
# WEEK BLOCK ENGINE (IMPORTANT)
# =========================
def build_week_blocks(columns):
    cols = columns[len(BASE_COLS):]
    blocks = []

    i = 0
    while i < len(cols):
        chunk = cols[i:i+8]  # 7 days + OT
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
            if target in str(col):
                return idx
    return 0


# =========================
# OT FIX (WORKS FOR ALL BLOCKS)
# =========================
def calculate_row_ot(row, ot_col):
    val = str(row.get(ot_col, "")).lower()

    match = re.findall(r"(\d+(?:\.\d+)?)\s*h", val)
    if match:
        return f"{sum(float(x) for x in match)} hrs"

    match2 = re.findall(r"ot\s*[:\-]?\s*(\d+(?:\.\d+)?)", val)
    if match2:
        return f"{sum(float(x) for x in match2)} hrs"

    return "0 hrs"


# =========================
# VIEW BUILDER (DYNAMIC WEEK)
# =========================
def build_view(df):
    display = pd.DataFrame()
    display["Name"] = df["Name"]
    display["Role"] = df["Role"]

    for d in ACTIVE_DAYS:
        display[d] = df.get(d, "")

    display["Over-Time"] = df.apply(
        lambda r: calculate_row_ot(r, ACTIVE_OT),
        axis=1
    )

    return display


# =========================
# UI
# =========================
st.title(f"🏢 Schedule: {st.session_state.selected_branch}")

selected_date = st.date_input("📅 Select Date", value=datetime.today())

# =========================
# LOAD DATA
# =========================
df_all = load_data()

if df_all.empty:
    st.error("No data found in sheet")
    st.stop()

df = df_all[df_all["Branch"] == st.session_state.selected_branch].copy()

# =========================
# BUILD WEEK SYSTEM
# =========================
columns = list(df_all.columns)
week_blocks = build_week_blocks(columns)

active_week = find_week_index(week_blocks, selected_date)
active_block = week_blocks[active_week]

ACTIVE_DAYS = active_block["days"]
ACTIVE_OT = active_block["ot"]

# =========================
# SHIFT BUFFER (RESTORED)
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

edit_mode = st.toggle("Edit Mode Only")

# =========================
# DISPLAY DATA
# =========================
def apply_buffer(df_display):
    for i, row in df_display.iterrows():
        for d in ACTIVE_DAYS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]
    return df_display


# =========================
# EDIT MODE
# =========================
if edit_mode:

    df_display = build_view(df)
    df_display = apply_buffer(df_display)

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

    for d in ACTIVE_DAYS:
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

    # SHIFT BUFFER SAVE
    for i, row in edited_df.iterrows():
        for d in ACTIVE_DAYS:
            val = row.get(d)

            if val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"

            if val == "➕ Custom Time":
                st.session_state.shift_buffer[f"{i}_{d}"] = "CUSTOM"

    # SUBMIT
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

    df_display = build_view(df).reset_index(drop=True)

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
# BACK
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
