import streamlit as st
import gspread
import random
import string
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

import gspread.utils

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.rerun()





def deduct_stock(client, branch_string, item_name, qty_to_deduct):
    try:
        # 1. CLEAN THE BRANCH CODE
        # Extracts digits from the branch string (e.g., 'B006 - SAFA1' -> '006')
        import re
        branch_numbers = re.findall(r'\d+', branch_string.split(" - ")[0])
        branch_id_str = branch_numbers[0] if branch_numbers else ""
        
        # 2. SEARCH FOR FILE BY NUMBER
        sh = None
        # We look for a file that contains the number part, e.g., '06'
        for spreadsheet in client.openall():
            # Check if the file name contains the branch ID (e.g., BART06 contains 06)
            if str(int(branch_id_str)) in spreadsheet.title:
                sh = spreadsheet
                break
        
        if not sh:
            available = [s.title for s in client.openall()]
            return f"Error: Could not find matching file for '{branch_string}'. Available: {available}"

        # 3. WORK WITH THE 'Stocks' TAB
        ws = sh.worksheet("Stocks")

        # 4. FIND ROW
        all_items = ws.col_values(1)
        if item_name not in all_items:
            return f"Item '{item_name}' not in Column A."
        row_index = all_items.index(item_name) + 1

        # 5. FIND COLUMN (Last date)
        header_row = ws.row_values(1)
        non_empty = [i for i, h in enumerate(header_row) if h and str(h).strip()]
        col_index = non_empty[-1] + 1
        
        # 6. READ AND CALCULATE
        cell_a1 = gspread.utils.rowcol_to_a1(row_index, col_index)
        current_val = ws.acell(cell_a1).value
        # Ensure we handle empty cells correctly
        current_num = int(float(current_val)) if current_val and str(current_val).strip() else 0
        new_val = current_num - int(qty_to_deduct)
        
        # 7. WRITE TO SHEET
        ws.update(range_name=cell_a1, values=[[new_val]])
        
        print(f"DEBUG: Successfully deducted {qty_to_deduct} from {cell_a1} in {sh.title}")
        return "Success"
        
    except Exception as e:
        return f"CRITICAL ERROR: {str(e)}"
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
    with st.spinner("Processing..."):
        try:
            jeddah_time = datetime.now() + timedelta(hours=3)
            transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
            
            creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # Log to Master
            transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
            transfer_sheet.append_row([
                transfer_id, str(st.session_state.get("selected_branch", "Unknown")), 
                str(destination), "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                str(reason), "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
            ])

            # Update Branch
            origin_branch = st.session_state.selected_branch
            for entry in st.session_state.transfer_cart:
                result = deduct_stock(client, origin_branch, entry['item'], entry['qty'])
                if result != "Success":
                    st.error(f"Failed to deduct {entry['item']} from {origin_branch}: {result}")
                    st.stop()
            
            st.session_state.transfer_cart = []
            success_dialog(f"Transfer successful! ID: {transfer_id}")
            
        except Exception as e:
            st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
