"use client";

import { useEffect, useState } from "react";

// A visual explainer of the real generation pipeline: what each stage does,
// which model runs it, and how the 5-minute budget (packages/server's
// GENERATION_BUDGET_SECONDS) is actually split between them. Every number
// and model name here is read from the same constants and skill configs the
// server itself uses (apps/server/src/server/main.py, skills/*/config.yaml)
// — this page explains the system, it doesn't invent one.

type StageKind = "client" | "deterministic" | "model";

type Stage = {
  key: string;
  title: string;
  kind: StageKind;
  // Share of the 300s budget this stage's cap represents, for the bar and
  // the auto-play timing — not a promise that a real run takes this long.
  shareSeconds: number;
  what: string;
  detail: string[];
};

const KIND_COLOR: Record<StageKind, string> = {
  client: "#737373",
  deterministic: "#4da3ff",
  model: "#ff5c8a",
};

const KIND_LABEL: Record<StageKind, string> = {
  client: "клиент, без сети",
  deterministic: "код, без LLM",
  model: "вызов модели",
};

const STAGES: Stage[] = [
  {
    key: "materials",
    title: "Бриф и материалы",
    kind: "client",
    shareSeconds: 0,
    what: "Пользователь описывает презентацию текстом и (по желанию) прикладывает репозиторий, документы или картинки.",
    detail: [
      "Ничего не уходит на сервер, пока не нажата «Отправить»",
      "Репозиторий распаковывается и фильтруется на сервере: README, манифесты, дерево файлов — не весь код",
    ],
  },
  {
    key: "parse",
    title: "Разбор шаблона",
    kind: "deterministic",
    shareSeconds: 1,
    what: "python-pptx читает выбранный .pptx и строит внутреннее представление: шрифты, цвета, сетку макетов, роли фигур на каждом слайде.",
    detail: [
      "Без LLM — чистый разбор XML/OOXML",
      "Результат кэшируется по хэшу файла, повторный разбор того же шаблона — мгновенный",
      "На этом же представлении работает инспектор шаблона (роли: заголовок/текст/карточка/картинка/…)",
    ],
  },
  {
    key: "digest",
    title: "Дайджест источников",
    kind: "model",
    shareSeconds: 75,
    what: "Если приложены материалы — модель сжимает их в короткий фактлист (что за проект, проблема, решение, цифры, команда), который дальше служит единственным брифом для генерации.",
    detail: [
      "Скилл source-digest → generator.ingest.facts.FactSheet",
      "Бюджет: до 75 с; пропускается целиком, если материалов нет",
      "Не успел уложиться в срок — в брифе используются сырые материалы напрямую, шаг не блокирует пайплайн",
    ],
  },
  {
    key: "outline",
    title: "План презентации",
    kind: "model",
    shareSeconds: 75,
    what: "Модель раскладывает бриф на слайды: для каждого — роль (макет из каталога шаблона), интонация и о чём он. План можно поправить руками перед генерацией текста.",
    detail: [
      "Скилл outline-generation",
      "Бюджет: до 75 с, но никогда не отнимает у следующего шага меньше 120 с",
      "Первый слайд принудительно ставится на обложку шаблона, а не на случайный макет",
      "Роль, которую модель не узнала, детерминированно сводится к ближайшей из каталога — пайплайн не падает на её ошибке",
    ],
  },
  {
    key: "content",
    title: "Текст слайдов",
    kind: "model",
    shareSeconds: 149,
    what: "По одному вызову на слайд (параллельно) модель пишет заголовок, буллеты и текст выступления — под реальную вместимость именно той фигуры шаблона, куда это ляжет.",
    detail: [
      "Скилл slide-content, лимиты символов и слов берутся из геометрии фигуры на шаблоне",
      "Получает весь оставшийся бюджет — гарантированно не меньше 120 с",
      "Число/факт, которого нет в брифе — под подозрением: точечный ремонт (skills/text-fix) переписывает только сломанную строку, до 2 заходов, иначе строка вырезается",
    ],
  },
  {
    key: "layout",
    title: "Вёрстка — 3 варианта",
    kind: "deterministic",
    shareSeconds: 0.4,
    what: "Текст раскладывается на копии слайдов шаблона сразу в трёх версиях плотности (сжато/стандарт/подробно); шрифт, который не влез в рамку, ужимается по типографической шкале самого шаблона.",
    detail: [
      "Без LLM: правила сопоставления фигур + автоподгонка размера",
      "Фото ищутся один раз на слайд и переиспользуются во всех трёх вариантах",
      "Шаблонные стоковые фото, не подошедшие под тему, заменяются на плоский цвет — не остаются в готовой колоде",
    ],
  },
  {
    key: "audit",
    title: "Аудит",
    kind: "deterministic",
    shareSeconds: 0.3,
    what: "Каждый из трёх вариантов проверяется набором детерминированных правил — выход за границы, наложения текста, плотность, шрифты не из шаблона, выдуманные цифры и другое.",
    detail: [
      "15 категорий проверок, без LLM — см. полный список ниже",
      "Диапазон плотности слайда берётся из самого шаблона, а не задан числом",
      "11 более субъективных проверок (логика, связность, релевантность фото) описаны в AUDIT.md, но пока не подключены как автоматический шаг",
    ],
  },
  {
    key: "export",
    title: "Экспорт и превью",
    kind: "client",
    shareSeconds: 0,
    what: "Итоговый .pptx собирается прямо из файла шаблона — не с нуля, поэтому фон, мастер-слайды и тема переживают экспорт. Предпросмотр в интерфейсе — это и есть тот же файл, отрисованный в браузере.",
    detail: [
      "Каждый слайд копируется из шаблона; меняются только текст, фото, таблицы и размер шрифта",
      "Предпросмотр не требует LibreOffice или другого стороннего ПО на сервере — работает где угодно",
      "Тот же принцип и в выборе шаблона: если сервер не умеет рендерить обложки, картинка рисуется в браузере",
    ],
  },
];

