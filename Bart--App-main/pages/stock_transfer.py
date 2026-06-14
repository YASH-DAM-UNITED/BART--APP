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
        branch_id = branch_string.split(" - ")[0].replace("B", "")
        file_name = f"BART{branch_id}"
        sh = client.open(file_name)
        ws = sh.worksheet("Stocks")

        # 1. Row Identification
        all_items = ws.col_values(1)
        if item_name not in all_items:
            return f"Error: '{item_name}' not in Col 1."
        row_index = all_items.index(item_name) + 1
        print(f"DEBUG: Item Found! Row: {row_index}")

        # 2. Force Column Identification (Skip empty gap)
        # We look at Row 1, but we tell it to look from Column 14 (N) to 20
        # This prevents it from counting 'DAILY ITEM' or 'SKU' as the date column
        header_row = ws.row_values(1)
        
        # We define a range: looking for the latest date in columns 14 to 20
        # This assumes your dates are always in columns N through T
        potential_date_cols = header_row[13:20] 
        # Find the last non-empty column index in that range
        last_col_idx = 0
        for i, val in enumerate(potential_date_cols):
            if val and str(val).strip():
                last_col_idx = 14 + i
        
        col_index = last_col_idx
        print(f"DEBUG: Selected Column: {col_index}")

        if col_index < 14:
            return "Error: Could not identify Date Column. Check that dates are in Columns N-T."

        # 3. Update using Cell Value direct
        current_val = ws.cell(row_index, col_index).value
        current_int = int(current_val) if (current_val and str(current_val).strip().isdigit()) else 0
        new_val = current_int - int(qty_to_deduct)
        
        # Using a direct write that is more compatible than update()
        ws.update_cell(row_index, col_index, new_val)
        print(f"DEBUG: Successfully updated cell at ({row_index}, {col_index}) to {new_val}")
        
        return "Success"
        
    except Exception as e:
        print(f"DEBUG CRITICAL ERROR: {str(e)}")
        return str(e)

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
            for entry in st.session_state.transfer_cart:
                result = deduct_stock(client, destination, entry['item'], entry['qty'])
                if result != "Success":
                    st.error(f"Failed to deduct {entry['item']}: {result}")
                    st.stop()
            
            st.session_state.transfer_cart = []
            success_dialog(f"Transfer successful! ID: {transfer_id}")
            
        except Exception as e:
            st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
