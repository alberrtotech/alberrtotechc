import os
import json
import shutil
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import uvicorn
import uuid

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== إعدادات Google Drive =====
FOLDER_ID = "1w-VK9ULNGAHN35HeR-mMlT21xPUjY46r"

# قراءة البيانات من متغير البيئة وإصلاح مشكلة الـ \n
service_account_json = os.environ.get("SERVICE_ACCOUNT_JSON")
if service_account_json:
    try:
        # تحويل النص إلى Dictionary
        info = json.loads(service_account_json)
        # إصلاح الـ Private Key: استبدال الـ \n النصية بسطر حقيقي
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        SERVICE_ACCOUNT_INFO = info
    except Exception as e:
        print(f"Error loading JSON: {e}")
        SERVICE_ACCOUNT_INFO = {}
else:
    SERVICE_ACCOUNT_INFO = {}

def get_drive_service():
    if not SERVICE_ACCOUNT_INFO:
        raise HTTPException(status_code=500, detail="Service Account Info is missing")
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

@app.get("/")
def root():
    return FileResponse("index.html")

TEMP_CHUNKS_DIR = "temp_chunks"
if not os.path.exists(TEMP_CHUNKS_DIR):
    os.makedirs(TEMP_CHUNKS_DIR)

@app.post("/upload/start")
def start_upload():
    return {"upload_id": str(uuid.uuid4())}

@app.post("/upload/chunk")
def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...)
):
    chunk_path = os.path.join(TEMP_CHUNKS_DIR, f"{upload_id}_chunk_{chunk_index}.tmp")
    with open(chunk_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"success": True}

@app.post("/upload/complete")
def complete_upload(
    upload_id: str = Form(...),
    filename: str = Form(...)
):
    final_file_path = os.path.join(TEMP_CHUNKS_DIR, f"{upload_id}_final.tmp")
    try:
        chunks = sorted(
            [f for f in os.listdir(TEMP_CHUNKS_DIR) if f.startswith(f"{upload_id}_chunk_")],
            key=lambda x: int(x.split("_chunk_")[1].split(".")[0])
        )
        if not chunks:
            return JSONResponse({"success": False, "error": "No chunks found"}, status_code=404)

        with open(final_file_path, "wb") as final_file:
            for chunk_file in chunks:
                chunk_path = os.path.join(TEMP_CHUNKS_DIR, chunk_file)
                with open(chunk_path, "rb") as f:
                    shutil.copyfileobj(f, final_file)
                os.remove(chunk_path)

        service = get_drive_service()
        file_metadata = {"name": filename, "parents": [FOLDER_ID]}
        media = MediaFileUpload(final_file_path, mimetype="application/octet-stream", resumable=True, chunksize=5*1024*1024)
        uploaded = service.files().create(body=file_metadata, media_body=media, fields="id,name").execute()
        return {"success": True, "file_id": uploaded.get("id")}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    finally:
        if os.path.exists(final_file_path): os.unlink(final_file_path)
        for f in os.listdir(TEMP_CHUNKS_DIR):
            if f.startswith(upload_id):
                try: os.unlink(os.path.join(TEMP_CHUNKS_DIR, f))
                except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
