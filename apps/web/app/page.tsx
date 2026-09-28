"use client";

import { useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { MessageView } from "./components/MessageView";
import { PipelinePanel } from "./components/PipelinePanel";
import { Sidebar } from "./components/Sidebar";
import { prettyName, TemplatePicker } from "./components/TemplatePicker";
import { ThinkingBubble } from "./components/ThinkingBubble";
import { useChatSessions } from "./hooks/useChatSessions";
import { useLibrary } from "./hooks/useLibrary";
import { requestOutline, streamAudit, uploadMaterials } from "./lib/api";
import { AUTO_TEMPLATE_OPTION, EMPTY_MATERIALS, SECTION_BREAK } from "./lib/constants";
import { errorMessage, hasMaterials, uid } from "./lib/format";
import {
  type GenerationSettings,
  type QuestionId,
  type QuestionOption,
  nextQuestion,
  questionById,
  settingsFromBrief,
  TEMPLATE_QUESTION,
} from "./lib/questions";
import type {
  GenerationRequest,
  Outline,
  OutlineReviewMessage,
  QuestionMessage,
  StageStatus,
  TaskMaterials,
} from "./lib/types";

export default function Home() {
  const [input, setInput] = useState("");
  const [materials, setMaterials] = useState<TaskMaterials>(EMPTY_MATERIALS);
  // The template question's "Выбрать шаблон" opens the picker for this chat.
  const [pickerFor, setPickerFor] = useState<{ sessionId: string; message: QuestionMessage } | null>(
    null,
  );
  const library = useLibrary();
  const {
    sessions,
    viewingId,
    setViewingId,
    viewingIdRef,
    active,
    updateSession,
    appendMessage,
    setSessionStage,
    ensureSession,
  } = useChatSessions();
  const scrollRef = useRef<HTMLDivElement>(null);

  const messages = active?.messages ?? [];
  const busy = active?.busy ?? false;
  const stages = active?.stages ?? {};

  function scrollToBottom(forSessionId: string) {
    if (viewingIdRef.current !== forSessionId) return;
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  function requestBody(
    brief: string,
    settings: GenerationSettings,
    sourceId: string,
  ): GenerationRequest {
    return {
      template_id: settings.templateId ?? library.templateId,
      brief,
      // Auto (0) lets the server derive it from the talk length (or from the
      // brief's own "---" sections); an explicit count wins over that.
      slide_count: settings.slideCount || null,
      duration_minutes: settings.duration || null,
      // "Выступления не будет" (duration 0): no speaker notes at all.
      speaker_notes: settings.duration > 0,
      mode: settings.mode || null,
      density: settings.density,
      brand_pack_id: library.packId,
      source_id: sourceId,
      text_mode: settings.textMode,
      card_split: SECTION_BREAK.test(brief) ? "input_breaks" : "auto",
    };
  }

  async function runPipeline(
    sessionId: string,
    brief: string,
    settings: GenerationSettings,
    taskMaterials: TaskMaterials,
    plan?: { sourceId: string; outline: Outline },
  ) {
    // After the plan step, reading the request and planning are already done.
    const planned: Record<string, StageStatus> = plan ? { digest: "done", outline: "done" } : {};
    updateSession(sessionId, (s) => ({ ...s, busy: true, stages: planned, startedAt: Date.now() }));
    scrollToBottom(sessionId);

    let lastStage = "parse";
    setSessionStage(sessionId, lastStage, "active");
    scrollToBottom(sessionId);

    try {
      // Materials become text on the server first (no LLM, seconds); the
      // generation request then only carries the resulting id.
      const sourceId =
        plan?.sourceId ?? (hasMaterials(taskMaterials) ? await uploadMaterials(taskMaterials) : "");
      const audit = await streamAudit(
        { ...requestBody(brief, settings, sourceId), outline: plan?.outline ?? null },
        (stage, status) => {
          lastStage = stage;
          setSessionStage(sessionId, stage, status);
          scrollToBottom(sessionId);
        },
      );
      appendMessage(sessionId, { id: uid(), kind: "audit", audit, density: settings.density });
      setSessionStage(sessionId, "ready", "done");
    } catch (e) {
      setSessionStage(sessionId, lastStage, "error");
      appendMessage(sessionId, { id: uid(), kind: "error", text: errorMessage(e) });
    } finally {
      updateSession(sessionId, (s) => ({ ...s, busy: false }));
      scrollToBottom(sessionId);
    }
  }

  // Gamma-style two-step generation, always on: the plan first, reviewed and
  // edited by the user, then the slides written for exactly that plan.
  async function startGeneration(
    sessionId: string,
    brief: string,
    settings: GenerationSettings,
    taskMaterials: TaskMaterials,
  ) {
    // Pin the template now: the plan's slide roles belong to it.
    settings = { ...settings, templateId: settings.templateId ?? library.templateId };
    updateSession(sessionId, (s) => ({ ...s, busy: true, stages: {}, startedAt: null }));
    // "Reading your materials" covers the request itself when nothing is attached.
    let current = "digest";
    setSessionStage(sessionId, current, "active");
    scrollToBottom(sessionId);
    try {
      const sourceId = hasMaterials(taskMaterials) ? await uploadMaterials(taskMaterials) : "";
      setSessionStage(sessionId, current, "done");
      current = "outline";
      setSessionStage(sessionId, current, "active");
      const outline = await requestOutline(requestBody(brief, settings, sourceId));
      setSessionStage(sessionId, current, "done");
      appendMessage(sessionId, {
        id: uid(),
        kind: "outline-review",
        brief,
        settings,
        sourceId,
        outline,
        confirmed: false,
      });
    } catch (e) {
      setSessionStage(sessionId, current, "error");
      appendMessage(sessionId, { id: uid(), kind: "error", text: errorMessage(e) });
    } finally {
      updateSession(sessionId, (s) => ({ ...s, busy: false }));
      scrollToBottom(sessionId);
    }
  }

  function handleOutlineConfirm(sessionId: string, message: OutlineReviewMessage, outline: Outline) {
    updateSession(sessionId, (s) => ({
      ...s,
      messages: s.messages.map((m) =>
        m.id === message.id && m.kind === "outline-review" ? { ...m, outline, confirmed: true } : m,
      ),
    }));
    void runPipeline(sessionId, message.brief, message.settings, EMPTY_MATERIALS, {
      sourceId: message.sourceId,
      outline,
    });
  }

  function handleSend() {
    const brief = input.trim();
    if (!brief || busy) return;
    setInput("");
    const taskMaterials = materials;
    setMaterials(EMPTY_MATERIALS);
    const id = ensureSession();
    const attached = [
      ...taskMaterials.files.map((f) => f.name),
      ...(taskMaterials.story.trim() ? ["история команды"] : []),
    ];
    appendMessage(id, {
      id: uid(),
      kind: "user",
      text: attached.length ? `${brief}\n\n📎 ${attached.join(", ")}` : brief,
    });

    askNext(id, brief, taskMaterials, settingsFromBrief(brief), []);
  }

  // Ask the next setup question in the chat, or — when all are settled —
  // go on to the plan. See lib/questions.ts for the order and defaults.
  function askNext(
    sessionId: string,
    brief: string,
    taskMaterials: TaskMaterials,
    settings: GenerationSettings,
    asked: QuestionId[],
  ) {
    const question = nextQuestion(brief, asked);
    if (!question) {
      // Last stop before generation: remind about the template if none was
      // chosen (a brand pack brings its own, so no reminder then).
      if (!library.templateChosen && !library.packId && !asked.includes(TEMPLATE_QUESTION.id)) {
        appendMessage(sessionId, {
          id: uid(),
          kind: "question",
          qid: TEMPLATE_QUESTION.id,
          prompt: TEMPLATE_QUESTION.prompt,
          options: TEMPLATE_QUESTION.options,
          answered: null,
          brief,
          materials: taskMaterials,
          settings,
          asked: [...asked, TEMPLATE_QUESTION.id],
        });
        scrollToBottom(sessionId);
        return;
      }
      void startGeneration(sessionId, brief, settings, taskMaterials);
      return;
    }
    appendMessage(sessionId, {
      id: uid(),
      kind: "question",
      qid: question.id,
      prompt: question.prompt,
      options: question.options(settings),
      answered: null,
      brief,
      materials: taskMaterials,
      settings,
      asked: [...asked, question.id],
    });
    scrollToBottom(sessionId);
  }

  // Mark a question answered and echo the answer as the user's reply.
  function markAnswered(sessionId: string, message: QuestionMessage, value: string, label: string) {
    updateSession(sessionId, (s) => ({
      ...s,
      messages: s.messages.flatMap((m) =>
        m.id === message.id && m.kind === "question"
          ? [{ ...m, answered: value }, { id: uid(), kind: "user" as const, text: label }]
          : [m],
      ),
    }));
  }

  function chooseTemplateAndGo(sessionId: string, message: QuestionMessage, templateId: string, label: string) {
    library.chooseTemplate(templateId);
    markAnswered(sessionId, message, templateId || "auto", label);
    void startGeneration(sessionId, message.brief, { ...message.settings, templateId }, message.materials);
  }

  function handleAnswer(sessionId: string, message: QuestionMessage, option: QuestionOption) {
    if (message.qid === TEMPLATE_QUESTION.id) {
      if (option.value === "pick") {
        setPickerFor({ sessionId, message });
      } else {
        chooseTemplateAndGo(sessionId, message, AUTO_TEMPLATE_OPTION, option.label);
      }
      return;
    }
    updateSession(sessionId, (s) => ({
      ...s,
      messages: s.messages.flatMap((m) =>
        m.id === message.id && m.kind === "question"
          ? [{ ...m, answered: option.value }, { id: uid(), kind: "user" as const, text: option.label }]
          : [m],
      ),
    }));
    const settings = questionById(message.qid).apply(message.settings, option.value);
    askNext(sessionId, message.brief, message.materials, settings, message.asked);
  }

  const isEmpty = messages.length === 0;
  const lastAudit = [...messages].reverse().find((m) => m.kind === "audit");
  const lastTotal = lastAudit?.kind === "audit" ? lastAudit.audit.timings?.total ?? null : null;

  return (
    <div style={{ display: "flex", height: "100vh", background: "var(--background)" }}>
      <Sidebar
        library={library}
        busy={busy}
        sessions={sessions}
        viewingId={viewingId}
        onSelectSession={setViewingId}
        materials={materials}
        onMaterialsChange={setMaterials}
      />

      {/* Main chat column */}
      <main style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "2rem" }}>
          {isEmpty ? (
            <div style={{ maxWidth: 640, margin: "4rem auto 0" }}>
              <h1 style={{ fontSize: "1.6rem", marginBottom: "0.5rem" }}>О чём должна быть презентация?</h1>
              <p style={{ color: "var(--muted)", marginBottom: "2rem" }}>
                Слева в «Дополнительных файлах» можно добавить бренд-пакет (шаблоны,
                брендбук, логотипы) и материалы: репозиторий, документацию, картинки,
                историю команды. Потом опиши повод — дальше я задам пару коротких
                вопросов. На выходе — слайды в стиле бренда и текст выступления к каждому.
              </p>
            </div>
          ) : (
            <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: "1rem" }}>
              {messages.map((m) => (
                <MessageView
                  key={m.id}
                  message={m}
                  onAnswer={
                    m.kind === "question" && m.answered === null
                      ? (option) => handleAnswer(active!.id, m, option)
                      : undefined
                  }
                  onConfirmOutline={
                    m.kind === "outline-review"
                      ? (outline) => handleOutlineConfirm(active!.id, m, outline)
                      : undefined
                  }
                />
              ))}
              {busy && <ThinkingBubble />}
            </div>
          )}
        </div>

        <Composer
          busy={busy}
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          materials={materials}
        />
      </main>

      {pickerFor && (
        <TemplatePicker
          templates={library.templates}
          currentId={library.templateId}
          autoLabel="Авто (по теме брифа)"
          uploading={library.uploading}
          onUpload={() => setPickerFor(null)}
          onChoose={(id) => {
            const chosen = library.templates.find((t) => t.id === id);
            chooseTemplateAndGo(
              pickerFor.sessionId,
              pickerFor.message,
              id,
              chosen ? `Шаблон: ${prettyName(chosen.label)}` : "Подобрать автоматически",
            );
            setPickerFor(null);
          }}
          onClose={() => setPickerFor(null)}
        />
      )}

      <PipelinePanel
        stages={stages}
        busy={busy}
        startedAt={active?.startedAt ?? null}
        lastTotal={lastTotal}
      />
    </div>
  );
}
