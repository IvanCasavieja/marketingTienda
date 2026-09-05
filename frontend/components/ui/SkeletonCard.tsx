export function SkeletonCard({ className = "" }: { className?: string }) {
  return <div className={`skeleton h-24 ${className}`} />;
}

/** `colSpan` debe matchear la cantidad de columnas de la tabla donde se usa
 * (ver `<th>` del `<thead>`) — es una sola fila de placeholder, no una celda
 * por columna, así que sin el colSpan correcto el layout de la tabla se
 * corre. Tiene que ser `<tr>/<td>`, no un `<div>` suelto: metido directo
 * dentro de un `<tbody>` un `<div>` es HTML inválido y React tira un
 * hydration error en la consola. */
export function SkeletonRow({ colSpan = 5 }: { colSpan?: number }) {
  return (
    <tr className="border-b border-slate-50">
      <td colSpan={colSpan} className="p-0">
        <div className="flex gap-4 px-4 py-3.5">
          <div className="skeleton h-4 w-20 rounded-md" />
          <div className="skeleton h-4 w-48 rounded-md" />
          <div className="skeleton h-4 w-16 rounded-md ml-auto" />
          <div className="skeleton h-4 w-14 rounded-md" />
          <div className="skeleton h-4 w-14 rounded-md" />
        </div>
      </td>
    </tr>
  );
}

export function SkeletonText({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-2.5">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className={`skeleton h-3.5 rounded-md ${i === lines - 1 ? "w-3/4" : "w-full"}`} />
      ))}
    </div>
  );
}