const TOTAL_BUDGET = 300; // GENERATION_BUDGET_SECONDS, apps/server/src/server/main.py

// The real fallback chain each LLM call goes through — see any skill's
// config.yaml `fallback_models`. Same chain everywhere; shown once.
const MODEL_CHAIN = [
  { name: "qwen3-30b-a3b-instruct-2507", note: "основная, платная" },
  { name: "qwen3.8-27b", note: "бесплатная" },
  { name: "gemma-4-31b-it", note: "бесплатная" },
  { name: "nemotron-3-ultra-550b-a55b", note: "бесплатная" },
  { name: "glm-5.2", note: "бесплатная" },
  { name: "dots-3-note-preview", note: "бесплатная" },
  { name: "gemma-4-26b-a4b-it", note: "бесплатная" },
  { name: "nemotron-3-super-120b-a12b", note: "бесплатная" },
];

const FAILURE_TRIGGERS = ["нет баланса (402)", "модель снята (404)", "лимит (429)", "5xx", "таймаут"];

const DETERMINISTIC_CHECKS: { group: string; items: string[] }[] = [
  {
    group: "Геометрия",
    items: [
      "текст или таблица вышли за границы слайда",
      "два текстовых элемента наложились друг на друга",
      "текст не поместился в свою рамку",
      "элементы не выровнены по направляющим макета",
      "картинка растянута, пропорции нарушены",
    ],
  },
  {
    group: "Стиль шаблона",
    items: [
      "шрифт не из набора шаблона",
      "кегль не из типографической шкалы шаблона",
      "цвет не из палитры шаблона",
      "слайд собран не на макете из шаблона",
    ],
  },
  {
    group: "Плотность",
    items: [
      "больше 6 буллетов на слайде",
      "буллет длиннее 15 слов",
      "таблица больше 7 строк или 5 колонок",
      "заполнение слайда плотнее или реже, чем когда-либо в самом шаблоне",
    ],
  },
  {
    group: "Целостность",
    items: [
      "остался текст-заглушка (lorem ipsum, XXX, TODO)",
      "пустой слайд или слайд с одним заголовком",
      "два слайда дублируют друг друга",
      "цифра/факт на слайде, которого нет в исходном брифе",
    ],
  },
];

