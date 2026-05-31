import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from rapidfuzz import process, fuzz
from datetime import datetime
import time
import pandas as pd
import pdfplumber
import re
import string

# ---------------- PAGE CONFIG ----------------
st.set_page_config(layout="wide", page_title="BART - Daily Sales")

# ---------------- HIDE UI ----------------
st.markdown("""
<style>
#MainMenu {visibility:hidden;}
footer {visibility:hidden;}
header {visibility:hidden;}
[data-testid="stToolbar"] {display:none;}
[data-testid="stSidebar"] {display:none;}
div.stButton > button {
    height:60px; 
    font-size:18px; 
    border-radius:12px; 
    margin:8px; 
    width:240px;
}
</style>
""", unsafe_allow_html=True)

# ---------------- SESSION SAFETY ----------------
if "sheet_id" not in st.session_state or "selected_branch" not in st.session_state:
    st.warning("⚠️ Please select a branch first")
    st.stop()

# ---------------- LOAD ITEMS ----------------
with open("bart_items.txt", "r", encoding="utf-8") as f:
    valid_items = [line.strip() for line in f.readlines()]

if not valid_items:
    st.error("Items list is empty")
    st.stop()

# ---------------- GOOGLE SHEETS ----------------
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(st.session_state.sheet_id).worksheet("Sales")
except Exception as e:
    st.error(f"Google Sheets Error: {e}")
    st.stop()

# ---------------- TITLE ----------------
st.markdown(f"<h1 style='text-align:center; color:red;'>Daily Sales Entry</h1>", unsafe_allow_html=True)
st.success(f"📍 Active Branch: {st.session_state.selected_branch}")

# ---------------- DATE ----------------
date = st.date_input("Select Date", value=datetime.today())
date_str = date.strftime("%Y-%m-%d")

# ---------------- UPLOAD ----------------
st.markdown("## 📤 Upload Sales Report")
uploaded_file = st.file_uploader("Upload PDF / Excel / CSV / TXT", type=["pdf", "xlsx", "csv", "txt"])

# ---------------- PARSER ----------------
def smart_parse_line(line):
    line = line.strip()
    if not line or any(x in line.lower() for x in ["daily", "date", "currency", "time"]):
        return None

    numbers = re.findall(r"\d+\.?\d*", line)
    if len(numbers) < 2:
        return None

    try:
        if len(numbers) >= 3:
            qty = float(numbers[-3])
            price = float(numbers[-2])
        else:
            qty = float(numbers[-2])
            price = float(numbers[-1])

        text_part = re.sub(r"\d+\.?\d*", "", line)
        text_part = re.sub(r"\b\d{1,2}:\d{2}\b", "", text_part)
        item = " ".join(text_part.split()).strip()
        if not item:
            return None

        return (item, qty, price)
    except:
        return None


def parse_sales_lines(lines):
    parsed = []
    for line in lines:
        result = smart_parse_line(line)
        if result:
            parsed.append(result)
    return parsed

# ---------------- EXTRACT DATA ----------------
sales_today = []
pdf_total_items = None
pdf_revenue = None

if uploaded_file is not None:
    try:
        lines = []

        # -------- PDF --------
        if uploaded_file.type == "application/pdf":
            words = []
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    page_words = page.extract_words()
                    if page_words:
                        words.extend(page_words)

            lines_dict = {}
            for w in words:
                y = round(w['top'])
                lines_dict.setdefault(y, []).append(w['text'])

            for y in sorted(lines_dict.keys()):
                line = " ".join(lines_dict[y])
                lines.append(line)

        # -------- CSV / XLSX / TXT --------
        elif uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
            lines = df.astype(str).apply(lambda x: " ".join(x), axis=1).tolist()

        elif uploaded_file.name.endswith(".xlsx"):
            df = pd.read_excel(uploaded_file)
            lines = df.astype(str).apply(lambda x: " ".join(x), axis=1).tolist()

        elif uploaded_file.name.endswith(".txt"):
            text = uploaded_file.read().decode("utf-8")
            lines = text.split("\n")

        if not lines:
            st.warning("No readable data found in file")
            st.stop()

        # -------- TOTALS SAFE PARSING --------
        for line in lines:
            if "Total Items Sold" in line:
                nums = re.findall(r"\d+", line)
                if nums:
                    pdf_total_items = int(nums[0])

            if "Gross Revenue" in line:
                nums = re.findall(r"\d+", line)
                if nums:
                    pdf_revenue = float(nums[0])

        sales_today = parse_sales_lines(lines)
        st.success(f"✅ Extracted {len(sales_today)} records")

    except Exception as e:
        st.error(f"File Error: {e}")

