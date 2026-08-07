import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import random
import string
import re
from datetime import datetime, timedelta
import gspread.utils
import threading
import pandas as pd

# ========================================================
# DUAL GOOGLE CREDENTIALS POOL (WITH THREADING LOCK)
# ========================================================

client_lock = threading.Lock()

def disable_button():
    st.session_state.is_submitting = True

def get_gs_client():
    """
    Round-robin client pool manager with dual credential keys.
    Uses threading lock to prevent race conditions in multi-threaded environments.
    """
    if "client_pool" not in st.session_state:
        keys = ["GOOGLE_CREDS_JSON", "GOOGLE_CREDS_JSON1"]  
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
            st.stop()
            return None
            
        st.session_state.client_pool = pool
        st.session_state.client_index = 0
    
    with client_lock:
        idx = st.session_state.client_index
        st.session_state.client_index = (idx + 1) % len(st.session_state.client_pool)
        client = st.session_state.client_pool[idx]
    
    return client

# ========================================================
# LOAD BRANCH MAP ON STARTUP
# ========================================================

def load_data():
    client = get_gs_client()
    master_sh = client.open("MASTERBRANCHSHEET")
    
    branch_ws = master_sh.worksheet("Branches")
    branch_data = branch_ws.get_all_values()[1:]

    branch_map = {}
    branch_list = []
    for row in branch_data:
        if len(row) >= 3:
            branch_map[row[0]] = row[1]
            branch_list.append(f"{row[0]} - {row[2]}")

    st.session_state.branch_map = branch_map
    st.session_state.branch_list = branch_list
    
    transfer_ws = master_sh.worksheet("Transfers")
    st.session_state.all_transfers = transfer_ws.get_all_records()

def render_history_view():
    st.subheader("📜 Transfer History")
    if "all_transfers" not in st.session_state:
        try:
            load_data()
        except Exception:
            st.error("Failed to load transfer history.")
            return
    
    my_branch = st.session_state.get('selected_branch', '')
    
    filtered = [t for t in st.session_state.all_transfers 
                if t.get('Origin') == my_branch or t.get('Destination') == my_branch]
    
    filtered.sort(key=lambda x: x.get('Timestamp', ''), reverse=True)
    
    if not filtered:
        st.info("No records found.")
    else:
        limit = st.session_state.get('history_limit', 3)
        df = pd.DataFrame(filtered[:limit])
        
        desired_cols = ['ID', 'Origin', 'Destination', 'Items', 'Status', 'Timestamp']
        available_cols = [c for c in desired_cols if c in df.columns]
        display_df = df[available_cols] if available_cols else df
        
        st.dataframe(
            display_df, 
            use_container_width=True, 
            hide_index=True
        )
            
    if len(filtered) > st.session_state.get('history_limit', 3):
        if st.button("Load More"):
            st.session_state.history_limit = st.session_state.get('history_limit', 3) + 3
            st.rerun()
            
    if st.button("⬅ Close Transfer History"):
        st.session_state.history_limit = 3 
        st.session_state.show_history = False
        st.rerun()

def render_transfer_form():
    if st.button("📜 View Transfer History"):
        st.session_state.show_history = True
        st.rerun()

# ========================================================
# ENSURE INITIALIZATION FUNCTION
# ========================================================

def ensure_branch_data():
    if "branch_map" not in st.session_state or "branch_list" not in st.session_state:
        with st.spinner("Initializing connection..."):
            try:
                client = get_gs_client()
                master_sh = client.open("MASTERBRANCHSHEET")
                branch_ws = master_sh.worksheet("Branches")
                data = branch_ws.get_all_values()[1:]
                
                branch_map = {}
                branch_list = []
                for row in data:
                    if len(row) >= 3:
                        branch_map[row[0]] = row[1]
                        branch_list.append(f"{row[0]} - {row[2]}")

                st.session_state.branch_map = branch_map
                st.session_state.branch_list = branch_list
            except Exception as e:
                st.error(f"Failed to initialize: {e}")
                st.session_state.branch_map = {}
                st.session_state.branch_list = []
                st.stop()

ensure_branch_data()

# ========================================================
# PAGE CONFIG
# ========================================================

st.set_page_config(page_title="Stock Transfer", layout="centered")

