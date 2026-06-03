import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date

import pytz


saudi_tz = pytz.timezone("Asia/Riyadh")
now = datetime.now(saudi_tz)
now_min = now.hour * 60 + now.minute
st.sidebar.write(f"Server Time (Jeddah): {now.strftime('%H:%M')}")
st.sidebar.write(f"Minutes Calculation: {now_min}")
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

def clean(text):
    text = str(text).replace("–", "-").replace("—", "-")
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_shift(cell):
    if not cell or not isinstance(cell, str): 
        return None
    
    # AGGRESSIVE CLEANING:
    # 1. Convert to string and handle hidden bytes/non-breaking spaces
    cell = str(cell).replace('\xa0', ' ').replace('\u202f', ' ')
    # 2. Replace all forms of dashes with a standard hyphen
    cell = cell.replace("–", "-").replace("—", "-")
    # 3. Remove everything inside parentheses (OT, etc)
    cell = re.sub(r"\(.*?\)", "", cell)
    # 4. Strip whitespace
    cell = cell.strip()
    
    # Now look for the pattern
    pattern = r"(\d{1,2})\s*(AM|PM)"
    matches = re.findall(pattern, cell, re.I)
    
    if len(matches) < 2:
        return None

    def to_minutes(h, m):
        h, m = int(h), m.upper().strip()
        if m == "AM": return (0 if h == 12 else h) * 60
        return (12 if h == 12 else h + 12) * 60

    start_min = to_minutes(matches[0][0], matches[0][1])
    end_min = to_minutes(matches[1][0], matches[1][1])
    
    return start_min, end_min


def is_active_in_range(shift_val, start_min, end_min):
    shift = get_shift(shift_val)
    if not shift: return False
    
    s_start, s_end = shift
    
    # Logic: Does the shift intersect with the selected [start_min, end_min] range?
    # We check if there is any overlap between (s_start, s_end) and (start_min, end_min)
    if s_start < s_end:
        # Standard shift: e.g., 8am-5pm (480-1020)
        return not (s_end <= start_min or s_start >= end_min)
    else:
        # Overnight shift: e.g., 10pm-6am (1320-360)
        # It is active if it's NOT (ending before start_min AND starting after end_min)
        # This covers all overlaps for overnight shifts
        return not (s_end <= start_min and s_start >= end_min)

def is_active(cell, now_min):
    shift = get_shift(cell)
    if not shift:
        return False
    
    start, end = shift
    
    # Logic for normal shifts (e.g., 5 AM to 5 PM)
    if start < end:
        return start <= now_min < end
    # Logic for overnight shifts (e.g., 10 PM to 6 AM)
    else:
        return now_min >= start or now_min < end

def extract_day_month(col):
    match = re.search(r"\((\d{1,2}\s\w{3})\)", col)
    return match.group(1).strip() if match else None

def safe_df(df):
    return df.loc[:, ~df.columns.duplicated()].copy()


def compute_range(df, start_min, end_min):
    active, inactive = [], []
    cols = df.columns.tolist()
    
    for _, row in df.iterrows():
        shift_val = str(row["Shift"])
        if is_active_in_range(shift_val, start_min, end_min):
            active.append(row.to_dict())
        else:
            inactive.append(row.to_dict())
            
    return (pd.DataFrame(active, columns=cols) if active else pd.DataFrame(columns=cols),
            pd.DataFrame(inactive, columns=cols) if inactive else pd.DataFrame(columns=cols))
# 1. UPDATE THE FUNCTION DEFINITION
def compute(df, start_min, end_min):
    active, inactive = [], []
    cols = df.columns.tolist()
    
    for _, row in df.iterrows():
        shift_val = str(row["Shift"])
        
        # 2. USE THE NEW RANGE LOGIC INSIDE
        # We use the same is_active_in_range logic created previously
        if is_active_in_range(shift_val, start_min, end_min):
            active.append(row.to_dict())
        else:
            inactive.append(row.to_dict())
            
    # 3. RETURN DATA
    active_df = pd.DataFrame(active, columns=cols) if active else pd.DataFrame(columns=cols)
    inactive_df = pd.DataFrame(inactive, columns=cols) if inactive else pd.DataFrame(columns=cols)
    
    return active_df, inactive_df
    


