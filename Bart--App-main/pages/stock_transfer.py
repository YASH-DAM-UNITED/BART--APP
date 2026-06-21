import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import random
import string
import re
from datetime import datetime, timedelta
import gspread.utils
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
# LOAD BRANCH MAP ON STARTUP
# ========================================================


# ========================================================
# ENSURE INITIALIZATION FUNCTION
# ========================================================

def ensure_branch_data():
    """Ensures branch data exists in session_state."""
    if "branch_map" not in st.session_state or "branch_list" not in st.session_state:
        with st.spinner("Initializing connection..."):
            try:
                client = get_gs_client()
                master_sh = client.open("MASTERBRANCHSHEET")
                branch_ws = master_sh.worksheet("Branches")
                data = branch_ws.get_all_values()[1:]
                
                st.session_state.branch_map = {row[0]: row[1] for row in data}
                st.session_state.branch_list = [f"{row[0]} - {row[2]}" for row in data]
            except Exception as e:
                st.error(f"Failed to initialize: {e}")
                st.session_state.branch_map = {}
                st.session_state.branch_list = []
                st.stop() # Stop execution if we can't get the data

# CALL THIS FIRST THING
ensure_branch_data()
# ========================================================
# LOAD BRANCH MAP ON STARTUP
# ========================================================

if "branch_map" not in st.session_state:
    with st.spinner("Initializing connection..."):
        try:
            client = get_gs_client()
            
            # Load the Branch Map from the Master Sheet
            master_sh = client.open("MASTERBRANCHSHEET")
            branch_ws = master_sh.worksheet("Branches")
            data = branch_ws.get_all_values()[1:]
            
            # Create a dictionary: {'B001': '1VF7g...', 'B002': '1cEku...', ...}
            st.session_state.branch_map = {row[0]: row[1] for row in data}
            
            # --- ADD THIS LINE TO INITIALIZE THE LIST ---
            # Assuming row[0] is ID and row[2] is Branch Name, adjust index as needed
            st.session_state.branch_list = [f"{row[0]} - {row[2]}" for row in data]
            
        except Exception as e:
            st.error(f"Failed to initialize: {e}")
            st.session_state.branch_map = {}
            st.session_state.branch_list = [] # Initialize empty list to prevent crash

# ========================================================
# PAGE CONFIG
# ========================================================

st.set_page_config(page_title="Stock Transfer", layout="centered")

# ========================================================
# DIALOG DEFINITION
# ========================================================

@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.switch_page("pages/staff_dashboard.py")

def prepare_batch_updates(ws, cart, mode="subtract"):
    """Batch update with error handling, matching yesterday's date column."""
    try:
        all_data = ws.get_all_values()
        if not all_data:
            return "Error: Sheet is empty"
        
        # Calculate yesterday's date string (Match this format to your sheet's header)
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        headers = all_data[0]
        
        if target_date not in headers:
            return f"Error: Column for {target_date} not found"
        
        col_index = headers.index(target_date)
        items_column = [row[0] for row in all_data]
        
        batch_list = []
        for entry in cart:
            if entry['item'] in items_column:
                row_idx = items_column.index(entry['item'])
                current_val = all_data[row_idx][col_index]
                current_num = int(float(current_val)) if current_val and str(current_val).strip() else 0
                
                if mode == "subtract":
                    new_val = current_num - int(entry['qty'])
                else:
                    new_val = current_num + int(entry['qty'])
                
                cell_address = gspread.utils.rowcol_to_a1(row_idx + 1, col_index + 1)
                batch_list.append({"range": cell_address, "values": [[new_val]]})
                
        if batch_list:
            ws.batch_update(batch_list)
            return "Success"
        return "Error: Items not found"
    except Exception as e:
        return f"Error: {str(e)}"
# ========================================================
# MAIN APP LOGIC
# ========================================================

st.title("🚚 Internal Stock Transfer")

if "transfer_cart" not in st.session_state:
    st.session_state.transfer_cart = []

