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
def compute(df, now_min):
    active, inactive = [], []
    
    for _, row in df.iterrows():
        # 1. Convert to string and handle possible NaNs/None
        shift_val = str(row["Shift"]) if pd.notnull(row["Shift"]) else ""
        
        # 2. Check activity
        if is_active(shift_val, now_min):
            active.append(row.to_dict())
        else:
            inactive.append(row.to_dict())
            
    cols = df.columns.tolist()
    
    # 3. Handle empty lists to avoid DataFrame errors
    active_df = pd.DataFrame(active, columns=cols) if active else pd.DataFrame(columns=cols)
    inactive_df = pd.DataFrame(inactive, columns=cols) if inactive else pd.DataFrame(columns=cols)
    
    return active_df, inactive_df

# --- UI & LOGIC ---
st.title("STAFF Schedule Control Center")

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

# Create working dataframe copy
df_work = df_full.copy()
df_work["Shift"] = df_work[shift_col]
now_min = datetime.now().hour * 60 + datetime.now().minute
branches = sorted(df_work["Branch"].dropna().unique().tolist())

u_act, u_inact = compute(df_work, now_min)



# --- DEBUG SECTION ---
with st.expander("🔍 Click to Debug Data"):
    st.write("Current Time (Minutes from Midnight):", now_min)
    st.write("First 5 rows of dataframe:")
    st.dataframe(df_work.head())
    if not df_work.empty:
        sample_shift = df_work["Shift"].iloc[0]
        st.write(f"Sample Shift String: '{sample_shift}'")
        st.write("Parsed Shift Result:", get_shift(sample_shift))
# ---------------------

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
col1, col2 = st.columns(2)
with col1: selected_branch = st.selectbox("🏢 Branch", branches)
with col2: selected_date = st.date_input("📅 Date", value=date.today())

df_branch = df_work[df_work["Branch"] == selected_branch]
b_act, b_inact = compute(df_branch, now_min)

st.subheader("🏢 Branch Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Branch", selected_branch)
c2.metric("Date", selected_date.strftime("%d-%m-%Y"))
c3.metric("Active", len(b_act))
c4.metric("Inactive", len(b_inact))

st.subheader("🔥 Active Staff")
st.dataframe(b_act, use_container_width=True, hide_index=True)

st.subheader("📊 Full View")
full_view = pd.concat([b_act, b_inact], ignore_index=True)
st.dataframe(full_view, use_container_width=True, hide_index=True)
