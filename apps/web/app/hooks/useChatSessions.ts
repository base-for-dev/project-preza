import { useEffect, useRef, useState } from "react";
import { sessionTitle, uid } from "../lib/format";
import type { ChatSession, Message, StageStatus } from "../lib/types";

// Each chat owns its own messages/busy/stages — a generation started for
// one session writes into that session by id, never into "whatever's on
// screen right now", so switching chats mid-generation can't bleed one
// chat's output into another's history.
export function useChatSessions() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [viewingId, setViewingId] = useState<string | null>(null);
  // Read by long-running async flows that must know which chat is on
  // screen *now*, not when they started.
  const viewingIdRef = useRef<string | null>(null);

  useEffect(() => {
    viewingIdRef.current = viewingId;
  }, [viewingId]);

  const active = sessions.find((s) => s.id === viewingId) ?? null;

  function updateSession(id: string, updater: (s: ChatSession) => ChatSession) {
    setSessions((prev) => prev.map((s) => (s.id === id ? updater(s) : s)));
  }

  function appendMessage(id: string, msg: Message) {
    updateSession(id, (s) => {
      const nextMessages = [...s.messages, msg];
      const title = s.messages.length === 0 && msg.kind === "user" ? sessionTitle(nextMessages) : s.title;
      return { ...s, messages: nextMessages, title };
    });
  }

  function setSessionStage(id: string, key: string, status: StageStatus) {
    updateSession(id, (s) => ({ ...s, stages: { ...s.stages, [key]: status } }));
  }

  // The chat on screen, or a fresh one if the user is on "new session".
  function ensureSession(): string {
    let id = viewingId;
    if (!id) {
      id = uid();
      setSessions((prev) => [
        { id: id!, title: "Новый чат", messages: [], busy: false, stages: {}, startedAt: null },
        ...prev,
      ]);
      setViewingId(id);
    }
    return id;
  }

  // A chat restored from storage: shown at the top and opened.
  function addSession(session: ChatSession) {
    setSessions((prev) => [session, ...prev.filter((s) => s.id !== session.id)]);
    setViewingId(session.id);
  }

  return {
    addSession,
    sessions,
    viewingId,
    setViewingId,
    viewingIdRef,
    active,
    updateSession,
    appendMessage,
    setSessionStage,
    ensureSession,
  };
}
