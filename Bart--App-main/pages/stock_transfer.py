import streamlit as st
import gspread
import random
import string
import re
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import gspread.utils

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Stock Transfer", layout="centered")

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.rerun()

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
        # 1. Define variables
        jeddah_time = datetime.now() + timedelta(hours=3)
        transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
        origin_branch = st.session_state.selected_branch

        with st.spinner("Processing your transfer..."):
            try:
                # 2. Setup client
                creds = ServiceAccountCredentials.from_json_keyfile_dict(
                    st.secrets["GOOGLE_CREDS_JSON"], 
                    ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                )
                client = gspread.authorize(creds)
                
                # 3. Identify Branch
                origin_id = re.findall(r'\d+', st.session_state.selected_branch.split(" - ")[0])[0]
                dest_id = re.findall(r'\d+', str(destination).split(" - ")[0])[0]
                sh_origin = next(s for s in client.openall() if str(int(origin_id)) in s.title)
                sh_dest = next(s for s in client.openall() if str(int(dest_id)) in s.title)
                
                
                if not sh_origin or not sh_dest:
                    st.error("Could not find branch spreadsheet.")
                else:
                    
                    
                    res_origin = prepare_batch_updates(sh_origin.worksheet("Stocks"), st.session_state.transfer_cart, "subtract")
                    res_dest = prepare_batch_updates(sh_dest.worksheet("Stocks"), st.session_state.transfer_cart, "add")
                    
                    if res_sub == "Success" and res_add == "Success":
                        # 5. Log to Master
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
                        st.error(result)
            except Exception as e:
                st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
