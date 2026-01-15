from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

SCOPES = ['https://www.googleapis.com/auth/drive.file']
SERVICE_ACCOUNT_FILE = 'alpine-guild-473812-e9-8b95d4e03b9e.json'
FOLDER_ID = '1-KxaTjPO8YuIG2QDAqEPv9d2Rrx9N6ZH'  # <-- встав сюди ID папки

def upload_to_gdrive(local_file_path, filename=None):
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=creds)
    file_metadata = {
        'name': filename or os.path.basename(local_file_path),
        'parents': [FOLDER_ID]
    }
    media = MediaFileUpload(local_file_path, resumable=True)
    file = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id'
    ).execute()
    file_id = file.get('id')
    service.permissions().create(
        fileId=file_id,
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()
    file_url = f"https://drive.google.com/file/d/{file_id}/view?usp=sharing"
    return file_url