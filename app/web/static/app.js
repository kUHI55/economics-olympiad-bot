const state = {
  data: null,
  progress: { available: false, answer_mode: "local", themes: {} },
  view: "topics",
  themeId: null,
  themePane: "theory",
  subtopicId: null,
  quizThemeId: "all",
  quizCategory: "all",
  questions: [],
  questionIndex: 0,
  answered: false,
  selectedAnswer: null,
  quizError: null,
  quizSession: null,
  quizSummary: null,
  password: null,
  lastResult: null,
  learning: null,
  remoteLearning: null,
  storageAvailable: true,
  returnContext: null,
};
const content = document.querySelector("#content");
const nav = document.querySelector("#navigation");
const mainViews = [["topics", "Темы"], ["quizzes", "Квизы"], ["stats", "Статистика"]];

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\\\\\((.*?)\\\\\)/g, '<span class="math-inline">$1</span>')
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function renderMarkdown(source) {
  const output = [];
  let paragraph = [];
  let list = null;
  let listItems = [];
  let table = [];
  let inCode = false;
  let code = [];
  const flushParagraph = () => {
    if (paragraph.length) output.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  const flushList = () => {
    if (list) output.push(`<${list}>${listItems.join("")}</${list}>`);
    list = null;
    listItems = [];
  };
  const flushTable = () => {
    if (table.length) {
      const rows = table.filter((row) => !/^\|?\s*:?-{3,}/.test(row));
      const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
      const head = cells(rows.shift() || "");
      output.push(`<table><thead><tr>${head.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${cells(row).map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
    }
    table = [];
  };
  for (const line of source.replace(/&#x20;/g, " ").replace(/\r/g, "").split("\n")) {
    if (line.trim().startsWith("```")) {
      flushParagraph(); flushList(); flushTable();
      if (inCode) output.push(`<pre class="math-block">${escapeHtml(code.join("\n"))}</pre>`);
      inCode = !inCode; code = []; continue;
    }
    if (inCode) { code.push(line); continue; }
    if (!line.trim()) { flushParagraph(); flushList(); flushTable(); continue; }
    if (/^\s*\|.*\|\s*$/.test(line)) { flushParagraph(); flushList(); table.push(line); continue; }
    if (/^\s{0,3}#{1,6}\s/.test(line)) {
      flushParagraph(); flushList(); flushTable();
      const match = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
      const depth = Math.min(match[1].length, 4) + 1;
      const title = match[2].replace(/\s+#+\s*$/, "");
      const id = `section-${output.length}`;
      output.push(`<h${depth} id="${id}">${inlineMarkdown(title)}</h${depth}>`); continue;
    }
    if (/^\\\\\[|^\\\\\]|^\$\$/.test(line.trim())) { flushParagraph(); output.push(`<pre class="math-block">${escapeHtml(line.trim())}</pre>`); continue; }
    if (/^\s*>/.test(line)) { flushParagraph(); flushList(); flushTable(); output.push(`<blockquote>${inlineMarkdown(line.replace(/^\s*>\s?/, ""))}</blockquote>`); continue; }
    const listMatch = line.match(/^\s*(?:[-*+]\s+|\d+[.)]\s+)(.*)$/);
    if (listMatch) {
      flushParagraph(); flushTable();
      const nextList = /^\s*\d+[.)]\s+/.test(line) ? "ol" : "ul";
      if (list && list !== nextList) flushList();
      list = nextList; listItems.push(`<li>${inlineMarkdown(listMatch[1])}</li>`); continue;
    }
    flushList(); flushTable(); paragraph.push(line.trim());
  }
  flushParagraph(); flushList(); flushTable();
  return output.join("\n");
}

function setNavigation() {
  const active = ["quizzes", "stats"].includes(state.view) ? state.view : "topics";
  nav.innerHTML = mainViews.map(([id, label]) => `<a href="#${id}" data-view="${id}" class="${active === id ? "active" : ""}">${label}</a>`).join("");
  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault();
    navigateTo(link.dataset.view);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));
}

function saveLearning() {
  if (state.learning) {
    state.learning.lastRoute = captureRoute();
    state.storageAvailable = EcolabLearning.writeStore(state.learning);
    if (state.storageAvailable) state.learning.warning = false;
  }
}

function currentSession() {
  return state.learning?.sessions.find((session) => session.id === state.learning.activeSessionId) || null;
}

function saveCurrentQuestionState() {
  const session = currentSession();
  if (!session) return;
  session.currentIndex = state.questionIndex;
  session.current = {
    selectedAnswer: state.selectedAnswer,
    answered: state.answered,
    result: state.lastResult,
    scrollY: window.scrollY,
  };
  saveLearning();
}

function captureRoute() {
  return {
    view: state.view, themeId: state.themeId, themePane: state.themePane,
    subtopicId: state.subtopicId, quizSessionId: currentSession()?.id || state.quizSession?.id || null,
    questionIndex: state.questionIndex, returnContext: state.returnContext,
    quizSummary: state.quizSummary,
    quizState: state.quizSession ? {
      selectedAnswer: state.selectedAnswer, answered: state.answered,
      result: state.lastResult, scrollY: window.scrollY,
    } : null,
  };
}

function replaceCurrentRoute() {
  history.replaceState({ ecolab: true, route: captureRoute() }, "", window.location.href);
}

function navigateTo(view, { replace = false } = {}) {
  saveCurrentQuestionState();
  state.view = view;
  saveLearning();
  const snapshot = { ecolab: true, route: captureRoute() };
  if (replace) history.replaceState(snapshot, "", `#${view}`);
  else history.pushState(snapshot, "", `#${view}`);
  render();
}

function currentSessionAttempts() {
  return state.quizSession?.attempts || [];
}

function restoreSession(session, route = {}) {
  if (!session || !state.data) return false;
  const byId = new Map(allQuestions().map((question) => [question.id, question]));
  const questions = session.questionIds.map((id) => byId.get(id)).filter(Boolean);
  if (!questions.length) return false;
  state.questions = questions;
  state.quizSession = session;
  state.questionIndex = Math.min(route.questionIndex ?? session.currentIndex ?? 0, questions.length - 1);
  const current = route.quizState || (state.questionIndex === session.currentIndex ? session.current : {}) || {};
  state.selectedAnswer = current.selectedAnswer ?? null;
  state.answered = Boolean(current.answered);
  state.lastResult = current.result || null;
  state.quizSummary = route.quizSummary || null;
  state.returnContext = route.returnContext || null;
  state.themeId = route.themeId || session.context?.themeId || null;
  state.subtopicId = route.subtopicId || session.context?.subtopicId || null;
  state.themePane = route.themePane || "theory";
  state.view = route.view || "quizzes";
  return true;
}

