import os
import json
import shutil
import tempfile
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

# قراءة بيانات الحساب من متغير بيئة مشفر بـ Base64 لضمان عدم وجود أخطاء
import base64
service_account_b64 = os.environ.get("SERVICE_ACCOUNT_B64", "")
if service_account_b64:
    try:
        decoded = base64.b64decode(service_account_b64).decode("utf-8")
        SERVICE_ACCOUNT_INFO = json.loads(decoded)
    except Exception as e:
        print(f"Error decoding SERVICE_ACCOUNT_B64: {e}")
        SERVICE_ACCOUNT_INFO = {}
else:
    SERVICE_ACCOUNT_INFO = {}

def get_drive_service():
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

@app.get("/")
def root():
    return FileResponse("index.html")

# مجلد لتخزين الأجزاء مؤقتاً
TEMP_CHUNKS_DIR = "temp_chunks"
if not os.path.exists(TEMP_CHUNKS_DIR):
    os.makedirs(TEMP_CHUNKS_DIR)

@app.post("/upload/start")
def start_upload():
    # إنشاء معرف فريد للجلسة
    return {"upload_id": str(uuid.uuid4())}

@app.post("/upload/chunk")
def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    file: UploadFile = File(...)
):
    # حفظ كل جزء في ملف مستقل لتجنب تداخل الترتيب
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
        # 1. تجميع الأجزاء بالترتيب الصحيح بناءً على الرقم
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
                os.remove(chunk_path) # حذف الجزء فوراً بعد دمج توفيراً للمساحة

        # 2. رفع الملف النهائي لـ Google Drive
        service = get_drive_service()
        file_metadata = {
            "name": filename,
            "parents": [FOLDER_ID]
        }
        media = MediaFileUpload(
            final_file_path,
            mimetype="application/octet-stream",
            resumable=True,
            chunksize=5 * 1024 * 1024
        )
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,name"
        ).execute()

        return {"success": True, "file_id": uploaded.get("id")}
    
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
    
    finally:
        # تنظيف أي ملفات متبقية (سواء نجح الرفع أو فشل)
        if os.path.exists(final_file_path):
            os.unlink(final_file_path)
        for f in os.listdir(TEMP_CHUNKS_DIR):
            if f.startswith(upload_id):
                try: os.unlink(os.path.join(TEMP_CHUNKS_DIR, f))
                except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
