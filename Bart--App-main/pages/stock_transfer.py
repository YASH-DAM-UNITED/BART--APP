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

st.session_state.branch_list = branches
# ---------------- NAVIGATION ----------------
st.markdown("---")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("pages/staff_dashboard.py")
