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


def update_stocks(worksheet, cart, operation):
    all_data = worksheet.get_all_values()
    items_col = [row[0] for row in all_data]
    col_idx = [i for i, h in enumerate(all_data[0]) if h and str(h).strip()][-1]
    
    batch = []
    for entry in cart:
        if entry['item'] in items_col:
            row_idx = items_col.index(entry['item'])
            current = int(float(all_data[row_idx][col_idx] or 0))
            # The only difference: addition or subtraction
            new_val = (current - int(entry['qty'])) if operation == "sub" else (current + int(entry['qty']))
            
            cell = gspread.utils.rowcol_to_a1(row_idx + 1, col_idx + 1)
            batch.append({"range": cell, "values": [[new_val]]})
            
    if batch:
        worksheet.batch_update(batch)
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
    # 1. Define variables at the start so they are accessible throughout the block
    jeddah_time = datetime.now() + timedelta(hours=3)
    transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    destination = st.session_state.get("dest_sel", "Unknown")
    reason = st.session_state.get("reason_input", "No reason provided")
    origin_branch = st.session_state.selected_branch

with st.spinner("Processing your transfer..."):
        try:
            # 1. Setup client
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                st.secrets["GOOGLE_CREDS_JSON"], 
                ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            )
            client = gspread.authorize(creds)
            
            # 2. Identify Origin Branch
            branch_id = re.findall(r'\d+', origin_branch.split(" - ")[0])[0]
            sh = next((s for s in client.openall() if str(int(branch_id)) in s.title), None)
            
            if not sh:
                st.error("Could not find origin branch spreadsheet.")
            else:
                ws = sh.worksheet("Stocks")
                
                # --- SUBTRACTION (Origin) ---
                # We use your existing function to handle the minus
                res_sub = prepare_batch_updates(ws, st.session_state.transfer_cart)
                
                if res_sub == "Success":
                    # --- ADDITION (Destination) ---
                    # Keep your destination variable logic as is
                    dest_sh = client.open(destination)
                    dest_ws = dest_sh.worksheet("Stocks")
                    
                    # We reuse your existing function logic, but we need to add, 
                    # so we create a small temporary helper for the addition:
                    dest_data = dest_ws.get_all_values()
                    dest_items = [row[0] for row in dest_data]
                    dest_header = dest_data[0]
                    dest_col_idx = [i for i, h in enumerate(dest_header) if h and str(h).strip()][-1]
                    
                    add_list = []
                    for entry in st.session_state.transfer_cart:
                        if entry['item'] in dest_items:
                            row_idx = dest_items.index(entry['item'])
                            curr_val = int(float(dest_data[row_idx][dest_col_idx] or 0))
                            new_val = curr_val + int(entry['qty'])
                            cell_addr = gspread.utils.rowcol_to_a1(row_idx + 1, dest_col_idx + 1)
                            add_list.append({"range": cell_addr, "values": [[new_val]]})
                    
                    if add_list:
                        dest_ws.batch_update(add_list)
                    
                    # 3. Log to Master
                    transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                    transfer_sheet.append_row([
                        transfer_id, origin_branch, str(destination), 
                        "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                        "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                        reason, "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                    ])
                    
                    st.session_state.transfer_cart = []
                    success_dialog(f"Transfer successful! ID: {transfer_id}")
                else:
                    st.error(res_sub)
        except Exception as e:
            st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
