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

# ========================================================
# PAGE CONFIG
# ========================================================
st.set_page_config(page_title="Management Panel", layout="wide", initial_sidebar_state="collapsed")
st.title("📦 BART - Stock Management (All Branches)")

st.markdown(
    """
    <style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="collapsedControl"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ========================================================
# GOOGLE AUTH
# ========================================================
creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_client():
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

client = get_client()

# ========================================================
# EXPORT HELPERS
# ========================================================
def get_professional_report(report_data, date_str):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        summary_ws = workbook.add_worksheet("Dashboard Summary")
        summary_ws.hide_gridlines(2)
        title_fmt = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': '#2C3E50'})
        summary_ws.write('B2', 'BART Inventory Executive Report', title_fmt)
        summary_ws.write('B4', f'Generated Date: {date_str}')
        for sheet_name, df in report_data.items():
            if '::auto_unique_id::' in df.columns: df = df.drop(columns=['::auto_unique_id::'])
            safe_name = "".join([c for c in sheet_name if c.isalnum() or c in (' ', '_')])[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
    return output.getvalue()

def to_excel_bytes(data_frames):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in data_frames.items():
            if '::auto_unique_id::' in df.columns: df = df.drop(columns=['::auto_unique_id::'])
            safe_name = "".join([c for c in sheet_name if c.isalnum() or c in (' ', '_')])[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)
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
    return [{"BranchName": str(b["BranchName"]).strip(), "SheetID": str(b["SheetID"]).strip()} 
            for b in data if b.get("SheetID") and b.get("BranchName")]

branches = load_branches()
branch_names = [b["BranchName"] for b in branches]

# ========================================================
# DATA & RETRY CONFIG
# ========================================================
FOOD_SKUS = {"-", "B034", "F066", "B032", "B029", "F081", "B019", "B018", "CF007", "CF006", "F148", "B028", "K072", "K176", "CB036", "K265", "B016", "CB078", "K154", "CB054", "K226", "CB074", "M&M", "B014", "K242", "S019", "B006", "CB055", "B017", "CB076", "CB056", "B026", "CB037", "K087", "CB043", "CB009", "CB043", "K063"}
DRY_SKUS = {"C013", "IC013", "P244", "P245", "P254", "P095", "P296", "P343", "P343(1)", "P012", "P091", "P155", "P081", "P253", "P101", "P218", "P132", "P264", "P219", "P338", "P341", "P342", "P210", "P320", "P322", "P321", "P082", "P318", "P208", "P315", "C014", "F070", "P298", "P178", "CB009", "C015", "CF009", "P145", "P133", "P156", "RS002", "C011", "C012", "P189", "P160", "C005", "P157", "C010", "C007", "CB010", "P161", "P039", "P125", "C045", "RS001", "P084", "P163", "P162", "C016", "C017", "P158", "C048", "P083"}
MISC_SKUS = {"K063", "T063", "T060", "T066", "TOY1", "ΤΟΥ1", "T026", "SVP", "F089", "P130"}

branch_cache = {}

def fetch_branch(branch):
    name = branch["BranchName"]
    try:
        ws = client.open_by_key(branch["SheetID"]).worksheet("Stocks")
        data = ws.get_all_values()
        branch_cache[name] = data
        return name, data
    except Exception:
        return name, branch_cache.get(name, [])

@st.cache_data(ttl=None)
def load_all_data(branches):
    completed = {}
    failed = branches
    progress = st.progress(0)
    status = st.empty()
    
    with ThreadPoolExecutor(max_workers=7) as ex:
        futures = {ex.submit(fetch_branch, b): b for b in branches}
        done = 0
        for f in as_completed(futures):
            name, data = f.result()
            if data: completed[name] = data
            else: pass # Simplified for combined snippet
            done += 1
            progress.progress(done / len(branches))
    return [(b["BranchName"], completed.get(b["BranchName"], [])) for b in branches]

# ========================================================
# NAVIGATION
# ========================================================
if "show_manager_login" not in st.session_state: st.session_state.show_manager_login = False

col1, col2, col3, col4 = st.columns(4)
if col1.button(" 🔄 Refresh Data"): st.cache_data.clear(); st.cache_resource.clear(); st.rerun()
if col2.button("👥 Staff Alignment"): st.switch_page("pages/staff_alignment.py")
if col3.button("🔑 Area Manager Login"): st.session_state.show_manager_login = True; st.rerun()
if col4.button("⬅ LOGOUT "): st.switch_page("app.py")

if st.session_state.show_manager_login:
    st.write("Manager Login Screen")
    if st.button("← Back to Dashboard"): st.session_state.show_manager_login = False; st.rerun()
else:
    # ========================================================
    # PROCESSING FUNCTIONS
    # ========================================================
    selected_date = st.date_input("📅 Select Date")
    selected_date_str = selected_date.strftime("%Y-%m-%d")

    @st.cache_data(ttl=None)
    def process_stock(all_data, selected_date_str, branch_names):
        daily, weekly = {}, {}
        for branch_name, raw in all_data:
            if not raw or len(raw) < 2: continue
            headers = [str(x).strip() for x in raw[0]]
            date_index = next((i for i, h in enumerate(headers) if h == selected_date_str), None)
            mode = None
            for row in raw:
                if not row: continue
                text = " ".join(str(x) for x in row).lower()
                if "daily item" in text: mode = "daily"; continue
                if "weekly item" in text: mode = "weekly"; continue
                if not mode: continue
                item = str(row[0]).strip() if len(row) > 0 else ""
                sku = str(row[1]).replace(" ", "").strip() if len(row) > 1 else ""
                uom = str(row[2]).strip() if len(row) > 2 else ""
                if not item: continue
                key = f"{item}_{sku}_{uom}"
                target = daily if mode == "daily" else weekly
                if key not in target:
                    target[key] = {"Item Name": item, "SKU": sku, "UOM": uom}
                    for b in branch_names: target[key][b] = 0
                qty = 0
                try:
                    if date_index is not None and len(row) > date_index:
                        val = str(row[date_index]).strip()
                        qty = 0 if val in ["", None, "-", "None"] else float(val)
                except: qty = 0
                target[key][branch_name] = qty
        return daily, weekly

    def build_df(data_dict, branch_names):
        rows = []
        for _, v in data_dict.items():
            row = {"Item Name": v["Item Name"], "SKU": v["SKU"], "UOM": v["UOM"]}
            for b in branch_names: row[b] = v.get(b, 0)
            row["Total"] = sum(row[b] for b in branch_names)
            rows.append(row)
        return pd.DataFrame(rows)

    def detect_category(sku):
        s = str(sku).replace(" ", "").strip().upper()
        if not s or s in ["-", "NONE", "NAN"]: return "FOOD ITEMS"
        if s in FOOD_SKUS: return "FOOD ITEMS"
        if s in DRY_SKUS: return "DRY ITEMS"
        if s in MISC_SKUS: return "MISC ITEMS"
        if s.startswith(('B', 'F', 'K', 'CB', 'CF', 'S')): return "FOOD ITEMS"
        if s.startswith(('C', 'P', 'IC', 'RS')): return "DRY ITEMS"
        if s.startswith(('T', 'SVP', 'TOY', 'ΤΟΥ')): return "MISC ITEMS"
        return "UNCATEGORIZED DETECTED"

    def build_category_dfs(df):
        cats = {"FOOD ITEMS": pd.DataFrame(columns=df.columns), "DRY ITEMS": pd.DataFrame(columns=df.columns), "MISC ITEMS": pd.DataFrame(columns=df.columns), "UNCATEGORIZED DETECTED": pd.DataFrame(columns=df.columns)}
        if df.empty: return cats
        cat_series = df["SKU"].apply(detect_category)
        for cat_name in list(cats.keys()):
            sub_df = df[cat_series == cat_name]
            cats[cat_name] = sub_df.sort_values(by="Item Name", key=lambda col: col.str.lower())
        if cats["UNCATEGORIZED DETECTED"].empty: del cats["UNCATEGORIZED DETECTED"]
        return cats

    def make_grid(df, key):
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(resizable=True, sortable=True, filter=True)
        gb.configure_column("Item Name", pinned="left", lockPinned=True, width=250)
        for b in branch_names: 
            gb.configure_column(b, type=["numericColumn"], width=120)
        if "Total" in df.columns: 
            gb.configure_column("Total", pinned="right", width=100)
        AgGrid(df, gridOptions=gb.build(), theme="streamlit", key=key, allow_unsafe_jscode=True)

    # ========================================================
    # RUN PIPELINE
    # ========================================================
    all_data = load_all_data(branches)
    daily_items, weekly_items = process_stock(all_data, selected_date_str, branch_names)
    daily_df, weekly_df = build_df(daily_items, branch_names), build_df(weekly_items, branch_names)



# ========================================================
    # GLOBAL GOOGLE-STYLE INVENTORY SEARCH
    # ========================================================
    st.subheader("🔍 Global Inventory Search")

    pool_daily = daily_df.copy()
    pool_daily["Schedule"] = "Daily"
    pool_weekly = weekly_df.copy()
    pool_weekly["Schedule"] = "Weekly"
    search_pool = pd.concat([pool_daily, pool_weekly], ignore_index=True)

    if not search_pool.empty:
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
                
                display_cols = ["Item Name", "SKU", "UOM"] + branch_names + ["Total"]
                result_df = matched_row[display_cols].reset_index(drop=True)
                search_grid_key = f"search_result_grid_{selected_date_str}_{hashlib.md5(selected_option.encode()).hexdigest()}"
                
                make_grid(result_df, search_grid_key)
                
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
    # CATEGORY VIEW
    # ========================================================
    st.subheader("📊 Category Wise Stock Overview")

    combined_stock = pd.concat([daily_df, weekly_df], ignore_index=True)
    combined_stock = combined_stock.drop_duplicates(subset=["Item Name", "SKU", "UOM"])
    category_dfs = build_category_dfs(combined_stock)

    tab_labels = [f"📂 {cat} ({len(sub_df)})" for cat, sub_df in category_dfs.items()]
    selected_tab = st.radio("Category Selector", options=tab_labels, index=0, horizontal=True, label_visibility="collapsed", key="cat_radio_tabs")
    
    active_cat = next(cat for cat in category_dfs if f"📂 {cat}" in selected_tab)
    sub_df = category_dfs[active_cat]

    if not sub_df.empty:
        grid_key = f"ag_grid_radio_{active_cat}_{selected_date_str}"
        make_grid(sub_df, grid_key)
    else:
        st.info(f"No items found in {active_cat}")

    # CSS for Tabs
    st.markdown("""<style>
        div[role="radiogroup"] > label > div:first-of-type { display: none; }
        div[role="radiogroup"] { display: flex; gap: 0px; border-bottom: 2px solid #ddd; }
        div[role="radiogroup"] > label { padding: 10px 20px; cursor: pointer; font-weight: 600; color: #555; }
        div[role="radiogroup"] > label:has(input:checked) { border-bottom: 3px solid #ff4b4b; color: #ff4b4b; }
    </style>""", unsafe_allow_html=True)

    # ========================================================
    # MAIN TABLES & EXPORT
    # ========================================================
    def render(df, title):
        st.subheader(title)
        if df.empty: st.warning("No Data"); return
        make_grid(df, f"grid_{title}_{selected_date_str}")

    render(daily_df, "📦 Daily Items Stock")
    render(weekly_df, "📦 Weekly Items Stock")

    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("📊 Inventory Insights")
        st.caption("Exports all categories into a professionally styled Excel workbook.")
    with col2:
        report_data = {"Daily": daily_df, "Weekly": weekly_df, **{k: v for k, v in category_dfs.items() if not v.empty}}
        st.download_button(
            label=" 📊 Generate LIVE Report into Excel",
            data=get_professional_report(report_data, selected_date_str),
            file_name=f"BART_Report_{selected_date_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