function restoreRoute(route) {
  if (!route) return;
  const session = route.quizSessionId
    ? state.learning.sessions.find((item) => item.id === route.quizSessionId)
    : null;
  if (session && restoreSession(session, route)) {
    if (state.view === "quizzes" && session.current?.scrollY) {
      requestAnimationFrame(() => window.scrollTo(0, session.current.scrollY));
    }
  } else {
    state.view = route.view === "theme" && state.data.themes.some((theme) => theme.id === route.themeId)
      ? "theme" : route.view === "stats" ? "stats" : route.view === "quizzes" ? "quizzes" : "topics";
    state.themeId = route.themeId;
    state.themePane = route.themePane || "theory";
    state.subtopicId = route.subtopicId || null;
    state.returnContext = null;
    state.questions = [];
    state.quizSession = null;
  }
  render();
}

window.addEventListener("popstate", (event) => {
  if (event.state?.ecolab) restoreRoute(event.state.route);
  else {
    state.view = window.location.hash === "#stats" ? "stats" : window.location.hash === "#quizzes" ? "quizzes" : "topics";
    render();
  }
});

function currentTheme() { return state.data.themes.find((theme) => theme.id === state.themeId) || state.data.themes[0]; }
function allQuestions() {
  return state.data.themes.flatMap((theme) => theme.subtopics.flatMap((subtopic) => subtopic.questions.map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: subtopic.id, subtopic_title: subtopic.title }))));
}
function progressFor(themeId) { return state.progress.themes?.[themeId] || null; }
function progressMarkup(themeId) {
  const progress = progressFor(themeId);
  const value = progress ? progress.percent : 0;
  return `<div class="progress-row"><div class="progress-track"><span style="width:${value}%"></span></div><small>${progress ? `${value}% · ${progress.studied}/${progress.total} изучено` : "Начни тренировку"}</small></div>`;
}
function button(label, action, active = false, extra = "") {
  return `<button type="button" class="${active ? "active" : ""}" data-action="${escapeHtml(action)}" ${extra}>${label}</button>`;
}

function renderTopics() {
  return `<div class="section-head"><div><p class="eyebrow">БИБЛИОТЕКА</p><h2>Выбери тему</h2></div><p>Открой конспект, разберись в конструкциях и закрепи материал квизом.</p></div><div class="card-grid">${state.data.themes.map((theme, index) => `<button class="topic-card" data-theme="${escapeHtml(theme.id)}"><span class="topic-number"><i class="spark">✦</i> ТЕМА ${String(index + 1).padStart(2, "0")}</span><h3>${escapeHtml(theme.title)}</h3><p>${escapeHtml(theme.description)}</p><div class="counts"><span>${theme.subtopics.length} разделов</span><span>${theme.question_count} вопросов</span></div>${progressMarkup(theme.id)}</button>`).join("")}</div>`;
}

function renderThemeHeader(theme) {
  const panes = [["theory", "Теория"], ["constructions", "Конструкции"], ["quiz", "Квиз"]];
  const returnButton = state.returnContext && isReturnContextValid()
    ? `<button class="button primary return-quiz" data-action="return-to-question">← Вернуться к вопросу</button>`
    : state.returnContext ? `<div class="feedback error">Исходный вопрос уже не является текущим. <button class="text-button" data-action="return-to-quiz-list">Открыть квизы</button></div>` : "";
  return `${returnButton}<button class="back-link" data-action="back-topics">← Все темы</button><div class="theme-heading"><div><p class="eyebrow">ТЕМА</p><h2>${escapeHtml(theme.title)}</h2><p>${escapeHtml(theme.description)}</p></div>${progressMarkup(theme.id)}</div><div class="tabs">${panes.map(([id, label]) => button(label, `pane:${id}`, state.themePane === id)).join("")}</div>`;
}

function isReturnContextValid() {
  if (!state.returnContext) return false;
  const session = state.learning.sessions.find((item) => item.id === state.returnContext.sessionId);
  return Boolean(session && session.status === "in_progress"
    && session.currentIndex === state.returnContext.questionIndex
    && session.questionIds[session.currentIndex] === state.returnContext.questionId
    && session.current?.answered);
}

function renderKnowledgeItem(item) {
  return `<article class="knowledge-item" id="knowledge-${escapeHtml(item.id)}"><span class="label">${escapeHtml(item.type.replaceAll("_", " ").toUpperCase())}</span><h3>${escapeHtml(item.title)}</h3>${item.formula ? `<div class="formula">${escapeHtml(item.formula)}</div>` : ""}<p>${escapeHtml(item.explanation)}</p>${Object.keys(item.definitions || {}).length ? `<ul>${Object.entries(item.definitions).map(([key, value]) => `<li><strong>${escapeHtml(key)}:</strong> ${escapeHtml(value)}</li>`).join("")}</ul>` : ""}<p class="source">Источник: ${escapeHtml(item.source.name)} · ${escapeHtml(item.source.excerpt)}</p></article>`;
}

async function renderDocument(theme, name) {
  content.innerHTML = `<p class="loading">Открываю материал…</p>`;
  const response = await fetch(`/api/documents/${encodeURIComponent(theme.id)}/${encodeURIComponent(name)}`);
  if (!response.ok) throw new Error("Не удалось загрузить документ темы.");
  const source = await response.text();
  const html = renderMarkdown(source);
  const headings = [...html.matchAll(/<h([2-5]) id="([^"]+)">([^<]+)<\/h\d>/g)];
  const sidebar = headings.map((heading) => `<a href="#${heading[2]}">${heading[3]}</a>`).join("");
  content.innerHTML = `${renderThemeHeader(theme)}<div class="lesson-layout"><aside class="lesson-nav">${sidebar}</aside><article class="markdown">${html}</article></div>`;
  bindActions();
}

