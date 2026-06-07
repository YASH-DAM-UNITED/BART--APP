import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
import time
import hashlib
import io
import plotly.express as px



import hashlib

def verify_manager_password(manager_name, password_input):
    # 1. Get the dictionary of all passwords
    all_passwords = st.secrets.get("MANAGER_PASSWORDS", {})
    
    # 2. Get the specific hash for the selected manager
    stored_hash = all_passwords.get(manager_name)
    
    # 3. If manager doesn't exist in secrets, fail safe
    if not stored_hash:
        return False
        
    # 4. Hash the input and compare
    input_hash = hashlib.sha256(password_input.encode()).hexdigest()
    return input_hash == stored_hash



# Initialize the state if it doesn't exist
if "show_manager" not in st.session_state:
    st.session_state.show_manager = False



@st.cache_data(ttl=3600)
def load_manager_mapping():
    # Connect to your new sheet
    sheet = client.open_by_key("1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0").worksheet("Sheet1")
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def get_filtered_branches(manager_name, full_branch_list, mapping_df):
    # Filter the mapping sheet for the selected manager
    managed_branches = mapping_df[mapping_df['AreaManager'] == manager_name]['BranchName'].tolist()
    # Filter your actual branch list by these names
    return [b for b in full_branch_list if b['BranchName'] in managed_branches]
# The "Toggle" function to change the state
def toggle_manager():
    st.session_state.show_manager = not st.session_state.show_manager







# ========================================================
# PAGE CONFIG
# ========================================================

st.set_page_config(
    
    page_title="Management Panel",
    layout="wide",
    
    initial_sidebar_state="collapsed"
)

st.title("📦 BART - Stock Management (All Branches)")


st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            display: none !important;
        }
        [data-testid="collapsedControl"] {
            display: none !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)







# ========================================================
# GOOGLE AUTH
# ========================================================

creds_dict = st.secrets["GOOGLE_CREDS_JSON"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_client():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        creds_dict,
        scope
    )
    return gspread.authorize(creds)

client = get_client()





