import streamlit as st
import time

# Use the cached data from your main app/session
# Assuming you stored your stocks in st.session_state during the login or dashboard phase
if 'current_stocks' not in st.session_state:
    st.error("No stock data found. Please return to the dashboard.")
    st.stop()

items_data = st.session_state.current_stocks

st.subheader("📦 Transfer Stock to Another Branch")

# 1. UI for selection
selected_item_name = st.selectbox("Select Item to Transfer", [row['Item'] for row in items_data])
qty = st.number_input("Quantity to Transfer", min_value=1, step=1)
target_branch = st.selectbox("Select Destination Branch", [b for b in branches if b != st.session_state.selected_branch])

# 2. The Send Logic
if st.button("🚀 Confirm & Send"):
    with st.spinner("Processing transfer..."):
        # A. Add to Notification Sheet (The "Push" notification)
        master_sheet = client.open("MASTERBRANCHSHEET").worksheet("Notifications")
        master_sheet.append_row([
            target_branch.split(" - ")[0], 
            f"{qty} units of {selected_item_name} sent from {st.session_state.selected_branch}", 
            "unread", 
            time.strftime("%Y-%m-%d %H:%M:%S")
        ])
        
        # B. Deduct from your current branch sheet
        # You need to find the row index of the item to update it
        current_sheet = client.open_by_key(st.session_state.branch_info["SheetID"]).worksheet("Stocks")
        cell = current_sheet.find(selected_item_name)
        if cell:
            # Get current value (column 2 for example, adjust based on your sheet)
            current_val = int(current_sheet.cell(cell.row, 2).value)
            current_sheet.update_cell(cell.row, 2, current_val - qty)
            
            st.success(f"Successfully sent {qty} {selected_item_name} to {target_branch}!")
        else:
            st.error("Item not found in your stock sheet.")

if st.button("⬅ Back to Dashboard"):
    st.switch_page("app.py")
