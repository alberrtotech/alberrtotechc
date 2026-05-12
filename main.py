import os
import shutil
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import uvicorn
import uuid
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return FileResponse("index.html")

# مجلد لتخزين الأجزاء مؤقتاً
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
        # 1. تجميع الأجزاء بالترتيب الصحيح
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

        # 2. الحصول على أفضل سيرفر من Gofile
        server_res = requests.get("https://api.gofile.io/servers")
        server_data = server_res.json()
        if server_data.get("status") != "ok":
            raise Exception("Failed to get Gofile server")
        server = server_data["data"]["servers"][0]["name"]

        # 3. رفع الملف إلى Gofile
        with open(final_file_path, "rb") as f:
            upload_res = requests.post(
                f"https://{server}.gofile.io/contents/uploadfile",
                files={"file": (filename, f)},
                timeout=600
            )

        result = upload_res.json()
        if result.get("status") == "ok":
            download_page = result["data"]["downloadPage"]
            # طباعة الرابط في سجلات السيرفر فقط (Render Logs)
            print(f"========== FILE UPLOADED ==========")
            print(f"Filename: {filename}")
            print(f"Download: {download_page}")
            print(f"===================================")
            # إرجاع نجاح بدون إظهار الرابط للمستخدم
            return {"success": True}
        else:
            raise Exception(f"Gofile upload failed: {result}")

    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

    finally:
        if os.path.exists(final_file_path):
            os.unlink(final_file_path)
        for f in os.listdir(TEMP_CHUNKS_DIR):
            if f.startswith(upload_id):
                try: os.unlink(os.path.join(TEMP_CHUNKS_DIR, f))
                except: pass

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
