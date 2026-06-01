import streamlit as st

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Stock Transfer", layout="centered")

st.title("🚀 Internal Stock Transfer")

# 1. SAFETY CHECK: Ensure data was passed from dashboard
if "current_stocks" not in st.session_state:
    st.error("No stock data found. Please return to the Dashboard and click 'Stock View' first.")
    if st.button("⬅ Go Back to Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# 2. DATA ACCESS
items_data = st.session_state.current_stocks

# 3. CATEGORY SELECTION
# Using the dictionary structure created in staff_dashboard.py
category = st.radio("Select Item Category", ["Daily Items", "Weekly Items"], horizontal=True)

if category == "Daily Items":
    target_list = items_data['daily']
else:
    target_list = items_data['weekly']

# 4. ITEM SELECTION
item_names = [row['Item'] for row in target_list]
selected_item = st.selectbox("Select Item to Transfer", item_names)

# 5. TRANSFER FORM
with st.form("transfer_form"):
    qty = st.number_input("Quantity to Transfer", min_value=1, step=1)
    
    # This reads the memory cached from the dashboard. 
    # NO API CALLS HAPPEN HERE.
    if "branch_list" in st.session_state:
        # We use a copy to avoid mutating the session state directly
        destination = st.selectbox("Select Destination Branch", st.session_state.branch_list)
    else:
        st.warning("Branch list missing. Please return to the Dashboard.")
        destination = None
        
    reason = st.text_area("Reason for Transfer")
    
    submitted = st.form_submit_button("Confirm Transfer")
    
    if submitted and destination:
        # Process the transfer logic (e.g., writing to a local log or updating session)
        st.success(f"Successfully prepared transfer of {qty} of {selected_item} to {destination}!")
# ---------------- NAVIGATION ----------------
st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
