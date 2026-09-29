import { useCallback, useEffect, useState } from "react";
import { fetchHistory, fetchHistoryRecord } from "../lib/api";
import { uid } from "../lib/format";
import type { ChatSession, Density, HistoryItem } from "../lib/types";

// Whether an S3 bucket is connected, and the generations kept in it. Without
// one nothing outlives the page — the app says so (see StorageNotice).
export function useStorage() {
  const [connected, setConnected] = useState<boolean | null>(null);
  const [items, setItems] = useState<HistoryItem[]>([]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetchHistory();
      setConnected(r.connected);
      setItems(r.items);
    } catch {
      setConnected((c) => c ?? false); // unreachable bucket: treated as not saving
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // A saved generation as a chat: its brief, then the finished result.
  async function openRecord(id: string): Promise<ChatSession> {
    const record = await fetchHistoryRecord(id);
    const brief = record.request.brief ?? "Сохранённая презентация";
    const density = (["compact", "standard", "detailed"].includes(record.request.density ?? "")
      ? record.request.density
      : "standard") as Density;
    return {
      id: `saved-${id}`,
      title: brief.length > 40 ? brief.slice(0, 40) + "…" : brief,
      messages: [
        { id: uid(), kind: "user", text: brief },
        { id: uid(), kind: "audit", audit: record.result, density, brief },
      ],
      busy: false,
      stages: {},
      startedAt: null,
    };
  }

  return { connected, items, refresh, openRecord };
}
