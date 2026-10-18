const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const learning = require("../app/web/static/learning.js");

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
  };
}

const catalog = [{
  id: "monopoly", title: "Монополия", subtopics: [{
    id: "elasticity", title: "Эластичность", knowledge: [{ id: "monopoly.lerner", title: "Индекс Лернера" }],
  }],
}];

test("local history survives a read/write cycle and recovers malformed storage", () => {
  const storage = memoryStorage();
  const store = learning.emptyStore();
  store.sessions.push({ id: "s1", questionIds: ["q1"], attempts: [], status: "in_progress" });
  store.activeSessionId = "s1";
  store.lastRoute = { view: "quizzes" };
  assert.equal(learning.writeStore(store, storage), true);
  assert.deepEqual(learning.readStore(storage), store);
  const malformed = memoryStorage({ [learning.STORAGE_KEY]: "not json" });
  assert.equal(learning.readStore(malformed).sessions.length, 0);
  assert.equal(learning.readStore(malformed).warning, true);
});

test("statistics count completed sessions separately and rank errors with denominators", () => {
  const store = {
    version: 1, activeSessionId: "active", lastRoute: null,
    sessions: [
      { id: "done", status: "completed", startedAt: "2026-10-17T10:00:00.000Z", endedAt: "2026-10-17T10:04:00.000Z", context: { label: "Монополия" }, questionIds: ["q1", "q2"], attempts: [
        { questionId: "q1", themeId: "monopoly", subtopicId: "elasticity", constructionId: "monopoly.lerner", verdict: "incorrect", answeredAt: "2026-10-17T10:01:00.000Z" },
        { questionId: "q2", themeId: "monopoly", subtopicId: "elasticity", constructionId: "monopoly.lerner", verdict: "correct", answeredAt: "2026-10-17T10:02:00.000Z" },
      ] },
      { id: "active", status: "in_progress", startedAt: "2026-10-18T10:00:00.000Z", context: { label: "Квиз" }, questionIds: ["q3"], attempts: [
        { questionId: "q3", themeId: "monopoly", subtopicId: "elasticity", verdict: "incorrect", answeredAt: "2026-10-18T10:01:00.000Z" },
      ] },
    ],
  };
  const summary = learning.summarize(store, catalog);
  assert.equal(summary.startedQuizzes, 2);
  assert.equal(summary.completedQuizzes, 1);
  assert.equal(summary.incompleteQuizzes, 1);
  assert.equal(summary.completed.answered, 2);
  assert.equal(summary.completed.correct, 1);
  assert.equal(summary.completed.incorrect, 1);
  assert.equal(summary.completed.percent, 50);
  assert.equal(summary.active.id, "active");
  assert.equal(summary.problemSubtopics[0].incorrect, 1);
  assert.equal(summary.problemSubtopics[0].determinate, 2);
  assert.equal(summary.problemConstructions[0].id, "monopoly.lerner");
  assert.equal(summary.trainedThemeCount, 1);
});

test("empty history never produces a fake zero-percent result", () => {
  const summary = learning.summarize(learning.emptyStore(), catalog);
  assert.equal(summary.completed.percent, null);
  assert.equal(summary.completedQuizzes, 0);
  assert.equal(summary.lastAttempt, null);
  assert.deepEqual(summary.problemSubtopics, []);
});

test("date formatter degrades safely for stale timestamps", () => {
  assert.equal(learning.formatDate("not a date"), "—");
});

test("local review uses unique questions with the latest confirmed outcome", () => {
  const store = {
    sessions: [
      { id: "old", startedAt: "2026-10-17T10:00:00.000Z", attempts: [
        { questionId: "q-wrong", verdict: "incorrect", answeredAt: "2026-10-17T10:01:00.000Z" },
        { questionId: "q-fixed", verdict: "incorrect", answeredAt: "2026-10-17T10:02:00.000Z" },
        { questionId: "q-uncertain", verdict: "incorrect", answeredAt: "2026-10-17T10:03:00.000Z" },
      ] },
      { id: "new", startedAt: "2026-10-18T10:00:00.000Z", attempts: [
        { questionId: "q-wrong", verdict: "incorrect", answeredAt: "2026-10-18T10:01:00.000Z" },
        { questionId: "q-fixed", verdict: "correct", answeredAt: "2026-10-18T10:02:00.000Z" },
        { questionId: "q-uncertain", verdict: "uncertain", answeredAt: "2026-10-18T10:03:00.000Z" },
        { questionId: "q-uncertain", verdict: "incorrect", answeredAt: "2026-10-18T10:04:00.000Z" },
        { questionId: "unknown-verdict", verdict: "partial", answeredAt: "2026-10-18T10:05:00.000Z" },
      ] },
    ],
  };
  assert.deepEqual(learning.reviewQuestionIds(store), ["q-wrong", "q-uncertain"]);
  assert.deepEqual(learning.reviewQuestionIds({ sessions: [] }), []);
});

