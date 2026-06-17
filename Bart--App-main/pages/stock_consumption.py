import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time
import uuid
from background import set_background
from gspread import Cell
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import streamlit.components.v1 as components

# -----------------------------
# UI SETUP
# -----------------------------


@st.dialog("⚠️ Input Error")
def show_error_dialog(message):
    st.error(message)
    if st.button("Close"):
        st.rerun()
st.set_page_config(page_title="Stock System", layout="wide")

st.markdown("""
<style>
#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}
[data-testid="stSidebar"] {display:none;}
.block-container {padding:0 !important; max-width:100% !important;}

.stApp {
    background: linear-gradient(135deg,#eef2f7,#d6e4ff);
}

div.stButton > button{
    height:55px;
    font-size:18px;
    border-radius:10px;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# SESSION INIT
# -----------------------------
if "page" not in st.session_state:
    st.session_state.page = "mode_select"

st.session_state.setdefault("mode", None)
st.session_state.setdefault("review_mode", False)
st.session_state.setdefault("draft_data", {})
st.session_state.setdefault("show_success", False)
st.session_state.setdefault("submitted", False)
st.session_state.setdefault("tx_id", None)

st.session_state.setdefault("scroll_to_review", False)
st.session_state.setdefault("proceed_submit", False)

# -----------------------------
# SCROLL FUNCTION
# -----------------------------
def scroll_to_review():
    """Uses a dedicated component to force the browser to scroll."""
    js_code = """
    <script>
        // Find the element with the specific ID
        const target = window.parent.document.getElementById("review_section");
        if (target) {
            target.scrollIntoView({behavior: "smooth", block: "start"});
        }
    </script>
    """
    # Use components.html to inject the script reliably
    components.html(js_code, height=0, width=0)

# -----------------------------
# TITLE
# -----------------------------
branch = st.session_state.get("selected_branch", "Branch")

st.markdown(
    f"<h1 style='text-align:center;color:red;'>{branch} - Stock System</h1>",
    unsafe_allow_html=True
)

# -----------------------------
# SHEET CHECK
# -----------------------------
sheet_id = st.session_state.get("sheet_id")
tab_name = st.session_state.get("tab_name")

if not sheet_id or not tab_name:
    st.error("Session expired.")

    if st.button("⬅ Back to Staff Dashboard"):
        st.switch_page("pages/staff_dashboard.py")

    st.stop()

# -----------------------------
# GOOGLE SHEETS AUTH
# -----------------------------
creds_dict = st.secrets["GOOGLE_CREDS_JSON"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_client():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

client = get_client()

@st.cache_resource
def get_sheet(sheet_id, tab_name):
    return client.open_by_key(sheet_id).worksheet(tab_name)

sheet = get_sheet(sheet_id, tab_name)

# -----------------------------
# LOAD DATA WITH INDICES MAPPED
# -----------------------------
def load_sheet_data(ws):
    """Loads all data to ensure items match their exact original spreadsheet row and UMO."""
    return ws.get_all_values()

sheet_data = load_sheet_data(sheet)

# Find sections by parsing the raw first column
raw_col_a = [row[0].strip() if row else "" for row in sheet_data]

def find_index(items, name):
    for i, v in enumerate(items):
        if v.strip().upper() == name:
            return i
    return None

daily_start = find_index(raw_col_a, "DAILY ITEM")
weekly_start = find_index(raw_col_a, "WEEKLY ITEM")

if daily_start is None or weekly_start is None:
    st.error("❌ DAILY ITEM or WEEKLY ITEM not found")
    st.stop()

# -----------------------------
# DIALOG FOR DUPLICATE SUBMISSION
# -----------------------------
@st.dialog("Submission Restricted")
def show_duplicate_warning():
    st.warning("Data for this date has already been submitted.")
    st.write("No rewrite is possible. Contact Branch Manager or Developer for queries.")
    if st.button("Close"):
        st.rerun()

# -----------------------------
# MODE SELECT & DATE CHECK (FIXED)
# -----------------------------
if st.session_state.page == "mode_select":
    st.markdown("## Select Date & Option")
    
    yesterday = datetime.now().date() - timedelta(days=1)
    selected_date = st.date_input("Select Date", value=yesterday)
    date_str = str(selected_date)

    def is_submitted(mode):
        headers = sheet_data[0]
        if date_str not in headers:
            return False 
        
        col_index = headers.index(date_str)
        
        # Calculate ranges dynamically based on your existing indices
        # daily_start is the row of "DAILY ITEM"
        # weekly_start is the row of "WEEKLY ITEM"
        if mode == "daily":
            # Check rows between DAILY ITEM and WEEKLY ITEM
            search_range = range(daily_start + 1, weekly_start)
        else:
            # Check rows from WEEKLY ITEM to the end of the data
            search_range = range(weekly_start + 1, len(sheet_data))
            
        for row_idx in search_range:
            # sheet_data is 0-indexed; row_idx is the index in the list
            row_content = sheet_data[row_idx]
            # Ensure col_index is within bounds and check for data
            if col_index < len(row_content):
                if str(row_content[col_index]).strip() != "":
                    return True
        return False

    c1, c2 = st.columns(2)

    if c1.button("📦 Daily Stock"):
        if is_submitted("daily"):
            show_duplicate_warning()
        else:
            st.session_state.mode = "daily"
            st.session_state.page = "stock_entry"
            st.rerun()

    if c2.button("📊 Weekly Stock"):
        if is_submitted("weekly"):
            show_duplicate_warning()
        else:
            st.session_state.mode = "weekly"
            st.session_state.page = "stock_entry"
            st.rerun()

    if st.button("⬅ Back to Staff"):
        st.switch_page("pages/staff_dashboard.py")

    st.stop()
# -----------------------------
# FILTER ITEMS & PRESERVE ROW DATA
# -----------------------------
mode = st.session_state.mode

# We build a list of dicts that hold item name, its UMO, and its original spreadsheet row index
processed_items = []
start_idx = (daily_start + 1) if mode == "daily" else (weekly_start + 1)
end_idx = weekly_start if mode == "daily" else len(sheet_data)

for idx in range(start_idx, end_idx):
    if idx < len(sheet_data):
        row = sheet_data[idx]
        item_name = row[0].strip() if row and row[0].strip() else ""
        
        # Skip section headers or empty cells accidentally left in the list
        if not item_name or item_name.upper() in ["DAILY ITEM", "WEEKLY ITEM"]:
            continue
            
        umo = row[2].strip() if len(row) >= 3 and row[2] else ""
        processed_items.append({
            "name": item_name,
            "umo": umo,
            "row_idx": idx + 1 # 1-based indexing for gspread
        })

st.info(f"Mode: {mode.upper()} | Items: {len(processed_items)}")

if st.button("⬅ Back"):
    st.session_state.page = "mode_select"
    st.session_state.mode = None
    st.rerun()

# -----------------------------
# DATE
# -----------------------------

yesterday = datetime.now().date() - timedelta(days=1)
date = st.date_input("Select Date", value=yesterday)
date_str = str(date)




# -----------------------------
# FORCE NUMERIC KEYPAD ON MOBILE
# -----------------------------
# This script targets all text inputs and forces them to show the number pad
# without changing the visual appearance or functionality of the input box.
components.html("""
<script>
    function setNumericKeypad() {
        var inputs = window.parent.document.querySelectorAll('input[type="text"]');
        inputs.forEach(function(input) {
            input.setAttribute('inputmode', 'numeric');
            input.setAttribute('pattern', '[0-9]*');
        });
    }
    // Run after a short delay to ensure elements are rendered
    setTimeout(setNumericKeypad, 500);
</script>
""", height=0)
# -----------------------------
# 1. PERSISTENT STORAGE INIT
# -----------------------------
if "stock_inputs" not in st.session_state:
    st.session_state.stock_inputs = {item["name"]: "" for item in processed_items}

if "search_clear" not in st.session_state:
    st.session_state.search_clear = ""

# 2. SYNC CALLBACK FUNCTION
def update_val(item_name):
    st.session_state.stock_inputs[item_name] = str(st.session_state[f"input_{item_name}"]).strip()

# -----------------------------
# 3. SEARCH BAR
# -----------------------------
# We use st.session_state.search_clear to allow the code to force-clear the UI
search_query = st.text_input(
    "🔍 Search by SKU or UOM", 
    value=st.session_state.search_clear,
    placeholder="Type SKU or UOM..."
).lower()

# Update state if the user types manually
st.session_state.search_clear = search_query

filtered_items = [
    item for item in processed_items 
    if search_query in item["name"].lower() or search_query in item["umo"].lower()
]

# -----------------------------
# 4. CUSTOM WARNING DIALOG
# -----------------------------
# -----------------------------
# 4. CUSTOM WARNING DIALOG (UPDATED TO WARNING)
# -----------------------------
@st.dialog("⚠️ Pending Items")
def show_missing_warning():
    # Changed from st.warning/st.error to be more descriptive
    st.markdown("### 📋 Action Required")
    st.warning("Some items are still empty. Please clear the search to see the full list and fill in all quantities.")
    
    st.write("#### Missing quantities for:")
    # Using st.warning instead of st.error for the list of items
    st.warning(", ".join(st.session_state.get("pending_items", [])[:10]) + ("..." if len(st.session_state.get("pending_items", [])) > 10 else ""))
    
    if st.button("Clear Search & View All", type="primary"):
        st.session_state.search_clear = "" # This forces the search bar to empty
        st.rerun()# -----------------------------
# 4. CUSTOM WARNING DIALOG (UPDATED TO WARNING)
# -----------------------------
@st.dialog("⚠️ Pending Items")
def show_missing_warning():
    # Changed from st.warning/st.error to be more descriptive
    st.markdown("### 📋 Action Required")
    st.warning("Some items are still empty. Please clear the search to see the full list and fill in all quantities.")
    
    st.write("#### Missing quantities for:")
    # Using st.warning instead of st.error for the list of items
    st.warning(", ".join(st.session_state.get("pending_items", [])[:10]) + ("..." if len(st.session_state.get("pending_items", [])) > 10 else ""))
    
    if st.button("Clear Search & View All", type="primary"):
        st.session_state.search_clear = "" # This forces the search bar to empty
        st.rerun()
# -----------------------------
# 5. DYNAMIC INPUT FIELDS (NO FORM)
# -----------------------------
st.markdown("## Enter Stock")

for i in range(0, len(filtered_items), 4):
    cols = st.columns(4)
    for j, col in enumerate(cols):
        if i + j < len(filtered_items):
            item_data = filtered_items[i + j]
            item_name = item_data["name"]
            
            # Persistent value pulled from master dictionary
            col.text_input(
                label=f"{item_name} [{item_data['umo']}]",
                value=st.session_state.stock_inputs.get(item_name, ""),
                key=f"input_{item_name}",
                on_change=update_val,
                args=(item_name,),
                placeholder="Qty"
            )

# -----------------------------
# 6. MANUAL SUBMIT BUTTON
# -----------------------------
if st.button("🔍 Review Stock", type="primary", use_container_width=True):
    # Validation against the Master Dictionary
    missing = [name for name, val in st.session_state.stock_inputs.items() if not val]
    invalid = [name for name, val in st.session_state.stock_inputs.items() if val and not val.isdigit()]
    
    if invalid:
        show_error_dialog(f"Invalid numbers in: {', '.join(invalid)}")
    elif missing:
        st.session_state.pending_items = missing
        show_missing_warning()
    else:
        # Move to Review
        st.session_state.draft_data = st.session_state.stock_inputs
        st.session_state.review_mode = True
        st.session_state.scroll_to_review = True
        st.rerun()
# -----------------------------
# 5-COLUMN COMPACT REVIEW
# -----------------------------
if st.session_state.review_mode:
    st.markdown('<div id="review_section"></div>', unsafe_allow_html=True)
    
    st.markdown("### 📋 Final Review")

    # Tight CSS for ultra-compact cards
    st.markdown("""
    <style>
    .compact-card {
        padding: 4px;
        border: 1px solid #d1d9e6;
        border-radius: 6px;
        margin: 2px;
        background: #fdfdfd;
        text-align: center;
        font-size: 12px;
    }
    </style>
    """, unsafe_allow_html=True)

    # 5-Column layout
    data_items = list(st.session_state.draft_data.items())
    cols = st.columns(5)
    
    for idx, (item, qty) in enumerate(data_items):
        with cols[idx % 5]:
            st.markdown(f"""
            <div class="compact-card">
                <small>{item}</small><br><b>{qty}</b>
            </div>
            """, unsafe_allow_html=True)
            
    st.markdown("---")
    
    # Action Buttons
    c1, c2 = st.columns(2)
    if c1.button("⬅ Edit", use_container_width=True):
        st.session_state.review_mode = False
        st.rerun()
        
    if c2.button("✅ Submit", type="primary", use_container_width=True):
        st.session_state.proceed_submit = True
        st.rerun()

# -----------------------------
# AUTO SCROLL
# -----------------------------
if st.session_state.get("scroll_to_review", False):
    # This must be called AFTER the div with id="review_section" is rendered
    scroll_to_review()
    st.session_state.scroll_to_review = False
# -----------------------------
# FINAL SUBMIT
# -----------------------------
if st.session_state.proceed_submit:
    try:
        with st.spinner("Saving stock..."):
            # Headers configuration remain unchanged
            headers = sheet_data[0]
            submission_time = time.strftime("%Y-%m-%d %H:%M:%S")

            if not st.session_state.tx_id:
                st.session_state.tx_id = str(uuid.uuid4())[:8]

            if date_str in headers:
                col_index = headers.index(date_str) + 1
            else:
                col_index = len(headers) + 1
                sheet.update_cell(1, col_index, date_str)

            col_values = sheet.col_values(1)
            item_to_row = {val.strip(): i + 1 for i, val in enumerate(col_values)}

            cells = []
            for item, qty in st.session_state.draft_data.items():
                row = item_to_row.get(item)
                if row:
                    cells.append(Cell(row=row, col=col_index, value=qty))

            if cells:
                sheet.update_cells(cells, value_input_option="USER_ENTERED")

            # ---------------- EMAIL ----------------
            report = f"""
Stock Submission Report

Submitted By: System Auto Entry
Time: {submission_time}
Transaction ID: {st.session_state.tx_id}
Branch: {st.session_state.get('selected_branch')}
Mode: {st.session_state.mode}

STATUS: STOCK SUBMITTED SUCCESSFULLY
"""

            sender_email = "yashu8088234@gmail.com"
            sender_password = st.secrets["EMAIL_PASSWORD"]

            msg = MIMEText(report)
            msg["Subject"] = "New Stock Submission"
            msg["From"] = sender_email
            msg["To"] = "yash2002anitha@gmail.com"

            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, "yash2002anitha@gmail.com", msg.as_string())
            server.quit()

            st.session_state.proceed_submit = False
            st.session_state.review_mode = False
            st.session_state.show_success = True
            st.session_state.submitted = True

        st.rerun()

    except Exception as e:
        st.error(f"Error: {e}")

# -----------------------------
# SUCCESS SCREEN
# -----------------------------
if st.session_state.show_success:
    st.markdown("""
    <div style="
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100vh;
        background: rgba(0,0,0,0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
    ">
        <div style="
            background: white;
            padding: 50px;
            border-radius: 20px;
            text-align: center;
            width: 500px;
            box-shadow: 0px 10px 30px rgba(0,0,0,0.3);
        ">
            <div style="font-size: 90px; color: #00c853;">✔</div>
            <div style="font-size: 36px; font-weight: 900;">SUBMITTED</div>
            <div style="margin-top:10px; color: gray;">
                Stock saved successfully
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.toast(f"Submitted ✔ | TX: {st.session_state.tx_id}", icon="✔")
    time.sleep(6)

    st.session_state.page = "mode_select"
    st.session_state.mode = None
    st.session_state.review_mode = False
    st.session_state.draft_data = {}
    st.session_state.show_success = False
    st.session_state.submitted = False
    st.session_state.tx_id = None

    st.switch_page("pages/staff_dashboard.py")
