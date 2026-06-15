import streamlit as st
import gspread
import random
import string
import re
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import gspread.utils



# 1. Setup client and Branch Map
if "branch_map" not in st.session_state:
    with st.spinner("Initializing connection..."):
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["GOOGLE_CREDS_JSON"], 
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        st.session_state.client = client
        
        # Load the Branch Map from the Master Sheet
        master_sh = client.open("MASTERBRANCHSHEET")
        branch_ws = master_sh.worksheet("Branches") # Ensure this tab exists
        data = branch_ws.get_all_values()[1:] # Skip header
        
        # Create a dictionary: {'B001': '1VF7g...', 'B002': '1cEku...', ...}
        st.session_state.branch_map = {row[0]: row[1] for row in data}
# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Stock Transfer", layout="centered")

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.switch_page("pages/staff_dashboard.py")
        
        

def prepare_batch_updates(ws, cart, mode="subtract"):
    all_data = ws.get_all_values()
    if not all_data: return "Error: Sheet is empty"
    
    items_column = [row[0] for row in all_data]
    col_index = [i for i, h in enumerate(all_data[0]) if h and str(h).strip()][-1]
    
    batch_list = []
    for entry in cart:
        if entry['item'] in items_column:
            row_idx = items_column.index(entry['item'])
            current_val = all_data[row_idx][col_index]
            current_num = int(float(current_val)) if current_val and str(current_val).strip() else 0
            
            # Subtraction for origin, Addition for destination
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

# ---------------- MAIN APP LOGIC ----------------
st.title("🚚 Internal Stock Transfer")

if "transfer_cart" not in st.session_state:
    st.session_state.transfer_cart = []

if "current_stocks" not in st.session_state:
    st.error("No stock data found. Please return to the Dashboard.")
    if st.button("⬅ Go Back to Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# 1. ADD ITEMS SECTION
with st.expander("➕ Add Items to Transfer", expanded=True):
    category = st.radio("Select Item Category", ["Daily Items", "Weekly Items"], horizontal=True, key="cat_radio")
    target_list = st.session_state.current_stocks['daily'] if category == "Daily Items" else st.session_state.current_stocks['weekly']
    
    item_names = [row['Item'] for row in target_list]
    selected_item = st.selectbox("Select Item", item_names, key="item_sel")
    
    selected_row = next(row for row in target_list if row['Item'] == selected_item)
    uom_display = selected_row.get('DATE->  UOM', 'units') 
    
    col1, col2 = st.columns([3, 1])
    qty = col1.number_input("Quantity", min_value=1, step=1, key="qty_input")
    col2.markdown("<br>", unsafe_allow_html=True) 
    col2.write(f"**{uom_display}**")
    
    if st.button("Add to List", key="add_btn"):
        st.session_state.transfer_cart.append({"item": selected_item, "qty": qty, "uom": uom_display})
        st.success(f"Added {selected_item} to cart!")

# 2. CART AND DESTINATION SECTION
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
        origin_key = st.session_state.branch_map.get(origin_id)
        dest_key = st.session_state.branch_map.get(dest_id)
        
        if not origin_key or not dest_key:
            st.error("Branch ID not found in mapping table.")
        else:
            sh_origin = st.session_state.client.open_by_key(origin_key)
            sh_dest = st.session_state.client.open_by_key(dest_key)
            
            ws_origin = sh_origin.worksheet("Stocks")
            
            # --- PRE-VALIDATION CHECK ---
            all_origin_data = ws_origin.get_all_values()
            origin_items = [row[0] for row in all_origin_data]
            col_index = len(all_origin_data[0]) - 1
            
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
            # ----------------------------
            
            ws_dest = sh_dest.worksheet("Stocks")
            
            res_sub = prepare_batch_updates(ws_origin, st.session_state.transfer_cart, "subtract")
            res_add = prepare_batch_updates(ws_dest, st.session_state.transfer_cart, "add")
            
            if res_sub == "Success" and res_add == "Success":
                transfer_sheet = st.session_state.client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                transfer_sheet.append_row([
                    transfer_id, origin_branch_raw, str(destination), 
                    "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                    "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                    reason, "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                ])
                
                st.session_state.transfer_cart = []
                success_dialog(f"Transfer successful! ID: {transfer_id}")
            else:
                st.error(f"Transfer Failed: Origin({res_sub}) | Destination({res_add})")
                
    except Exception as e:
        st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
