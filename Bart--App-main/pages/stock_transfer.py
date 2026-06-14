import streamlit as st
import gspread
import random
import string
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import streamlit as st
import gspread
import re
from oauth2client.service_account import ServiceAccountCredentials
import gspread.utils

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.rerun()





# During App Initialization (e.g., inside your main dashboard file)
if "branch_map" not in st.session_state:
    try:
        # Load your credentials
        creds = ServiceAccountCredentials.from_json_keyfile_dict(
            st.secrets["GOOGLE_CREDS_JSON"], 
            ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        
        # Fetch the mapping from a 'Config' sheet in your MASTERBRANCHSHEET
        # Assume Column A is Branch ID, Column B is Spreadsheet ID
        config_ws = client.open("MASTERBRANCHSHEET").worksheet("Config")
        data = config_ws.get_all_values()
        st.session_state.branch_map = {row[0]: row[1] for row in data if len(row) > 1}
    except Exception as e:
        st.error(f"Error initializing branch map: {e}")


def prepare_batch_updates(ws, cart):
    # Fetch all data once to avoid repeated calls
    all_data = ws.get_all_values()
    if not all_data: return "Error: Sheet is empty"
    
    items_column = [row[0] for row in all_data]
    header_row = all_data[0]
    
    # Identify the correct column (last non-empty column)
    non_empty = [i for i, h in enumerate(header_row) if h and str(h).strip()]
    col_index = non_empty[-1] 
    
    batch_list = []
    
    for entry in cart:
        if entry['item'] in items_column:
            row_idx = items_column.index(entry['item'])
            current_val = all_data[row_idx][col_index]
            current_num = int(float(current_val)) if current_val and str(current_val).strip() else 0
            new_val = current_num - int(entry['qty'])
            
            # Prepare update for batch
            cell_address = gspread.utils.rowcol_to_a1(row_idx + 1, col_index + 1)
            batch_list.append({"range": cell_address, "values": [[new_val]]})
            
    if batch_list:
        ws.batch_update(batch_list)
        return "Success"
    return "Error: Items not found in sheet"
# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Stock Transfer", layout="centered")
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
    # Pre-calculate details
    jeddah_time = datetime.now() + timedelta(hours=3)
    transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    origin_branch = st.session_state.selected_branch
    branch_id = re.findall(r'\d+', origin_branch.split(" - ")[0])[0]
    
    with st.spinner("Processing..."):
        try:
            # Re-authorize client
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                st.secrets["GOOGLE_CREDS_JSON"], 
                ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )
            client = gspread.authorize(creds)
            
            # 1. CALL 1: Update Branch Stocks (Using Cached ID)
            sheet_id = st.session_state.branch_map.get(branch_id)
            if not sheet_id:
                st.error("Branch ID not found in mapping!")
                st.stop()
                
            sh = client.open_by_key(sheet_id)
            ws = sh.worksheet("Stocks")
            
            # Use the Batch Update function (Defined previously)
            result = prepare_batch_updates(ws, st.session_state.transfer_cart)
            
            if result == "Success":
                # 2. CALL 2: Log to Master Sheet
                transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                transfer_sheet.append_row([
                    transfer_id, origin_branch, str(st.session_state.dest_sel), 
                    "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                    "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                    st.session_state.reason_input, "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                ])
                
                st.session_state.transfer_cart = []
                success_dialog(f"Transfer successful! ID: {transfer_id}")
            else:
                st.error(result)
                    
        except Exception as e:
            st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
