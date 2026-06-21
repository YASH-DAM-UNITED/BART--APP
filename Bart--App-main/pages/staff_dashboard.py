import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import gspread.utils
from datetime import datetime, timedelta
import gspread.utils
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from pathlib import Path
import pandas as pd
import time
import threading

# ========================================================
# DUAL GOOGLE CREDENTIALS POOL (WITH THREADING LOCK)
# ========================================================

client_lock = threading.Lock()

def get_gs_client():
    """
    Round-robin client pool manager with dual credential keys.
    Uses threading lock to prevent race conditions in multi-threaded environments.
    """
    if "client_pool" not in st.session_state:
        # Load your keys from secrets
        keys = ["GOOGLE_CREDS_JSON", "GOOGLE_CREDS_JSON1"]  # Add more as needed
        pool = []
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        for k in keys:
            if k in st.secrets:
                try:
                    creds = Credentials.from_service_account_info(dict(st.secrets[k]), scopes=scopes)
                    pool.append(gspread.authorize(creds))
                except Exception as e:
                    st.error(f"Failed to load credentials for {k}: {e}")
        
        if not pool:
            st.error("No Google credentials found in secrets!")
            return None
            
        st.session_state.client_pool = pool
        st.session_state.client_index = 0
    
    # Use the lock to prevent threads from grabbing the same index
    with client_lock:
        idx = st.session_state.client_index
        # Rotate index
        st.session_state.client_index = (idx + 1) % len(st.session_state.client_pool)
        client = st.session_state.client_pool[idx]
    
    return client

# ========================================================
# INITIALIZE GOOGLE CLIENT
# ========================================================

if "gs_client" not in st.session_state:
    st.session_state.gs_client = get_gs_client()

# ========================================================
# PAGE CONFIG
# ========================================================

st.set_page_config(layout="wide", page_title="BART Staff Dashboard")

SESSION_TIMEOUT = 30 * 60

# ========================================================
# CLEAN UI STYLE
# ========================================================

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

# ========================================================
# HEADER
# ========================================================

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

# ========================================================
# PASSWORD FILE
# ========================================================

FILE_NAME = Path(__file__).parent / "passwords.json"

def init_file():
    if not FILE_NAME.exists():
        with open(FILE_NAME, "w") as f:
            json.dump({"admin": "admin123"}, f)

def load_admin():
    with open(FILE_NAME, "r") as f:
        return json.load(f)

init_file()

# ========================================================
# SESSION STATE
# ========================================================

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


# Load the Branch Map so "Reject" logic knows where to send stock back
if "branch_map" not in st.session_state:
    try:
        client = get_gs_client()
        master_sh = client.open("MASTERBRANCHSHEET")
        branch_ws = master_sh.worksheet("Branches")
        data = branch_ws.get_all_values()[1:]
        st.session_state.branch_map = {row[0]: row[1] for row in data}
    except Exception as e:
        st.error(f"Error loading branch map: {e}")
        st.session_state.branch_map = {}


# ========================================================
# HELPER FUNCTIONS FOR NOTIFICATIONS
# ========================================================

@st.dialog("📦 New Transfer Received")
def show_transfer_dialog(transfer):
    st.write(f"### Transfer ID: `{transfer['ID']}`")
    st.info(f"**From:** {transfer['Origin']}")
    
    st.markdown("---")
    with st.container(border=True):
        st.write("**Items to be accepted:**")
        st.text(transfer['Items']) 
        st.write(f"**Quantities:**")
        st.text(transfer['Quantities'])
    
    st.write(f"**Reason:** {transfer['Reason']}")
    
    col1, col2 = st.columns(2)
    if col1.button("✅ Accept", use_container_width=True):
        update_transfer_status(transfer['ID'], "Accepted", transfer)
        st.rerun()
    if col2.button("❌ Reject", use_container_width=True):
        update_transfer_status(transfer['ID'], "Rejected", transfer)
        st.rerun()

def parse_transfer_items(transfer_data):
    # Ensure we get strings, even if the data is None or empty
    items_str = str(transfer_data.get('Items', ""))
    qtys_str = str(transfer_data.get('Quantities', ""))
    
    # If there is no data, return an empty list immediately
    if not items_str.strip() or not qtys_str.strip():
        return []
    
    # Clean and split
    items = [i.replace("• ", "").strip() for i in items_str.split("\n") if i.strip()]
    qtys = [q.strip() for q in qtys_str.split("\n") if q.strip()]
    
    cart = []
    # Loop through the shorter list to avoid index errors
    for i in range(min(len(items), len(qtys))):
        # Extract item name if it has extra detail like "(Qty UOM)"
        item_name = items[i].split(" (")[0].strip()
        cart.append({"item": item_name, "qty": qtys[i]})
        
    return cart


