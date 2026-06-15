import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time
import pytz

# --- INITIAL SETUP ---
saudi_tz = pytz.timezone("Asia/Riyadh")
now = datetime.now(saudi_tz)
now_min = now.hour * 60 + now.minute

st.set_page_config(
    layout="wide",
    page_title="Ops Control Center",
    initial_sidebar_state="collapsed"
)

# --- CONFIGURATION & STATE ---
if "data_refresh_token" not in st.session_state:
    st.session_state.data_refresh_token = 0

SHEET_ID = "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
TAB_NAME = "StaffSchedule"

# --- HELPER FUNCTIONS ---
@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["GOOGLE_CREDS_JSON"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=900)
def load_data(refresh_token):
    client = get_client()
    sheet = client.open_by_key(SHEET_ID)
    ws = sheet.worksheet(TAB_NAME)
    raw = ws.get_all_values()
    if not raw:
        return pd.DataFrame()
    return pd.DataFrame(raw[1:], columns=raw[0]).fillna("")

def get_shift(cell):
    if not cell or not isinstance(cell, str): 
        return []
    
    # 1. Clean the string
    cell = str(cell).replace('\xa0', ' ').replace('\u202f', ' ').replace("–", "-").replace("—", "-")
    cell = re.sub(r"\(.*?\)", "", cell).strip()
    
    # 2. Split by | for split shifts
    # If there is no |, parts will just be a list with the original string (Old logic compatibility)
    parts = cell.split('|')
    shift_intervals = []
    
    for part in parts:
        pattern = r"(\d{1,2})\s*(AM|PM)"
        matches = re.findall(pattern, part, re.I)
        
        if len(matches) >= 2:
            def to_minutes(h, m):
                h, m = int(h), m.upper().strip()
                if m == "AM": return (0 if h == 12 else h) * 60
                return (12 if h == 12 else h + 12) * 60
            
            start = to_minutes(matches[0][0], matches[0][1])
            end = to_minutes(matches[1][0], matches[1][1])
            shift_intervals.append((start, end))
            
    return shift_intervals

def is_active_in_range(shift_val, start_min, end_min):
    intervals = get_shift(shift_val)
    if not intervals: 
        return False
    
    # Loop through all blocks (handles old logic as a list of one)
    for s_start, s_end in intervals:
        if s_start < s_end:
            # Standard shift: overlaps if it doesn't end before start OR start after end
            if not (s_end <= start_min or s_start >= end_min):
                return True
        else:
            # Overnight shift: overlaps if it is NOT (ends before start AND starts after end)
            if not (s_end <= start_min and s_start >= end_min):
                return True
                
    return False

def compute(df, start_min, end_min):
    active, inactive = [], []
    cols = df.columns.tolist()
    for _, row in df.iterrows():
        if is_active_in_range(str(row["Shift"]), start_min, end_min):
            active.append(row.to_dict())
        else:
            inactive.append(row.to_dict())
    return pd.DataFrame(active, columns=cols) if active else pd.DataFrame(columns=cols), \
           pd.DataFrame(inactive, columns=cols) if inactive else pd.DataFrame(columns=cols)

def extract_day_month(col):
    match = re.search(r"\((\d{1,2}\s\w{3})\)", col)
    return match.group(1).strip() if match else None

def safe_df(df):
    return df.loc[:, ~df.columns.duplicated()].copy()

# --- UI & DATA LOADING ---
st.title("STAFF Schedule Control Center")
df_full = safe_df(load_data(st.session_state.data_refresh_token))
meta_cols = ["Branch", "Name", "Role"]
shift_cols = [c.strip() for c in df_full.columns if c not in meta_cols]
today_day_month = date.today().strftime("%d %b")
default_index = next((i for i, col in enumerate(shift_cols) if extract_day_month(col) == today_day_month), len(shift_cols) - 1)

col1, col2, col3 = st.columns([4, 1, 1], vertical_alignment="center")
with col1:
    shift_col = st.selectbox("Shift Column", shift_cols, index=default_index, label_visibility="collapsed")
with col2:
    if st.button("🔄", use_container_width=True):
        load_data.clear()
        st.session_state.data_refresh_token += 1
        st.rerun()
with col3:
    if st.button("⬅", use_container_width=True):
        st.switch_page("pages/management_dashboard.py")

# --- CUSTOM RANGE UI ---
st.markdown("### 🕒 Analyze Schedule for Custom Time Range")

# Define the selectors
r1, r2 = st.columns(2)
with r1:
    h1 = st.selectbox("Start Hour", range(1, 13), key="s_h")
    m1 = st.selectbox("Start Min", range(0, 60, 5), key="s_m")
    p1 = st.selectbox("Start Period", ["AM", "PM"], key="s_p")
with r2:
    h2 = st.selectbox("End Hour", range(1, 13), key="e_h")
    m2 = st.selectbox("End Min", range(0, 60, 5), key="e_m")
    p2 = st.selectbox("End Period", ["AM", "PM"], key="e_p")

if st.button("🚀 Calculate Range"):
    # Conversion logic
    def to_min(h, m, p):
        h = 0 if (h == 12 and p == "AM") else (h if p == "AM" else (h + 12 if h < 12 else 12))
        return (h * 60) + m

    st.session_state.start_min = to_min(h1, m1, p1)
    st.session_state.end_min = to_min(h2, m2, p2)
    
    # Save the strings so the header doesn't crash
    st.session_state.start_time_str = f"{h1:02}:{m1:02} {p1}"
    st.session_state.end_time_str = f"{h2:02}:{m2:02} {p2}"
    st.rerun()

# --- ENSURE VARIABLES EXIST FOR THE REST OF THE APP ---
start_input = st.session_state.get("start_time_str", "12:00 AM")
end_input = st.session_state.get("end_time_str", "11:59 PM")

# --- CORE CALCULATION ---
df_work = df_full.copy()
df_work["Shift"] = df_work[shift_col]
branches = sorted(df_work["Branch"].dropna().unique().tolist())
start_m, end_m = st.session_state.start_min, st.session_state.end_min

# Universal Overview
u_act, u_inact = compute(df_work, start_m, end_m)
st.subheader(f"STAFF Universal Overview ({start_input} to {end_input})")
c1, c2, c3, c4 = st.columns(4)
c1.metric("🏢 Branches", len(branches)); c2.metric("👥 Staff", len(df_work)); c3.metric("🟢 Active", len(u_act)); c4.metric("⚪ Inactive", len(u_inact))
st.divider()

# Branchwise Status
st.subheader("👥 Branchwise Status")
summary = [{"Branch": b, "Active": len(compute(df_work[df_work["Branch"] == b], start_m, end_m)[0]), "Inactive": len(compute(df_work[df_work["Branch"] == b], start_m, end_m)[1])} for b in branches]
st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)
st.divider()

# Specific Branch View
s_col1, _ = st.columns([1, 2])
with s_col1: selected_branch = st.selectbox("🏢 Select Branch", branches)
df_branch = df_work[df_work["Branch"] == selected_branch]
b_act, b_inact = compute(df_branch, start_m, end_m)

st.subheader(f"🏢 {selected_branch} Detailed Overview")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("Active", len(b_act)); sc2.metric("Inactive", len(b_inact)); sc3.metric("Total", len(df_branch))
st.subheader("🔥 Active Staff"); st.dataframe(b_act, use_container_width=True, hide_index=True)
st.subheader("📊 Full Branch Data"); st.dataframe(pd.concat([b_act, b_inact], ignore_index=True), use_container_width=True, hide_index=True)
