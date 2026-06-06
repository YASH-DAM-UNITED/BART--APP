import streamlit as st
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# Page Config
st.set_page_config(page_title="Delivery Note", layout="centered")

st.title("📝 Delivery Note Upload")

# 1. Helper function for Google Drive Upload
def upload_to_drive(file_bytes, file_name, folder_id):
    # Uses the client already authorized in app.py
    creds = st.session_state.gs_client.auth
    drive_service = build('drive', 'v3', credentials=creds)
    
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_bytes), mimetype='image/jpeg')
    
    # Upload file
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    
    # Make file viewable by anyone with the link
    drive_service.permissions().create(
        fileId=file.get('id'),
        body={'type': 'anyone', 'role': 'reader'}
    ).execute()
    
    return f"https://drive.google.com/uc?id={file.get('id')}"

# 2. Main Logic
transfer_id = st.text_input("Enter Transfer ID")
uploaded_file = st.camera_input("Take a photo of the Delivery Note")

if uploaded_file and transfer_id:
    if st.button("Submit Delivery Note"):
        # REPLACE THIS with the actual Folder ID from your Google Drive
        FOLDER_ID = "YOUR_FOLDER_ID_HERE" 
        
        with st.spinner("Uploading to Drive..."):
            try:
                # Upload to Drive
                file_name = f"Delivery_{transfer_id}.jpg"
                link = upload_to_drive(uploaded_file.getvalue(), file_name, FOLDER_ID)
                
                # Update Google Sheet
                sheet = st.session_state.gs_client.open("MASTERBRANCHSHEET").worksheet("Transfers")
                cell = sheet.find(transfer_id)
                
                if cell:
                    # Update column 8 with the link (Adjust column index as needed)
                    sheet.update_cell(cell.row, 8, link)
                    st.success(f"Successfully uploaded! Link: {link}")
                else:
                    st.error("Transfer ID not found in Master Sheet.")
                    
            except Exception as e:
                st.error(f"An error occurred: {e}")

if st.button("⬅ Back to Dashboard"):
    st.switch_page("app.py")
