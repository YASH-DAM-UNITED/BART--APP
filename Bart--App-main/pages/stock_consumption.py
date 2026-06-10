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
# INPUT SECTION (No st.form)
# -----------------------------
st.markdown("## Enter Stock")

# 1. Search Box
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

st.text_input(
    "🔍 Search for an item...", 
    key="search_input",
    on_change=lambda: setattr(st.session_state, "search_query", st.session_state.search_input)
)

# 2. Filtered list
query = st.session_state.search_query.lower()
filtered_items = [item for item in processed_items if query in item["name"].lower()]

# 3. Manual Entry fields (No form wrapper)
for i in range(0, len(filtered_items), 4):
    cols = st.columns(4)
    for j, col in enumerate(cols):
        if i + j < len(filtered_items):
            item_data = filtered_items[i + j]
            # Use the persistent key
            col.text_input(
                f"{item_data['name']} [{item_data['umo']}]",
                key=f"val_{item_data['row_idx']}" 
            )

# 4. Manual "Review" Button (This replaces the form_submit_button)
if st.button("🔍 Review Stock", type="primary"):
    collected_inputs = {}
    missing = []
    invalid = []
    
    # Collect data from all keys stored in session_state
    for item_data in processed_items:
        key = f"val_{item_data['row_idx']}"
        val = str(st.session_state.get(key, "")).strip()
        
        if val != "": # Only validate if they typed something
            if not val.isdigit():
                invalid.append(item_data["name"])
            else:
                collected_inputs[item_data["name"]] = val
                
    if invalid:
        show_error_dialog(f"Invalid numbers: {', '.join(invalid)}")
    elif not collected_inputs:
        show_error_dialog("Please enter at least one quantity.")
    else:
        st.session_state.draft_data = collected_inputs
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