function parseConstructionCards(source) {
  const rows = [];
  let current = null;
  for (const line of source.split(/\r?\n/)) {
    const heading = line.match(/^##\s+\d+\.\s+(.+)$/);
    if (heading) {
      current = { title: heading[1], body: [] };
      rows.push(current);
      continue;
    }
    if (/^##\s+/.test(line)) { current = null; continue; }
    if (!current || !line.trim()) continue;
    const item = line.match(/^\d+\.\s+\*\*(.+?)\*\*\s*(.*)$/);
    if (item && item[1] === "Название.") continue;
    current.body.push(line.replace(/^\d+\.\s+/, ""));
  }
  return rows;
}

async function renderConstructions(theme) {
  if (!theme.documents.includes("problem-constructions.md")) {
    const mechanisms = theme.subtopics.flatMap((subtopic) => subtopic.knowledge.filter((item) => ["mechanism", "example", "common_mistake"].includes(item.type)).map((item) => ({ ...item, subtopic_title: subtopic.title })));
    content.innerHTML = `${renderThemeHeader(theme)}<div class="section-head"><div><p class="eyebrow">КОНСТРУКЦИИ И АЛГОРИТМЫ</p><h2>Из условий — к методу</h2></div><p>Конструкции появятся здесь по мере подготовки материала и вопросов для тренировки.</p></div>${mechanisms.length ? `<div class="card-grid">${mechanisms.map((item) => `<article class="construction-card"><span class="label">${escapeHtml(item.subtopic_title)}</span><h3>${escapeHtml(item.title)}</h3><p>${escapeHtml(item.explanation)}</p></article>`).join("")}</div>` : `<div class="empty-card">Для этой темы каталог конструкций пока не подготовлен.</div>`}`;
    bindActions(); return;
  }
  content.innerHTML = `<p class="loading">Загружаю каталог…</p>`;
  const response = await fetch(`/api/documents/${encodeURIComponent(theme.id)}/problem-constructions.md`);
  if (!response.ok) throw new Error("Не удалось загрузить каталог конструкций.");
  const source = await response.text();
  const cards = parseConstructionCards(source);
  content.innerHTML = `${renderThemeHeader(theme)}<div class="section-head"><div><p class="eyebrow">КОНСТРУКЦИИ ОЛИМПИАДНЫХ ЗАДАЧ</p><h2>Узнай ход задачи</h2></div><p>Признаки, ключевой приём, ограничения и ловушки взяты из каталога. Подробные разборы — в конспекте.</p></div><div class="construction-grid">${cards.map((card, index) => `<article class="construction-card" id="construction-${String(index + 1).padStart(2, "0")}"><span class="topic-number">КОНСТРУКЦИЯ ${String(index + 1).padStart(2, "0")}</span><h3>${escapeHtml(card.title)}</h3><p>${card.body.map(inlineMarkdown).join("<br>")}</p><small>Распознавание · алгоритм · границы · проверка</small><button class="text-button" data-action="construction-quiz:${String(index + 1).padStart(2, "0")}">Тренировать эту конструкцию →</button></article>`).join("")}</div><button class="button" data-action="construction-quiz">Тренировать все конструкции →</button><div class="study-card"><h3>Примеры и оговорки источника</h3><p>Открой полный конспект, чтобы перейти к разобранным задачам, вычислениям и отмеченным неоднозначностям.</p><button class="button" data-action="theme-document:study-notes.md">Читать конспект</button></div>`;
  bindActions();
}

function renderThemeTheory(theme) {
  if (theme.documents.includes("study-notes.md")) {
    return `<div class="section-head"><div><p class="eyebrow">ПОЛНЫЙ СВЯЗНЫЙ МАТЕРИАЛ</p><h2>Теория и конспект</h2></div><p>Сначала подробный конспект, ниже — структурированные элементы с формулами, обозначениями и ссылками на источник.</p></div><button class="button primary" data-action="theme-document:study-notes.md">Открыть подробный конспект →</button>`;
  }
  return `<div class="section-head"><div><p class="eyebrow">ТЕОРИЯ</p><h2>Разделы темы</h2></div><p>Выбери раздел, чтобы раскрыть определения, формулы и пояснения.</p></div>`;
}

function renderThemeTheoryContent(theme) {
  const subtopics = theme.subtopics.map((subtopic) => `<details class="subtopic-card" ${state.subtopicId === subtopic.id || (!state.subtopicId && subtopic === theme.subtopics[0]) ? "open" : ""}><summary><span>${escapeHtml(subtopic.title)}</span><small>${subtopic.knowledge.length} элементов · ${subtopic.questions.length} вопросов</small></summary><div class="subtopic-content">${subtopic.knowledge.map(renderKnowledgeItem).join("")}<button class="text-button" data-action="subtopic-quiz:${escapeHtml(subtopic.id)}">Тренировать раздел →</button></div></details>`).join("");
  return `${renderThemeTheory(theme)}<div class="subtopic-list">${subtopics}</div>${theme.documents.includes("review-sheet.md") ? `<button class="text-button" data-action="theme-document:review-sheet.md">Открыть памятку для повторения →</button>` : ""}`;
}

function renderThemeQuiz(theme) {
  const questions = theme.subtopics.flatMap((subtopic) => subtopic.questions);
  const constructions = questions.filter((question) => question.category === "construction").length;
  const progressNote = state.progress.answer_mode === "local" ? "Проверка работает локально; без PostgreSQL прогресс не сохраняется." : "Попытки сохраняются в общий прогресс и расписание повторения.";
  return `<div class="section-head"><div><p class="eyebrow">ТРЕНИРОВКА</p><h2>Закрепи тему</h2></div><p>Смешивай теорию и конструкции или выбери отдельный формат.</p></div><div class="quiz-card"><div class="quiz-controls"><label for="theme-quiz-kind">Режим</label><select id="theme-quiz-kind"><option value="all">Смешанный квиз</option><option value="theory">Теория и формулы</option><option value="construction" ${constructions ? "" : "disabled"}>Конструкции задач (${constructions})</option></select></div><div class="quiz-controls"><label for="theme-quiz-count">Вопросов</label><select id="theme-quiz-count"><option>5</option><option selected>10</option><option>20</option></select></div><button class="button primary" data-action="start-theme-quiz">Начать тренировку</button><p class="progress-note">${progressNote}</p></div>`;
}

function renderQuizLanding() {
  const options = state.data.themes.map((theme) => `<option value="${escapeHtml(theme.id)}" ${state.quizThemeId === theme.id ? "selected" : ""}>${escapeHtml(theme.title)}</option>`).join("");
  const constructionCount = allQuestions().filter((question) => question.category === "construction").length;
  const active = currentSession();
  const resume = active ? `<article class="quiz-card resume-card"><p class="eyebrow">НЕЗАВЕРШЁННАЯ ТРЕНИРОВКА</p><h3>Продолжить квиз</h3><p>Вопрос ${active.currentIndex + 1} из ${active.questionIds.length}. Сессия сохранена в этом браузере.</p><button class="button primary" data-action="resume-quiz">Продолжить</button></article>` : "";
  return `<div class="section-head"><div><p class="eyebrow">ПРАКТИКА И ПОВТОРЕНИЕ</p><h2>Квизы</h2></div><p>Тренируй одну тему, выбирай тип вопросов или смешивай материал из всей библиотеки.</p></div>${resume}<div class="quiz-grid"><article class="quiz-card quiz-config"><h3>Новая тренировка</h3><label for="quiz-theme">Тема</label><select id="quiz-theme"><option value="all" ${state.quizThemeId === "all" ? "selected" : ""}>Все темы · смешанный квиз</option>${options}</select><label for="quiz-kind">Что тренируем</label><select id="quiz-kind"><option value="all">Всё вперемешку</option><option value="theory">Теорию и формулы</option><option value="construction" ${constructionCount ? "" : "disabled"}>Конструкции задач (${constructionCount})</option></select><label for="quiz-count">Количество вопросов</label><select id="quiz-count"><option>5</option><option selected>10</option><option>20</option></select><button class="button primary" data-action="start-global-quiz">Начать квиз</button><button class="text-button" data-view="stats">Открыть статистику обучения →</button></article><article class="quiz-card review-card"><span class="review-icon">↻</span><h3>Вернуться к ошибкам</h3><p>Повтори вопросы, которые уже пора проверить по расписанию интервального повторения.</p><button class="button" data-action="review-errors">Показать вопросы к повторению</button><p class="progress-note">${state.progress.available ? "История доступна." : "Плановое повторение требует PostgreSQL и пароля сайта."}</p></article></div>`;
}

function renderStatistics() {
  const databaseMode = state.progress.answer_mode === "database";
  const stats = EcolabLearning.summarize(databaseMode ? (state.remoteLearning || EcolabLearning.emptyStore()) : state.learning, state.data.themes);
  const pct = stats.completed.percent === null ? "—" : `${stats.completed.percent}%`;
  const active = currentSession() || stats.active;
  const activeAnswered = active ? Math.max(active.attempts.length, (active.currentIndex || 0) + (active.current?.answered ? 1 : 0)) : 0;
  const activeCard = active ? `<article class="stat-card current-session"><p class="eyebrow">ТЕКУЩАЯ · НЕЗАВЕРШЁННАЯ</p><h3>${escapeHtml(active.context.label || "Тренировка")}</h3><p>Отвечено ${activeAnswered} из ${active.questionIds.length}; текущий вопрос ${(active.currentIndex || 0) + 1}.</p><button class="button primary" data-action="resume-quiz">Продолжить тренировку</button></article>` : `<div class="empty-card">Сейчас нет незавершённой тренировки.</div>`;
  const metrics = [
    ["Начато квизов", stats.startedQuizzes], ["Завершено", stats.completedQuizzes], ["Незавершено", stats.incompleteQuizzes],
    ["Ответов в завершённых квизах", stats.completed.answered], ["Верно / неверно", `${stats.completed.correct} / ${stats.completed.incorrect}`],
    ["Точность завершённых", pct], ["Темы / подразделы", `${stats.trainedThemeCount} / ${stats.trainedSubtopicCount}`],
  ];
  const rows = (items, scope) => items.length ? `<div class="stats-list">${items.map((item) => {
    const confidence = item.determinate < 5 ? " · мало попыток" : "";
    const rate = item.percent === null ? "нет данных" : `${item.incorrect}/${item.determinate} ошибок · ${100 - item.percent}%`;
    return `<article class="stats-row"><div><strong>${escapeHtml(item.title)}</strong><small>${rate}${confidence}</small></div><div class="stat-bar"><span style="width:${item.determinate ? (item.incorrect / item.determinate) * 100 : 0}%"></span></div><button class="text-button" data-action="repeat-group:${scope}:${escapeHtml(item.id)}">Тренировать →</button></article>`;
  }).join("")}</div>` : `<p class="progress-note">Пока недостаточно проверенных ответов для рейтинга.</p>`;
  const themeRows = stats.themes.length ? `<div class="stats-list">${stats.themes.map((theme) => `<article class="stats-row"><div><strong>${escapeHtml(theme.title)}</strong><small>${theme.completedQuizzes} завершённых квизов · ${theme.answered} ответов · ${theme.correct}/${theme.determinate} верно${theme.percent === null ? "" : ` · ${theme.percent}%`}</small>${theme.mostErrors.filter((item) => item.incorrect).slice(0, 2).map((item) => `<small>Чаще ошибки: ${escapeHtml(item.title)} — ${item.incorrect}/${item.determinate}</small>`).join("")}<div class="trend-bars" aria-label="Динамика точности по завершённым квизам">${theme.trend.map((value) => `<span title="${value}%" style="height:${Math.max(5, value)}%"></span>`).join("")}</div></div><div class="stat-bar"><span style="width:${theme.percent ?? 0}%"></span></div><button class="text-button" data-action="theme-from-stats:${escapeHtml(theme.id)}">Открыть тему →</button></article>`).join("")}</div>` : `<p class="progress-note">Завершённых тренировок пока нет.</p>`;
  const history = stats.history.length ? `<div class="stats-list">${stats.history.map((session) => {
    const correct = session.attempts.filter((attempt) => attempt.verdict === "correct").length;
    const incorrect = session.attempts.filter((attempt) => attempt.verdict === "incorrect").length;
    const determinate = correct + incorrect;
    const percent = determinate ? Math.round((correct / determinate) * 100) : null;
    const theme = state.data.themes.find((item) => item.id === session.context.themeId);
    const subtopic = theme?.subtopics.find((item) => item.id === session.context.subtopicId);
    const title = session.context.label || (session.context.themeId === "all" ? "Смешанный квиз" : subtopic ? `${theme.title} · ${subtopic.title}` : theme?.title || "Тема");
    const status = session.status === "completed" ? "Завершён" : "Не завершён";
    return `<details class="history-item"><summary><span><strong>${escapeHtml(title)}</strong><small>${EcolabLearning.formatDate(session.startedAt)} · ${correct}/${determinate} верно · ${session.attempts.length}/${session.questionIds.length} ответов</small></span><span class="history-status">${status}</span></summary><p>${percent === null ? "Нет оцениваемых ответов" : `${percent}% правильных ответов`} · ошибок: ${incorrect}</p></details>`;
  }).join("")}</div>` : `<p class="progress-note">Завершённых сессий пока нет.</p>`;
  const recommendation = stats.problemSubtopics[0];
  let recommendationMarkup = `<p class="progress-note">Сначала пройди несколько вопросов — тогда появятся рекомендации по реальным ошибкам.</p>`;
  if (recommendation) {
    const [themeId, subtopicId] = recommendation.id.split("/");
    const theme = state.data.themes.find((item) => item.id === themeId);
    const subtopic = theme?.subtopics.find((item) => item.id === subtopicId);
    if (theme && subtopic) recommendationMarkup = `<p>Чаще всего ошибки были в разделе <strong>${escapeHtml(subtopic.title)}</strong>: ${recommendation.incorrect} из ${recommendation.determinate} ответов${recommendation.determinate < 5 ? " (мало попыток)" : ""}.</p><button class="button" data-action="recommend:${escapeHtml(themeId)}:${escapeHtml(subtopicId)}">Повторить этот раздел →</button>`;
  }
  const sourceNote = databaseMode
    ? state.remoteLearning ? `Статистика загружена из PostgreSQL. ${state.remoteLearning.legacyAttempts ? `${state.remoteLearning.legacyAttempts} старых попыток не были привязаны к сессиям и поэтому не считаются завершёнными квизами.` : ""}` : `Статистика ответов берётся из PostgreSQL; локальная копия попыток не создаётся. <button class="text-button" data-action="load-database-statistics">Загрузить статистику из базы</button>`
    : `${state.learning.warning ? "Сохранённая история повреждена или устарела; начата новая локальная статистика. " : ""}${state.storageAvailable ? "Локальная статистика хранится в этом браузере и не переносится на другие устройства." : "Браузер запретил localStorage: история может не сохраниться после закрытия страницы."}`;
  return `<div class="section-head"><div><p class="eyebrow">ТВОИ РЕЗУЛЬТАТЫ</p><h2>Статистика обучения</h2></div><p>Завершённый квиз учитывается только после последнего вопроса. Незавершённая тренировка показана отдельно.</p></div><div class="progress-note">${sourceNote}</div><div class="stats-grid">${metrics.map(([label, value]) => `<article class="stat-card"><small>${label}</small><strong>${value}</strong></article>`).join("")}<article class="stat-card"><small>Последняя тренировка</small><strong class="stat-date">${EcolabLearning.formatDate(stats.lastTraining)}</strong></article></div><div class="stats-columns"><section class="quiz-card"><h3>Текущая тренировка</h3>${activeCard}</section><section class="quiz-card"><h3>Что повторить</h3>${recommendationMarkup}</section></div><section class="quiz-card stats-section"><h3>По темам</h3>${themeRows}</section><div class="stats-columns"><section class="quiz-card"><h3>Где чаще ошибки</h3><h4>Темы</h4>${rows(stats.problemThemes, "theme")}<h4>Подразделы</h4>${rows(stats.problemSubtopics, "subtopic")}<h4>Конструкции</h4>${rows(stats.problemConstructions, "construction")}<h4>Повторные ошибки по вопросам</h4>${rows(stats.repeatedQuestions, "question")}</section><section class="quiz-card"><h3>История тренировок</h3>${history}<p class="progress-note">Последний ответ: ${EcolabLearning.formatDate(stats.lastAttempt)}</p></section></div><div class="stats-footer"><p class="progress-note">Сброс очищает только локальные записи этого браузера. Записи PostgreSQL и учебные материалы не удаляются.</p><button class="button danger" data-action="reset-statistics">Сбросить локальную статистику</button></div>`;
}

function renderQuizQuestion() {
  const question = state.questions[state.questionIndex];
  const hasFourOptions = Array.isArray(question.options) && question.options.length === 4;
  const options = hasFourOptions
    ? `<div>${question.options.map((option, index) => `<label class="quiz-option"><input type="radio" name="answer" value="${index}" ${state.selectedAnswer === String(index) ? "checked" : ""} ${state.answered ? "disabled" : ""}><span>${escapeHtml(option.text)}</span></label>`).join("")}</div>`
    : `<div class="feedback error">В этом вопросе не настроены четыре варианта ответа. Выбери другой вопрос или сообщи о проблеме.</div>`;
  const result = state.lastResult;
  const feedback = result ? `<div class="feedback ${result.verdict === "incorrect" ? "error" : ""}"><strong>${result.verdict === "correct" ? "Верно!" : result.verdict === "partial" ? "Частично верно" : result.verdict === "uncertain" ? "Не удалось надёжно оценить автоматически" : "Неверно — разберём ответ"}</strong><p>${escapeHtml(result.short_explanation || "")}</p><p><strong>Правильный ответ:</strong> ${escapeHtml(result.reference_answer)}</p><p>${escapeHtml(result.explanation)}</p><p class="source">Основание: ${escapeHtml(result.source_excerpt)}</p>${result.progress_saved === false ? '<p class="progress-note">Проверка работает локально; прогресс не сохраняется без PostgreSQL.</p>' : ""}<button class="text-button" data-action="open-answer-theory">Открыть связанный раздел теории →</button></div>` : "";
  return `<div class="quiz-card active-quiz"><p class="eyebrow">${escapeHtml(question.theme_title)} · ${escapeHtml(question.subtopic_title)}</p><span class="quiz-progress">ВОПРОС ${state.questionIndex + 1} / ${state.questions.length} · СЛОЖНОСТЬ ${question.difficulty}/5</span><p class="quiz-question">${escapeHtml(question.question)}</p><form id="answer-form">${options}<div class="quiz-actions"><button class="button primary" type="submit" ${state.answered || !hasFourOptions ? "disabled" : ""}>Проверить ответ</button>${state.answered ? `<button class="button" type="button" data-action="next-question">${state.questionIndex + 1 === state.questions.length ? "Показать итог" : "Следующий вопрос"}</button>` : ""}</div></form>${state.quizError ? `<div class="feedback error">${escapeHtml(state.quizError)}</div>` : ""}${feedback}</div>`;
}

function renderQuizSummary() {
  const summary = state.quizSummary;
  const percent = summary.total ? Math.round((summary.correct / summary.total) * 100) : 0;
  return `<div class="quiz-card"><p class="eyebrow">ТРЕНИРОВКА ЗАВЕРШЕНА</p><h2>Квиз пройден</h2><p>Правильных ответов: <strong>${summary.correct} из ${summary.total}</strong> (${percent}%).</p><p class="progress-note">${summary.local ? "Проверка работала локально; прогресс не сохранялся без PostgreSQL." : "Результаты сохранены в прогресс."}</p><button class="button primary" type="button" data-action="new-quiz">Новая тренировка</button></div>`;
}

function render() {
  setNavigation();
  if (!state.data) { content.innerHTML = `<p class="loading">Загружаю библиотеку…</p>`; return; }
  if (state.view === "topics") content.innerHTML = renderTopics();
  else if (state.view === "quizzes") content.innerHTML = state.questions.length && state.quizSession ? renderQuizQuestion() : state.quizSummary ? renderQuizSummary() : renderQuizLanding();
  else if (state.view === "stats") content.innerHTML = renderStatistics();
  else {
    const theme = currentTheme();
    const body = state.themePane === "theory" ? renderThemeTheoryContent(theme) : state.themePane === "quiz" ? renderThemeQuiz(theme) : "";
    if (state.themePane === "constructions") { renderConstructions(theme).catch(showError); return; }
    content.innerHTML = `${renderThemeHeader(theme)}${body}`;
  }
  bindActions();
}

function showError(error) { content.innerHTML = `<div class="feedback error">${escapeHtml(error.message)}</div>`; }
function showQuizError(message) { state.quizError = message; render(); }
function setTheme(id) {
  state.themeId = id; state.subtopicId = null; state.themePane = "theory"; state.view = "theme";
  saveLearning(); history.pushState({ ecolab: true, route: captureRoute() }, "", `#theme-${encodeURIComponent(id)}`);
  render(); window.scrollTo({ top: 0, behavior: "smooth" });
}
async function beginQuiz(questions, count = questions.length, ensureThemeCoverage = false, context = {}) {
  if (!questions.length) { showQuizError("Для выбранного раздела пока нет вопросов с вариантами ответа."); return; }
  const shuffled = (items) => [...items].sort(() => Math.random() - 0.5);
  let selected = shuffled(questions);
  if (ensureThemeCoverage && count > 1) {
    const groups = new Map();
    for (const question of selected) {
      if (!groups.has(question.theme_id)) groups.set(question.theme_id, []);
      groups.get(question.theme_id).push(question);
    }
    const representatives = [...groups.values()].map((group) => group[0]).slice(0, count);
    const representativeIds = new Set(representatives.map((question) => question.id));
    const remaining = selected.filter((question) => !representativeIds.has(question.id));
    selected = shuffled([...representatives, ...shuffled(remaining).slice(0, count - representatives.length)]);
  } else {
    selected = selected.slice(0, count);
  }
  state.questions = selected;
  if (!state.questions.length) { showQuizError("В выбранном режиме не нашлось вопросов."); return; }
  state.questionIndex = 0;
  state.answered = false;
  state.selectedAnswer = null;
  state.lastResult = null;
  state.quizError = null;
  state.quizSummary = null;
  const session = {
    id: globalThis.crypto?.randomUUID?.() || `quiz-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    startedAt: new Date().toISOString(), endedAt: null, status: "in_progress",
    context: { type: context.type || "mixed", themeId: context.themeId || "all", subtopicId: context.subtopicId || null, label: context.label || "" },
    questionIds: state.questions.map((question) => question.id), currentIndex: 0,
    current: { selectedAnswer: null, answered: false, result: null, scrollY: 0 }, attempts: [],
    local: state.progress.answer_mode === "local",
  };
  if (state.progress.answer_mode === "database") {
    const headers = databaseHeaders(true);
    if (!headers) return;
    try {
      const response = await fetch("/api/quiz-sessions", {
        method: "POST", headers,
        body: JSON.stringify({ question_ids: session.questionIds, context: session.context, started_at: session.startedAt }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Не удалось сохранить начало тренировки.");
      session.dbSessionId = payload.session_id;
    } catch (error) { showError(error); return; }
  }
  const previous = currentSession();
  if (previous) previous.status = "incomplete";
  state.learning.sessions.push(session);
  state.learning.activeSessionId = session.id;
  state.quizSession = session;
  state.view = "quizzes";
  state.returnContext = null;
  saveLearning();
  history.pushState({ ecolab: true, route: captureRoute() }, "", "#quizzes");
  render();
}
function bindActions() {
  content.querySelectorAll("[data-theme]").forEach((card) => card.addEventListener("click", () => setTheme(card.dataset.theme)));
  content.querySelectorAll("[data-action]").forEach((element) => element.addEventListener("click", async () => {
    const action = element.dataset.action;
    if (action === "back-topics") navigateTo("topics");
    else if (action === "new-quiz") { state.quizSummary = null; state.quizSession = null; state.returnContext = null; navigateTo("quizzes"); }
    else if (action === "resume-quiz") {
      const session = currentSession();
      if (session && restoreSession(session, { view: "quizzes" })) { history.pushState({ ecolab: true, route: captureRoute() }, "", "#quizzes"); render(); }
      else showError(new Error("Сохранённую тренировку не удалось восстановить. Начни новую из списка квизов."));
    }
    else if (action === "return-to-question") {
      if (isReturnContextValid()) {
        const context = state.returnContext;
        const session = state.learning.sessions.find((item) => item.id === context.sessionId);
        restoreSession(session, { view: "quizzes", questionIndex: context.questionIndex });
        state.returnContext = null;
        saveCurrentQuestionState();
        history.pushState({ ecolab: true, route: captureRoute() }, "", "#quizzes");
        render();
        requestAnimationFrame(() => window.scrollTo(0, context.scrollY || 0));
      } else showError(new Error("Исходная тренировка недоступна. Открой раздел «Квизы», чтобы начать новую."));
    }
    else if (action === "return-to-quiz-list") { state.returnContext = null; navigateTo("quizzes"); }
    else if (action === "reset-statistics") {
      if (window.confirm("Удалить сохранённую статистику и незавершённые сессии только из этого браузера? Учебные материалы и PostgreSQL не изменятся.")) {
        state.learning = EcolabLearning.emptyStore();
        state.questions = []; state.quizSession = null; state.quizSummary = null; state.returnContext = null;
        saveLearning(); render();
      }
    }
    else if (action === "load-database-statistics") await loadDatabaseStatistics();
    else if (action.startsWith("theme-from-stats:")) setTheme(action.slice(17));
    else if (action.startsWith("recommend:")) {
      const [, themeId, subtopicId] = action.split(":");
      const theme = state.data.themes.find((item) => item.id === themeId);
      const subtopic = theme?.subtopics.find((item) => item.id === subtopicId);
      if (theme && subtopic) await beginQuiz(subtopic.questions.map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: subtopic.id, subtopic_title: subtopic.title })), subtopic.questions.length, false, { type: "subtopic", themeId, subtopicId, label: `${theme.title} · ${subtopic.title}` });
    }
    else if (action.startsWith("repeat-group:")) {
      const [, groupType, groupId] = action.split(":");
      let questions = allQuestions();
      if (groupType === "theme") questions = questions.filter((question) => question.theme_id === groupId);
      else if (groupType === "subtopic") { const [themeId, subtopicId] = groupId.split("/"); questions = questions.filter((question) => question.theme_id === themeId && question.subtopic_id === subtopicId); }
      else if (groupType === "construction") questions = questions.filter((question) => question.knowledge_id === groupId && question.category === "construction");
      else if (groupType === "question") questions = questions.filter((question) => question.id === groupId);
      if (questions.length) await beginQuiz(questions, questions.length, false, { type: groupType, label: "Повторение ошибок" });
    }
    else if (action.startsWith("pane:")) { state.themePane = action.slice(5); render(); }
    else if (action.startsWith("theme-document:")) renderDocument(currentTheme(), action.slice(15)).catch(showError);
    else if (action.startsWith("subtopic-quiz:")) {
      const id = action.slice(14); const theme = currentTheme();
      const subtopic = theme.subtopics.find((item) => item.id === id);
      await beginQuiz(subtopic?.questions.map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: id, subtopic_title: subtopic.title })) || [], undefined, false, { type: "subtopic", themeId: theme.id, subtopicId: id, label: `${theme.title} · ${subtopic?.title || id}` });
    }
    else if (action === "construction-quiz" || action.startsWith("construction-quiz:")) {
      const constructionId = action.split(":")[1];
      const questions = currentTheme().subtopics.flatMap((subtopic) => subtopic.questions.filter((question) => question.category === "construction" && (!constructionId || question.id.includes(`.construction-${constructionId}-`))).map((question) => ({ ...question, theme_id: currentTheme().id, theme_title: currentTheme().title, subtopic_id: subtopic.id, subtopic_title: subtopic.title })));
      if (questions.length) await beginQuiz(questions, questions.length, false, { type: "construction", themeId: currentTheme().id, label: `${currentTheme().title} · конструкции` }); else showError(new Error("В теме пока нет квиз-вопросов по конструкциям."));
    }
    else if (action === "start-theme-quiz") {
      const theme = currentTheme(); const category = document.querySelector("#theme-quiz-kind").value; const count = Number(document.querySelector("#theme-quiz-count").value);
      const questions = theme.subtopics.flatMap((subtopic) => subtopic.questions.filter((question) => category === "all" || question.category === category).map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: subtopic.id, subtopic_title: subtopic.title })));
      await beginQuiz(questions, count, false, { type: "theme", themeId: theme.id, label: theme.title });
    }
    else if (action === "start-global-quiz") {
      const themeId = document.querySelector("#quiz-theme").value; const category = document.querySelector("#quiz-kind").value; const count = Number(document.querySelector("#quiz-count").value);
      const questions = allQuestions().filter((question) => (themeId === "all" || question.theme_id === themeId) && (category === "all" || question.category === category));
      await beginQuiz(questions, count, themeId === "all", { type: themeId === "all" ? "mixed" : "theme", themeId, label: themeId === "all" ? "Смешанный квиз" : state.data.themes.find((theme) => theme.id === themeId)?.title });
    }
    else if (action === "next-question") {
      if (state.questionIndex + 1 >= state.questions.length) {
        const completed = currentSession();
        let databaseSummary = null;
        if (completed?.dbSessionId) {
          try {
            const headers = databaseHeaders(true);
            const response = await fetch(`/api/quiz-sessions/${completed.dbSessionId}/complete`, {
              method: "POST", headers, body: JSON.stringify({ ended_at: new Date().toISOString() }),
            });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error || "Не удалось завершить сессию в базе.");
            databaseSummary = payload;
          } catch (error) { state.quizError = error.message; render(); return; }
        }
        if (completed) { completed.status = "completed"; completed.endedAt = new Date().toISOString(); }
        const correct = currentSessionAttempts().filter((attempt) => attempt.verdict === "correct").length;
        state.learning.activeSessionId = null;
        state.quizSummary = { total: databaseSummary?.total ?? state.questions.length, correct: databaseSummary?.correct ?? correct, local: state.progress.answer_mode === "local" };
        state.quizSession = null;
        state.questions = [];
      } else {
        state.questionIndex += 1;
      }
      state.answered = false;
      state.selectedAnswer = null;
      state.lastResult = null;
      state.quizError = null;
      state.returnContext = null;
      if (state.quizSession) {
        state.quizSession.currentIndex = state.questionIndex;
        state.quizSession.current = { selectedAnswer: null, answered: false, result: null, scrollY: 0 };
      }
      saveLearning();
      history.pushState({ ecolab: true, route: captureRoute() }, "", "#quizzes");
      render();
    }
    else if (action === "open-answer-theory") {
      const question = state.questions[state.questionIndex];
      saveCurrentQuestionState();
      state.returnContext = { sessionId: currentSession()?.id, questionId: question.id, questionIndex: state.questionIndex, scrollY: window.scrollY };
      state.themeId = question.theme_id; state.view = "theme";
      state.themePane = "theory"; state.subtopicId = question.subtopic_id;
      saveLearning();
      history.pushState({ ecolab: true, route: captureRoute() }, "", `#theme-${encodeURIComponent(question.theme_id)}`);
      render();
      document.querySelector(`#knowledge-${CSS.escape(question.knowledge_id)}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    else if (action === "review-errors") await loadReviewQuestions();
  }));
  content.querySelectorAll('input[name="answer"]').forEach((input) => input.addEventListener("change", () => {
    state.selectedAnswer = input.value;
    state.quizError = null;
    saveCurrentQuestionState();
    replaceCurrentRoute();
  }));
  content.querySelectorAll("[data-view]").forEach((element) => element.addEventListener("click", () => navigateTo(element.dataset.view)));
  const form = document.querySelector("#answer-form");
  if (form) form.addEventListener("submit", submitAnswer);
}

async function submitAnswer(event) {
  event.preventDefault();
  if (state.answered) return;
  const question = state.questions[state.questionIndex];
  const selected = document.querySelector('input[name="answer"]:checked');
  const answer = selected ? selected.value : state.selectedAnswer;
  if (!Array.isArray(question.options) || question.options.length !== 4) { showQuizError("В этом вопросе должны быть настроены ровно четыре варианта ответа."); return; }
  if (answer === null || answer === undefined || answer === "") { showQuizError("Сначала выбери один из четырёх вариантов ответа."); return; }
  const localMode = state.progress.answer_mode === "local";
  const headers = localMode ? { "Content-Type": "application/json" } : databaseHeaders(true);
  if (!headers) return;
  try {
    const response = await fetch("/api/answer", { method: "POST", headers, body: JSON.stringify({ question_id: question.id, answer, ...(localMode ? {} : { session_id: state.quizSession?.dbSessionId }) }) });
    const result = await response.json();
    if (!response.ok) { if (response.status === 401) state.password = null; throw new Error(result.error || "Проверка не удалась."); }
    state.answered = true;
    state.lastResult = result;
    state.quizError = null;
    if (state.quizSession) {
      state.quizSession.local = result.progress_saved === false;
      if (result.progress_saved === false) recordLocalAttempt(question, answer, result);
      saveCurrentQuestionState();
    }
    replaceCurrentRoute();
    render();
    if (result.progress_saved !== false) state.progress = await fetch("/api/progress").then((reply) => reply.json()).catch(() => state.progress);
  } catch (error) {
    const message = error instanceof TypeError
      ? "Не удалось связаться с сервером. Выбранный вариант сохранён — попробуй отправить его ещё раз."
      : error.message || "Проверка не удалась. Выбранный вариант сохранён — попробуй ещё раз.";
    showQuizError(message);
  }
}

function recordLocalAttempt(question, answer, result) {
  const session = currentSession();
  if (!session || session.status !== "in_progress") return;
  if (session.attempts.some((attempt) => attempt.questionId === question.id)) return;
  session.attempts.push({
    questionId: question.id, themeId: question.theme_id, subtopicId: question.subtopic_id,
    constructionId: question.category === "construction" ? question.knowledge_id : null,
    selectedOption: question.options?.[Number(answer)]?.text || String(answer),
    verdict: result.verdict, answeredAt: new Date().toISOString(),
  });
  saveLearning();
}

async function loadReviewQuestions() {
  if (state.password === null) state.password = window.prompt("Пароль сайта (WEB_PASSWORD):");
  if (state.password === null) return;
  try {
    const credential = btoa(String.fromCodePoint(...new TextEncoder().encode(`website:${state.password}`)));
    const response = await fetch("/api/review-questions", { headers: { Authorization: `Basic ${credential}` } });
    const result = await response.json();
    if (!response.ok) { if (response.status === 401) state.password = null; throw new Error(result.error || "Не удалось загрузить повторение."); }
    const ids = new Set(result.question_ids);
    const questions = allQuestions().filter((question) => ids.has(question.id));
    if (!questions.length) throw new Error("Пока нет вопросов, срок повторения которых наступил.");
    await beginQuiz(questions, questions.length, false, { type: "review", label: "Повторение по расписанию" });
  } catch (error) { showError(error); }
}

function databaseHeaders(prompt) {
  if (state.password === null && prompt) state.password = window.prompt("Пароль сайта (WEB_PASSWORD):");
  if (state.password === null) return null;
  return {
    "Content-Type": "application/json",
    Authorization: `Basic ${btoa(String.fromCodePoint(...new TextEncoder().encode(`website:${state.password}`)))}`,
  };
}

async function loadDatabaseStatistics() {
  const headers = databaseHeaders(true);
  if (!headers) return;
  try {
    const response = await fetch("/api/statistics", { headers });
    const payload = await response.json();
    if (!response.ok) { if (response.status === 401) state.password = null; throw new Error(payload.error || "Не удалось загрузить статистику."); }
    const sessions = payload.sessions || [];
    const activeSession = sessions.find((session) => session.status === "in_progress");
    state.remoteLearning = {
      version: 1, sessions, activeSessionId: activeSession?.id || null,
      legacyAttempts: payload.legacyAttempts || 0,
    };
    render();
  } catch (error) { showError(error); }
}

Promise.all([
  fetch("/api/theory").then((response) => { if (!response.ok) throw new Error("Не удалось загрузить учебные темы."); return response.json(); }),
  fetch("/api/progress").then((response) => response.json()).catch(() => ({ available: false, answer_mode: "local", themes: {} })),
]).then(async ([data, progress]) => {
  state.data = data; state.progress = progress; state.learning = EcolabLearning.readStore();
  const storageStatus = document.querySelector("#progress-storage-status");
  if (storageStatus) storageStatus.textContent = progress.answer_mode === "local"
    ? "Проверка и статистика доступны локально; данные хранятся в этом браузере."
    : "Ответы сохраняются в PostgreSQL; локальная статистика не дублирует попытки базы.";
  if (!state.data.themes.length) throw new Error("В библиотеке пока нет учебных тем.");
  const active = currentSession();
  if (active) restoreSession(active, state.learning.lastRoute || { view: "quizzes" });
  else state.view = window.location.hash === "#stats" ? "stats" : window.location.hash === "#quizzes" ? "quizzes" : "topics";
  history.replaceState({ ecolab: true, route: captureRoute() }, "", window.location.hash || "#home");
  render();
}).catch(showError);