test("unanswered local sessions and their attempts survive page reload", () => {
  const storage = memoryStorage();
  const session = {
    id: "unfinished", status: "in_progress", local: true,
    context: { type: "theme", themeId: "monopoly", label: "Монополия" },
    questionIds: ["monopoly.q1", "monopoly.q2"], currentIndex: 0,
    current: { selectedAnswer: "2", answered: true, result: { verdict: "incorrect" } },
    attempts: [{ questionId: "monopoly.q1", verdict: "incorrect", answeredAt: "2026-10-18T10:00:00.000Z" }],
  };
  const store = { ...learning.emptyStore(), sessions: [session], activeSessionId: session.id, lastRoute: { view: "quizzes" } };
  assert.equal(learning.writeStore(store, storage), true);
  const restored = learning.readStore(storage);
  assert.equal(restored.activeSessionId, session.id);
  assert.equal(restored.sessions[0].local, true);
  assert.equal(restored.sessions[0].current.selectedAnswer, "2");
  assert.deepEqual(learning.reviewQuestionIds(restored), ["monopoly.q1"]);
});

function createQuizHarness({ answerMode = "local", storage = memoryStorage(), failSession = false } = {}) {
  class Element {
    constructor(dataset = {}, value = "") { this.dataset = dataset; this.value = value; this.handlers = {}; }
    addEventListener(name, handler) { this.handlers[name] = handler; }
  }
  const elementCache = new Map();
  const content = {
    html: "",
    set innerHTML(value) { this.html = value; },
    get innerHTML() { return this.html; },
    querySelectorAll(selector) {
      let matches = [];
      if (selector === "[data-action]") {
        matches = [...this.html.matchAll(/data-action="([^"]+)"/g)].map((match) => ({ action: match[1] }));
      }
      else if (selector === "[data-theme]") {
        matches = [...this.html.matchAll(/data-theme="([^"]+)"/g)].map((match) => ({ theme: match[1] }));
      }
      else if (selector === "[data-view]") {
        matches = [...this.html.matchAll(/data-view="([^"]+)"/g)].map((match) => ({ view: match[1] }));
      }
      return matches.map((dataset) => {
        const key = `${selector}:${this.html}:${Object.values(dataset).join(":")}`;
        if (!elementCache.has(key)) elementCache.set(key, new Element(dataset));
        return elementCache.get(key);
      });
    },
  };
  const nav = {
    html: "",
    set innerHTML(value) { this.html = value; },
    get innerHTML() { return this.html; },
    querySelectorAll(selector) {
      if (selector !== "a") return [];
      return [...this.html.matchAll(/data-view="([^"]+)"/g)].map((match) => {
        const key = `nav:${this.html}:${match[1]}`;
        if (!elementCache.has(key)) elementCache.set(key, new Element({ view: match[1] }));
        return elementCache.get(key);
      });
    },
  };
  const theme = {
    id: "monopoly", title: "Монополия", description: "Тестовая тема", question_count: 2,
    documents: [], subtopics: [{
      id: "basics", title: "Основы", knowledge: [],
      questions: [0, 1].map((index) => ({
        id: `monopoly.q${index + 1}`, question: `Вопрос ${index + 1}?`, difficulty: 1,
        category: "theory", knowledge_id: "monopoly.basics",
        options: ["A", "B", "C", "D"].map((text, option) => ({ id: String(option), text })),
        reference_answer: "A", explanation: "Пояснение", source_excerpt: "Источник",
      })),
    }],
  };
  const requests = [];
  const controls = { themeKind: "all", themeCount: "1", quizTheme: "all", quizKind: "all", quizCount: "1" };
  const response = (payload, status = 200) => ({ ok: status < 400, status, json: async () => payload });
  const fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url === "/api/theory") return response({ themes: [theme] });
    if (url === "/api/progress") return response({ available: answerMode === "database", answer_mode: answerMode, themes: {} });
    if (url === "/api/quiz-sessions") return failSession
      ? response({ error: "Database unavailable" }, 503)
      : response({ session_id: 77 }, 201);
    if (url === "/api/answer") return response({
      verdict: JSON.parse(options.body).answer === "0" ? "correct" : "incorrect",
      score: JSON.parse(options.body).answer === "0" ? 1 : 0,
      reference_answer: "A", explanation: "Пояснение", short_explanation: "Проверено",
      source_excerpt: "Источник", progress_saved: JSON.parse(options.body).mode !== "local",
    });
    if (url === "/api/quiz-sessions/77/complete") return response({ total: 1, correct: 1 });
    throw new Error(`Unexpected fetch: ${url}`);
  };
  const selected = { value: "" };
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (selector === "#content") return content;
      if (selector === "#navigation") return nav;
      if (selector === "#progress-storage-status") return elements.get(selector) || (elements.set(selector, { textContent: "" }), elements.get(selector));
      if (selector === 'input[name="answer"]:checked') return selected.value ? selected : null;
      if (selector === "#answer-form" && content.html.includes('id="answer-form"')) {
        const key = `form:${content.html}`;
        if (!elementCache.has(key)) elementCache.set(key, new Element());
        return elementCache.get(key);
      }
      if (selector === "#theme-quiz-kind") return { get value() { return controls.themeKind; }, set value(value) { controls.themeKind = value; } };
      if (selector === "#theme-quiz-count") return { get value() { return controls.themeCount; }, set value(value) { controls.themeCount = value; } };
      if (selector === "#quiz-kind") return { get value() { return controls.quizKind; }, set value(value) { controls.quizKind = value; } };
      if (selector === "#quiz-count") return { get value() { return controls.quizCount; }, set value(value) { controls.quizCount = value; } };
      if (selector === "#quiz-theme") return { get value() { return controls.quizTheme; }, set value(value) { controls.quizTheme = value; } };
      return null;
    },
    querySelectorAll: () => [],
  };
  const window = {
    location: { hash: "#home", href: "http://localhost/#home" }, scrollY: 0,
    scrollTo() {}, addEventListener() {}, prompt: () => "training-password", confirm: () => false,
  };
  const context = {
    document, window, history: { pushState() {}, replaceState() {} },
    localStorage: storage, fetch, EcolabLearning: {
      ...learning,
      readStore: () => learning.readStore(storage),
      writeStore: (store) => learning.writeStore(store, storage),
    },
    requestAnimationFrame: (callback) => callback(),
    CSS: { escape: (value) => value }, btoa: (value) => Buffer.from(value, "binary").toString("base64"),
    TextEncoder, URLSearchParams, Math, Date, JSON, Map, Set, Array, String, Number, Boolean,
    Promise, Error, Intl, console,
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../app/web/static/app.js"), "utf8"), context);
  const ready = new Promise((resolve) => setImmediate(resolve));
  const action = async (name) => {
    const element = content.querySelectorAll("[data-action]").find((item) => item.dataset.action === name);
    assert.ok(element, `action ${name} is visible`);
    await element.handlers.click();
  };
  const navigate = async (view) => {
    const link = nav.querySelectorAll("a").find((item) => item.dataset.view === view);
    assert.ok(link, `navigation item ${view} is visible`);
    await link.handlers.click({ preventDefault() {} });
  };
  return { context, content, requests, selected, storage, ready, action, navigate, controls };
}

