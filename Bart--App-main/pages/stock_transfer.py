import streamlit as st
import gspread
import random
import string
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.rerun()

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
        try:
            # 1. Setup Connection
            creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
            scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
            client = gspread.authorize(creds)
            
            # 2. Get Source Branch Data
            source_branch = st.session_state.get("selected_branch")
            if not source_branch:
                st.error("Branch not selected.")
                st.stop()
                
            branch_sheet = client.open(source_branch).worksheet("Stocks")
            
            # 3. Identify the last column (most recent date)
            # Assuming row 1 contains the headers/dates
            header_row = branch_sheet.row_values(1)
            last_col_index = len(header_row) 
            
            # 4. Check Stock Availability First (Transaction Integrity)
            for entry in st.session_state.transfer_cart:
                item_cell = branch_sheet.find(entry['item'])
                if not item_cell:
                    st.error(f"Item '{entry['item']}' not found in {source_branch} sheet.")
                    st.stop()
                
                current_val = branch_sheet.cell(item_cell.row, last_col_index).value
                current_stock = int(current_val) if (current_val and current_val.isdigit()) else 0
                
                if current_stock < entry['qty']:
                    st.error(f"Insufficient stock for {entry['item']}! (Available: {current_stock})")
                    st.stop()

            # 5. Perform Deductions
            for entry in st.session_state.transfer_cart:
                item_cell = branch_sheet.find(entry['item'])
                current_val = int(branch_sheet.cell(item_cell.row, last_col_index).value)
                new_stock = current_val - entry['qty']
                branch_sheet.update_cell(item_cell.row, last_col_index, new_stock)
            
            # 6. Log to Master Transfer Sheet
            transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
            
            jeddah_time = datetime.now() + timedelta(hours=3)
            date_str = jeddah_time.strftime("%Y%m%d")
            random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            transfer_id = f"TR-{date_str}-{random_suffix}"
            
            combined_items_str = "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart])
            combined_qtys_str = "\n".join([str(e['qty']) for e in st.session_state.transfer_cart])
            
            row_data = [
                transfer_id,
                str(source_branch),
                str(destination),
                str(combined_items_str),
                str(combined_qtys_str),
                str(reason),
                "Pending",
                jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
            ]
            
            transfer_sheet.append_row(row_data)
            
            # 7. Finalize
            st.session_state.transfer_cart = []
            success_dialog(f"Transfer {transfer_id} processed and stock deducted.")
            
        except Exception as e:
            st.error(f"System Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