const MODEL_CHECKS = [
  "заголовок содержит вывод, а не просто называет тему",
  "содержимое слайда соответствует заголовку",
  "слайд пересказывается одним предложением",
  "каждая цифра прослеживается до исходных материалов",
  "есть реальный контент, не только заголовок",
  "картинки/иконки относятся к теме слайда",
  "нет служебного мусора: реплик спикера, кусков промпта",
  "нет опечаток",
  "вся колода на одном языке",
  "каждая строка таблицы работает на мысль слайда",
  "соседние слайды связаны логически",
];

const AUTONOMY_CARDS = [
  {
    title: "Работает без стороннего ПО",
    body: "Предпросмотр — это тот же .pptx, отрисованный в браузере библиотекой pptx-preview, а не картинка с сервера. Демо не ломается от того, что на машине нет LibreOffice.",
  },
  {
    title: "Не заточено под 5 образцов",
    body: "Каталог макетов, роли фигур и границы плотности каждый раз считаются заново с чистого листа по загруженному файлу — по условиям задачи система обязана работать на шаблоне, которого не видела.",
  },
  {
    title: "Отказ модели не роняет генерацию",
    body: "Любой шаг с LLM проходит по цепочке из 8 моделей и укладывается в дедлайн; пропуск дайджеста, ремонт текста и отказ от галлюцинированной роли макета — то же самое: деградируем, а не падаем.",
  },
];

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

// Auto-play speed: the whole ~300s budget plays out in this many real ms,
// so the wow-effect demo doesn't make anyone wait five minutes.
const PLAY_DURATION_MS = 16000;

