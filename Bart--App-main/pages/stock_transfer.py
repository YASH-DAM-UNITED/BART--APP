import streamlit as st
import time

# Ensure we have the branch data
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.error("Please login first!")
    st.stop()

st.title("📦 Internal Stock Transfer")

# Use the cached data from session_state
items_data = st.session_state.current_stocks
item_names = [row['Item'] for row in items_data]

# UI Inputs
selected_item = st.selectbox("Select Item", item_names)
qty = st.number_input("Quantity", min_value=1)
target_branch = st.selectbox("Destination", [b for b in branches if b != st.session_state.selected_branch])

if st.button("🚀 Send Transfer"):
    # 1. Update Notifications (The 'Trigger')
    master_sheet = client.open("MASTERBRANCHSHEET").worksheet("Notifications")
    master_sheet.append_row([
        target_branch.split(" - ")[0],
        f"{qty} units of {selected_item} from {st.session_state.selected_branch}",
        "unread",
        time.strftime("%Y-%m-%d %H:%M:%S")
    ])
    
    # 2. Logic to update your local stock sheet (The 'Deduction')
    # Use client.open_by_key(...) to update the sender's stock sheet
    st.success(f"Sent {qty} of {selected_item} to {target_branch}!")
    
    if st.button("Back to Dashboard"):
        st.switch_page("app.py")
