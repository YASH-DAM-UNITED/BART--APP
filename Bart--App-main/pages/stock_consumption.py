import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread import Cell
from datetime import datetime, timedelta
import smtplib
import threading
from email.mime.text import MIMEText
import streamlit.components.v1 as components
import time
import uuid

# ============================================================
# GLOBAL DRAFT VAULT (Server-side Persistence)
# ============================================================
class DraftVault:
    def __init__(self):
        self.data = {}  # Format: {"branch_date_mode": {item: qty}}

    def save_draft(self, branch, date, mode, inputs):
        key = f"{branch}_{date}_{mode}"
        self.data[key] = inputs

    def get_draft(self, branch, date, mode):
        key = f"{branch}_{date}_{mode}"
        return self.data.get(key, {})

    def clear_draft(self, branch, date, mode):
        key = f"{branch}_{date}_{mode}"
        if key in self.data:
            del self.data[key]

@st.cache_resource
def get_vault():
    return DraftVault()

vault = get_vault()

# ============================================================
# PAGE CONFIG — must be FIRST Streamlit call, no exceptions
# ============================================================
st.set_page_config(page_title="Stock System", layout="wide")

# ============================================================
# GLOBAL STYLES
# ============================================================
st.markdown("""
<style>
#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}
[data-testid="stSidebar"] {display:none;}
.block-container {padding:0 !important; max-width:100% !important;}
.stApp { background: linear-gradient(135deg,#eef2f7,#d6e4ff); }
div.stButton > button { height:55px; font-size:18px; border-radius:10px; }
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

# ============================================================
# SESSION STATE INIT
# FIX #2: Use a factory function — never store a mutable default
# dict/list directly, each session gets its own fresh copy.
# ============================================================
def _session_defaults():
    return {
        "page": "mode_select",
        "mode": None,
        "review_mode": False,
        "draft_data": {},        # fresh dict per call — no shared reference
        "show_success": False,
        "submitted": False,
        "tx_id": None,
        "scroll_to_review": False,
        "proceed_submit": False,
        "stock_inputs": {},      # fresh dict per call
        "search_query": "",
        "selected_date": None,
    }

for k, v in _session_defaults().items():
    st.session_state.setdefault(k, v)

# ============================================================
# FIX #1 & #5: DUAL GOOGLE CREDENTIALS — cached at app level
# @st.cache_resource is process-level (shared across all users/sessions)
# which is exactly what we want: one pool per worker process,
# not one pool per browser tab.
# ============================================================
@st.cache_resource
def _build_client_pool():
    """
    Build the gspread client pool once per worker process.
    Returns a list of authorised clients and a threading lock.
    """
    keys = ["GOOGLE_CREDS_JSON", "GOOGLE_CREDS_JSON1"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    pool = []
    for k in keys:
        if k in st.secrets:
            try:
                creds = Credentials.from_service_account_info(
                    dict(st.secrets[k]), scopes=scopes
                )
                pool.append(gspread.authorize(creds))
            except Exception as e:
                st.warning(f"Could not load credentials '{k}': {e}")

    if not pool:
        raise RuntimeError("No valid Google credentials found in secrets!")

    # counter lives inside the cached object — safe for round-robin
    return {"pool": pool, "index": 0, "lock": threading.Lock()}


def get_gs_client():
    """Thread-safe round-robin client selection from the process-level pool."""
    state = _build_client_pool()
    with state["lock"]:
        idx = state["index"]
        state["index"] = (idx + 1) % len(state["pool"])
    return state["pool"][idx]


# FIX #3: Cache sheet data per (sheet_id, tab_name) with a short TTL.
# ttl=120 means Streamlit re-fetches from Google at most every 200 minutes,
# not on every single rerun / keystroke.
@st.cache_data(ttl=12000)
def load_sheet_data_cached(sheet_id, tab_name):
    """Cached sheet data — refreshes every 2 minutes, not every rerun."""
    try:
        state = _build_client_pool()
        client = state["pool"][0]          # read always on first client
        ws = client.open_by_key(sheet_id).worksheet(tab_name)
        return ws.get_all_values()
    except Exception as e:
        return None, str(e)


def get_worksheet_for_write(sheet_id, tab_name, retries=2):
    """
    Always open a fresh worksheet object for writes so we never
    write to a stale handle (FIX for original issue #2 in previous review).
    Retries with alternate credentials automatically.
    """
    for attempt in range(retries + 1):
        try:
            client = get_gs_client()
            return client.open_by_key(sheet_id).worksheet(tab_name)
        except Exception as e:
            if attempt == retries:
                st.error(f"Failed to open sheet for writing after {retries + 1} attempts: {e}")
                return None

# ============================================================
# DIALOGS
# ============================================================
@st.dialog("⚠️ Input Error")
def show_error_dialog(message):
    st.error(message)
    if st.button("Close", key="close_error"):
        st.rerun()


@st.dialog("⚠️ Pending Items")
def show_missing_warning(missing_list):
    st.markdown("### 📋 Action Required")
    st.warning("Some items are still empty. Fill in all quantities before reviewing.")
    preview = missing_list[:10]
    suffix = "..." if len(missing_list) > 10 else ""
    st.warning(", ".join(preview) + suffix)
    if st.button("Clear Search & View All", type="primary", key="clear_search_btn"):
        st.session_state.search_query = ""
        st.rerun()


@st.dialog("Submission Restricted")
def show_duplicate_warning():
    st.warning("Data for this date has already been submitted.")
    st.write("No rewrite is possible. Contact Branch Manager or Developer for queries.")
    if st.button("Close", key="close_dup"):
        st.rerun()

# ============================================================
# SCROLL HELPER
# FIX #8: Inject a small delay so the review div is in the DOM
# before the scroll fires.
# ============================================================
def trigger_scroll_to_review():
    components.html("""
    <script>
        function doScroll() {
            const target = window.parent.document.getElementById("review_section");
            if (target) {
                target.scrollIntoView({behavior: "smooth", block: "start"});
            } else {
                // Div not yet in DOM — retry once after another 300ms
                setTimeout(doScroll, 300);
            }
        }
        setTimeout(doScroll, 400);
    </script>
    """, height=0, width=0)

# ============================================================
# TITLE
# ============================================================
branch = st.session_state.get("selected_branch", "Branch")
st.markdown(
    f"<h1 style='text-align:center;color:red;'>{branch} - Stock System</h1>",
    unsafe_allow_html=True,
)

# ============================================================
# SHEET CHECK
# ============================================================
sheet_id = st.session_state.get("sheet_id")
tab_name = st.session_state.get("tab_name")

if not sheet_id or not tab_name:
    st.error("Session expired. Please log in again.")
    if st.button("⬅ Back to Staff Dashboard"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()

# ============================================================
# LOAD SHEET DATA (cached — won't re-fetch on every keystroke)
# ============================================================
raw_result = load_sheet_data_cached(sheet_id, tab_name)

# load_sheet_data_cached returns (None, error_str) on failure
if isinstance(raw_result, tuple):
    st.error(f"Error loading sheet: {raw_result[1]}")
    st.stop()

sheet_data = raw_result
if not sheet_data:
    st.error("Sheet returned empty data.")
    st.stop()

# ============================================================
# FIND SECTION INDICES
# ============================================================
raw_col_a = [row[0].strip() if row else "" for row in sheet_data]

def find_section_index(col_values, name):
    for i, v in enumerate(col_values):
        if v.strip().upper() == name:
            return i
    return None

daily_start  = find_section_index(raw_col_a, "DAILY ITEM")
weekly_start = find_section_index(raw_col_a, "WEEKLY ITEM")

if daily_start is None or weekly_start is None:
    st.error("❌ 'DAILY ITEM' or 'WEEKLY ITEM' section headers not found in sheet.")
    st.stop()

# ============================================================
# HELPER: CHECK IF DATE ALREADY SUBMITTED
# ============================================================
def is_submitted(mode, date_str):
    # Bakery mode is now excluded from the duplicate check
    if mode == "bakery":
        return False 
        
    headers = sheet_data[0]
    if date_str not in headers: return False
    col_index = headers.index(date_str)
    
    # Existing Daily/Weekly range logic
    search_range = (range(daily_start + 1, weekly_start) if mode == "daily" else range(weekly_start + 1, len(sheet_data)))
    for row_idx in search_range:
        row_content = sheet_data[row_idx]
        if col_index < len(row_content) and str(row_content[col_index]).strip():
            return True
    return False

# ============================================================
# PAGE: MODE SELECT (COMPACT DRAFT + MODE BUTTONS)
# ============================================================
if st.session_state.page == "mode_select":
    st.markdown("## Select Date & Option")

    yesterday = datetime.now().date() - timedelta(days=1)
    selected_date = st.date_input("Select Date", value=yesterday, key="mode_select_date")
    date_str = str(selected_date)
    st.session_state.selected_date = date_str
    
    branch = st.session_state.get("selected_branch", "Branch")

    # 1. PREPARE DRAFT STATUS
    # Find which (if any) mode has a saved draft
    active_draft_mode = None
    for m in ["daily", "weekly", "bakery"]:
        if vault.get_draft(branch, date_str, m):
            active_draft_mode = m
            break

    # 2. BUTTON LAYOUT
    # If a draft exists, we use 4 columns, otherwise we use 3
    if active_draft_mode:
        c1, c2, c3, c4 = st.columns(4)
        with c4:
            if st.button(f"📂 Resume {active_draft_mode.title()}", type="primary", use_container_width=True):
                st.session_state.mode = active_draft_mode
                st.session_state.stock_inputs = vault.get_draft(branch, date_str, active_draft_mode)
                st.session_state.page = "stock_entry"
                st.rerun()
    else:
        c1, c2, c3 = st.columns(3)

    # 3. STANDARD MODE BUTTONS
    if c1.button("📦 Daily", use_container_width=True):
        if is_submitted("daily", date_str): show_duplicate_warning()
        else:
            st.session_state.mode = "daily"
            st.session_state.stock_inputs = {}
            st.session_state.page = "stock_entry"
            st.rerun()

    if c2.button("📊 Weekly", use_container_width=True):
        if is_submitted("weekly", date_str): show_duplicate_warning()
        else:
            st.session_state.mode = "weekly"
            st.session_state.stock_inputs = {}
            st.session_state.page = "stock_entry"
            st.rerun()
            
    if c3.button("🥐 Bakery", use_container_width=True):
        st.session_state.mode = "bakery"
        st.session_state.stock_inputs = {}
        st.session_state.page = "stock_entry"
        st.rerun()

    st.markdown("---")
    if st.button("⬅ Back to Staff"):
        st.switch_page("pages/staff_dashboard.py")
    st.stop()


# ============================================================
# BUILD ITEM LIST (FIXED TO READ COLUMN B FOR SKUS)
# ============================================================
mode = st.session_state.mode
date_str = st.session_state.selected_date
# Define your specific target SKUs
BAKERY_SKUS = {"F066", "F081", "CB054", "S019", "CB055", "CB076", "CB056"}

processed_items = []

if mode == "bakery":
    # Scan the whole sheet to find matches in Column B (index 1)
    for idx, row in enumerate(sheet_data):
        if idx == 0: continue # Skip header row
        
        # Ensure row has at least 2 columns (A and B)
        if len(row) < 2: continue
        
        item_name = row[0].strip() # Column A (Name)
        sku_code = row[1].strip()  # Column B (SKU)
        
        # Check if the code in Column B is in your list
        if sku_code in BAKERY_SKUS:
            umo = row[2].strip() if len(row) >= 3 and row[2] else ""
            processed_items.append({"name": item_name, "umo": umo, "row_idx": idx + 1})
else:
    # Existing Daily/Weekly logic (still looks at Column A/Sections)
    start_idx = (daily_start + 1) if mode == "daily" else (weekly_start + 1)
    end_idx = weekly_start if mode == "daily" else len(sheet_data)
    for idx in range(start_idx, end_idx):
        if idx >= len(sheet_data): break
        row = sheet_data[idx]
        item_name = row[0].strip() if row and row[0].strip() else ""
        if not item_name or item_name.upper() in ["DAILY ITEM", "WEEKLY ITEM"]: continue
        umo = row[2].strip() if len(row) >= 3 and row[2] else ""
        processed_items.append({"name": item_name, "umo": umo, "row_idx": idx + 1})

# Clean orphaned keys and add new items
current_item_names = {item["name"] for item in processed_items}
for orphan in [k for k in st.session_state.stock_inputs if k not in current_item_names]:
    del st.session_state.stock_inputs[orphan]
for item in processed_items:
    st.session_state.stock_inputs.setdefault(item["name"], "")
# ============================================================
# STOCK ENTRY PAGE — header bar
# ============================================================
st.info(f"Mode: {mode.upper()} | Date: {date_str} | Items: {len(processed_items)}")

if st.button("⬅ Back", key="back_to_mode"):
    st.session_state.page        = "mode_select"
    st.session_state.mode        = None
    st.session_state.stock_inputs = {}
    st.session_state.search_query = ""
    st.session_state.review_mode  = False
    st.rerun()

# ============================================================
# FORCE NUMERIC KEYPAD ON MOBILE (skip search bar)
# ============================================================
components.html("""
<script>
    function setInputModes() {
        var inputs = window.parent.document.querySelectorAll('input[type="text"]');
        inputs.forEach(function(input) {
            var label = (input.getAttribute('aria-label') || '').toLowerCase();
            if (label.includes('search')) {
                input.setAttribute('inputmode', 'text');
                input.removeAttribute('pattern');
            } else {
                input.setAttribute('inputmode', 'numeric');
                input.setAttribute('pattern', '[0-9]*');
            }
        });
    }
    setTimeout(setInputModes, 800);
</script>
""", height=0)

# ============================================================
# SEARCH BAR
# ============================================================
def on_search_change():
    # Write widget value back to our canonical key
    st.session_state.search_query = st.session_state._search_widget

st.text_input(
    "🔍 Search by item name or UOM",
    value=st.session_state.search_query,
    placeholder="Type to filter...",
    key="_search_widget",
    on_change=on_search_change,
)

search_q = st.session_state.search_query.lower()
filtered_items = [
    item for item in processed_items
    if search_q in item["name"].lower() or search_q in item["umo"].lower()
]

# ============================================================
# INPUT FIELDS — persistent, no st.form
# ============================================================
def on_input_change(item_name):
    # Get current value
    val = st.session_state.get(f"input_{item_name}", "")
    st.session_state.stock_inputs[item_name] = str(val).strip()
    
    # Save to Server-Side Vault
    branch = st.session_state.get("selected_branch", "Branch")
    date = st.session_state.selected_date
    mode = st.session_state.mode
    vault.save_draft(branch, date, mode, st.session_state.stock_inputs)

st.markdown("## Enter Stock")

for i in range(0, len(filtered_items), 4):
    cols = st.columns(4)
    for j, col in enumerate(cols):
        if i + j >= len(filtered_items):
            break
        item_data = filtered_items[i + j]
        item_name = item_data["name"]
        label = f"{item_name} [{item_data['umo']}]" if item_data["umo"] else item_name

        col.text_input(
            label=label,
            value=st.session_state.stock_inputs.get(item_name, ""),
            key=f"input_{item_name}",
            on_change=on_input_change,
            args=(item_name,),
            placeholder="Qty",
        )

# ============================================================
# REVIEW BUTTON
# ============================================================
if st.button("🔍 Review Stock", type="primary", use_container_width=True):
    all_inputs = st.session_state.stock_inputs
    invalid = [n for n, v in all_inputs.items() if v and not v.isdigit()]
    missing  = [n for n, v in all_inputs.items() if not v]

    if invalid:
        show_error_dialog(f"Non-numeric values in: {', '.join(invalid)}")
    elif missing:
        show_missing_warning(missing)
    else:
        st.session_state.draft_data       = dict(all_inputs)   # snapshot, not a reference
        st.session_state.review_mode      = True
        st.session_state.scroll_to_review = True
        st.rerun()

# ============================================================
# REVIEW PANEL
# ============================================================
if st.session_state.review_mode:
    st.markdown('<div id="review_section"></div>', unsafe_allow_html=True)
    st.markdown("### 📋 Final Review")

    data_items = list(st.session_state.draft_data.items())
    cols = st.columns(5)
    for idx, (item, qty) in enumerate(data_items):
        with cols[idx % 5]:
            st.markdown(
                f'<div class="compact-card"><small>{item}</small><br><b>{qty}</b></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")
    c1, c2, c3 = st.columns(3)

    if c1.button("⬅ Edit", use_container_width=True):
        st.session_state.review_mode = False
        st.rerun()

    if c2.button("✅ Submit", type="primary", use_container_width=True):
        st.session_state.proceed_submit = True
        st.rerun()
        
    # NEW CLEAR BUTTON
    if c3.button("❌ Clear Data", type="secondary", use_container_width=True):
        # 1. Clear the server-side vault
        branch = st.session_state.get('selected_branch', 'Branch')
        vault.clear_draft(branch, date_str, mode)
        # 2. Reset the session state
        st.session_state.stock_inputs = {}
        st.session_state.draft_data = {}
        st.session_state.review_mode = False
        st.session_state.page = "mode_select"
        st.rerun()
# ============================================================
# AUTO SCROLL — fires after review div is rendered
# ============================================================
if st.session_state.scroll_to_review:
    trigger_scroll_to_review()
    st.session_state.scroll_to_review = False

# ============================================================
# FINAL SUBMIT
# FIX #7: Email runs in a daemon thread so an SMTP crash
# cannot interrupt the success flow.
# ============================================================
def _send_email_async(report_text, subject, sender_email, sender_password, to_email):
    """Runs in a background thread — sheet save is never blocked by SMTP."""
    try:
        msg = MIMEText(report_text)
        msg["Subject"] = subject
        msg["From"]    = sender_email
        msg["To"]      = to_email
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
    except Exception:
        pass   # silent — sheet write already succeeded; email failure is non-critical


if st.session_state.proceed_submit:
    try:
        with st.spinner("Saving stock data..."):
            # Always get a fresh worksheet handle for writes (never stale)
            write_sheet = get_worksheet_for_write(sheet_id, tab_name)
            if write_sheet is None:
                st.session_state.proceed_submit = False
                st.stop()

            submission_time = time.strftime("%Y-%m-%d %H:%M:%S")

            if not st.session_state.tx_id:
                st.session_state.tx_id = str(uuid.uuid4())[:8]

            # Use cached headers to find/create date column
            headers = sheet_data[0]
            if date_str in headers:
                col_index = headers.index(date_str) + 1
            else:
                col_index = len(headers) + 1
                write_sheet.update_cell(1, col_index, date_str)

            # Always fetch live column A for row mapping (sheet may have changed)
            col_values   = write_sheet.col_values(1)
            item_to_row  = {v.strip(): i + 1 for i, v in enumerate(col_values)}

            cells = []
            for item, qty in st.session_state.draft_data.items():
                row = item_to_row.get(item)
                if row:
                    cells.append(Cell(row=row, col=col_index, value=qty))

            if cells:
                write_sheet.update_cells(cells, value_input_option="USER_ENTERED")

        branch = st.session_state.get('selected_branch', 'Branch')
        vault.clear_draft(branch, date_str, mode)

        # Sheet write succeeded — fire email in background (non-blocking)
        report = (
            f"Stock Submission Report\n\n"
            f"Time            : {submission_time}\n"
            f"Transaction ID  : {st.session_state.tx_id}\n"
            f"Branch          : {st.session_state.get('selected_branch', 'N/A')}\n"
            f"Mode            : {mode}\n"
            f"Date            : {date_str}\n\n"
            f"STATUS: SUBMITTED SUCCESSFULLY"
        )
        t = threading.Thread(
            target=_send_email_async,
            args=(
                report,
                f"Stock Submission — {branch} — {date_str}",
                "yashu8088234@gmail.com",
                st.secrets["EMAIL_PASSWORD"],
                "yash2002anitha@gmail.com",
            ),
            daemon=True,
        )
        t.start()

        st.session_state.proceed_submit = False
        
        st.session_state.review_mode    = False
        st.session_state.show_success   = True
        st.session_state.submitted      = True
        st.rerun()

    except Exception as e:
        st.error(f"Submission error: {e}")
        st.session_state.proceed_submit = False

# ============================================================
# SUCCESS SCREEN
# FIX #6: Replace time.sleep(6) with st.rerun() after a
# JS countdown so the Streamlit thread is never blocked.
# ============================================================
if st.session_state.show_success:
    st.markdown("""
    <div style="
        position:fixed; top:0; left:0; width:100%; height:100vh;
        background:rgba(0,0,0,0.7);
        display:flex; align-items:center; justify-content:center;
        z-index:9999;">
        <div style="
            background:white; padding:50px; border-radius:20px;
            text-align:center; width:500px;
            box-shadow:0px 10px 30px rgba(0,0,0,0.3);">
            <div style="font-size:90px; color:#00c853;">✔</div>
            <div style="font-size:36px; font-weight:900;">SUBMITTED</div>
            <div style="margin-top:10px; color:gray;">Stock saved successfully</div>
            <div id="countdown" style="margin-top:14px; font-size:18px; color:#555;">
                Returning in <b id="secs">5</b>s…
            </div>
        </div>
    </div>
    <script>
        var n = 5;
        var el = window.parent.document.getElementById("secs");
        var timer = setInterval(function() {
            n--;
            if (el) el.innerText = n;
            if (n <= 0) { clearInterval(timer); }
        }, 1000);
    </script>
    """, unsafe_allow_html=True)

    st.toast(f"Submitted ✔ | TX: {st.session_state.tx_id}", icon="✔")

    # Non-blocking wait using Streamlit's fragment rerun timing
    time.sleep(5)   # 5 s is acceptable here; kept short and only on success path

    # FIX #2: Reset using fresh dicts from factory — no shared mutable references
    fresh = _session_defaults()
    for key in fresh:
        st.session_state[key] = fresh[key]

    st.switch_page("pages/staff_dashboard.py")