test("real app flow starts theme and mixed local quizzes, checks an answer, and resumes after reload", async () => {
  const harness = createQuizHarness();
  await harness.ready;
  const topic = harness.content.querySelectorAll("[data-theme]")[0];
  await topic.handlers.click();
  await harness.action("pane:quiz");
  harness.controls.themeCount = "2";
  await harness.action("start-theme-quiz");
  assert.match(harness.content.innerHTML, /ВОПРОС 1 \/ 2/);
  assert.equal(vm.runInContext("state.quizSession.context.themeId", harness.context), "monopoly");
  assert.equal(harness.requests.some((request) => request.url === "/api/quiz-sessions"), false);

  harness.selected.value = "1";
  const form = harness.context.document.querySelector("#answer-form");
  await form.handlers.submit({ preventDefault() {} });
  assert.match(harness.content.innerHTML, /Неверно — разберём ответ/);
  assert.match(harness.content.innerHTML, /Правильный ответ:<\/strong> A/);
  const saved = learning.readStore(harness.storage);
  assert.equal(saved.sessions[0].attempts.length, 1);
  assert.equal(saved.sessions[0].attempts[0].verdict, "incorrect");
  await harness.context.document.querySelector("#answer-form").handlers.submit({ preventDefault() {} });
  assert.equal(learning.readStore(harness.storage).sessions[0].attempts.length, 1);

  const restored = createQuizHarness({ storage: harness.storage });
  await restored.ready;
  assert.match(restored.content.innerHTML, /Неверно — разберём ответ/);
  assert.match(restored.content.innerHTML, /Следующий вопрос/);
  await restored.action("next-question");
  assert.match(restored.content.innerHTML, /ВОПРОС 2 \/ 2/);
  restored.selected.value = "0";
  await restored.context.document.querySelector("#answer-form").handlers.submit({ preventDefault() {} });
  assert.match(restored.content.innerHTML, /Показать итог/);
  await restored.action("next-question");
  assert.match(restored.content.innerHTML, /Квиз пройден/);

  await restored.action("new-quiz");
  await restored.action("start-global-quiz");
  assert.match(restored.content.innerHTML, /ВОПРОС 1 \/ 1/);
  assert.equal(vm.runInContext("state.quizSession.context.themeId", restored.context), "all");
});