# ---------------- PREVIEW ----------------
if sales_today:
    st.markdown("### 🔍 Preview")
    for item, qty, price in sales_today[:20]:
        st.write(f"{item} → {qty} x {price}")

# ---------------- SUMMARY ----------------
if sales_today:
    total_items_calc = sum(q for _, q, _ in sales_today)
    total_revenue_calc = sum(q * p for _, q, p in sales_today)

    st.markdown("## 📊 Calculated Summary")
    st.write(f"Total Items: {total_items_calc}")
    st.write(f"Total Revenue: SAR {total_revenue_calc:.2f}")

    if pdf_total_items and total_items_calc != pdf_total_items:
        st.error(f"⚠️ Items mismatch! PDF: {pdf_total_items} | Calculated: {total_items_calc}")
    elif pdf_total_items:
        st.success("✅ Items count matches PDF")

    if pdf_revenue and abs(total_revenue_calc - pdf_revenue) > 5:
        st.error(f"⚠️ Revenue mismatch! PDF: {pdf_revenue} | Calculated: {total_revenue_calc}")
    elif pdf_revenue:
        st.success("✅ Revenue matches PDF")

# ---------------- SESSION ----------------
if "pending_sales" not in st.session_state:
    st.session_state.pending_sales = []

# ---------------- NORMALIZATION ----------------
def normalize(text):
    return text.lower().translate(str.maketrans("", "", string.punctuation)).strip()

def find_best_match(item_name, valid_items):
    for v in valid_items:
        if normalize(item_name) == normalize(v):
            return v, True

    matches = process.extract(item_name, valid_items, scorer=fuzz.ratio, limit=3)
    for m in matches:
        if m[1] > 85:
            return m[0], False

    matches = process.extract(item_name, valid_items, scorer=fuzz.token_set_ratio, limit=3)
    for m in matches:
        if m[1] > 90:
            return m[0], False

    return None, False

# ---------------- APPLY MATCHING ----------------
for item_name, qty, price in sales_today:
    if not any(item_name == x[0] for x in st.session_state.pending_sales):
        match, exact = find_best_match(item_name, valid_items)
        if match:
            st.session_state.pending_sales.append((match, qty, price))
            if not exact:
                st.info(f"⚠️ Review match: '{item_name}' → '{match}'")
        else:
            st.warning(f"❌ Unknown item: {item_name}")

# ---------------- SHOW ----------------
for i, (iname, qty, price) in enumerate(st.session_state.pending_sales):
    st.checkbox(f"{iname} → {qty} x {price} = {qty*price}", value=True, key=f"chk_{i}")

# ---------------- SUBMIT ----------------
def safe_append(row):
    for _ in range(3):
        try:
            sheet.append_row(row)
            return True
        except Exception as e:
            time.sleep(2)
    return False

if st.button("🚀 Submit Sales"):
    for i, (iname, qty, price) in enumerate(st.session_state.pending_sales):
        if st.session_state.get(f"chk_{i}", True):
            safe_append([date_str, iname, qty, price, qty * price])

    st.session_state["just_submitted"] = True

    st.success("✅ Uploaded successfully. Redirecting to dashboard in 4 seconds...")
    time.sleep(4)
    st.switch_page("pages/staff_dashboard.py")

    st.session_state.pending_sales = []

# ---------------- BACK ----------------
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
