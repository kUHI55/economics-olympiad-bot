const test = require("node:test");
const assert = require("node:assert/strict");
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
