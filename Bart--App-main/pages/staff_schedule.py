import streamlit as st
import pandas as pd
import gspread
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
# AUTH
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("Session expired")
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
# LOAD DATA
# =========================
def load_data():
    data = ws.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame()

all_data_df = load_data()

if all_data_df.empty:
    st.stop()

# =========================
# LOCK SHEET HEADERS (IMPORTANT FIX)
# =========================
SHEET_HEADERS = ws.row_values(1)

BASE_COLUMNS = ["Branch", "Name", "Role"]
SHIFT_COLS = [c for c in SHEET_HEADERS if c not in BASE_COLUMNS]

# only valid shift columns (date-based)
SHIFT_COLS = [
    c for c in SHIFT_COLS
    if re.search(r"\(", c)  # ensures only "Friday (01 May)" type
]

# =========================
# FILTER BRANCH
# =========================
branch = st.session_state.selected_branch
df = all_data_df[all_data_df["Branch"] == branch].copy()

st.title(f"🏢 Schedule: {branch}")

# =========================
# SHIFT LOGIC
# =========================
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
# EDIT MODE
# =========================
edit_mode = st.toggle("Edit Mode Only")

if edit_mode:

    df_display = df[["Name", "Role"]].drop_duplicates().reset_index(drop=True)

    for c in SHIFT_COLS:
        df_display[c] = ""

    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    edited_df = st.data_editor(df_display, num_rows="dynamic", use_container_width=True)

    # =========================
    # SUBMIT (HEADER SAFE MODE)
    # =========================
    if st.button("✅ Submit"):
        try:
            old_data = load_data()

            others = old_data[old_data["Branch"] != branch]

            new_data = edited_df.copy()
            new_data["Branch"] = branch

            final = pd.concat([others, new_data], ignore_index=True)

            # =========================
            # 🔥 CRITICAL FIX: ALIGN WITH SHEET HEADERS
            # =========================
            final = final.reindex(columns=SHEET_HEADERS, fill_value="")

            # NEVER allow header overwrite
            if list(final.columns) != SHEET_HEADERS:
                st.error("Header mismatch detected - aborting write")
                st.stop()

            ws.update(
                values=[SHEET_HEADERS] + final.fillna("").values.tolist()
            )

            st.success("Saved successfully (headers protected)")

        except Exception as e:
            st.error(f"Submit failed: {e}")

# =========================
# VIEW MODE
# =========================
else:

    if st.button("🔄 Refresh Data"):
        st.rerun()

    df_display = df.copy()
    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1)

    AgGrid(df_display, height=500)

# =========================
# BACK
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