# Definition now expects TWO arguments: report_data and date_str
def get_professional_report(report_data, date_str):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        summary_ws = workbook.add_worksheet("Dashboard Summary")
        summary_ws.hide_gridlines(2)
        title_fmt = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': '#2C3E50'})
        summary_ws.write('B2', 'BART Inventory Executive Report', title_fmt)
        
        # This will now work because date_str is provided as an argument
        summary_ws.write('B4', f'Generated Date: {date_str}')
        
        for sheet_name, df in report_data.items():
            # Drop the artifact column if it exists to keep your Excel clean
            if '::auto_unique_id::' in df.columns:
                df = df.drop(columns=['::auto_unique_id::'])
                
            safe_name = "".join([c for c in sheet_name if c.isalnum() or c in (' ', '_')])[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
            # ... [rest of your styling logic] ...
            
    return output.getvalue()

def to_excel_bytes(data_frames):
    """
    Converts a dictionary of {sheet_name: dataframe} into Excel bytes.
    """
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in data_frames.items():
            if '::auto_unique_id::' in df.columns:
                df = df.drop(columns=['::auto_unique_id::'])
            # Ensure sheet name is valid for Excel (max 31 chars)
            safe_name = "".join([c for c in sheet_name if c.isalnum() or c in (' ', '_')])[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
            
            # Optional: Add formatting here if you want consistency
            worksheet = writer.sheets[safe_name]
            worksheet.hide_gridlines(2)
            
    return output.getvalue()
# ========================================================
# LOAD BRANCHES
# ========================================================

@st.cache_data(ttl=None)
def load_branches():
    sheet = client.open("MASTERBRANCHSHEET").sheet1
    data = sheet.get_all_records()

    branches = []

    for b in data:
        if b.get("SheetID") and b.get("BranchName"):
            branches.append({
                "BranchName": str(b["BranchName"]).strip(),
                "SheetID": str(b["SheetID"]).strip()
            })

    return branches

branches = load_branches()
branch_names = [b["BranchName"] for b in branches]

# ========================================================
# RESTORED CATEGORY SETS (MATCHED TO PDF WITH '-')
# ========================================================

FOOD_SKUS = {
    "-", "B034", "F066", "B032", "B029", "F081", "B019", "B018", "CF007", 
    "CF006", "F148", "B028", "K072", "K176", "CB036", "K265", "B016", 
    "CB078", "K154", "CB054", "K226", "CB074", "M&M", "B014", "K242", 
    "S019", "B006", "CB055", "B017", "CB076", "CB056", "B026", "CB037", 
    "K087", "CB043", "CB009", "CB043", "K063"
}

DRY_SKUS = {
    "C013", "IC013", "P244", "P245", "P254", "P095", "P296", "P343", 
    "P343(1)", "P012", "P091", "P155", "P081", "P253", "P101", "P218", 
    "P132", "P264", "P219", "P338", "P341", "P342", "P210", "P320", 
    "P322", "P321", "P082", "P318", "P208", "P315", "C014", "F070", 
    "P298", "P178", "CB009", "C015", "CF009", "P145", "P133", "P156", 
    "RS002", "C011", "C012", "P189", "P160", "C005", "P157", "C010", 
    "C007", "CB010", "P161", "P039", "P125", "C045", "RS001", "P084", 
    "P163", "P162", "C016", "C017", "P158", "C048", "P083"
}

MISC_SKUS = {
    "K063", "T063", "T060", "T066", "TOY1", "ΤΟΥ1", "T026", "SVP", 
    "F089", "P130"
}

# ========================================================
# CACHE
# ========================================================

branch_cache = {}

# ========================================================
# FETCH BRANCH
# ========================================================

def fetch_branch(branch):
    name = branch["BranchName"]
    try:
        ws = client.open_by_key(branch["SheetID"]).worksheet("Stocks")
        data = ws.get_all_values()
        branch_cache[name] = data
        return name, data
    except Exception:
        return name, branch_cache.get(name, [])

# ========================================================
# LOAD ALL DATA (WITH RETRY SYSTEM)
# ========================================================

MAX_RETRIES = 10
RETRY_DELAY = 60

@st.cache_data(ttl=None)
def load_all_data(branches):
    completed = {}
    failed = []

    progress = st.progress(0)
    status = st.empty()

    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(fetch_branch, b): b for b in branches}
        done = 0

        for f in as_completed(futures):
            name, data = f.result()
            if data:
                completed[name] = data
            else:
                failed.append(futures[f])
            done += 1
            progress.progress(done / len(branches))

    round_no = 1
    while failed and round_no <= MAX_RETRIES:
        failed_names = [b["BranchName"] for b in failed]

        with status.container():
            st.info(
                f"Retry {round_no}/{MAX_RETRIES} → "
                f"{', '.join(failed_names)}"
            )

        time.sleep(RETRY_DELAY)
        new_failed = []

        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {ex.submit(fetch_branch, b): b for b in failed}
            for f in as_completed(futures):
                name, data = f.result()
                if data:
                    completed[name] = data
                else:
                    new_failed.append(futures[f])

        failed = new_failed
        round_no += 1

    if failed:
        status.warning("Some branches still failed after retries")
    else:
        status.success("All branches loaded successfully")
        time.sleep(0.5)
        status.empty()

    return [
        (b["BranchName"], completed.get(b["BranchName"], []))
        for b in branches
    ]

# ========================================================
# REFRESH / NAVIGATION
# ========================================================
col1, col2,  col3 = st.columns(3)

if col1.button(" 🔄 Refresh Data"):
    st.cache_data.clear()
    st.cache_resource.clear()
    branch_cache.clear()
    st.rerun()

if col2.button("👥 Staff Alignment"):
    st.switch_page("pages/staff_alignment.py")



if col3.button("⬅ LOGOUT "):
    st.switch_page("app.py")

# ========================================================
# THE "EXIT" GATE
# ========================================================
# ========================================================
# Your 1000 lines of code start here...
# No indentation changes needed!
# ========================================================
        
# ========================================================
# DATE
# ========================================================

selected_date = st.date_input("📅 Select Date")
selected_date_str = selected_date.strftime("%Y-%m-%d")





# ========================================================
# PROCESS STOCK
# ========================================================

@st.cache_data(ttl=None)
def process_stock(all_data, selected_date_str, branch_names):
    daily = {}
    weekly = {}

    for branch_name, raw in all_data:
        if not raw or len(raw) < 2:
            continue

        # Strip spaces and cast to clean strings to prevent breaking matching logic
        headers = [str(x).strip() for x in raw[0]]

        date_index = None
        for i, h in enumerate(headers):
            if h == selected_date_str:
                date_index = i
                break

        mode = None

        for row in raw:
            if not row:
                continue

            text = " ".join(str(x) for x in row).lower()

            if "daily item" in text:
                mode = "daily"
                continue

            if "weekly item" in text:
                mode = "weekly"
                continue

            if not mode:
                continue

            # Heavy structural cleaning to catch spaces or control characters from cells
            item = str(row[0]).strip() if len(row) > 0 else ""
            sku = str(row[1]).replace(" ", "").strip() if len(row) > 1 else ""
            uom = str(row[2]).strip() if len(row) > 2 else ""

            if not item:
                continue

            key = f"{item}_{sku}_{uom}"
            target = daily if mode == "daily" else weekly

            if key not in target:
                target[key] = {
                    "Item Name": item,
                    "SKU": sku,
                    "UOM": uom
                }
                for b in branch_names:
                    target[key][b] = 0

            qty = 0
            try:
                if date_index is not None and len(row) > date_index:
                    val = str(row[date_index]).strip()
                    qty = 0 if val in ["", None, "-", "None"] else float(val)
            except:
                qty = 0

            target[key][branch_name] = qty

    return daily, weekly

# ========================================================
# BUILD DF
# ========================================================

def build_df(data_dict, branch_names):
    rows = []
    for _, v in data_dict.items():
        row = {
            "Item Name": v["Item Name"],
            "SKU": v["SKU"],
            "UOM": v["UOM"]
        }
        for b in branch_names:
            row[b] = v.get(b, 0)

        row["Total"] = sum(row[b] for b in branch_names)
        rows.append(row)
    return pd.DataFrame(rows)

# ========================================================
# CATEGORY LOGIC (FIXED LOGIC PIPELINE)
# ========================================================

def normalize_sku(value):
    return str(value).replace(" ", "").strip().upper()

def detect_category(sku):
    s = normalize_sku(sku)
    
    # Check explicitly missing or divider values first
    if not s or s == "-" or s == "NONE" or s == "NAN":
        return "FOOD ITEMS"
        
    # 1. Clean strict exact match lookup
    if s in FOOD_SKUS:
        return "FOOD ITEMS"
    if s in DRY_SKUS:
        return "DRY ITEMS"
    if s in MISC_SKUS:
        return "MISC ITEMS"
        
    # 2. Smart Fallback Patterns (Catching prefixes safely)
    if s.startswith(('B', 'F', 'K', 'CB', 'CF', 'S')):
        return "FOOD ITEMS"
    if s.startswith(('C', 'P', 'IC', 'RS')):
        return "DRY ITEMS"
    if s.startswith(('T', 'SVP', 'TOY', 'ΤΟΥ')):
        return "MISC ITEMS"
        
    # 3. Dynamic Uncategorized Safety bucket
    return "UNCATEGORIZED DETECTED"

def build_category_dfs(df):
    cats = {
        "FOOD ITEMS": pd.DataFrame(columns=df.columns),
        "DRY ITEMS": pd.DataFrame(columns=df.columns),
        "MISC ITEMS": pd.DataFrame(columns=df.columns),
        "UNCATEGORIZED DETECTED": pd.DataFrame(columns=df.columns)
    }
    
    if df.empty:
        return cats

    category_series = df["SKU"].apply(detect_category)
    
    for cat_name in list(cats.keys()):
        sub_df = df[category_series == cat_name]
        cats[cat_name] = sub_df.sort_values(by="Item Name", key=lambda col: col.str.lower())
        
    if cats["UNCATEGORIZED DETECTED"].empty:
        del cats["UNCATEGORIZED DETECTED"]
        
    return cats

# ========================================================
# SAFE CRYPTO KEY (FIXES VISUAL FLIP-FLOP & TAB RE-RENDER BUG)
# ========================================================

def stable_key(prefix, name, df=None):
    """
    Generates a truly reactive unique component state signature key.
    Including the dataframe dimensions ensures AgGrid completely forces a cache-rebuild 
    whenever changing tabs or picking dates.
    """
    shape_str = f"_{df.shape[0]}x{df.shape[1]}" if df is not None else ""
    raw_str = f"{prefix}_{name}{shape_str}"
    return prefix + "_" + hashlib.md5(raw_str.encode()).hexdigest()

# ========================================================
# AGGRID (UNMODIFIED ROW DESIGN - STABLE BINDING)
# ========================================================

def make_grid(df, key):
    gb = GridOptionsBuilder.from_dataframe(df)

    gb.configure_default_column(
        resizable=True,
        sortable=True,
        filter=True,
        editable=False,
        wrapText=False,
        autoHeight=False,
        cellStyle={
            "display": "flex",
            "alignItems": "center",
            "fontSize": "13px",
            "paddingTop": "0px",
            "paddingBottom": "0px"
        }
    )

    gb.configure_column(
        "Item Name",
        pinned="left",
        lockPinned=True,
        width=250, minWidth=250, maxWidth=350,
    )

    gb.configure_column(
        "SKU",
        pinned="left",
        lockPinned=True,
        width=100, minWidth=100, maxWidth=350,
    )

    gb.configure_column(
        "UOM",
        pinned="left",
        lockPinned=True,
        width=100, minWidth=100, maxWidth=350,
    )

    for b in branch_names:
        gb.configure_column(
            b,
            type=["numericColumn"],
            wrapText=False,
            width=120, minWidth=120, maxWidth=350,
            autoHeight=False,
            cellStyle={
                "textAlign": "center",
                "display": "flex",
                "alignItems": "center",
                "justifyContent": "center",
                "fontSize": "13px",
                "paddingTop": "0px",
                "paddingBottom": "0px"
            }
        )



    if "Total" in df.columns:
        gb.configure_column(
            "Total",
            type=["numericColumn"],
            pinned="right",  # Pin to the right so it's always visible
            minWidth=100,
            cellStyle={
                "textAlign": "center",
                "fontWeight": "bold",
                "backgroundColor": "#f8f9fa" # Optional: light gray background
            }
        )

    gb.configure_grid_options(
        headerHeight=38,
        rowHeight=32,
        suppressHorizontalScroll=False,
        alwaysShowHorizontalScroll=True,
        alwaysShowVerticalScroll=True
    )

    time.sleep(0.0003)

    AgGrid(
        df,
        gridOptions=gb.build(),
        custom_css={
            ".ag-header-cell-label": {
                "justify-content": "center",
                "font-size": "12px",
                "font-weight": "600"
            },
            ".ag-header-cell": {
                "padding-top": "0px",
                "padding-bottom": "0px"
            },
            ".ag-cell": {
                "padding-top": "0px",
                "padding-bottom": "0px"
            }
        },
        theme="streamlit",
        fit_columns_on_grid_load=False,
        enable_enterprise_modules=False,
        update_mode=GridUpdateMode.NO_UPDATE,
        allow_unsafe_jscode=True,
        reload_data=True,
        height=500,
        width="100%",
        key=key
    )




# ========================================================
# PIPELINE RUN
# ========================================================

all_data = load_all_data(branches)

daily_items, weekly_items = process_stock(
    all_data,
    selected_date_str,
    branch_names
)

daily_df = build_df(daily_items, branch_names)
weekly_df = build_df(weekly_items, branch_names)


# 2. GATEKEEPER LOGIC
if "user_role" not in st.session_state:
    st.switch_page("app.py")
# ========================================================
# AREA MANAGER RESTRICTED VIEW (AUTHENTICATED)
# ========================================================
# ========================================================
# AREA MANAGER RESTRICTED VIEW (AUTHENTICATED)
# ========================================================
if st.session_state.user_role == "area_manager":
    st.subheader("🔑 Area Manager Restricted Access")
    
    mapping_df = load_manager_mapping()
    # Normalize names: strip whitespace, handle irregular spacing
    unique_managers = sorted([str(m).strip() for m in mapping_df['AreaManager'].unique() if m])
    
    selected_manager = st.selectbox("👤 Select Area Manager", options=["Select..."] + unique_managers)

    # 1. Reset Auth if user switches Manager
    if "last_mgr" not in st.session_state:
        st.session_state.last_mgr = None
    
    if selected_manager != st.session_state.last_mgr:
        st.session_state.mgr_authenticated = False
        st.session_state.last_mgr = selected_manager

    # 2. Password Validation
    if selected_manager != "Select...":
        if not st.session_state.get("mgr_authenticated", False):
            password = st.text_input(f"Enter password for {selected_manager}", type="password")
            if st.button("🔓 Login"):
                # Clean the name: Remove hidden chars/extra spaces, force uppercase
                clean_name = " ".join(selected_manager.upper().split())
                # Format into the expected secret key: e.g., MANAGER_HARRY_CAMPANO
                secret_key = f"MANAGER_{clean_name.replace(' ', '_')}"
                
                stored_password = st.secrets.get(secret_key)
                
                # Check for password match
                if stored_password and password.strip() == stored_password:
                    st.session_state.mgr_authenticated = True
                    st.rerun()
                else:
                    st.error(f"Invalid password for {selected_manager}.")
                    # Use this for debugging if it still fails:
                    # st.info(f"System is checking secret key: {secret_key}")
        
        # 3. Render Data ONLY if Authenticated
        if st.session_state.get("mgr_authenticated", False):
            assigned_branch_names = mapping_df[mapping_df['AreaManager'].str.strip() == selected_manager.strip()]['BranchName'].tolist()
            manager_all_data = [item for item in all_data if item[0].strip() in [b.strip() for b in assigned_branch_names]]
            
            if not manager_all_data:
                st.warning(f"No data found for branches managed by {selected_manager}.")
            else:
                st.success(f"Authenticated as {selected_manager}")
                m_daily, m_weekly = process_stock(manager_all_data, selected_date_str, assigned_branch_names)
                
                st.write("### 📦 Manager Daily Items")
                make_grid(build_df(m_daily, assigned_branch_names), "mgr_daily_grid")
                
                st.write("### 📦 Manager Weekly Items")
                make_grid(build_df(m_weekly, assigned_branch_names), "mgr_weekly_grid")

    st.stop()

# ========================================================
# AREA MANAGER PORTAL (USING PRE-FETCHED DATA)
# ========================================================
if st.session_state.get("show_manager", False):
    st.divider()
    st.subheader("🔑 Area Manager Portal")
    
    mapping_df = load_manager_mapping()
    unique_managers = sorted([str(m) for m in mapping_df['AreaManager'].unique() if m])
    selected_manager = st.selectbox("👤 Select Area Manager", options=["Select..."] + unique_managers)


    if st.button("⬅ Back to Main Dashboard"):
        st.session_state.show_manager = False
        st.rerun()
    
    if selected_manager != "Select...":
        # 1. Get the list of Branch Names assigned to this manager
        # (This uses the mapping sheet we already loaded)
        assigned_branch_names = mapping_df[mapping_df['AreaManager'].str.strip() == selected_manager.strip()]['BranchName'].tolist()
        
        # 2. Filter the ALREADY LOADED 'all_data' variable
        # 'all_data' is a list of tuples: (BranchName, raw_data)
        manager_all_data = [item for item in all_data if item[0].strip() in [b.strip() for b in assigned_branch_names]]
        
        if not manager_all_data:
            st.warning(f"No data found for branches managed by {selected_manager}.")
        else:
            st.info(f"Viewing {len(manager_all_data)} branches managed by: {selected_manager}")
            
            # 3. Process the filtered data (Instant, no re-fetch)
            m_daily, m_weekly = process_stock(manager_all_data, selected_date_str, assigned_branch_names)
            
            m_daily_df = build_df(m_daily, assigned_branch_names)
            m_weekly_df = build_df(m_weekly, assigned_branch_names)
            
            # 4. Display
            st.write("### 📦 Manager Daily Items")
            make_grid(m_daily_df, "mgr_daily_grid")
            
            st.write("### 📦 Manager Weekly Items")
            make_grid(m_weekly_df, "mgr_weekly_grid")

    
    st.stop()




# ========================================================
# GLOBAL GOOGLE-STYLE INVENTORY SEARCH (UPDATED)
# ========================================================

st.subheader("🔍 Global Inventory Search")

# 1. Ensure both DataFrames have the "Total" column
# (The build_df function already adds "Total", so this just ensures it's carried over)
pool_daily = daily_df.copy()
pool_daily["Schedule"] = "Daily"

pool_weekly = weekly_df.copy()
pool_weekly["Schedule"] = "Weekly"

search_pool = pd.concat([pool_daily, pool_weekly], ignore_index=True)

if not search_pool.empty:
    # 2. Create clean, searchable labels
    search_pool["Search_Label"] = (
        search_pool["SKU"].astype(str) + " | " + 
        search_pool["Item Name"].astype(str) + " (" + 
        search_pool["UOM"].astype(str) + ") [" + 
        search_pool["Schedule"] + "]"
    )
    
    search_options = sorted(search_pool["Search_Label"].unique())
    
    selected_option = st.selectbox(
        "Type an Item Name, SKU, or UOM to inspect branch stock...",
        options=search_options,
        index=None,
        placeholder="🔍 Start typing to search across all branches...",
        key=f"global_search_bar_{selected_date_str}"
    )
    
    if selected_option:
        matched_row = search_pool[search_pool["Search_Label"] == selected_option]
        
        if not matched_row.empty:
            st.markdown("---")
            st.success(f"📌 **Selected Product:** {selected_option}")
            
            # Include "Total" in the display columns list
            display_cols = ["Item Name", "SKU", "UOM"] + branch_names + ["Total"]
            result_df = matched_row[display_cols].reset_index(drop=True)
            
            search_grid_key = f"search_result_grid_{selected_date_str}_{hashlib.md5(selected_option.encode()).hexdigest()}"
            
            with st.container():
                # make_grid will now automatically see "Total" and apply the pinning logic
                make_grid(result_df, search_grid_key)
                
                # Excel export remains the same
                excel_data = to_excel_bytes({selected_option[:20]: result_df})
                st.download_button(
                    label="📥 Export Selected Item",
                    data=excel_data,
                    file_name=f"Report_{selected_date_str}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            st.markdown("---")
            
else:
    st.info("No stock data available to search for this date.")
# ========================================================
# CATEGORY VIEW (COMBINED & BULLETPROOF SKU MATCHING)
# ========================================================
st.subheader("📊 Category Wise Stock Overview")

# 1. Prepare data
combined_stock = pd.concat([daily_df, weekly_df], ignore_index=True)
combined_stock = combined_stock.drop_duplicates(subset=["Item Name", "SKU", "UOM"])
combined_stock["SKU_CLEAN"] = combined_stock["SKU"].astype(str).str.replace(" ", "").str.upper()
category_dfs = build_category_dfs(combined_stock)

# 2. Create the Radio "Tabs"
# We define the labels for the UI
tab_labels = [f"📂 {cat} ({len(sub_df)})" for cat, sub_df in category_dfs.items()]

# The radio component
selected_tab = st.radio(
    "Category Selector",
    options=tab_labels,
    index=0,
    horizontal=True,
    label_visibility="collapsed",
    key="cat_radio_tabs"
)

# 3. Map back to the dataframe key
# Find which category matches the selected label
active_cat = next(cat for cat in category_dfs if f"📂 {cat}" in selected_tab)
sub_df = category_dfs[active_cat]

# 4. Render only the active Grid
if not sub_df.empty:
    grid_key = f"ag_grid_radio_{active_cat}_{selected_date_str}"
    make_grid(sub_df.drop(columns=["SKU_CLEAN"], errors="ignore"), grid_key)
else:
    st.info(f"No items found in {active_cat}")

# 5. CSS to transform Radio Buttons into Tabs
st.markdown("""
    <style>
    /* Hide the radio circles */
    div[role="radiogroup"] > label > div:first-of-type {
        display: none;
    }
    /* Flex the radio group to look like a tab row */
    div[role="radiogroup"] {
        display: flex;
        gap: 0px;
        border-bottom: 2px solid #ddd;
    }
    /* Style the labels as tabs */
    div[role="radiogroup"] > label {
        padding: 10px 20px;
        margin: 0 !important;
        cursor: pointer;
        font-weight: 600;
        background-color: transparent !important;
        border-radius: 0 !important;
        border-bottom: 3px solid transparent;
        color: #555;
    }
    /* Style the active tab */
    div[role="radiogroup"] > label:has(input:checked) {
        border-bottom: 3px solid #ff4b4b !important;
        color: #ff4b4b !important;
    }
    </style>
""", unsafe_allow_html=True)
# ========================================================
# MAIN TABLES
# ========================================================

def render(df, title):
    st.subheader(title)
    if df.empty:
        st.warning("No Data")
        return
    render_key = stable_key("grid", title, df=df)
    make_grid(df, render_key)

render(daily_df, "📦 Daily Items Stock")
render(weekly_df, "📦 Weekly Items Stock")


  
st.markdown("---")
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📊 Inventory Insights")
    st.caption("Exports all categories into a professionally styled Excel workbook.")

with col2:
    report_data = {"Daily": daily_df, "Weekly": weekly_df}
    for cat, sub_df in category_dfs.items():
        if not sub_df.empty: report_data[cat] = sub_df
    
    st.download_button(
        label=" 📊 Generate LIVE  Report into Excel",
        # Pass BOTH report_data and the date variable:
        data=get_professional_report(report_data, selected_date_str), 
        file_name=f"BART_Report_{selected_date_str}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )




