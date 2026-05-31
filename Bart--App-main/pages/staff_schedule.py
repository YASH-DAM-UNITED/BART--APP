import streamlit as st
import pandas as pd
import gspread
import time

from google.oauth2.service_account import Credentials
from datetime import datetime
from st_aggrid import AgGrid

# =========================
# CONFIG
# =========================
st.set_page_config(layout="wide", page_title="Schedule System")

CACHE_TTL = 60 * 20  # 20 minutes

# =========================
# AUTH
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("Session expired")
    st.stop()

# =========================
# GOOGLE SHEETS CLIENT
# =========================
if "gclient" not in st.session_state:
    creds = Credentials.from_service_account_info(
        st.secrets["GOOGLE_CREDS_JSON"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    st.session_state.gclient = gspread.authorize(creds)

sheet = st.session_state.gclient.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

# =========================
# CACHE INIT
# =========================
st.session_state.setdefault("cached_df", None)
st.session_state.setdefault("cache_time", 0)

# =========================
# SAFE DATA LOADER (STRICT CACHE)
# =========================
def load_data(force=False):

    now = time.time()

    # USE CACHE IF VALID
    if (
        not force
        and st.session_state.cached_df is not None
        and (now - st.session_state.cache_time) < CACHE_TTL
    ):
        return st.session_state.cached_df

    # API CALL ONLY HERE
    ws = sheet.worksheet("StaffSchedule")
    df = pd.DataFrame(ws.get_all_records())

    st.session_state.cached_df = df
    st.session_state.cache_time = now

    return df


# =========================
# MANUAL REFRESH BUTTON (ONLY API TRIGGER)
# =========================
col1, col2 = st.columns([1, 6])

with col1:
    if st.button("🔄 Refresh Data"):
        load_data(force=True)
        st.success("Data refreshed from Google Sheets")
        st.rerun()

with col2:
    st.caption(
        f"Last updated: "
        f"{datetime.fromtimestamp(st.session_state.cache_time).strftime('%Y-%m-%d %H:%M:%S') if st.session_state.cache_time else 'Never'}"
    )

# =========================
# LOAD DATA (CACHE ONLY)
# =========================
df = load_data()

if df is None or df.empty:
    st.error("No data found")
    st.stop()

# =========================
# VIEW MODE (NO API CALLS HERE)
# =========================
st.title("📅 Schedule View (Cached)")

view_mode = st.toggle("Edit Mode")

# =========================
# SIMPLE DISPLAY
# =========================
if view_mode:

    edited = st.data_editor(
        df,
        use_container_width=True,
        key="editor"
    )

else:

    AgGrid(df, height=500)

# =========================
# BACK BUTTON
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
