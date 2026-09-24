export type Toast = { id: number; text: string; alert: boolean };

export function Toasts({ items }: { items: Toast[] }) {
  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((t) => (
        <div key={t.id} className={`toast${t.alert ? " alert" : ""}`}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
