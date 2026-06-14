import streamlit as st
import gspread
import random
import string
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
import gspread
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import random
import string
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
    source_branch = st.session_state.get("selected_branch")
    
    try:
        # 1. Setup Auth
        creds = Credentials.from_service_account_info(
            st.secrets["GOOGLE_CREDS_JSON"], 
            scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        )
        client = gspread.authorize(creds)
        
        # 2. Open Spreadsheet by Name
        spreadsheet = client.open(source_branch)
        branch_sheet = spreadsheet.get_worksheet(0)
        last_col = len(branch_sheet.row_values(1))
        
        # 3. Process Items
        for entry in st.session_state.transfer_cart:
            cell = branch_sheet.find(entry['item'].strip(), in_column=1)
            
            if cell:
                # Calculate
                raw_val = branch_sheet.cell(cell.row, last_col).value
                current_val = float(raw_val) if (raw_val and str(raw_val).replace('.','',1).isdigit()) else 0.0
                new_val = current_val - float(entry['qty'])
                
                # 4. BYPASS: Use raw API call to update the cell
                # This bypasses the gspread response parsing that causes the [200] error
                spreadsheet.values_update(
                    f"'{branch_sheet.title}'!{gspread.utils.rowcol_to_a1(cell.row, last_col)}",
                    params={'valueInputOption': 'RAW'},
                    body={'values': [[new_val]]}
                )
        
        # 5. Log to Master (Also using raw update for consistency)
        transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
        transfer_sheet.append_row([
            "TR-SYNC", source_branch, destination, str(entry['item']), str(entry['qty']), "Pending", "Success"
        ])
        
        st.session_state.transfer_cart = []
        st.success("Deduction complete!")
        st.rerun()

    except Exception as e:
        # If this STILL fails, the error message will be the exact Google API response body
        st.error(f"SYSTEM BYPASS FAILURE: {str(e)}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
