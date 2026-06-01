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

# Initialize Cart in session state
if "transfer_cart" not in st.session_state:
    st.session_state.transfer_cart = []

# 1. SAFETY CHECK
if "current_stocks" not in st.session_state:
    st.error("No stock data found. Please return to the Dashboard and click 'Stock View' first.")
    if st.button("⬅ Go Back to Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# 2. ADD TO CART FORM
with st.expander("➕ Add Items to Transfer", expanded=True):
    category = st.radio("Select Item Category", ["Daily Items", "Weekly Items"], horizontal=True)
    target_list = st.session_state.current_stocks['daily'] if category == "Daily Items" else st.session_state.current_stocks['weekly']
    
    item_names = [row['Item'] for row in target_list]
    selected_item = st.selectbox("Select Item", item_names)
    qty = st.number_input("Quantity to Transfer", min_value=1, step=1)
    
    if st.button("Add to List"):
        st.session_state.transfer_cart.append({
            "item": selected_item,
            "qty": qty
        })
        st.success(f"Added {selected_item} to cart!")

# 3. DISPLAY CART
if st.session_state.transfer_cart:
    st.subheader("📋 Current Transfer List")
    for i, entry in enumerate(st.session_state.transfer_cart):
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{entry['item']}**")
        col2.write(f"{entry['qty']} units")
        if col3.button("Remove", key=f"del_{i}"):
            st.session_state.transfer_cart.pop(i)
            st.rerun()

# 4. FINAL SUBMISSION
if st.session_state.transfer_cart:
    st.markdown("---")
    with st.form("final_transfer_form"):
        if "branch_list" in st.session_state:
            destination = st.selectbox("Select Destination Branch", st.session_state.branch_list)
        else:
            st.warning("Branch list missing.")
            destination = None
            
        reason = st.text_area("Reason for Transfer")
        submitted = st.form_submit_button("Confirm and Send All")
        
        if submitted and destination:
            try:
                creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
                scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
                client = gspread.authorize(creds)
                sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                
                # Batch process
                for entry in st.session_state.transfer_cart:
                    row_data = [st.session_state.selected_branch, destination, entry['item'], entry['qty'], reason]
                    sheet.append_row(row_data)
                
                # Clear cart and show success
                st.session_state.transfer_cart = []
                success_dialog("Successfully transferred all items!")
                
            except Exception as e:
                st.error(f"Error saving to Google Sheets: {e}")

# ---------------- NAVIGATION ----------------
st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