if "current_stocks" not in st.session_state:
    st.error("No stock data found. Please return to the Dashboard.")
    ensure_branch_data()
    if st.button("⬅ Go Back to Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# ========================================================
# ADD ITEMS SECTION
# ========================================================

with st.expander("➕ Add Items to Transfer", expanded=True):
    category = st.radio("Select Item Category", ["Daily Items", "Weekly Items"], horizontal=True, key="cat_radio")
    target_list = st.session_state.current_stocks['daily'] if category == "Daily Items" else st.session_state.current_stocks['weekly']
    
    # ADDED: Check if list is empty
    if not target_list:
        st.warning(f"No items available in {category}.")
    else:
        item_names = [list(row.values())[0] for row in target_list]
        selected_item = st.selectbox("Select Item", item_names, key="item_sel")

        # Now only perform lookups if target_list actually had items
        selected_row = next(row for row in target_list if list(row.values())[0] == selected_item)
        uom_display = selected_row.get('DATE->  UOM', 'units') 
        
        col1, col2 = st.columns([3, 1])
        qty = col1.number_input("Quantity", min_value=1, step=1, key="qty_input")
        col2.markdown("<br>", unsafe_allow_html=True) 
        col2.write(f"**{uom_display}**")
        
        if st.button("Add to List", key="add_btn"):
            st.session_state.transfer_cart.append({"item": selected_item, "qty": qty, "uom": uom_display})
            st.success(f"Added {selected_item} to cart!")

# ========================================================
# CART AND DESTINATION SECTION
# ========================================================

if st.session_state.transfer_cart:
    st.subheader("📋 Current Transfer List")
    for i, entry in enumerate(st.session_state.transfer_cart):
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{entry['item']}**")
        col2.write(f"{entry['qty']} {entry['uom']}")
        if col3.button("Remove", key=f"del_{i}"):
            st.session_state.transfer_cart.pop(i)
            st.rerun()

    st.markdown("---")
    st.subheader("📦 Finalize Transfer")
    destination = st.selectbox("Select Destination Branch", st.session_state.branch_list, key="dest_sel")
    reason = st.text_area("Reason for Transfer", key="reason_input")
    
if st.button("Confirm and Send All", key="confirm_btn"):
    jeddah_time = datetime.now() + timedelta(hours=3)
    transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    origin_branch_raw = st.session_state.selected_branch
    
    origin_id = origin_branch_raw.split(" - ")[0]
    dest_id = str(destination).split(" - ")[0]

    try:
        # Get client with automatic round-robin rotation
        client = get_gs_client()
        
        origin_key = st.session_state.branch_map.get(origin_id)
        dest_key = st.session_state.branch_map.get(dest_id)
        
        if not origin_key or not dest_key:
            st.error("Branch ID not found in mapping table.")
        else:
            try:
                sh_origin = client.open_by_key(origin_key)
                sh_dest = client.open_by_key(dest_key)
            except Exception as e:
                st.error(f"Failed to open sheets: {e}")
                st.stop()
            
            ws_origin = sh_origin.worksheet("Stocks")
            
            # --- PRE-VALIDATION CHECK ---
# --- PRE-VALIDATION CHECK ---
            try:
                all_origin_data = ws_origin.get_all_values()
                origin_items = [row[0] for row in all_origin_data]
                
                # Calculate column index for yesterday's date
                # Ensure the format '%Y-%m-%d' matches exactly what is in your Sheet headers
                target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                headers = all_origin_data[0]
                
                if target_date not in headers:
                    st.error(f"❌ Could not find column for yesterday's date: {target_date} in the Origin sheet.")
                    st.stop()
                    
                col_index = headers.index(target_date)
                
                insufficient_items = []
                for entry in st.session_state.transfer_cart:
                    if entry['item'] in origin_items:
                        row_idx = origin_items.index(entry['item'])
                        current_stock = int(float(all_origin_data[row_idx][col_index] or 0))
                        if int(entry['qty']) > current_stock:
                            insufficient_items.append(f"• **{entry['item']}**: Available {current_stock}, Requested {entry['qty']}")

                if insufficient_items:
                    st.error("❌ **INSUFFICIENT STOCK**")
                    for error_msg in insufficient_items:
                        st.write(error_msg)
                    st.stop()
            except Exception as e:
                st.error(f"Error validating stock: {e}")
                st.stop()
            # ----------------------------
            
            # ----------------------------
            
            ws_dest = sh_dest.worksheet("Stocks")
            
            res_sub = prepare_batch_updates(ws_origin, st.session_state.transfer_cart, "subtract")
            res_add = prepare_batch_updates(ws_dest, st.session_state.transfer_cart, "add")
            
            if res_sub == "Success" and res_add == "Success":
                try:
                    transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                    transfer_sheet.append_row([
                        transfer_id, origin_branch_raw, str(destination), 
                        "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                        "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                        reason, "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                    ])
                    
                    st.session_state.transfer_cart = []
                    success_dialog(f"Transfer successful! ID: {transfer_id}")
                except Exception as e:
                    st.error(f"Transfer recorded but failed to log: {e}")
            else:
                st.error(f"Transfer Failed: Origin({res_sub}) | Destination({res_add})")
                
    except Exception as e:
        st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
