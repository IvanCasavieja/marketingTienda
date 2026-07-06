from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


async def read_limited(file: UploadFile, label: str = "archivo") -> bytes:
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"El {label} supera el límite de 50 MB ({len(data) // (1024*1024)} MB recibidos)"
        )
    return data
