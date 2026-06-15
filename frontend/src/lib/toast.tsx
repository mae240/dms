// Minimales Toast-System (ohne Abhaengigkeiten). Modul-Store, damit auch der
// QueryClient (MutationCache) ausserhalb von React Toasts ausloesen kann.

import { useEffect, useState } from "react";

type ToastKind = "success" | "error";

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

let counter = 0;
let items: ToastItem[] = [];
const listeners = new Set<(t: ToastItem[]) => void>();

function notify() {
  listeners.forEach((l) => l(items));
}

function remove(id: number) {
  items = items.filter((t) => t.id !== id);
  notify();
}

export function pushToast(kind: ToastKind, message: string): void {
  const id = ++counter;
  items = [...items, { id, kind, message }];
  notify();
  setTimeout(() => remove(id), 4000);
}

export const toast = {
  success: (m: string) => pushToast("success", m),
  error: (m: string) => pushToast("error", m),
};

export function ToastContainer() {
  const [list, setList] = useState<ToastItem[]>(items);
  useEffect(() => {
    listeners.add(setList);
    return () => {
      listeners.delete(setList);
    };
  }, []);
  return (
    <div className="toast-container">
      {list.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} onClick={() => remove(t.id)}>
          {t.message}
        </div>
      ))}
    </div>
  );
}
