# ========================================================
# CART AND DESTINATION SECTION
# ========================================================

if st.session_state.transfer_cart:
    st.subheader("📋 Current Transfer List")
    for i, entry in enumerate(list(st.session_state.transfer_cart)):
        col1, col2, col3 = st.columns([3, 1, 1])
        col1.write(f"**{entry['item']}**")
        col2.write(f"{entry['qty']} {entry['uom']}")
        if col3.button("Remove", key=f"del_{i}"):
            st.session_state.transfer_cart.pop(i)
            st.rerun()

    st.markdown("---")
    st.subheader("📦 Finalize Transfer")
    
    if st.session_state.get('branch_list'):
        destination = st.selectbox(
            "Select Destination Branch", 
            options=st.session_state.branch_list, 
            index=None, 
            placeholder="Choose a branch...",
            key="dest_sel"
        )
    else:
        destination = None
        st.warning("No destination branches available. Contact admin.")
    
    reason = st.text_area("Reason for Transfer", key="reason_input")

    if destination:
        # Use a standard button click check with a safety unlock mechanism
        confirm_clicked = st.button(
            "Confirm and Send All", 
            key="confirm_btn", 
            disabled=st.session_state.get('is_submitting', False)
        )
        
        if confirm_clicked:
            st.session_state.is_submitting = True
            
            try:
                jeddah_time = datetime.now() + timedelta(hours=3)
                transfer_id = f"TR-{jeddah_time.strftime('%Y%m%d')}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
                origin_branch_raw = st.session_state.get('selected_branch')
                
                if not origin_branch_raw:
                    st.error("Origin branch not set. Please return to Dashboard and select a branch.")
                    st.stop()
                
                origin_id = origin_branch_raw.split(" - ")[0]
                dest_id = str(destination).split(" - ")[0]

                client = get_gs_client()
                origin_key = st.session_state.branch_map.get(origin_id)
                dest_key = st.session_state.branch_map.get(dest_id)
                
                if not origin_key or not dest_key:
                    st.error("Branch ID not found in mapping table.")
                    st.stop()
                
                sh_origin = client.open_by_key(origin_key)
                sh_dest = client.open_by_key(dest_key)
                ws_origin = sh_origin.worksheet("Stocks")
                
                # --- PRE-VALIDATION CHECK ---
                all_origin_data = ws_origin.get_all_values()
                if not all_origin_data or len(all_origin_data) < 2:
                    st.error("Origin stocks sheet is empty or malformed.")
                    st.stop()

                data_rows = all_origin_data[1:]
                origin_items = [row[0] for row in data_rows if len(row) > 0]
                target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                headers = all_origin_data[0]
                
                if target_date not in headers:
                    st.error(f"❌ Could not find column for yesterday's date: {target_date}. Make sure your sheet has a column named '{target_date}'.")
                    st.stop()
                    
                col_index = headers.index(target_date)
                insufficient_items = []
                for entry in st.session_state.transfer_cart:
                    if entry['item'] in origin_items:
                        row_idx = origin_items.index(entry['item'])
                        current_val = ""
                        if col_index < len(data_rows[row_idx]):
                            current_val = data_rows[row_idx][col_index]
                        try:
                            cur = int(float(str(current_val).replace(',', '').strip() or 0))
                        except Exception:
                            cur = 0

                        if cur < int(entry['qty']):
                            insufficient_items.append({"item": entry['item'], "have": cur, "need": entry['qty']})
                    else:
                        insufficient_items.append({"item": entry['item'], "have": 0, "need": entry['qty']})

                if insufficient_items:
                    st.error("❌ Insufficient stock for some items:\n" + "\n".join([f"• {it['item']}: have {it['have']}, need {it['need']}" for it in insufficient_items]))
                    st.stop()
                
                # --- EXECUTE TRANSFER ---
                ws_dest = sh_dest.worksheet("Stocks")
                res_sub = prepare_batch_updates(ws_origin, st.session_state.transfer_cart, "subtract")
                res_add = prepare_batch_updates(ws_dest, st.session_state.transfer_cart, "add")
                
                if res_sub == "Success" and res_add == "Success":
                    transfer_sheet = client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                    transfer_sheet.append_row([
                        transfer_id, origin_branch_raw, str(destination), 
                        "\n".join([f"• {e['item']} ({e['qty']} {e['uom']})" for e in st.session_state.transfer_cart]), 
                        "\n".join([str(e['qty']) for e in st.session_state.transfer_cart]), 
                        str(reason), "Pending", jeddah_time.strftime("%Y-%m-%d %I:%M:%S %p")
                    ])
                    st.session_state.transfer_cart = []
                    success_dialog(f"Transfer successful! ID: {transfer_id}")
                else:
                    st.error(f"Transfer Failed: Origin({res_sub}) | Destination({res_add})")
                    
            except Exception as e:
                st.error(f"Critical Error: {e}")
            finally:
                # GUARANTEE that the button unlocks no matter what happens above
                st.session_state.is_submitting = False
    else:
        st.info("Please select a destination branch to finalize the transfer.")
else:
    st.info("Add items to your cart to proceed with the transfer.")
