from fastapi import HTTPException, UploadFile

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


async def read_limited(file: UploadFile, sujeto: str = "El archivo") -> bytes:
    """Los bytes del archivo subido, con el tope global de 50 MB.

    `sujeto` es cómo se lo nombra en el mensaje, CON su artículo ("El Excel",
    "La planilla"): antes se armaba acá como "El {label}" y el que sube una
    planilla de 60 MB leía "El mailing supera el límite", o sea un mensaje sobre
    un archivo que no existe en su pantalla. El artículo no lo puede poner esta
    función porque no todas las fuentes son masculinas -- y quien llama ya sabe
    qué subió."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"{sujeto} supera el límite de 50 MB ({len(data) // (1024*1024)} MB recibidos)"
        )
    return data
