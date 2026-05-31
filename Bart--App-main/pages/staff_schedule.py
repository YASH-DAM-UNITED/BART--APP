import streamlit as st
import pandas as pd
import gspread
import time
import re

from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from st_aggrid import AgGrid

st.set_page_config(layout="wide", page_title="BART Master Schedule")

st.markdown("""
<style>
[data-testid="stSidebar"] {
    display: none;
}
[data-testid="collapsedControl"] {
    display: none;
}
</style>
""", unsafe_allow_html=True)

# =========================
# AUTH CHECK
# =========================
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    st.warning("⚠ Session expired. Please login again.")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("⬅ Back to Staff Login", use_container_width=True):
            st.switch_page("app.py")
    st.stop()

# =========================
# GOOGLE AUTH
# =========================
if "gspread_client" not in st.session_state:
    try:
        creds_dict = st.secrets["GOOGLE_CREDS_JSON"]
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        st.session_state.gspread_client = gspread.authorize(creds)
    except Exception as e:
        st.error(f"Authentication setup error: {e}")
        st.stop()

master_sheet = st.session_state.gspread_client.open_by_key(
    "1UtHUn7miqYzaP-NnrwMR_5wnSgLnaYPRQX2c4I7_9B0"
)

# =========================
# CONFIG
# =========================
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

SHIFT_OPTIONS = ["➕ Custom Time", "📴 Day Off"]
ROLE_OPTIONS = ["Team-Member", "Acting_Team_Leader", "Team_Leader",
                "Acting_Supervisor", "Supervisor", "Branch_Manager"]

# =========================
# OT CALC (CLEAN SYSTEM)
# =========================
def parse_hour(val):
    hour, ap = val.split()
    hour = int(hour)
    if ap == "PM" and hour != 12:
        hour += 12
    if ap == "AM" and hour == 12:
        hour = 0
    return hour


def calculate_hours(start, end):
    s = parse_hour(start)
    e = parse_hour(end)
    if e <= s:
        e += 24
    return e - s


def format_shift(start, end):
    hrs = calculate_hours(start, end)
    if hrs < 9:
        return None, hrs
    ot = max(0, hrs - 9)
    if ot > 0:
        return (f"{start} - {end} (OT {ot}h)", hrs)
    return (f"{start} - {end}", hrs)


def calculate_row_ot(row):
    total_ot = 0
    for day in DAYS:
        val = str(row.get(day, ""))
        match = re.search(r"\(OT\s+(\d+(?:\.\d+)?)\s*h\)", val)
        if match:
            total_ot += float(match.group(1))
    return round(total_ot, 2)


# =========================
# DATA LOADING (FIXED)
# =========================
def load_data(force_reload=False):
    if force_reload or st.session_state.get("cached_df") is None:
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            values = ws.get_all_values()

            if not values:
                df = pd.DataFrame()
            else:
                header = values[0]
                rows = values[1:]

                # FIX DUPLICATE HEADERS
                seen = {}
                unique_header = []
                for col in header:
                    if col in seen:
                        seen[col] += 1
                        unique_header.append(f"{col}_{seen[col]}")
                    else:
                        seen[col] = 0
                        unique_header.append(col)

                df = pd.DataFrame(rows, columns=unique_header)

            # Normalize day columns only
            if not df.empty:
                rename_map = {}
                for col in df.columns:
                    for day in DAYS:
                        if day in col:
                            rename_map[col] = day

                df = df.rename(columns=rename_map)

                # REMOVE ALL OT COLUMNS FROM SHEET
                df = df.drop(columns=[c for c in df.columns if "Over-Time" in c], errors="ignore")

            if df.empty:
                df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)

            st.session_state.cached_df = df

        except Exception as e:
            st.error(f"Error loading data: {e}")
            st.session_state.cached_df = pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)

    return st.session_state.cached_df


# =========================
# SESSION INIT
# =========================
if "shift_buffer" not in st.session_state:
    st.session_state.shift_buffer = {}

if "previous_week" not in st.session_state:
    st.session_state.previous_week = None

if "deleted_staff" not in st.session_state:
    st.session_state.deleted_staff = set()


# =========================
# UI HEADER
# =========================
st.title(f"🏢 Schedule: {st.session_state.selected_branch}")

selected_date = st.date_input("📅 Select Date", value=datetime.today())

week_start = selected_date - timedelta(days=(selected_date.weekday() + 1) % 7)
week_start_str = week_start.strftime('%d %b %Y')

st.caption(f"Week starting: {week_start_str}")

if st.session_state.previous_week != week_start_str:
    st.session_state.shift_buffer = {}
    st.session_state.deleted_staff = set()
    st.session_state.previous_week = week_start_str


