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

# Find the specific row data for the selected item
selected_details = next((item for item in target_list if item['Item'] == selected_item), None)

if selected_details:
    st.info(f"Current Stock Info: {selected_item}")
    # You can show the "Total" or other columns from your sheet here
    st.write(f"Total Available: {selected_details.get('Total', 0)}")

# 5. TRANSFER FORM
with st.form("transfer_form"):
    qty = st.number_input("Quantity to Transfer", min_value=1, step=1)
    destination = st.text_input("Destination Branch Code")
    reason = st.text_area("Reason for Transfer")
    
    submitted = st.form_submit_button("Confirm Transfer")
    
    if submitted:
        if not destination:
            st.error("Please enter a destination branch.")
        else:
            # --- ADD YOUR GOOGLE SHEET UPDATE LOGIC HERE ---
            # Example:
            # sheet = client.open_by_key(branch_info["SheetID"]).worksheet("Transfers")
            # sheet.append_row([selected_item, qty, destination, reason])
            
            st.success(f"Successfully transferred {qty} of {selected_item} to {destination}!")
            st.balloons()

# ---------------- NAVIGATION ----------------
st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
