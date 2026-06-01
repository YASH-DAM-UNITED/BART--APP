
import streamlit as st
import gspread

# 1. Load current branch stocks
# You already have branch_info in session_state from your login
sheet = client.open_by_key(st.session_state.branch_info["SheetID"]).worksheet("Stocks")
items_data = sheet.get_all_records() # Get items to transfer

# 2. UI for selection
selected_item = st.selectbox("Select Item to Transfer", [row['Item'] for row in items_data])
qty = st.number_input("Quantity", min_value=1)
target_branch = st.selectbox("Select Target Branch", [b for b in branches if b != st.session_state.selected_branch])

# 3. The "Send" Button
if st.button("🚀 Send Transfer"):
    # A. Update Master Notification Sheet
    master_sheet = client.open("MASTERBRANCHSHEET").worksheet("Notifications")
    master_sheet.append_row([
        target_branch.split(" - ")[0], # Target Branch Code
        f"Incoming {qty} of {selected_item} from {st.session_state.selected_branch}", # Message
        "unread",
        time.strftime("%Y-%m-%d %H:%M:%S")
    ])
    
    # B. Deduct from current branch (Optional logic)
    # ... your logic to update the current sheet ...
    
    st.success(f"Transfer of {selected_item} to {target_branch} initiated!")
