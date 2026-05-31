import streamlit as st
import pandas as pd
import gspread
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
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader", "Acting_Supervisor", "Supervisor", "Branch_Manager"]

BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# WEEK ENGINE (SUNDAY FIX)
# =========================
def get_sunday(date):
    return date - timedelta(days=(date.weekday() + 1) % 7)


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


# =========================
# OT
# =========================
def calculate_row_ot(row, ot_col):
    val = str(row.get(ot_col, ""))
    match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
    return f"{match.group(1)} hrs" if match else "0 hrs"


# =========================
# LOAD DATA
# =========================
def load_data():
    if "cached_df" not in st.session_state:
        ws = master_sheet.worksheet("StaffSchedule")
        data = ws.get_all_records()
        st.session_state.cached_df = pd.DataFrame(data)
    return st.session_state.cached_df


# =========================
# UI
# =========================
st.title(f"🏢 Schedule: {st.session_state.selected_branch}")

selected_date = st.date_input("📅 Select Date", value=datetime.today())

week_start = get_sunday(selected_date)
st.caption(f"Week starts Sunday: {week_start.strftime('%d %b %Y')}")

# =========================
# REFRESH BUTTON
# =========================
col1, col2 = st.columns([1, 6])
with col1:
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.session_state.cached_df = None
        st.session_state.shift_buffer = {}
        st.rerun()

edit_mode = st.toggle("Edit Mode Only")

# =========================
# DATA LOAD
# =========================
df_all = load_data()
df = df_all[df_all["Branch"] == st.session_state.selected_branch].copy()

columns = list(df_all.columns)
week_blocks = build_week_blocks(columns)

active_week = find_week_index(week_blocks, selected_date)
active_block = week_blocks[active_week]

ACTIVE_DAYS = active_block["days"]
ACTIVE_OT = active_block["ot"]

# =========================
# 🔥 FIX: FORCE PROPER COLUMN ORDER
# =========================
def build_view(df):
    display = df[["Name", "Role"]].copy()

    # force correct order (IMPORTANT FIX)
    for d in ACTIVE_DAYS:
        display[d] = df.get(d, "")

    display["Over-Time"] = df.apply(
        lambda r: calculate_row_ot(r, ACTIVE_OT),
        axis=1
    )

    return display


# =========================
# EDIT MODE
# =========================
if edit_mode:

    df_display = build_view(df)

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

    if st.button("✅ Submit"):
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            others = df_all[df_all["Branch"] != st.session_state.selected_branch]

            new_data = edited_df.copy()
            new_data["Branch"] = st.session_state.selected_branch

            final = pd.concat([others, new_data], ignore_index=True)

            ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

            st.success("Submitted successfully!")

        except Exception as e:
            st.error(f"Submit failed: {e}")

# =========================
# VIEW MODE (FIXED DISPLAY)
# =========================
else:

    df_display = build_view(df)

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
