import streamlit as st
import pandas as pd
import gspread
import re

from google.oauth2.service_account import Credentials
from datetime import datetime
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
    st.warning("Session expired")
    st.stop()

# =========================
# GOOGLE SHEETS
# =========================
if "gspread_client" not in st.session_state:
    creds = Credentials.from_service_account_info(
        st.secrets["GOOGLE_CREDS_JSON"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    st.session_state.gspread_client = gspread.authorize(creds)

sheet = st.session_state.gspread_client.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

# =========================
# SESSION STATE SAFETY FLAGS
# =========================
st.session_state.setdefault("shift_buffer", {})
st.session_state.setdefault("pending_dialog", None)
st.session_state.setdefault("dialog_open", False)
st.session_state.setdefault("last_trigger", None)
st.session_state.setdefault("cached_df", None)

# =========================
# CONSTANTS
# =========================
SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
BASE_COLS = ["Branch", "Name", "Role"]

# =========================
# LOAD DATA
# =========================
def load_data():
    if st.session_state.cached_df is None:
        ws = sheet.worksheet("StaffSchedule")
        st.session_state.cached_df = pd.DataFrame(ws.get_all_records())
    return st.session_state.cached_df


# =========================
# WEEK BLOCKS
# =========================
def build_week_blocks(columns):
    cols = columns[len(BASE_COLS):]
    blocks = []
    i = 0
    while i < len(cols):
        chunk = cols[i:i+8]
        if len(chunk) < 8:
            break
        blocks.append({"days": chunk[:7], "ot": chunk[7]})
        i += 8
    return blocks


def find_week_index(blocks, date):
    target = date.strftime("%d %b")
    for i, b in enumerate(blocks):
        if any(target in str(c) for c in b["days"]):
            return i
    return 0


# =========================
# SHIFT LOGIC
# =========================
def parse_hour(v):
    h, ap = v.split()
    h = int(h)
    if ap == "PM" and h != 12:
        h += 12
    if ap == "AM" and h == 12:
        h = 0
    return h


def format_shift(s, e):
    s = parse_hour(s)
    e = parse_hour(e)
    if e <= s:
        e += 24
    hrs = e - s
    if hrs < 9:
        return None
    return hrs


# =========================
# DIALOG (NO LOOP SAFE)
# =========================
@st.dialog("Set Custom Time")
def custom_time_dialog(row_key, name, day):

    st.write(f"{name} → {day}")

    c1, c2 = st.columns(2)

    with c1:
        sh = st.selectbox("Start", list(range(1, 13)), key=f"sh_{row_key}_{day}")
        sap = st.selectbox("AM/PM", ["AM", "PM"], key=f"sap_{row_key}_{day}")

    with c2:
        eh = st.selectbox("End", list(range(1, 13)), key=f"eh_{row_key}_{day}")
        eap = st.selectbox("AM/PM", ["AM", "PM"], key=f"eap_{row_key}_{day}")

    apply_all = st.checkbox("Apply all days", key=f"all_{row_key}_{day}")

    if st.button("Apply", key=f"btn_{row_key}_{day}"):

        hrs = format_shift(f"{sh} {sap}", f"{eh} {eap}")

        if hrs is None:
            st.error("Minimum 9 hours required")
            return

        value = f"{sh}{sap}-{eh}{eap} ({hrs}h)"

        if apply_all:
            for d in ACTIVE_DAYS:
                st.session_state.shift_buffer[f"{row_key}_{d}"] = value
        else:
            st.session_state.shift_buffer[f"{row_key}_{day}"] = value

        st.session_state.pending_dialog = None
        st.session_state.dialog_open = False

        st.rerun()
        st.stop()


# =========================
# UI HEADER
# =========================
st.title("Schedule System")

date = st.date_input("Date", value=datetime.today())

# =========================
# LOAD DATA
# =========================
df_all = load_data()

df = df_all.copy()

cols = list(df_all.columns)
blocks = build_week_blocks(cols)

ACTIVE_DAYS = blocks[0]["days"]

# =========================
# ROW KEY
# =========================
df["row_key"] = df["Name"].astype(str) + "_" + df["Role"].astype(str)

# =========================
# DISPLAY DF
# =========================
display = df.copy()

# =========================
# EDIT MODE
# =========================
edited = st.data_editor(
    display,
    key="editor",
    use_container_width=True
)

# =========================
# PROCESS ONLY ON CHANGE (IMPORTANT FIX)
# =========================
if "prev_df" not in st.session_state:
    st.session_state.prev_df = edited.copy()

changed = not edited.equals(st.session_state.prev_df)

if changed:
    st.session_state.prev_df = edited.copy()

    for i, row in edited.iterrows():

        row_key = row["row_key"]

        for d in ACTIVE_DAYS:

            val = row.get(d)

            trigger_key = f"{row_key}_{d}"

            # prevent infinite re-trigger
            if st.session_state.last_trigger == trigger_key:
                continue

            if val == "➕ Custom Time":
                st.session_state.last_trigger = trigger_key
                st.session_state.pending_dialog = {
                    "row_key": row_key,
                    "name": row["Name"],
                    "day": d
                }
                st.rerun()
                st.stop()

            if val == "📴 Day Off":
                st.session_state.shift_buffer[trigger_key] = "OFF"

# =========================
# OPEN DIALOG (SAFE SINGLE EXECUTION)
# =========================
if st.session_state.pending_dialog and not st.session_state.dialog_open:

    st.session_state.dialog_open = True

    d = st.session_state.pending_dialog
    custom_time_dialog(d["row_key"], d["name"], d["day"])

    st.stop()

# reset flag after render cycle
st.session_state.dialog_open = False

# =========================
# VIEW
# =========================
AgGrid(display, height=500)