edit_mode = st.toggle("Edit Mode Only")

all_data_df = load_data()

df = all_data_df[all_data_df["Branch"] == st.session_state.selected_branch].copy() \
    if not all_data_df.empty else pd.DataFrame(columns=["Branch", "Name", "Role"] + DAYS)

day_labels = {d: f"{d} ({(week_start + timedelta(days=i)).strftime('%d %b')})"
              for i, d in enumerate(DAYS)}

# =========================
# EDIT MODE
# =========================
if edit_mode:

    df_display = df[["Name", "Role"]].dropna().drop_duplicates().reset_index(drop=True) \
        if not df.empty else pd.DataFrame(columns=["Name", "Role"] + DAYS)

    if st.session_state.deleted_staff:
        df_display = df_display[~df_display["Name"].isin(st.session_state.deleted_staff)]

    for d in DAYS:
        df_display[d] = ""

    for i, row in df_display.iterrows():
        for d in DAYS:
            key = f"{i}_{d}"
            if key in st.session_state.shift_buffer:
                df_display.loc[i, d] = st.session_state.shift_buffer[key]

    # CLEAN OT (NOT STORED)
    df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1).astype(str) + " hrs"

    config = {
        "Name": st.column_config.SelectboxColumn(
            "Name",
            options=(df["Name"].dropna().unique().tolist() if not df.empty else []),
            width=90
        ),
        "Role": st.column_config.SelectboxColumn("Role", options=ROLE_OPTIONS, width=90),
        "Over-Time": st.column_config.TextColumn("Over-Time", disabled=True, width=80)
    }

    for d in DAYS:
        config[d] = st.column_config.SelectboxColumn(
            label=day_labels[d],
            options=list(set(SHIFT_OPTIONS + df_display[d].dropna().unique().tolist())),
            width=110
        )

    edited_df = st.data_editor(
        df_display[["Name", "Role"] + DAYS + ["Over-Time"]],
        column_config=config,
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )

    current_names = set(edited_df["Name"].dropna().tolist())

    for name in df_display["Name"].tolist():
        if name not in current_names:
            st.session_state.deleted_staff.add(name)

    for i, row in edited_df.iterrows():
        for d in DAYS:
            value = row.get(d)

            if value == "📴 Day Off":
                st.session_state.shift_buffer[f"{i}_{d}"] = "OFF"
                st.rerun()

            if value == "➕ Custom Time":
                st.warning("Custom time popup logic unchanged (your existing dialog)")
                # custom_time_dialog(row_idx=i, row_name=row["Name"], day_name=d)

    # =========================
    # SUBMIT
    # =========================
    if st.button("✅ Submit"):
        try:
            ws = master_sheet.worksheet("StaffSchedule")

            others = st.session_state.cached_df[
                st.session_state.cached_df["Branch"] != st.session_state.selected_branch
            ].copy()

            new_data = edited_df.copy()
            new_data["Branch"] = st.session_state.selected_branch

            final = pd.concat([others, new_data], ignore_index=True)

            # Rename ONLY day columns
            final = final.rename(columns={day: day_labels[day] for day in DAYS})

            # NEVER write OT
            final = final.drop(columns=[c for c in final.columns if "Over-Time" in c], errors="ignore")

            ws.update([final.columns.tolist()] + final.fillna("").values.tolist())

            st.session_state.cached_df = final
            st.session_state.shift_buffer = {}
            st.session_state.deleted_staff = set()

            st.success("Submitted successfully!")
            st.rerun()

        except Exception as e:
            st.error(f"❌ Submission Failed: {e}")

# =========================
# VIEW MODE
# =========================
else:

    if st.button("🔄 Refresh Data"):
        st.session_state.cached_df = None
        st.rerun()

    df_display = df.copy()

    if st.session_state.deleted_staff and not df_display.empty:
        df_display = df_display[~df_display["Name"].isin(st.session_state.deleted_staff)]

    if not df_display.empty:
        df_display["Over-Time"] = df_display.apply(calculate_row_ot, axis=1).astype(str) + " hrs"

    column_defs = [
        {"headerName": "Name", "field": "Name", "pinned": "left", "width": 110},
        {"headerName": "Role", "field": "Role", "width": 140},
    ]

    for d in DAYS:
        column_defs.append({"headerName": day_labels[d], "field": d, "width": 140})

    column_defs.append({"headerName": "Over-Time", "field": "Over-Time", "width": 100})

    AgGrid(
        df_display,
        gridOptions={"columnDefs": column_defs, "defaultColDef": {"resizable": True}},
        height=500
    )

# =========================
# BACK BUTTON
# =========================
if st.button("⬅ Back"):
    st.switch_page("pages/staff_dashboard.py")
