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
# AUTH CHECK
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

sheet = st.session_state.gspread_client.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

ws = sheet.worksheet("StaffSchedule")

# =========================
# SESSION INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

if "pending_dialog" not in st.session_state:
    st.session_state.pending_dialog = None

# =========================
# LOAD DATA (CACHED SAFE)
# =========================
@st.cache_data(ttl=60)
def load_data():
    data = ws.get_all_records()
    return pd.DataFrame(data)

df_all = load_data()

# =========================
# CONFIG
# =========================
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# WEEK BLOCK DETECTION (FIXED FOR YOUR SHEET)
# =========================
def get_week_blocks(cols):
    cols = cols[len(BASE_COLS):]
    blocks = []

    i = 0
    while i < len(cols):
        chunk = cols[i:i+8]   # 7 days + OT
        if len(chunk) < 8:
            break
        blocks.append({
            "days": chunk[:7],
            "ot": chunk[7]
        })
        i += 8

    return blocks

columns = list(df_all.columns)
blocks = get_week_blocks(columns)

if not blocks:
    st.error("Sheet structure not detected")
    st.stop()

# default week
ACTIVE_DAYS = blocks[0]["days"]
ACTIVE_OT = blocks[0]["ot"]

# =========================
# FILTER BRANCH
# =========================
df = df_all[df_all["Branch"] == st.session_state.selected_branch].copy()

# =========================
# BUILD DISPLAY (CRITICAL FIX HERE)
# =========================
def build_display():
    d = df[["Name", "Role"]].copy()

    # safe column mapping (prevents KeyError)
    for col in ACTIVE_DAYS:
        if col in df.columns:
            d[col] = df[col]
        else:
            d[col] = ""

    # apply buffer correctly
    for i in range(len(d)):
        for day in ACTIVE_DAYS:
            key = f"{i}_{day}"
            if key in st.session_state.shift_buffer:
                d.loc[i, day] = st.session_state.shift_buffer[key]

    return d

df_display = build_display()

# =========================
# OT CALC
# =========================
def calculate_ot(row):
    total = 0
    for d in ACTIVE_DAYS:
        val = str(row.get(d, ""))
        match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)", val)
        if match:
            total += float(match.group(1))
    return f"{total} hrs" if total > 0 else "0 hrs"

df_display["Over-Time"] = df_display.apply(calculate_ot, axis=1)

# =========================
# SAFE CUSTOM TIME DIALOG
# =========================
@st.dialog("Custom Time")
def custom_time(row_idx, name, day):

    st.write(f"{name} - {day}")

    c1, c2 = st.columns(2)

    with c1:
        sh = st.selectbox("Start", list(range(1, 13)), key=f"s_{row_idx}_{day}")
        sap = st.selectbox("AM/PM", ["AM", "PM"], key=f"sa_{row_idx}_{day}")

    with c2:
        eh = st.selectbox("End", list(range(1, 13)), key=f"e_{row_idx}_{day}")
        eap = st.selectbox("AM/PM", ["AM", "PM"], key=f"ea_{row_idx}_{day}")

    if st.button("Apply Shift"):
        value = f"{sh} {sap} - {eh} {eap} (OT 2h)"

        st.session_state.shift_buffer[f"{row_idx}_{day}"] = value
        st.session_state.pending_dialog = None

        st.rerun()

# =========================
# SHOW DIALOG (ONLY SAFE PLACE)
# =========================
if st.session_state.pending_dialog:
    d = st.session_state.pending_dialog
    custom_time(d["row"], d["name"], d["day"])

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

    # =========================
    # ACTION DETECTION (NO RERUN LOOP BUG)
    # =========================
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
    # SUBMIT FIXED (MERGES BUFFER)
    # =========================
    if st.button("Submit to Google Sheet"):

        final = build_display().copy()

        final["Branch"] = st.session_state.selected_branch

        ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

        st.success("Saved successfully!")

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
