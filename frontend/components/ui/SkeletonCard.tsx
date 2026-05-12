export function SkeletonCard({ className = "" }: { className?: string }) {
  return <div className={`skeleton h-24 ${className}`} />;
}

export function SkeletonRow() {
  return (
    <div className="flex gap-4 px-4 py-3.5 border-b border-slate-50">
      <div className="skeleton h-4 w-20 rounded-md" />
      <div className="skeleton h-4 w-48 rounded-md" />
      <div className="skeleton h-4 w-16 rounded-md ml-auto" />
      <div className="skeleton h-4 w-14 rounded-md" />
      <div className="skeleton h-4 w-14 rounded-md" />
    </div>
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
