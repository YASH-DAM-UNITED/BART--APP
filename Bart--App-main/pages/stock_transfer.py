import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ---------------- DIALOG DEFINITION ----------------
@st.dialog("Transfer Success")
def success_dialog(message):
    st.write(message)
    if st.button("Close"):
        st.rerun()

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Stock Transfer", layout="centered")
st.title("🚀 Internal Stock Transfer")

# 1. SAFETY CHECK
if "current_stocks" not in st.session_state:
    st.error("No stock data found. Please return to the Dashboard and click 'Stock View' first.")
    if st.button("⬅ Go Back to Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# 2. DATA ACCESS
items_data = st.session_state.current_stocks
category = st.radio("Select Item Category", ["Daily Items", "Weekly Items"], horizontal=True)
target_list = items_data['daily'] if category == "Daily Items" else items_data['weekly']

item_names = [row['Item'] for row in target_list]
selected_item = st.selectbox("Select Item to Transfer", item_names)

# 3. TRANSFER FORM
with st.form("transfer_form"):
    qty = st.number_input("Quantity to Transfer", min_value=1, step=1)
    
    # Branch Selection Dropdown
    if "branch_list" in st.session_state:
        destination = st.selectbox("Select Destination Branch", st.session_state.branch_list)
    else:
        st.warning("Branch list missing. Please return to the Dashboard to reload.")
        destination = None
        
    reason = st.text_area("Reason for Transfer")
    submitted = st.form_submit_button("Confirm Transfer")
    
    if submitted and destination:
        try:
            # --- GOOGLE SHEET INTEGRATION ---
            creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # Access the master sheet and the 'Transfers' tab
            sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
            
            # Save data: [From Branch, To Branch, Item, Qty, Reason]
            from_branch = st.session_state.selected_branch
            row_data = [from_branch, destination, selected_item, qty, reason]
            
            sheet.append_row(row_data)
            
            # Trigger Success Dialog
            success_dialog(f"Successfully transferred {qty} of {selected_item} to {destination}!")
            
        except Exception as e:
            st.error(f"Error saving to Google Sheets: {e}")

# ---------------- NAVIGATION ----------------
st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
