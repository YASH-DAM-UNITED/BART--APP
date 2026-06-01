import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials


import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from pathlib import Path
import pandas as pd
import time

# ---------------- PAGE CONFIG ----------------
st.set_page_config(layout="wide", page_title="BART Staff Dashboard")

SESSION_TIMEOUT = 30 * 60

# ---------------- CLEAN UI STYLE ----------------
st.markdown("""
<style>
#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}
[data-testid="stToolbar"] {display:none;}
[data-testid="stSidebar"] {display:none;}

.block-container {
    padding: 1rem 2rem;
    max-width: 1200px;
    margin: auto;
}

.stApp {
    background: linear-gradient(135deg,#eef2f7,#d6e4ff);
}

h1, h2, h3 {
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

# ---------------- HEADER ----------------
st.markdown("""
<div style="
    background: linear-gradient(90deg, #1f1f2e, #4b6cb7);
    padding: 20px;
    border-radius: 12px;
    text-align: center;
    margin-bottom: 20px;
">
<h1 style='color:white; margin:0;'>BART Staff Dashboard</h1>
<p style='color:#e0e0e0; margin:0;'>Select Branch & Access Operations</p>
</div>
""", unsafe_allow_html=True)

# ---------------- PASSWORD FILE ----------------
FILE_NAME = Path(__file__).parent / "passwords.json"

def init_file():
    if not FILE_NAME.exists():
        with open(FILE_NAME, "w") as f:
            json.dump({"admin": "admin123"}, f)

def load_admin():
    with open(FILE_NAME, "r") as f:
        return json.load(f)

init_file()

# ---------------- SESSION STATE ----------------
defaults = {
    "authenticated": False,
    "auth_branch": None,
    "reset_mode": False,
    "selected_branch": "-- Select Branch --",
    "last_activity": None
}

for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------- ACTIVITY ----------------
def refresh_activity():
    st.session_state.last_activity = time.time()

# ---------------- TIMEOUT ----------------
def check_timeout():
    if st.session_state.authenticated and st.session_state.last_activity:
        if time.time() - st.session_state.last_activity > SESSION_TIMEOUT:
            st.session_state.authenticated = False
            st.session_state.auth_branch = None
            st.session_state.last_activity = None
            st.warning("⏱️ Logged out due to inactivity.")

check_timeout()

# ---------------- SELF-HEALING GOOGLE CONNECTION ----------------
def get_fresh_client():
    creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    # Always create a fresh credential object to avoid stale token issues
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

# Ensure client exists and is fresh
if "gs_client" not in st.session_state:
    st.session_state.gs_client = get_fresh_client()
# ---------------- LOAD BRANCHES & PASSWORDS (CONSOLIDATED & CACHED) ----------------
@st.cache_data(ttl=300000)  # Use a numeric TTL (seconds) instead of None
def load_master_branch_data():
    # Access the client from session state instead of a global 'client' variable
    client = st.session_state.gs_client 
    sheet = client.open("MASTERBRANCHSHEET").sheet1
    records = sheet.get_all_records()
    
    # Pre-map a password dictionary
    passwords = {"admin": load_admin()["admin"]}
    for row in records:
        key = f"{row['BranchCode']} - {row['BranchName']}"
        passwords[key] = row.get("Password", "")
        
    return records, passwords
# Fetch data securely and instantly from memory
branch_data, passwords = load_master_branch_data()
branches = [f"{b['BranchCode']} - {b['BranchName']}" for b in branch_data]

# ONLY set this if it isn't already there to avoid unnecessary processing
if "branch_list" not in st.session_state:
    st.session_state.branch_list = branches

# Fetch data securely and instantly from memory
branch_data, passwords = load_master_branch_data()
branches = [f"{b['BranchCode']} - {b['BranchName']}" for b in branch_data]
branch_options = ["-- Select Branch --"] + branches

def save_passwords(branch_key, new_password):
    sheet = client.open("MASTERBRANCHSHEET").sheet1
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):
        key = f"{row['BranchCode']} - {row['BranchName']}"
        if key == branch_key:
            col_index = list(row.keys()).index("Password") + 1
            sheet.update_cell(idx, col_index, new_password)
            # Clear cache so the new password takes effect immediately
            load_master_branch_data.clear()
            return

# ---------------- PIN FIRST 3 COLUMNS ----------------
st.markdown("""
<style>
div[data-testid="stDataFrame"] thead th:nth-child(1),
div[data-testid="stDataFrame"] tbody td:nth-child(1) {
    position: sticky;
    left: 0;
    background: white;
    z-index: 3;
}

div[data-testid="stDataFrame"] thead th:nth-child(2),
div[data-testid="stDataFrame"] tbody td:nth-child(2) {
    position: sticky;
    left: 150px;
    background: white;
    z-index: 2;
}

div[data-testid="stDataFrame"] thead th:nth-child(3),
div[data-testid="stDataFrame"] tbody td:nth-child(3) {
    position: sticky;
    left: 300px;
    background: white;
    z-index: 2;
}
</style>
""", unsafe_allow_html=True)

# ---------------- BRANCH SELECT ----------------
st.subheader("Select Branch")

if st.session_state.selected_branch == "-- Select Branch --":
    st.session_state.authenticated = False
    st.session_state.auth_branch = None
    st.session_state.last_activity = None

    with st.popover("Choose Branch"):
        selected_branch = st.radio("Branch List", branch_options, index=0)

        if selected_branch != "-- Select Branch --":
            st.session_state.selected_branch = selected_branch
            st.rerun()

else:
    st.success(f"Selected Branch: {st.session_state.selected_branch}")

    if st.button("🔄 REFRESH OR CHANGE BRANCH"):
        st.session_state.selected_branch = "-- Select Branch --"
        st.session_state.authenticated = False
        st.session_state.auth_branch = None
        st.session_state.last_activity = None
        st.rerun()

# ---------------- BRANCH INFO ----------------
branch_info = None

if st.session_state.selected_branch != "-- Select Branch --":
    branch_info = next(
        b for b in branch_data
        if f"{b['BranchCode']} - {b['BranchName']}" == st.session_state.selected_branch
    )

# ---------------- MAIN ----------------
if st.session_state.selected_branch != "-- Select Branch --":

    if not st.session_state.authenticated:
        st.subheader("Branch Login")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Login"):
                with st.spinner("Verifying credentials..."):
                    if passwords.get(st.session_state.selected_branch, "") == password:
                        st.session_state.authenticated = True
                        st.session_state.auth_branch = st.session_state.selected_branch
                        st.session_state.last_activity = time.time()
                        st.session_state.sheet_id = branch_info["SheetID"]
                        st.session_state.tab_name = "Stocks"
                        st.session_state.branch_info = branch_info
                        st.rerun()
                    else:
                        st.error("Incorrect password")
        with col2:
            if st.button("Reset Password"):
                st.session_state.reset_mode = True

    # ---------------- RESET PASSWORD ----------------
    if st.session_state.reset_mode:
        st.subheader("Reset Password")
        admin_pass = st.text_input("Admin Password", type="password")
        new_pass = st.text_input("New Password", type="password")
        if st.button("Update Password"):
            if admin_pass == load_admin()["admin"]:
                save_passwords(st.session_state.selected_branch, new_pass)
                st.success("Password updated successfully")
                st.session_state.reset_mode = False
            else:
                st.error("Wrong admin password")

# ---------------- AFTER LOGIN ----------------
if st.session_state.authenticated:
    st.success(f"Logged in: {st.session_state.selected_branch}")
    col1, col2, col3 = st.columns(3)

    if col1.button("📦 Stock Record"):
        refresh_activity()
        st.switch_page("pages/stock_consumption.py")

    if col2.button("📅 Staff Schedule"):
        refresh_activity()
        st.switch_page("pages/staff_schedule.py")

# ---------------- STOCK VIEW SECTION ----------------
# 1. Button to Toggle State
if col3.button("🔍 Toggle Stock View"):
    st.session_state.show_stock_view = not st.session_state.get("show_stock_view", False)
    refresh_activity()
    st.rerun()

# 2. Only execute fetch and display logic if True
if st.session_state.get("show_stock_view", False):
    with st.spinner("Fetching live stock data..."):
        # Fetching only happens when the user clicks the button
        sheet = st.session_state.gs_client.open_by_key(branch_info["SheetID"])
        ws = sheet.worksheet("Stocks")
        data = ws.get_all_values()
        
        headers = data[0]
        date_columns = headers[1:]
        daily, weekly = [], []
        current_section = None

        # Data Parsing Logic
        for row in data:
            row_text = " ".join(row).strip().lower()
            if "daily item" in row_text:
                current_section = "daily"
                continue
            if "weekly item" in row_text:
                current_section = "weekly"
                continue
            if current_section is None or not row or not row[0]:
                continue
            
            item = row[0].strip()
            row_values = row[1:]
            padding_needed = len(date_columns) - len(row_values)
            values = row_values + ([""] * max(0, padding_needed))
            
            cleaned, total = [], 0
            for i, v in enumerate(values):
                if i < 3:
                    cleaned.append(v)
                    continue
                try:
                    num = float(v) if v != "" else 0
                except:
                    num = 0
                cleaned.append(num)
                total += num
            
            row_dict = {"Item": item}
            for i, col in enumerate(date_columns):
                row_dict[col] = cleaned[i]
            row_dict["Total"] = total
            
            if current_section == "daily":
                daily.append(row_dict)
            else:
                weekly.append(row_dict)

        # UI Display
        st.markdown("---")
        b_col1, b_col2 = st.columns(2)
        if b_col1.button("🚀 Internal Transfer"):
            st.switch_page("pages/stock_transfer.py")
        if b_col2.button("🔔 Notifications"):
            st.switch_page("pages/notifications.py")

        st.subheader("📦 Daily Items Stock")
        st.dataframe(pd.DataFrame(daily), use_container_width=True, height=400)
        st.subheader("📦 Weekly Items Stock")
        st.dataframe(pd.DataFrame(weekly), use_container_width=True, height=400)
        
        # Save to session state for other pages if needed
        st.session_state.current_stocks = {"daily": daily, "weekly": weekly}

# --- 1. Notification Check (Run on load) ---
def check_notifications():
    # Only hit the API for the notifications tab
    sheet = client.open("MASTERBRANCHSHEET").worksheet("Notifications")
    records = sheet.get_all_records()
    
    my_code = st.session_state.selected_branch.split(" - ")[0]
    
    # Filter for unread
    unread = [r for r in records if r['TargetBranchCode'] == my_code and r['Status'] == 'unread']
    
    for note in unread:
        st.toast(f"📦 Incoming Transfer: {note['Message']}", icon="🔔")
        # Update sheet to 'read' to prevent loop
        # (Add logic here to find row index and update status to 'read')



# ---------------- BACK ----------------
if st.button("⬅ Back"):
    st.switch_page("app.py")