def update_transfer_status(transfer_id, status, transfer_data):
    """Update transfer status with dual credential support"""
    client = get_gs_client()
    try:
        sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
        cell = sheet.find(transfer_id)
        if cell:
            sheet.update_cell(cell.row, 7, status)
    except Exception as e:
        st.error(f"Error updating transfer status: {e}")
        return
    
    # 2. If Rejected, perform the "Reverse" Operation on BOTH branches
    if status == "Rejected":
        origin_branch_raw = transfer_data['Origin']
        dest_branch_raw = transfer_data['Destination']
        
        origin_id = origin_branch_raw.split(" - ")[0]
        dest_id = dest_branch_raw.split(" - ")[0]
        
        origin_key = st.session_state.branch_map.get(origin_id)
        dest_key = st.session_state.branch_map.get(dest_id)
        
        cart = parse_transfer_items(transfer_data)
        
        if origin_key and dest_key:
            try:
                # Open both sheets with rotating credentials
                origin_sh = client.open_by_key(origin_key)
                dest_sh = client.open_by_key(dest_key)
                
                # Add back to Origin
                ws_origin = origin_sh.worksheet("Stocks")
                prepare_batch_updates(ws_origin, cart, "add")
                
                # Subtract from Destination
                ws_dest = dest_sh.worksheet("Stocks")
                prepare_batch_updates(ws_dest, cart, "subtract")
                
                st.success(f"Rejected: Stock returned to {origin_branch_raw} and removed from {dest_branch_raw}")
            except Exception as e:
                st.error(f"Error processing reversal: {e}")
        else:
            st.error("Could not find branch map IDs to complete the reversal.")

from datetime import datetime, timedelta
import gspread.utils

def prepare_batch_updates(ws, cart, mode="subtract"):
    """Batch update targeting the column matching yesterday's date."""
    try:
        # 1. Calculate yesterday's date in the format used in your headers
        # Adjust the format string '%Y-%m-%d' to match your actual header format
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        all_data = ws.get_all_values()
        if not all_data: 
            return "Error: Sheet is empty"
        
        # 2. Find the column index for the date
        headers = all_data[0]
        try:
            # Assumes column headers start from index 1 (0-based)
            col_index = headers.index(yesterday) + 1 
        except ValueError:
            return f"Error: Could not find column header for date {yesterday}"
        
        items_column = [row[0] for row in all_data]
        
        batch_list = []
        for entry in cart:
            if entry['item'] in items_column:
                row_idx = items_column.index(entry['item'])
                current_val = all_data[row_idx][col_index - 1]
                current_num = int(float(current_val)) if current_val and str(current_val).strip() else 0
                
                if mode == "subtract":
                    new_val = current_num - int(entry['qty'])
                else:
                    new_val = current_num + int(entry['qty'])
                    
                cell_address = gspread.utils.rowcol_to_a1(row_idx + 1, col_index)
                batch_list.append({"range": cell_address, "values": [[new_val]]})
                
        if batch_list:
            ws.batch_update(batch_list)
            return "Success"
        return "Error: Items not found"
    except Exception as e:
        st.error(f"Error in batch update: {e}")
        return f"Error: {str(e)}"

def check_for_pending_transfers():
    """Check pending transfers with error handling"""
    try:
        client = get_gs_client()
        sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
        records = sheet.get_all_records()
        my_branch = st.session_state.selected_branch
        
        # Filter for pending transfers where current branch is the destination
        pending = [r for r in records if r['Destination'] == my_branch and r['Status'] == 'Pending']
        
        for transfer in pending:
            show_transfer_dialog(transfer)
    except Exception as e:
        st.error(f"Error checking transfers: {e}")

# ========================================================
# ACTIVITY MANAGEMENT
# ========================================================

def refresh_activity():
    st.session_state.last_activity = time.time()

# ========================================================
# TIMEOUT CHECK
# ========================================================

def check_timeout():
    if st.session_state.authenticated and st.session_state.last_activity:
        if time.time() - st.session_state.last_activity > SESSION_TIMEOUT:
            st.session_state.authenticated = False
            st.session_state.auth_branch = None
            st.session_state.last_activity = None
            st.warning("⏱️ Logged out due to inactivity.")

check_timeout()

# ========================================================
# LOAD BRANCHES & PASSWORDS (CONSOLIDATED & CACHED)
# ========================================================