export default function AdminPage() {
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [elapsed, setElapsed] = useState(0);

  const cumulative: number[] = [];
  let acc = 0;
  for (const s of STAGES) {
    cumulative.push(acc);
    acc += s.shareSeconds;
  }
  const totalShare = acc;

  useEffect(() => {
    if (!playing) return;
    const start = performance.now() - (elapsed / totalShare) * PLAY_DURATION_MS;
    let frame: number;
    function tick(now: number) {
      const t = (now - start) / PLAY_DURATION_MS;
      const simSeconds = Math.min(totalShare, t * totalShare);
      setElapsed(simSeconds);
      let idx = 0;
      for (let i = 0; i < STAGES.length; i++) {
        if (simSeconds >= cumulative[i]!) idx = i;
      }
      setActive(idx);
      if (t < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        setPlaying(false);
      }
    }
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);

  function replay() {
    setElapsed(0);
    setActive(0);
    setPlaying(true);
  }

  const stage = STAGES[active]!;
  // Real budget seconds this stage's animated share maps to (0/1/0.4/0.3 are
  // illustrative for the instant deterministic steps, not real caps).
  const realBudgetLabel: Record<string, string> = {
    materials: "мгновенно",
    parse: "< 1 с",
    digest: "до 75 с, если есть материалы",
    outline: "до 75 с",
    content: "весь остаток, минимум 120 с",
    layout: "< 1 с",
    audit: "< 1 с",
    export: "мгновенно, в браузере",
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "var(--background)",
        color: "var(--foreground)",
        padding: "2.5rem 1.5rem 5rem",
      }}
    >
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <a
          href="/"
          style={{ fontSize: "0.8rem", color: "var(--muted)", textDecoration: "none" }}
        >
          ← вернуться к генератору
        </a>

        <h1 style={{ fontSize: "2rem", fontWeight: 700, margin: "0.75rem 0 0.4rem" }}>
          Как работает генерация
        </h1>
        <p style={{ color: "var(--muted)", fontSize: "0.95rem", maxWidth: 640, lineHeight: 1.5 }}>
          От брифа до готового .pptx — реальные шаги пайплайна, реальные модели и реальный
          бюджет времени: 5 минут на генерацию, ни секунды больше.
        </p>

        {/* Pipeline diagram */}
        <div style={{ marginTop: "2.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <div style={{ fontSize: "0.75rem", color: "var(--muted)", textTransform: "uppercase" }}>
              Пайплайн одного запроса
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <span style={{ fontSize: "0.78rem", color: "var(--muted)", fontVariantNumeric: "tabular-nums" }}>
                {fmtTime(elapsed)} / {fmtTime(totalShare)} · ускорено ×{Math.round((totalShare * 1000) / PLAY_DURATION_MS)}
              </span>
              <button onClick={playing ? () => setPlaying(false) : replay} style={playButton}>
                {playing ? "Пауза" : "Смотреть заново"}
              </button>
            </div>
          </div>

          <div
            style={{
              display: "flex",
              alignItems: "stretch",
              overflowX: "auto",
              paddingBottom: "0.5rem",
              gap: 0,
            }}
          >
            {STAGES.map((s, i) => (
              <div key={s.key} style={{ display: "flex", alignItems: "center", flex: "0 0 auto" }}>
                <button
                  onClick={() => {
                    setPlaying(false);
                    setActive(i);
                  }}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: "0.5rem",
                    width: 90,
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: "0.25rem",
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: "50%",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "0.8rem",
                      fontWeight: 700,
                      border: `2px solid ${KIND_COLOR[s.kind]}`,
                      background: i === active ? KIND_COLOR[s.kind] : "transparent",
                      color: i === active ? "#0a0a0a" : KIND_COLOR[s.kind],
                      animation: i === active ? "node-glow 1.6s ease-out infinite" : "none",
                      transition: "background 0.25s, color 0.25s",
                    }}
                  >
                    {i + 1}
                  </span>
                  <span
                    style={{
                      fontSize: "0.72rem",
                      textAlign: "center",
                      lineHeight: 1.25,
                      color: i === active ? "var(--foreground)" : "var(--muted)",
                      fontWeight: i === active ? 600 : 400,
                    }}
                  >
                    {s.title}
                  </span>
                </button>
                {i < STAGES.length - 1 && (
                  <div
                    style={{
                      width: 16,
                      height: 2,
                      background: "var(--border)",
                      position: "relative",
                      overflow: "hidden",
                      flexShrink: 0,
                      marginBottom: "1.7rem",
                    }}
                  >
                    {i < active && <div style={{ position: "absolute", inset: 0, background: KIND_COLOR[s.kind] }} />}
                    {i === active && playing && (
                      <div
                        style={{
                          position: "absolute",
                          inset: 0,
                          background: `linear-gradient(90deg, transparent, ${KIND_COLOR[s.kind]}, transparent)`,
                          animation: "flow-move 1s linear infinite",
                        }}
                      />
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Active stage detail */}
          <div key={stage.key} style={{ ...card, marginTop: "1.25rem", animation: "fade-in-up 0.25s ease-out" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.5rem" }}>
              <span
                style={{
                  fontSize: "0.68rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.03em",
                  color: KIND_COLOR[stage.kind],
                  border: `1px solid ${KIND_COLOR[stage.kind]}`,
                  borderRadius: 4,
                  padding: "0.1rem 0.4rem",
                }}
              >
                {KIND_LABEL[stage.kind]}
              </span>
              <span style={{ fontSize: "0.78rem", color: "var(--muted)" }}>
                {realBudgetLabel[stage.key]}
              </span>
            </div>
            <div style={{ fontSize: "1.05rem", fontWeight: 700, marginBottom: "0.4rem" }}>{stage.title}</div>
            <p style={{ fontSize: "0.88rem", lineHeight: 1.55, color: "var(--foreground)", marginBottom: "0.6rem" }}>
              {stage.what}
            </p>
            <ul style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
              {stage.detail.map((d) => (
                <li key={d} style={{ fontSize: "0.8rem", color: "var(--muted)", lineHeight: 1.5 }}>
                  {d}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Budget rule */}
        <Section title="Как делится бюджет">
          <p style={{ fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.6, marginBottom: "0.9rem" }}>
            Правило зашито в коде, не подобрано на глаз: дайджест и план получают не больше 75 с
            каждый, но что бы ни случилось — на текст слайдов всегда остаётся минимум 120 с из
            общих пяти минут.
          </p>
          <div style={{ display: "flex", height: 28, borderRadius: 6, overflow: "hidden", border: "1px solid var(--border)" }}>
            {[
              { label: "Дайджест", seconds: 75, color: "#ff5c8a" },
              { label: "План", seconds: 75, color: "#e8c547" },
              { label: "Текст слайдов", seconds: 150, color: "#3ddc97" },
            ].map((b) => (
              <div
                key={b.label}
                title={`${b.label}: до ${b.seconds} с`}
                style={{
                  width: `${(b.seconds / TOTAL_BUDGET) * 100}%`,
                  background: b.color,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  color: "#0a0a0a",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                }}
              >
                {b.label}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--muted)", marginTop: "0.3rem" }}>
            <span>0:00</span>
            <span>5:00 — жёсткий предел</span>
          </div>
        </Section>

        {/* Model chain */}
        <Section title="Цепочка моделей на каждом вызове">
          <p style={{ fontSize: "0.85rem", color: "var(--muted)", lineHeight: 1.6, marginBottom: "1rem" }}>
            Любой шаг с LLM пробует модели по очереди, пока одна не ответит. Переход дальше по
            цепочке: {FAILURE_TRIGGERS.join(", ")}.
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            {MODEL_CHAIN.map((m, i) => (
              <div key={m.name} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <div
                  style={{
                    border: `1px solid ${i === 0 ? "#e8c547" : "var(--border)"}`,
                    borderRadius: 8,
                    padding: "0.4rem 0.65rem",
                    fontSize: "0.75rem",
                    background: i === 0 ? "rgba(232,197,71,0.08)" : "#111",
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{m.name}</div>
                  <div style={{ color: "var(--muted)", fontSize: "0.68rem" }}>{m.note}</div>
                </div>
                {i < MODEL_CHAIN.length - 1 && <span style={{ color: "var(--muted)" }}>→</span>}
              </div>
            ))}
          </div>
        </Section>

        {/* Audit */}
        <Section title="Аудит результата">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.6rem" }}>
                <span style={dotStyle("#4da3ff")} />
                <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>Работает сегодня · без LLM</span>
              </div>
              {DETERMINISTIC_CHECKS.map((g) => (
                <div key={g.group} style={{ marginBottom: "0.7rem" }}>
                  <div style={{ fontSize: "0.72rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "0.25rem" }}>
                    {g.group}
                  </div>
                  <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                    {g.items.map((it) => (
                      <li key={it} style={{ fontSize: "0.78rem", lineHeight: 1.5, color: "var(--foreground)" }}>
                        {it}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.6rem" }}>
                <span style={dotStyle("#737373")} />
                <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>В разработке · нужна VLM</span>
              </div>
              <p style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.5, marginBottom: "0.5rem" }}>
                Описаны в AUDIT.md, но ещё не подключены как автоматический шаг пайплайна —
                судит модель по картинке слайда:
              </p>
              <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                {MODEL_CHECKS.map((it) => (
                  <li key={it} style={{ fontSize: "0.78rem", lineHeight: 1.6, color: "var(--muted)" }}>
                    {it}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </Section>

        {/* Autonomy */}
        <Section title="Почему это не ломается на демонстрации">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem" }}>
            {AUTONOMY_CARDS.map((c) => (
              <div key={c.title} style={card}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem", marginBottom: "0.4rem" }}>{c.title}</div>
                <div style={{ fontSize: "0.78rem", color: "var(--muted)", lineHeight: 1.55 }}>{c.body}</div>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: "3rem" }}>
      <div style={{ fontSize: "0.75rem", color: "var(--muted)", textTransform: "uppercase", marginBottom: "1rem" }}>
        {title}
      </div>
      {children}
    </div>
  );
}

const card: React.CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "1.1rem",
  background: "#111",
};

const playButton: React.CSSProperties = {
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--foreground)",
  padding: "0.3rem 0.7rem",
  fontSize: "0.75rem",
  cursor: "pointer",
};

function dotStyle(color: string): React.CSSProperties {
  return { width: 8, height: 8, borderRadius: "50%", background: color, display: "inline-block" };
}
