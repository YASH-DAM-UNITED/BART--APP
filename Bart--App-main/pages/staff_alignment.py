# --- Specific Branch View ---
s_col1, _ = st.columns([1, 2])
with s_col1: 
    selected_branch = st.selectbox("🏢 Select Branch", branches)

# Filter for the branch
df_branch = df_work[df_work["Branch"] == selected_branch]

# Calculate based on the single day (Original Logic remains untouched)
b_act, b_inact = compute(df_branch, start_m, end_m)

# 1. Define the week slice (3 days before, selected day, 3 days after)
selected_idx = shift_cols.index(shift_col)
start_idx = max(0, selected_idx - 3)
end_idx = min(len(shift_cols), selected_idx + 4)
weekly_columns = shift_cols[start_idx:end_idx]

st.subheader(f"🏢 {selected_branch} Detailed Overview")
sc1, sc2, sc3 = st.columns(3)
sc1.metric("Active", len(b_act)); sc2.metric("Inactive", len(b_inact)); sc3.metric("Total", len(df_branch))

st.subheader("🔥 Active Staff")
st.dataframe(b_act, use_container_width=True, hide_index=True)

st.subheader("📊 Full Branch Data (Weekly View)")
# Combine all data back together
df_combined = pd.concat([b_act, b_inact], ignore_index=True)

# 2. Identify the Overtime column dynamically
# This finds any column starting with "Over-Time" (e.g., "Over-Time 4")
ot_cols = [c for c in df_combined.columns if c.startswith("Over-Time")]

# 3. Define columns to show: Meta + Weekly Shifts + Dynamic Overtime column
display_cols = meta_cols + weekly_columns + ot_cols

# Display the final table
st.dataframe(df_combined[display_cols], use_container_width=True, hide_index=True)
