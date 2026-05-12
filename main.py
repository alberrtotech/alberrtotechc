import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
from mega import Mega

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# جلب البيانات من Environment Variables
MEGA_EMAIL = os.environ.get("MEGA_EMAIL")
MEGA_PASSWORD = os.environ.get("MEGA_PASSWORD")

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
    try:
        chunk_path = os.path.join(TEMP_CHUNKS_DIR, f"{upload_id}_chunk_{chunk_index}.tmp")
        with open(chunk_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"success": True}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.post("/upload/complete")
def complete_upload(
    upload_id: str = Form(...),
    filename: str = Form(...)
):
    final_file_path = os.path.join(TEMP_CHUNKS_DIR, f"{upload_id}_final.tmp")
    real_file_path = os.path.join(TEMP_CHUNKS_DIR, filename)

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

        # 2. التحقق من وجود بيانات MEGA
        if not MEGA_EMAIL or not MEGA_PASSWORD:
            raise Exception("MEGA_EMAIL or MEGA_PASSWORD environment variables are missing!")

        # 3. الرفع إلى MEGA
        print(f"Attempting MEGA login for {MEGA_EMAIL}...")
        mega = Mega()
        m = mega.login(MEGA_EMAIL, MEGA_PASSWORD)
        
        print(f"Uploading to MEGA: {filename}")
        if os.path.exists(real_file_path): os.remove(real_file_path)
        os.rename(final_file_path, real_file_path)
        
        m.upload(real_file_path)
        print(f"Successfully uploaded {filename} to MEGA")

        return {"success": True}

    except Exception as e:
        print(f"CRITICAL ERROR during upload: {str(e)}")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    finally:
        # تنظيف نهائي
        for path in [final_file_path, real_file_path]:
            if os.path.exists(path):
                try: os.remove(path)
                except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
