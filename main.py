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

SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "file-uploader-496110",
    "private_key_id": "d2045f07da5407216f4451f2b1e98ab40b983268",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQDolxwVfV1bOLuX\naTWV9jiCTX/ySXTZOcukzkxoevp9D5EkPn1WdhjlccCxzwQSNd89Q6ePNp5KmoL1\nPNAY00DKEddrcBkY03RSKZSTDafkgu7B7dYc0n+3t8WnurSEypX+ITIZwLd5fuHN\n6bQTvwiiVFvnZfFIW01UZtkpYXtlU0sSfQf8REvuFlfQ4azcakBvHKs74UkdYqdJ\nXp2LlgxNSjB/5eQVJW3TkFVE5NRH8IR/4OHvg/pJyP73N286Inhffzh5p25qtfnx\nZQH0+xlhjPRiTAcm/NcrANFFuLGM93e3OmgcXPX1rxTePXNrYc+uvLqV3grA3UTm\n/XTjJxnfAgMBAAECggEAbifHArx9fusXGUYYPV4/9CJ9QsQcZZb0Rij4UhFQWfOJ\n84bu+Ih1ERG3R976GB/QiyTkEjU1cbLM7BWxnthKWolpo3YTRMk80X7k4WJ5zgVe\ny5T3L25YU6vjHiWUQkHqGNIi9sRpgM6hZdLV2PZEQhE+95A13mVzcdJF7k2/UcRi\nVLfMwKz9RhnrP7KkFAjr8V2U9AVkC8uvUNfWIMPO3BaDyKdS33JlM5N4N3ar1+wL\ndeZfLDCRftkoeDE157LfRLBysxnaTzVyC0QDBUXOOLJJgmMakCKpxtvQvQHpjVg1\nZXO8TlxcUeg4aEvfwZaE7f3O+jikvjCZ53Z//1XzNQKBgQD6uj6dwfAomtnJVw6r\nFIuUL+0+KYKvTLur9BkXGo7LhE2RH/FeYdvi1DAl2pOMcxsnUyNXAUswOcI0jeHI\nilfxoTjmMPlCW0WdyAIEIPXSGMv0dyrIBw/moYOJEoIe4+aouoamDdud9H811yQY\n/SSv9RpIxDwsbFEzGdTo1ootZQKBgQDteznSN3Gtj995DimHSFvGplx17ddaPlFJ\nNoGGMGpZgCShMjp1nnWVyTPfEuZXR14khmqNchT2n0Twg3VDo6w7fEpTn6+qa6jp\nyZI/ya3lnymBkZQGD2hMgiK8lRfLsBc09S3YIqH3bszaf+HGXbU2SXZTx7Jhg2NH\ndx89XttH8wKBgQCmOnhtKzlIEnI1tIw7DKIFm0jVH7xO8La0KF/CG490isDKaL0j\n8AlSd498aU/NnDrydYJGmsr4rDJ/mVmKFX586oDIzMtVHSIom4QKrLeNlXcTGza3\n60a1h3unkyfFxx8T2qaOzT0/mewFDCAYmSyLpBrLB59FbILhOE0aGbL+qQKBgHF3\nbBQN26nS0TKU2rDBmOAcQpcyEbATkGELwu0rmtSyjk3aouXp1ULBBKCz9gyDk+6d\nrrFwbaW8SYMlPFUaEcPGSfkUlik2EVnKrq79nLHWz00SEoimue28S/6QufLfaucp\nskLPoVWIwiYv7d8KjPeoN/olsww2a6wMtYdsGBeTAoGAcIGGHhnf3FzIwFnZu8iM\n32QiSDTRGdfgHyNaQSAHKLpC/N2tA0n5sKRewaXKp8YwClV/ZGa+E0ShDgcPuf+I\neWF08tuALQ/5gbELA1rghg8MxLG6K4a5dmGra1DD0Gwg6rXKppB+AWsmM2gUrh08\nnhXFSaKrlMIEmEsyFG/diQg=\n-----END PRIVATE KEY-----\n",
    "client_email": "my-projectt1@file-uploader-496110.iam.gserviceaccount.com",
    "client_id": "115684423201119326919",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/my-projectt1%40file-uploader-496110.iam.gserviceaccount.com",
    "universe_domain": "googleapis.com"
}

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
                os.remove(chunk_path) # حذف الجزء فوراً بعد دمجه توفيراً للمساحة

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