# --- UI & LOGIC: TIME CONTROL ---
st.title("STAFF Schedule Control Center")

# --- INITIALIZATION ---
if "sim_min" not in st.session_state:
    st.session_state.sim_min = now_min

# --- UI: THE SELECTOR (NO RERUN ON CHANGE) ---


# --- DATA PROCESSING ---
df_full = load_data(st.session_state.data_refresh_token).copy()
df_full = safe_df(df_full)

meta_cols = ["Branch", "Name", "Role"]
shift_cols = [c.strip() for c in df_full.columns if c not in meta_cols]

today_day_month = date.today().strftime("%d %b")
default_index = len(shift_cols) - 1
for i, col in enumerate(shift_cols):
    if extract_day_month(col) == today_day_month:
        default_index = i
        break

st.markdown("### KINDLY SELECT THE DATE")
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
col1, col2, col3 = st.columns([2, 2, 1], vertical_alignment="bottom")

with col1:
    # 1. ADD A KEY here. This prevents the auto-rerun.
    range_start = st.time_input("From", value=datetime.now(saudi_tz).time(), key="start_time_key")
with col2:
    # 2. ADD A KEY here.
    range_end = st.time_input("To", value=datetime.now(saudi_tz).time(), key="end_time_key")
with col3:
    # 3. ONLY THIS BUTTON triggers the logic
    if st.button("🚀 Calculate Range", use_container_width=True):
        st.session_state.start_min = range_start.hour * 60 + range_start.minute
        st.session_state.end_min = range_end.hour * 60 + range_end.minute
        st.rerun() # This forces the ONE refresh you want

# Ensure these exist in session state
if "start_min" not in st.session_state:
    st.session_state.start_min = 0
    st.session_state.end_min = 1440

# Display status feedback
if st.session_state.sim_min != now_min:
    st.info(f" Viewing data for: **{st.session_state.sim_min // 60:02d}:{st.session_state.sim_min % 60:02d}** ")
else:
    st.info(f"Viewing Live Status: **{st.session_state.sim_min // 60:02d}:{st.session_state.sim_min % 60:02d}**")

# Set the active 'sim_min' for all calculations
sim_min = st.session_state.sim_min


# Create working dataframe copy
df_work = df_full.copy()
df_work["Shift"] = df_work[shift_col]
branches = sorted(df_work["Branch"].dropna().unique().tolist())

# Use the session state values set by your "Calculate" button
start_m = st.session_state.get("start_min", 0)
end_m = st.session_state.get("end_min", 1440)

# Use 'sim_min' for all calculations
u_act, u_inact = compute(df_work,start_m, end_m)

st.subheader("STAFF Universal Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("🏢 Branches", len(branches))
c2.metric("👥 Staff", len(df_work))
c3.metric("🟢 Active", len(u_act))
c4.metric("⚪ Inactive", len(u_inact))

st.divider()


# Force Test
test_val = "1 PM - 11 PM (OT 1h)"
st.sidebar.write(f"Hardcoded Test: {test_val}")
st.sidebar.write(f"Parsed Result: {get_shift(test_val)}")
st.sidebar.write(f"Is 15:49 (949 min) Active? {is_active(test_val, 949)}")
st.subheader("👥 Branchwise Status")
summary = []
for b in branches:
    temp = df_work[df_work["Branch"] == b]
    a, i = compute(temp, now_min)
    summary.append({"Branch": b, "Active": len(a), "Inactive": len(i)})
st.dataframe(pd.DataFrame(summary), use_container_width=True, hide_index=True)

st.divider()
col1, col2= st.columns(2)
with col1: selected_branch = st.selectbox("🏢 Branch", branches)

df_branch = df_work[df_work["Branch"] == selected_branch]
b_act, b_inact = compute(df_branch, now_min)

st.subheader("🏢 Branch Overview")
c1, c2, c3= st.columns(3)
c1.metric("Branch", selected_branch)

    

c2.metric("Active", len(b_act))
c3.metric("Inactive", len(b_inact))

st.subheader("🔥 Active Staff")
st.dataframe(b_act, use_container_width=True, hide_index=True)

st.subheader("📊 Full View")
full_view = pd.concat([b_act, b_inact], ignore_index=True)
st.dataframe(full_view, use_container_width=True, hide_index=True)
