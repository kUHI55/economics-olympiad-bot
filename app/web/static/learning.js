(function attachLearningStore(root) {
  const STORAGE_KEY = "ecolab.learning.v1";

  function emptyStore() {
    return { version: 1, sessions: [], activeSessionId: null };
  }

  function readStore(storage) {
    try {
      storage = storage || root.localStorage;
      const parsed = JSON.parse(storage.getItem(STORAGE_KEY) || "null");
      if (!parsed) return emptyStore();
      if (parsed.version !== 1 || !Array.isArray(parsed.sessions)) return { ...emptyStore(), warning: true };
      const sessions = parsed.sessions.filter((session) => session && typeof session.id === "string"
        && Array.isArray(session.questionIds) && Array.isArray(session.attempts));
      const active = sessions.find((session) => session.id === parsed.activeSessionId
        && session.status === "in_progress");
      return { version: 1, sessions, activeSessionId: active ? active.id : null,
        lastRoute: parsed.lastRoute && typeof parsed.lastRoute === "object" ? parsed.lastRoute : null };
    } catch (_error) {
      return { ...emptyStore(), warning: true };
    }
  }

  function writeStore(store, storage) {
    try {
      storage = storage || root.localStorage;
      storage.setItem(STORAGE_KEY, JSON.stringify({
        version: 1,
        sessions: store.sessions,
        activeSessionId: store.activeSessionId,
        lastRoute: store.lastRoute || null,
      }));
      return true;
    } catch (_error) {
      return false;
    }
  }

  function percent(numerator, denominator) {
    return denominator ? Math.round((numerator / denominator) * 100) : null;
  }

  function aggregateSessions(sessions) {
    const attempts = sessions.flatMap((session) => session.attempts);
    const correct = attempts.filter((attempt) => attempt.verdict === "correct").length;
    const incorrect = attempts.filter((attempt) => attempt.verdict === "incorrect").length;
    const determinate = correct + incorrect;
    return { sessions: sessions.length, answered: attempts.length, correct, incorrect,
      percent: percent(correct, determinate), determinate };
  }

  function reviewQuestionIds(store) {
    const latest = new Map();
    const attempts = (store?.sessions || []).flatMap((session, sessionIndex) =>
      (session.attempts || []).map((attempt, attemptIndex) => ({
        attempt,
        order: attempt.answeredAt || session.startedAt || "",
        sessionIndex,
        attemptIndex,
      })),
    ).sort((a, b) => a.order.localeCompare(b.order)
      || a.sessionIndex - b.sessionIndex || a.attemptIndex - b.attemptIndex);
    for (const { attempt } of attempts) {
      if (typeof attempt.questionId === "string"
          && ["correct", "incorrect"].includes(attempt.verdict)) {
        latest.set(attempt.questionId, attempt.verdict);
      }
    }
    return [...latest.entries()].filter(([, verdict]) => verdict === "incorrect").map(([id]) => id);
  }

  function summarize(store, themes) {
    const completed = store.sessions.filter((session) => session.status === "completed");
    const chronologicalCompleted = [...completed].sort((a, b) => (a.startedAt || "").localeCompare(b.startedAt || ""));
    const completedStats = aggregateSessions(completed);
    const allAttempts = store.sessions.flatMap((session) => session.attempts);
    const active = store.sessions.find((session) => session.id === store.activeSessionId) || null;
    const trainedThemeIds = new Set(allAttempts.map((attempt) => attempt.themeId).filter(Boolean));
    const trainedSubtopics = new Set(allAttempts.map((attempt) => `${attempt.themeId}/${attempt.subtopicId}`));
    const lastAttempt = allAttempts.map((attempt) => attempt.answeredAt).filter(Boolean).sort().at(-1) || null;
    const breakdown = new Map();
    const subtopics = new Map();
    const constructions = new Map();
    const questions = new Map();

    for (const theme of themes) breakdown.set(theme.id, { completedSessionKeys: new Set(), attempts: [] });

    for (const session of completed) {
      const ids = new Set(session.attempts.map((attempt) => attempt.themeId).filter(Boolean));
      for (const themeId of ids) {
        const key = `${session.id}/${themeId}`;
        if (!breakdown.has(themeId)) breakdown.set(themeId, { completedSessionKeys: new Set(), attempts: [] });
        breakdown.get(themeId).completedSessionKeys.add(key);
      }
      for (const attempt of session.attempts) {
        if (attempt.themeId) breakdown.get(attempt.themeId)?.attempts.push(attempt);
        addGroup(subtopics, `${attempt.themeId}/${attempt.subtopicId}`, attempt);
        if (attempt.constructionId) addGroup(constructions, attempt.constructionId, attempt);
        addGroup(questions, attempt.questionId, attempt);
      }
    }

    const themeRows = [...breakdown.entries()].map(([id, value]) => {
      const summary = aggregateSessions([{ attempts: value.attempts }]);
      const theme = themes.find((entry) => entry.id === id);
      const themeSubtopics = [...subtopics.entries()].filter(([key]) => key.startsWith(`${id}/`))
        .map(([key, group]) => ({ id: key.split("/")[1], ...groupStats(group) }))
        .sort((a, b) => b.incorrect - a.incorrect || (b.percent ?? -1) - (a.percent ?? -1));
      const trend = chronologicalCompleted.map((session) => groupStats(session.attempts.filter((attempt) => attempt.themeId === id)))
        .filter((item) => item.determinate > 0).slice(-8).map((item) => item.percent);
      return { id, title: theme?.title || id, completedQuizzes: value.completedSessionKeys.size,
        ...summary, mostErrors: themeSubtopics.slice(0, 3), trend };
    });
    const errorRows = (groups, labelFor) => [...groups.entries()].map(([id, attempts]) => ({
      id, title: labelFor(id), ...groupStats(attempts), priority: priorityScore(attempts),
    })).filter((row) => row.incorrect > 0).sort((a, b) => b.priority - a.priority || b.incorrect - a.incorrect);
    const history = store.sessions.filter((session) => session.id !== active?.id)
      .sort((a, b) => (b.startedAt || "").localeCompare(a.startedAt || ""));
    return {
      startedQuizzes: store.sessions.length,
      completedQuizzes: completed.length,
      incompleteQuizzes: store.sessions.filter((session) => session.status !== "completed").length,
      completed: completedStats,
      themes: themeRows.sort((a, b) => b.incorrect - a.incorrect || a.title.localeCompare(b.title)),
      trainedThemeCount: trainedThemeIds.size,
      trainedSubtopicCount: trainedSubtopics.size,
      lastAttempt,
      lastTraining: [...store.sessions].sort((a, b) => (b.startedAt || "").localeCompare(a.startedAt || ""))[0]?.startedAt || null,
      active,
      history,
      problemThemes: errorRows(new Map(themeRows.map((row) => [row.id, completed.flatMap((session) => session.attempts).filter((attempt) => attempt.themeId === row.id)])), (id) => themes.find((theme) => theme.id === id)?.title || id),
      problemSubtopics: errorRows(subtopics, (key) => {
        const [themeId, subtopicId] = key.split("/");
        const theme = themes.find((item) => item.id === themeId);
        return theme?.subtopics.find((item) => item.id === subtopicId)?.title || subtopicId;
      }),
      problemConstructions: errorRows(constructions, (id) => {
        for (const theme of themes) for (const subtopic of theme.subtopics) {
          const knowledge = subtopic.knowledge.find((item) => item.id === id);
          if (knowledge) return knowledge.title;
        }
        return id;
      }),
      repeatedQuestions: errorRows(questions, (id) => id).filter((row) => row.incorrect >= 2),
    };
  }

  function addGroup(groups, key, attempt) {
    if (!key || key.includes("undefined")) return;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(attempt);
  }

  function groupStats(attempts) {
    const correct = attempts.filter((attempt) => attempt.verdict === "correct").length;
    const incorrect = attempts.filter((attempt) => attempt.verdict === "incorrect").length;
    const determinate = correct + incorrect;
    return { answered: attempts.length, correct, incorrect, determinate, percent: percent(correct, determinate) };
  }

  function priorityScore(attempts) {
    const { incorrect, determinate } = groupStats(attempts);
    return determinate ? ((incorrect + 1) / (determinate + 2)) * Math.log2(determinate + 1) : 0;
  }

  function formatDate(value, options = { dateStyle: "medium", timeStyle: "short" }) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat("ru-RU", options).format(date);
  }

  const api = { STORAGE_KEY, emptyStore, readStore, writeStore, summarize, percent, formatDate, reviewQuestionIds };
  root.EcolabLearning = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window === "undefined" ? globalThis : window);
