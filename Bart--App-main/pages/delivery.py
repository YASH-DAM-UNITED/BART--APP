import streamlit as st
import gspread
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

st.set_page_config(page_title="Delivery Note", layout="centered")
st.title("📝 Delivery Note Upload")

# 1. Setup Google Services (Assuming client is in st.session_state)
if 'gs_client' not in st.session_state:
    st.error("Session expired. Please go back to the main page to reconnect.")
    st.stop()

def upload_to_drive(file_bytes, file_name, folder_id):
    # Using the credentials from the existing client
    creds = st.session_state.gs_client.auth
    drive_service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    # Set public access for the link
    drive_service.permissions().create(
        fileId=file.get('id'),
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return f"https://drive.google.com/uc?id={file.get('id')}"

# 2. Input Section
transfer_id = st.text_input("Enter Transfer ID")
uploaded_file = st.camera_input("Take a photo of the Delivery Note")

# 3. Processing
if uploaded_file and transfer_id:
    if st.button("Submit Delivery Note"):
        # REPLACE THIS with the actual Folder ID from your Google Drive folder URL
        # (This is different from the Spreadsheet ID)
        FOLDER_ID = "1zGHwdYDtw7kQPcx-UHLDjYTJYU-11_X4" 
        
        with st.status("Uploading...", expanded=True) as status:
            try:
                # Drive Upload
                st.write("Uploading image to Drive...")
                file_name = f"Delivery_{transfer_id}.jpg"
                link = upload_to_drive(uploaded_file.getvalue(), file_name, FOLDER_ID)
                
                # Sheet Update
                st.write("Updating Google Sheet...")
                # Using your provided Spreadsheet Key and "Delivery" tab
                sheet = st.session_state.gs_client.open_by_key("1zGHwdYDtw7kQPcx-UHLDjYTJYU-11_X4").worksheet("Delivery")
                
                # Find ID in the sheet
                cell = sheet.find(transfer_id)
                if cell:
                    # Updates column 8 (Column H) with the drive link
                    sheet.update_cell(cell.row, 8, link)
                    status.update(label="Complete!", state="complete", expanded=False)
                    st.success(f"Delivery Note saved for {transfer_id}!")
                    st.balloons()
                else:
                    status.update(label="Error", state="error")
                    st.error(f"Transfer ID '{transfer_id}' not found in the 'Delivery' sheet.")
                    
            except Exception as e:
                status.update(label="Critical Error", state="error")
                st.error(f"Error: {e}")
if st.button("⬅ Back to Dashboard"):
    st.switch_page("app.py")