@st.cache_data(ttl=300)
def load_master_branch_data():
    """Load branch data with dual credential pool support"""
    client = get_gs_client()
    try:
        sheet = client.open("MASTERBRANCHSHEET").sheet1
        records = sheet.get_all_records()
        
        # Pre-map a password dictionary
        passwords = {"admin": load_admin()["admin"]}
        for row in records:
            key = f"{row['BranchCode']} - {row['BranchName']}"
            passwords[key] = row.get("Password", "")
            
        return records, passwords
    except Exception as e:
        st.error(f"Error loading branch data: {e}")
        return [], {"admin": load_admin()["admin"]}

# Fetch data securely and instantly from memory
branch_data, passwords = load_master_branch_data()
branches = [f"{b['BranchCode']} - {b['BranchName']}" for b in branch_data]
branch_options = ["-- Select Branch --"] + branches

def save_passwords(branch_key, new_password):
    """Save password with dual credential support"""
    client = get_gs_client()
    try:
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
    except Exception as e:
        st.error(f"Error saving password: {e}")

# ========================================================
# PIN FIRST 3 COLUMNS
# ========================================================

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

# ========================================================
# BRANCH SELECT
# ========================================================

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

    col1, col2 = st.columns(2)

    if col1.button("🔄 Logout "):
        st.session_state.selected_branch = "-- Select Branch --"
        st.session_state.authenticated = False
        st.session_state.auth_branch = None
        st.session_state.last_activity = None
        st.rerun()
    if col2.button("🔄 Refresh "):
        st.rerun()

# ========================================================
# BRANCH INFO
# ========================================================

branch_info = None

if st.session_state.selected_branch != "-- Select Branch --":
    branch_info = next(
        (b for b in branch_data
        if f"{b['BranchCode']} - {b['BranchName']}" == st.session_state.selected_branch),
        None
    )

# ========================================================
# MAIN
# ========================================================

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
                        if branch_info:
                            st.session_state.sheet_id = branch_info["SheetID"]
                            st.session_state.tab_name = "Stocks"
                            st.session_state.branch_info = branch_info
                        st.rerun()
                    else:
                        st.error("Incorrect password")
        with col2:
            if st.button("Reset Password"):
                st.session_state.reset_mode = True

    # ========================================================
    # RESET PASSWORD
    # ========================================================

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

# ========================================================
# AFTER LOGIN
# ========================================================

if st.session_state.authenticated:
    st.success(f"Logged in: {st.session_state.selected_branch}")
    check_for_pending_transfers()
    
    col1, col2, col3, col4 = st.columns(4)

    if col1.button("📦 Stock Record"):
        refresh_activity()
        st.switch_page("pages/stock_consumption.py")

    if col2.button("📅 Staff Schedule"):
        refresh_activity()
        st.switch_page("pages/staff_schedule.py")

    if col4.button("📦 Stock Transfer Internal "):
        st.switch_page("pages/stock_transfer.py")

    if col3.button("🔍 Stock View"):
        st.session_state.show_stock_view = not st.session_state.get("show_stock_view", False)
        refresh_activity()
        

# ========================================================
# STOCK VIEW SECTION (CACHED FOR INSTANT PERFORMANCE)
# ========================================================

@st.cache_data(ttl=6000) # Caches data for 10 minutes
def fetch_stock_data(sheet_id):
    """Fetch and parse data once, then store in memory."""
    client = get_gs_client()
    sheet = client.open_by_key(sheet_id)
    ws = sheet.worksheet("Stocks")
    data = ws.get_all_values()
    
    headers = data[0]
    date_columns = headers[1:]
    daily, weekly = [], []
    current_section = None

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
            if i < 2:
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
            
    return {"daily": daily, "weekly": weekly}

@st.fragment
def render_stock_view(branch_info):
    """Display cached data instantly."""
    try:
        stocks = fetch_stock_data(branch_info["SheetID"])
        
        st.subheader("📦 Daily Items Stock")
        st.dataframe(pd.DataFrame(stocks["daily"]), use_container_width=True, height=400)
        
        st.subheader("📦 Weekly Items Stock")
        st.dataframe(pd.DataFrame(stocks["weekly"]), use_container_width=True, height=400)
        
        st.session_state.current_stocks = stocks
    except Exception as e:
        st.error(f"Error loading stock data: {e}")

# Trigger the fragment if the toggle is True
if st.session_state.get("show_stock_view", False):
    if branch_info is not None:
        render_stock_view(branch_info)
    else:
        st.session_state.show_stock_view = False

# ========================================================
# BACK
# ========================================================

if st.button("⬅ Back"):
    st.switch_page("app.py")
