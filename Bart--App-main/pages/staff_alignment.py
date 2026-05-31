import streamlit as st
import pandas as pd
import gspread
import re
from google.oauth2.service_account import Credentials
from datetime import datetime, date

st.set_page_config(
    layout="wide",
    page_title="Ops Control Center",
    initial_sidebar_state="collapsed"
)

st.title("STAFF Schedule Control Center")

st.markdown("""
<style>
section[data-testid="stSidebar"] {
    display: none !important;
}

div[data-testid="collapsedControl"] {
    display: none !important;
}

[data-testid="stAppViewContainer"] {
    padding-left: 1rem;
    padding-right: 1rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
div[data-testid="stHorizontalBlock"] {
    align-items: center;
}

div[data-testid="stButton"] > button {
    height: 38px;
    width: 60px;
    padding: 0px;
    font-size: 14px;
    border-radius: 8px;
}
</style>
""", unsafe_allow_html=True)

SHEET_ID = "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
TAB_NAME = "StaffSchedule"

@st.cache_resource
def get_client():
    creds = Credentials.from_service_account_info(
        st.secrets["GOOGLE_CREDS_JSON"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
    return gspread.authorize(creds)

client = get_client()
sheet = client.open_by_key(SHEET_ID)

@st.cache_data(ttl=900)
def load_data():
    ws = sheet.worksheet(TAB_NAME)
    raw = ws.get_all_values()
    df = pd.DataFrame(raw[1:], columns=raw[0]).fillna("")
    return df

df_full = load_data()
df_full = df_full.loc[:, ~df_full.columns.duplicated()].copy()

def clean(text):
    text = str(text).replace("–", "-").replace("—", "-")
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def get_shift(cell):
    if not cell:
        return None

    text = clean(cell)
    matches = re.findall(r"\d{1,2}\s*(?:AM|PM)", text, re.I)

    if len(matches) < 2:
        return None

    def convert(t):
        t = t.upper().replace(" ", "")
        h = int(re.findall(r"\d{1,2}", t)[0])

        if "AM" in t:
            if h == 12:
                h = 0
        else:
            if h != 12:
                h += 12

        return h * 60

    return convert(matches[0]), convert(matches[1])

def is_active(cell, now_min):
    shift = get_shift(cell)
    if not shift:
        return False

    start, end = shift

    if start < end:
        return start <= now_min < end
    else:
        return now_min >= start or now_min < end

meta_cols = ["Branch", "Name", "Role"]
shift_cols = [c.strip() for c in df_full.columns if c not in meta_cols]

def extract_day_month(col):
    match = re.search(r"\((\d{1,2}\s\w{3})\)", col)
    if match:
        return match.group(1).strip()
    return None

today_day_month = date.today().strftime("%d %b")
default_index = len(shift_cols) - 1

for i, col in enumerate(shift_cols):
    if extract_day_month(col) == today_day_month:
        default_index = i
        break

st.markdown("### KINDLY SELECT THE DATE")

col1, col2, col3 = st.columns([4, 1, 1], vertical_alignment="center")

with col1:
    shift_col = st.selectbox(
        "Shift Column",
        shift_cols,
        index=default_index,
        label_visibility="collapsed"
    )

with col2:
    refresh = st.button("🔄", use_container_width=True)

with col3:
    back = st.button("⬅", use_container_width=True)

if back:
    st.switch_page("pages/management_dashboard.py")

if refresh:
    st.cache_data.clear()
    st.cache_resource.clear()
    st.rerun()

if "Shift" in df_full.columns:
    df_full = df_full.drop(columns=["Shift"])

df_full["Shift"] = df_full[shift_col]

now_min = datetime.now().hour * 60 + datetime.now().minute
branches = sorted(df_full["Branch"].dropna().unique().tolist())

def safe_df(df):
    df = df.copy()
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def compute(df):
    active, inactive = [], []

    for _, row in df.iterrows():
        r = row.to_dict()

        if is_active(row["Shift"], now_min):
            active.append(r)
        else:
            inactive.append(r)

    cols = df.columns.tolist()

    return (
        pd.DataFrame(active, columns=cols),
        pd.DataFrame(inactive, columns=cols)
    )

u_act, u_inact = compute(df_full)

st.subheader("STAFF Universal Overview")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("🏢 Branches", len(branches))
with c2:
    st.metric("👥 Staff", len(df_full))
with c3:
    st.metric("🟢 Active", len(u_act))
with c4:
    st.metric("⚪ Inactive", len(u_inact))

st.divider()

st.subheader("👥 Branchwise Status")

summary = []
for b in branches:
    temp = df_full[df_full["Branch"] == b]
    a, i = compute(temp)

    summary.append({
        "Branch": b,
        "Active": len(a),
        "Inactive": len(i)
    })

st.dataframe(safe_df(pd.DataFrame(summary)), use_container_width=True, hide_index=True)

st.divider()

col1, col2 = st.columns(2)

with col1:
    selected_branch = st.selectbox("🏢 Branch", branches)

with col2:
    selected_date = st.date_input("📅 Date", value=date.today())

df_branch = df_full[df_full["Branch"] == selected_branch]
b_act, b_inact = compute(df_branch)

st.subheader("🏢 Branch Overview")

c1, c2, c3, c4 = st.columns(4)

with c1:
    st.metric("Branch", selected_branch)
with c2:
    st.metric("Date", selected_date.strftime("%d-%m-%Y"))
with c3:
    st.metric("Active", len(b_act))
with c4:
    st.metric("Inactive", len(b_inact))

st.divider()

st.subheader("🔥 Active Staff")
st.dataframe(safe_df(b_act), use_container_width=True, hide_index=True)

st.subheader("📊 Full View")

full_view = pd.concat([b_act, b_inact], ignore_index=True)
full_view = full_view[df_branch.columns]

st.dataframe(safe_df(full_view), use_container_width=True, hide_index=True)
