import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
from b2sdk.v2 import InMemoryAccountInfo, B2Api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعدادات Backblaze B2 (يتم جلبها من Render Environment Variables)
B2_KEY_ID = os.environ.get("B2_KEY_ID")
B2_APPLICATION_KEY = os.environ.get("B2_APPLICATION_KEY")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME")

def get_b2_api():
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    if B2_KEY_ID and B2_APPLICATION_KEY:
        b2_api.authorize_account("production", B2_KEY_ID, B2_APPLICATION_KEY)
    return b2_api

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
        # 1. تجميع الأجزاء
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

        # 2. الرفع إلى Backblaze B2
        if not all([B2_KEY_ID, B2_APPLICATION_KEY, B2_BUCKET_NAME]):
            raise Exception("Missing Backblaze B2 credentials. Please set B2_KEY_ID, B2_APPLICATION_KEY, and B2_BUCKET_NAME in Render.")

        b2_api = get_b2_api()
        bucket = b2_api.get_bucket_by_name(B2_BUCKET_NAME)
        
        print(f"Uploading {filename} to Backblaze B2 bucket: {B2_BUCKET_NAME}...")
        
        uploaded_file = bucket.upload_local_file(
            local_file=final_file_path,
            file_name=filename
        )
        
        print(f"========== FILE UPLOADED TO BACKBLAZE ==========")
        print(f"Filename: {filename}")
        print(f"File ID: {uploaded_file.id_}")
        print(f"================================================")

        return {"success": True}

    except Exception as e:
        print(f"Upload Error: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    finally:
        # تنظيف نهائي
        if os.path.exists(final_file_path):
            os.unlink(final_file_path)
        for f in os.listdir(TEMP_CHUNKS_DIR):
            if f.startswith(upload_id):
                try: os.unlink(os.path.join(TEMP_CHUNKS_DIR, f))
                except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
