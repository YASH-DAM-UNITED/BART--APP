import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date, time
import pytz
from datetime import datetime, date, time, timedelta

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



# --- INITIALIZATION ---
if "start_min" not in st.session_state:
    st.session_state.start_min = 0  # 12:00 AM
if "end_min" not in st.session_state:
    st.session_state.end_min = 1439  # 11:59 PM
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








meta_cols = ["Name", "Role","CONTACT"]
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
    if st.button("⬅Back", use_container_width=True):
        st.switch_page("pages/management_dashboard.py")

# --- CUSTOM RANGE UI ---
st.markdown("### 🕒 Analyze Schedule for Custom Time Range")

if "start_time_str" not in st.session_state: st.session_state.start_time_str = "12:00 AM"
if "end_time_str" not in st.session_state: st.session_state.end_time_str = "11:59 PM"

# 1. Use vertical_alignment="bottom" to align items across the row
col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1], vertical_alignment="bottom")

with col1:
    start_val = st.text_input("Start Time", value="12:00", key="s_val")
with col2:
    start_period = st.selectbox("AM/PM", ["AM", "PM"], key="s_per")
with col3:
    end_val = st.text_input("End Time", value="11:59", key="e_val")
with col4:
    end_period = st.selectbox("AM/PM", ["PM", "AM"], key="e_per")

with col5:
    if st.button(" Calculate", use_container_width=True):
        def to_min(t_str, period):
            h, m = map(int, t_str.split(":"))
            h = 12 if h == 12 else h
            if period == "PM": h += 12
            return (h * 60) + m

        st.session_state.start_min = to_min(start_val, start_period)
        st.session_state.end_min = to_min(end_val, end_period)
        st.session_state.start_time_str = f"{start_val} {start_period}"
        st.session_state.end_time_str = f"{end_val} {end_period}"
        st.rerun()

# Ensure variables exist for the subheader
start_input = st.session_state.start_time_str
end_input = st.session_state.end_time_str

# These ensure the variables exist for the rest of your app logic
start_input = st.session_state.start_time_str
end_input = st.session_state.end_time_str

# --- CORE CALCULATION ---



# --- CORE CALCULATION ---
# 1. Calculate the week columns
selected_date_str = extract_day_month(shift_col)
current_date = datetime.strptime(f"{selected_date_str} 2026", "%d %b %Y")
sunday = current_date - timedelta(days=(current_date.weekday() + 1) % 7)

# Generate the 7 days of the week string list: "(DD MMM)"
week_days = [(sunday + timedelta(days=i)).strftime("(%d %b)") for i in range(7)]

# Define the columns to show (Meta + Week Days + Overtime)
# We check if Overtime columns exist in the original sheet
cols_to_show = ["Name", "Role", "CONTACT", "Branch"] + week_days
if "Overtime 1" in df_full.columns: cols_to_show.append("Overtime 1")
if "Overtime 2" in df_full.columns: cols_to_show.append("Overtime 2")

# Create a safe copy and ensure missing columns appear as empty strings
df_work = df_full.copy()
for col in cols_to_show:
    if col not in df_work.columns:
        df_work[col] = ""

# --- UI DISPLAY ---
# Use this for your Branchwise and Detailed tables:
# df_work[cols_to_show]
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
st.subheader("🔥 Active Staff"); st.dataframe(b_act[cols_to_show], use_container_width=True, hide_index=True)
st.subheader("📊 Full Branch Data"); # Replace your current dataframe call with this
st.dataframe(pd.concat([b_act, b_inact], ignore_index=True)[cols_to_show], use_container_width=True, hide_index=True)