if "is_submitting" not in st.session_state:
    st.session_state.is_submitting = False

if "show_history" not in st.session_state:
    st.session_state.show_history = False

if "history_limit" not in st.session_state:
    st.session_state.history_limit = 3

if "transfer_cart" not in st.session_state:
    st.session_state.transfer_cart = []

# ========================================================
# DIALOG DEFINITION
# ========================================================

@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.switch_page("pages/staff_dashboard.py")

def prepare_batch_updates(ws, cart, mode="subtract"):
    try:
        all_data = ws.get_all_values()
        if not all_data or len(all_data) < 2:
            return "Error: Sheet is empty or has no data rows"
        
        target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        headers = all_data[0]
        data_rows = all_data[1:]
        
        if target_date not in headers:
            return f"Error: Column for {target_date} not found"
        
        col_index = headers.index(target_date)
        items_column = [row[0] for row in data_rows if len(row) > 0]
        
        batch_list = []
        for entry in cart:
            if entry['item'] in items_column:
                data_idx = items_column.index(entry['item'])
                row_idx = data_idx  
                current_val = ""
                if col_index < len(data_rows[row_idx]):
                    current_val = data_rows[row_idx][col_index]
                try:
                    if isinstance(current_val, str):
                        sanitized = current_val.replace(',', '').strip()
                        current_num = int(float(sanitized)) if sanitized else 0
                    elif current_val is None:
                        current_num = 0
                    else:
                        current_num = int(float(current_val))
                except Exception:
                    current_num = 0
                
                if mode == "subtract":
                    new_val = current_num - int(entry['qty'])
                else:
                    new_val = current_num + int(entry['qty'])
                
                sheet_row = row_idx + 2
                cell_address = gspread.utils.rowcol_to_a1(sheet_row, col_index + 1)
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

if st.session_state.get('show_history', False):
    render_history_view()
else:
    render_transfer_form()

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
    target_list = st.session_state.current_stocks.get('daily', []) if category == "Daily Items" else st.session_state.current_stocks.get('weekly', [])
    
    if not target_list:
        st.warning(f"No items available in {category}.")
    else:
        item_names = [list(row.values())[0] for row in target_list if row]
        if not item_names:
            st.warning("No valid item names found.")
        else:
            selected_item = st.selectbox("Select Item", item_names, key="item_sel")

            selected_row = next((row for row in target_list if list(row.values())[0] == selected_item), None)
            uom_display = selected_row.get('DATE->  UOM', 'units') if selected_row else 'units'
            
            # Extract SKU dynamically from selected row dictionary
            sku_val = ""
            if selected_row:
                keys_list = list(selected_row.keys())
                values_list = list(selected_row.values())
                for i, k in enumerate(keys_list):
                    if 'sku' in k.lower() or 'code' in k.lower():
                        sku_val = values_list[i]
                        break
                if not sku_val and len(values_list) > 1:
                    sku_val = values_list[1] # Fallback to second column

            col1, col2 = st.columns([3, 1])
            qty = col1.number_input("Quantity", min_value=1, step=1, key="qty_input")
            col2.markdown("<br>", unsafe_allow_html=True) 
            col2.write(f"**{uom_display}**")
            
            if st.button("Add to List", key="add_btn"):
                st.session_state.transfer_cart.append({
                    "item": selected_item, 
                    "sku": str(sku_val), 
                    "qty": qty, 
                    "uom": uom_display
                })
                st.success(f"Added {selected_item} to cart!")

# ========================================================
# CART AND DESTINATION SECTION
# ========================================================

