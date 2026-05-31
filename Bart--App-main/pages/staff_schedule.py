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
    st.warning("Session expired")
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

BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# SESSION STATE INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

if "pending_dialog" not in st.session_state:
    st.session_state.pending_dialog = None

if "cached_df" not in st.session_state:
    st.session_state.cached_df = None

# =========================
# LOAD DATA (NO SPAM REFRESH)
# =========================
@st.cache_data(ttl=60)
def load_sheet():
    ws = master_sheet.worksheet("StaffSchedule")
    data = ws.get_all_records()
    return pd.DataFrame(data)

df_all = load_sheet()

# =========================
# WEEK DETECTION
# =========================
columns = list(df_all.columns)
week_cols = columns[3:]   # after Branch, Name, Role

# group 8 columns (7 days + OT)
def get_week_blocks(cols):
    blocks = []
    i = 0
    while i < len(cols):
        chunk = cols[i:i+8]
        if len(chunk) < 8:
            break
        blocks.append(chunk)
        i += 8
    return blocks

blocks = get_week_blocks(week_cols)
ACTIVE_DAYS = blocks[0][:7]
ACTIVE_OT = blocks[0][7]

# =========================
# DATA FILTER
# =========================
df = df_all[df_all["Branch"] == st.session_state.selected_branch].copy()

# =========================
# BUILD DISPLAY SAFE
# =========================
def build_df():
    d = df[["Name", "Role"]].copy()

    for col in ACTIVE_DAYS:
        if col in df.columns:
            d[col] = df[col]
        else:
            d[col] = ""

    # apply buffer (IMPORTANT FIX)
    for i in range(len(d)):
        for day in ACTIVE_DAYS:
            key = f"{i}_{day}"
            if key in st.session_state.shift_buffer:
                d.loc[i, day] = st.session_state.shift_buffer[key]

    return d

df_display = build_df()

# =========================
# OT CALC
# =========================
def calculate_ot(row):
    total = 0
    for d in ACTIVE_DAYS:
        val = str(row.get(d, ""))
        m = re.search(r"\(OT\s+(\d+)", val)
        if m:
            total += float(m.group(1))
    return f"{total} hrs" if total > 0 else "0 hrs"

df_display["Over-Time"] = df_display.apply(calculate_ot, axis=1)

# =========================
# CUSTOM TIME DIALOG (SAFE)
# =========================
@st.dialog("Custom Time")
def custom_dialog(i, name, day):

    st.write(f"{name} - {day}")

    c1, c2 = st.columns(2)

    with c1:
        sh = st.selectbox("Start", list(range(1, 13)), key=f"s_{i}_{day}")
        sap = st.selectbox("AM/PM", ["AM", "PM"], key=f"sp_{i}_{day}")

    with c2:
        eh = st.selectbox("End", list(range(1, 13)), key=f"e_{i}_{day}")
        eap = st.selectbox("AM/PM", ["AM", "PM"], key=f"ep_{i}_{day}")

    if st.button("Apply"):
        value = f"{sh} {sap} - {eh} {eap} (OT 2h)"

        st.session_state.shift_buffer[f"{i}_{day}"] = value
        st.session_state.pending_dialog = None

        st.rerun()

# =========================
# SHOW DIALOG (ONLY HERE)
# =========================
if st.session_state.pending_dialog:
    d = st.session_state.pending_dialog
    custom_dialog(d["row"], d["name"], d["day"])

# =========================
# EDIT MODE
# =========================
edit_mode = st.toggle("Edit Mode")

if edit_mode:

    edited = st.data_editor(
        df_display,
        num_rows="dynamic",
        use_container_width=True
    )

    # detect actions (NO RERUN LOOP BUG FIXED)
    for i, row in edited.iterrows():
        for day in ACTIVE_DAYS:
            val = row.get(day)

            if val == "➕ Custom Time":
                st.session_state.pending_dialog = {
                    "row": i,
                    "name": row["Name"],
                    "day": day
                }

            elif val == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{day}"] = "OFF"

    # =========================
    # SUBMIT FIXED
    # =========================
    if st.button("Submit"):
        ws = master_sheet.worksheet("StaffSchedule")

        final = build_df().copy()
        final["Branch"] = st.session_state.selected_branch

        ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

        st.success("Saved to Google Sheet!")

# =========================
# VIEW MODE
# =========================
else:

    AgGrid(df_display, height=500)

# =========================
# BACK
# =========================
if st.button("Back"):
    st.switch_page("pages/staff_dashboard.py")
