import streamlit as st
import gspread
import random
import string
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close", key="close_dialog"):
        st.rerun()








def deduct_stock(client, branch_string, item_name, qty_to_deduct, date_header):
    try:
        # 1. Parse branch ID: 'B006 - SAFA1' -> 'B006' -> '006' -> 'BART006'
        # Adjust the split/replace logic to match your exact file naming
        branch_id = branch_string.split(" - ")[0].replace("B", "")
        file_name = f"BART{branch_id}"
        
        # 2. Open the specific file in Drive
        sh = client.open(file_name)
        # Note: Change "Inventory" to the exact name of the tab in your branch files
        ws = sh.worksheet("Inventory") 
        
        # 3. Find Item Row (Col 1) and Date Column (Row 1)
        item_cell = ws.find(item_name)
        if not item_cell:
            return f"Item '{item_name}' not found."
            
        header_row = ws.row_values(1)
        if date_header not in header_row:
            return f"Date '{date_header}' not found."
        
        col_index = header_row.index(date_header) + 1
        
        # 4. Perform math and update
        current_val = int(ws.cell(item_cell.row, col_index).value or 0)
        new_val = current_val - int(qty_to_deduct)
        
        ws.update_cell(item_cell.row, col_index, new_val)
        return "Success"
        
    except Exception as e:
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
    with st.spinner("Processing transfer and updating branch stock..."):
        try:
            # 1. Setup
            jeddah_time = datetime.now() + timedelta(hours=3)
            today_header = jeddah_time.strftime("%Y-%m-%d")
            transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
            
            creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # 2. Log to Master Sheet
            transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
            row_data = [
                transfer_id, 
                str(st.session_state.get("selected_branch", "Unknown")), 
                str(destination), 
                "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                str(reason),
                "Pending", 
                jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
            ]
            transfer_sheet.append_row(row_data)

            # 3. Update Branch Stock
            for entry in st.session_state.transfer_cart:
                result = deduct_stock(client, destination, entry['item'], entry['qty'], today_header)
                if result != "Success":
                    st.error(f"Failed to deduct {entry['item']}: {result}")
            
            # 4. Finalize
            st.session_state.transfer_cart = []
            success_dialog(f"Transfer successful! ID: {transfer_id}")
            
        except Exception as e:
            st.error(f"Critical Error: {e}")

st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