if st.session_state.transfer_cart:
    st.subheader("📋 Current Transfer List")
    for i, entry in enumerate(list(st.session_state.transfer_cart)):
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{entry['item']}** `[{entry.get('sku', 'N/A')}]`")
        col2.write(f"{entry['qty']} {entry['uom']}")
        if col3.button("Remove", key=f"del_{i}"):
            st.session_state.transfer_cart.pop(i)
            st.rerun()

    st.markdown("---")
    st.subheader("📦 Finalize Transfer")
    
    if st.session_state.get('branch_list'):
        destination = st.selectbox(
            "Select Destination Branch", 
            options=st.session_state.branch_list, 
            index=None, 
            placeholder="Choose a branch...",
            key="dest_sel"
        )
    else:
        destination = None
        st.warning("No destination branches available. Contact admin.")
    
    reason = st.text_area("Reason for Transfer", key="reason_input")

    if destination:
        # Uses on_click callback to instantly disable the button and prevent double clicks
        confirm_clicked = st.button(
            "Confirm and Send All", 
            key="confirm_btn", 
            on_click=disable_button, 
            disabled=st.session_state.get('is_submitting', False)
        )
        
        if confirm_clicked:
            try:
                jeddah_time = datetime.now() + timedelta(hours=3)
                transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
                origin_branch_raw = st.session_state.get('selected_branch')
                
                if not origin_branch_raw:
                    st.error("Origin branch not set. Please return to Dashboard and select a branch.")
                    st.stop()
                
                origin_id = origin_branch_raw.split(" - ")[0]
                dest_id = str(destination).split(" - ")[0]

                client = get_gs_client()
                origin_key = st.session_state.branch_map.get(origin_id)
                dest_key = st.session_state.branch_map.get(dest_id)
                
                if not origin_key or not dest_key:
                    st.error("Branch ID not found in mapping table.")
                    st.stop()
                
                sh_origin = client.open_by_key(origin_key)
                sh_dest = client.open_by_key(dest_key)
                ws_origin = sh_origin.worksheet("Stocks")
                
                # --- PRE-VALIDATION CHECK ---
                all_origin_data = ws_origin.get_all_values()
                if not all_origin_data or len(all_origin_data) < 2:
                    st.error("Origin stocks sheet is empty or malformed.")
                    st.stop()

                data_rows = all_origin_data[1:]
                origin_items = [row[0] for row in data_rows if len(row) > 0]
                target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                headers = all_origin_data[0]
                
                if target_date not in headers:
                    st.error(f"❌ Could not find column for yesterday's date: {target_date}")
                    st.stop()
                    
                col_index = headers.index(target_date)
                insufficient_items = []
                for entry in st.session_state.transfer_cart:
                    if entry['item'] in origin_items:
                        row_idx = origin_items.index(entry['item'])
                        current_val = ""
                        if col_index < len(data_rows[row_idx]):
                            current_val = data_rows[row_idx][col_index]
                        try:
                            cur = int(float(str(current_val).replace(',', '').strip() or 0))
                        except Exception:
                            cur = 0

                        if cur < int(entry['qty']):
                            insufficient_items.append({"item": entry['item'], "have": cur, "need": entry['qty']})
                    else:
                        insufficient_items.append({"item": entry['item'], "have": 0, "need": entry['qty']})

                if insufficient_items:
                    st.error("Insufficient stock for some items:\n" + "\n".join([f"{it['item']}: have {it['have']} need {it['need']}" for it in insufficient_items]))
                    st.stop()
                
                # --- EXECUTE TRANSFER ---
                ws_dest = sh_dest.worksheet("Stocks")
                res_sub = prepare_batch_updates(ws_origin, st.session_state.transfer_cart, "subtract")
                res_add = prepare_batch_updates(ws_dest, st.session_state.transfer_cart, "add")
                
                if res_sub == "Success" and res_add == "Success":
                    transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                    
                    # Appending rows including SKU codes cleanly formatted
                    transfer_sheet.append_row([
                        transfer_id, 
                        origin_branch_raw, 
                        str(destination), 
                        "\n".join([f"• [{e.get('sku', '')}] {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                        "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                        str(reason), 
                        "Pending", 
                        jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                    ])
                    st.session_state.transfer_cart = []
                    success_dialog(f"Transfer successful! ID: {transfer_id}")
                else:
                    st.error(f"Transfer Failed: Origin({res_sub}) | Destination({res_add})")
                    
            except Exception as e:
                st.error(f"Critical Error: {e}")
            finally:
                # Always guarantees button unlocks even if an error/stop occurs
                st.session_state.is_submitting = False
    else:
        st.info("Please select a destination branch to finalize the transfer.")
else:
    st.info("Add items to your cart to proceed with the transfer.")

if "all_transfers" not in st.session_state:
    try:
        load_data()
    except Exception:
        st.error("Failed to load transfers.")
    st.session_state.history_limit = 5
    st.session_state.show_history = False

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
