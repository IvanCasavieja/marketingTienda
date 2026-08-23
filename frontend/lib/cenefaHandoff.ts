// Traspaso del Excel convertido, del Convertidor al generador de cenefas.
//
// Viaja por sessionStorage y no por la URL ni por el server: es un archivo
// (no entra en un query param) y vive treinta segundos, así que persistirlo
// server-side pediría una tabla temporal y su limpieza para nada. Lo escribe
// ConvertidorGrid y lo lee -- borrándolo -- materiales/cenefas/page.tsx.

export const CONVERTIDOR_HANDOFF_KEY = "cenefas.excelConvertido";

const NOMBRE_ARCHIVO = "convertidor_cenefas.xlsx";
const MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

export async function guardarExcelParaCenefa(blob: Blob): Promise<void> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binario = "";
  // De a pedazos: con varios miles de filas, String.fromCharCode(...bytes) de
  // una sola vez revienta el stack por exceso de argumentos.
  for (let i = 0; i < bytes.length; i += 8192) {
    binario += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  sessionStorage.setItem(
    CONVERTIDOR_HANDOFF_KEY,
    JSON.stringify({ nombre: NOMBRE_ARCHIVO, b64: btoa(binario) }),
  );
}

export function tomarExcelConvertido(): File | null {
  try {
    const raw = sessionStorage.getItem(CONVERTIDOR_HANDOFF_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(CONVERTIDOR_HANDOFF_KEY);
    const { nombre, b64 } = JSON.parse(raw) as { nombre: string; b64: string };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    return new File([bytes], nombre || NOMBRE_ARCHIVO, { type: MIME_XLSX });
  } catch {
    // sessionStorage bloqueado, JSON roto o base64 inválido: se sigue sin
    // archivo precargado, que es el flujo normal de carga manual.
    return null;
  }
}