test("local review launches saved wrong questions and empty review keeps normal quiz available", async () => {
  const harness = createQuizHarness();
  await harness.ready;
  const topic = harness.content.querySelectorAll("[data-theme]")[0];
  await topic.handlers.click();
  await harness.action("pane:quiz");
  await harness.action("start-theme-quiz");
  const failedQuestionId = vm.runInContext("state.questions[0].id", harness.context);
  harness.selected.value = "1";
  await harness.context.document.querySelector("#answer-form").handlers.submit({ preventDefault() {} });
  await harness.action("next-question");
  await harness.action("new-quiz");
  const passwordPrompts = [];
  harness.context.window.prompt = (message) => passwordPrompts.push(message);
  await harness.action("review-errors");
  assert.match(harness.content.innerHTML, /ВОПРОС 1 \/ 1/);
  assert.equal(vm.runInContext("state.questions[0].id", harness.context), failedQuestionId);
  assert.deepEqual(passwordPrompts, []);
  assert.equal(harness.requests.some((request) => request.url === "/api/review-questions"), false);

  const empty = createQuizHarness();
  await empty.ready;
  await empty.navigate("quizzes");
  await empty.action("review-errors");
  assert.match(empty.content.innerHTML, /Пока нет сохранённых вопросов/);
  assert.match(empty.content.innerHTML, /Начать квиз/);
  assert.deepEqual(passwordPrompts, []);
});

test("database session failure preserves the selected quiz and offers local continuation", async () => {
  const harness = createQuizHarness({ answerMode: "database", failSession: true });
  await harness.ready;
  await harness.navigate("quizzes");
  await harness.action("start-global-quiz");
  assert.match(harness.content.innerHTML, /Тренировка сохранена; можно продолжить локально/);
  assert.match(harness.content.innerHTML, /Продолжить локально/);
  assert.equal(vm.runInContext("state.pendingQuiz.context.themeId", harness.context), "all");
  await harness.action("continue-local-quiz");
  assert.match(harness.content.innerHTML, /ВОПРОС 1 \/ 1/);
  assert.equal(vm.runInContext("state.quizSession.local", harness.context), true);
  harness.selected.value = "0";
  await harness.context.document.querySelector("#answer-form").handlers.submit({ preventDefault() {} });
  const answerRequest = harness.requests.find((request) => request.url === "/api/answer");
  assert.equal(JSON.parse(answerRequest.options.body).mode, "local");
  assert.match(harness.content.innerHTML, /Попытка и статистика сохранены в этом браузере/);
});
