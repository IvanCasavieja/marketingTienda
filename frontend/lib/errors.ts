// FastAPI devuelve `detail` como string cuando el error viene de un
// HTTPException explícito, pero como ARRAY de objetos de Pydantic cuando el
// rechazo pasa en la validación del schema (ej. los field_validator de
// contraseña en backend/app/schemas/auth.py) — un `toast.error(detail)` con
// ese array no muestra nada útil. Esto normaliza los dos casos a un string.
export function extractErrorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) return detail;

  if (Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown })?.msg;
    if (typeof msg === "string" && msg.trim()) {
      // Pydantic v2 antepone "Value error, " a los ValueError de field_validator
      return msg.replace(/^Value error,\s*/, "");
    }
  }

  return fallback;
}
