const state = {
  data: null,
  progress: { available: false, themes: {} },
  view: "topics",
  themeId: null,
  themePane: "theory",
  subtopicId: null,
  quizThemeId: "all",
  quizCategory: "all",
  questions: [],
  questionIndex: 0,
  answered: false,
  password: null,
  lastResult: null,
};
const content = document.querySelector("#content");
const nav = document.querySelector("#navigation");
const mainViews = [["topics", "Темы"], ["quizzes", "Квизы"]];

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
  const active = state.view === "quizzes" ? "quizzes" : "topics";
  nav.innerHTML = mainViews.map(([id, label]) => `<a href="#${id}" data-view="${id}" class="${active === id ? "active" : ""}">${label}</a>`).join("");
  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", (event) => {
    event.preventDefault(); state.view = link.dataset.view; state.questions = []; render(); window.scrollTo({ top: 0, behavior: "smooth" });
  }));
}

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
  return `<button class="back-link" data-action="back-topics">← Все темы</button><div class="theme-heading"><div><p class="eyebrow">ТЕМА</p><h2>${escapeHtml(theme.title)}</h2><p>${escapeHtml(theme.description)}</p></div>${progressMarkup(theme.id)}</div><div class="tabs">${panes.map(([id, label]) => button(label, `pane:${id}`, state.themePane === id)).join("")}</div>`;
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
  let group = "";
  for (const line of source.split(/\r?\n/)) {
    const heading = line.match(/^##\s+(.+)$/);
    if (heading) { group = heading[1]; continue; }
    const item = line.match(/^\d+\.\s+\*\*(.+?)\*\*\s*(.*)$/);
    if (item) rows.push({ group, title: item[1].replace(/[.]$/, ""), body: item[2] });
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
  content.innerHTML = `${renderThemeHeader(theme)}<div class="section-head"><div><p class="eyebrow">КОНСТРУКЦИИ ОЛИМПИАДНЫХ ЗАДАЧ</p><h2>Узнай ход задачи</h2></div><p>Признаки, ключевой приём, ограничения и ловушки взяты из каталога. Подробные разборы — в конспекте.</p></div><div class="construction-grid">${cards.map((card, index) => `<article class="construction-card" id="construction-${String(index + 1).padStart(2, "0")}"><span class="topic-number">КОНСТРУКЦИЯ ${String(index + 1).padStart(2, "0")}</span><h3>${escapeHtml(card.title)}</h3><p>${inlineMarkdown(card.body)}</p><small>${escapeHtml(card.group)}</small><button class="text-button" data-action="construction-quiz:${String(index + 1).padStart(2, "0")}">Тренировать эту конструкцию →</button></article>`).join("")}</div><button class="button" data-action="construction-quiz">Тренировать все конструкции →</button><div class="study-card"><h3>Примеры и оговорки источника</h3><p>Открой полный конспект, чтобы перейти к разобранным задачам, вычислениям и отмеченным неоднозначностям.</p><button class="button" data-action="theme-document:study-notes.md">Читать конспект</button></div>`;
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
  return `<div class="section-head"><div><p class="eyebrow">ТРЕНИРОВКА</p><h2>Закрепи тему</h2></div><p>Смешивай теорию и конструкции или выбери отдельный формат.</p></div><div class="quiz-card"><div class="quiz-controls"><label for="theme-quiz-kind">Режим</label><select id="theme-quiz-kind"><option value="all">Смешанный квиз</option><option value="theory">Теория и формулы</option><option value="construction" ${constructions ? "" : "disabled"}>Конструкции задач (${constructions})</option></select></div><div class="quiz-controls"><label for="theme-quiz-count">Вопросов</label><select id="theme-quiz-count"><option>5</option><option selected>10</option><option>20</option></select></div><button class="button primary" data-action="start-theme-quiz">Начать тренировку</button><p class="progress-note">Попытки сохраняются в общий прогресс и расписание повторения.</p></div>`;
}

function renderQuizLanding() {
  const options = state.data.themes.map((theme) => `<option value="${escapeHtml(theme.id)}" ${state.quizThemeId === theme.id ? "selected" : ""}>${escapeHtml(theme.title)}</option>`).join("");
  const constructionCount = allQuestions().filter((question) => question.category === "construction").length;
  return `<div class="section-head"><div><p class="eyebrow">ПРАКТИКА И ПОВТОРЕНИЕ</p><h2>Квизы</h2></div><p>Тренируй одну тему, выбирай тип вопросов или смешивай материал из всей библиотеки.</p></div><div class="quiz-grid"><article class="quiz-card quiz-config"><h3>Новая тренировка</h3><label for="quiz-theme">Тема</label><select id="quiz-theme"><option value="all" ${state.quizThemeId === "all" ? "selected" : ""}>Все темы · смешанный квиз</option>${options}</select><label for="quiz-kind">Что тренируем</label><select id="quiz-kind"><option value="all">Всё вперемешку</option><option value="theory">Теорию и формулы</option><option value="construction" ${constructionCount ? "" : "disabled"}>Конструкции задач (${constructionCount})</option></select><label for="quiz-count">Количество вопросов</label><select id="quiz-count"><option>5</option><option selected>10</option><option>20</option></select><button class="button primary" data-action="start-global-quiz">Начать квиз</button></article><article class="quiz-card review-card"><span class="review-icon">↻</span><h3>Вернуться к ошибкам</h3><p>Повтори вопросы, которые уже пора проверить по расписанию интервального повторения.</p><button class="button" data-action="review-errors">Показать вопросы к повторению</button><p class="progress-note">${state.progress.available ? "История доступна." : "Для истории ответов нужна PostgreSQL и пароль сайта."}</p></article></div>`;
}

function renderQuizQuestion() {
  const question = state.questions[state.questionIndex];
  const options = question.options.length ? `<div>${question.options.map((option, index) => `<label class="quiz-option"><input type="radio" name="answer" value="${index}" ${state.answered ? "disabled" : ""}><span>${escapeHtml(option.text)}</span></label>`).join("")}</div>` : `<textarea class="answer" name="answer" placeholder="Запиши ответ своими словами или формулой" ${state.answered ? "disabled" : ""}></textarea>`;
  const result = state.lastResult;
  const feedback = result ? `<div class="feedback ${result.verdict === "incorrect" ? "error" : ""}"><strong>${result.verdict === "correct" ? "Верно!" : result.verdict === "partial" ? "Частично верно" : result.verdict === "uncertain" ? "Ответ сохранён, нужна проверка" : "Неверно — разберём ответ"}</strong><p>${escapeHtml(result.short_explanation || "")}</p><p><strong>Правильный ответ:</strong> ${escapeHtml(result.reference_answer)}</p><p>${escapeHtml(result.explanation)}</p><p class="source">Основание: ${escapeHtml(result.source_excerpt)}</p><button class="text-button" data-action="open-answer-theory">Открыть связанный раздел теории →</button></div>` : "";
  return `<div class="quiz-card active-quiz"><p class="eyebrow">${escapeHtml(question.theme_title)} · ${escapeHtml(question.subtopic_title)}</p><span class="quiz-progress">ВОПРОС ${state.questionIndex + 1} / ${state.questions.length} · СЛОЖНОСТЬ ${question.difficulty}/5</span><p class="quiz-question">${escapeHtml(question.question)}</p><form id="answer-form">${options}<div class="quiz-actions"><button class="button primary" type="submit" ${state.answered ? "disabled" : ""}>Проверить ответ</button>${state.answered ? `<button class="button" type="button" data-action="next-question">${state.questionIndex + 1 === state.questions.length ? "Завершить" : "Следующий вопрос"}</button>` : ""}</div></form>${feedback}</div>`;
}

function render() {
  setNavigation();
  if (!state.data) { content.innerHTML = `<p class="loading">Загружаю библиотеку…</p>`; return; }
  if (state.view === "topics") content.innerHTML = renderTopics();
  else if (state.view === "quizzes") content.innerHTML = state.questions.length ? renderQuizQuestion() : renderQuizLanding();
  else {
    const theme = currentTheme();
    const body = state.themePane === "theory" ? renderThemeTheoryContent(theme) : state.themePane === "quiz" ? renderThemeQuiz(theme) : "";
    if (state.themePane === "constructions") { renderConstructions(theme).catch(showError); return; }
    content.innerHTML = `${renderThemeHeader(theme)}${body}`;
  }
  bindActions();
}

function showError(error) { content.innerHTML = `<div class="feedback error">${escapeHtml(error.message)}</div>`; }
function setTheme(id) { state.themeId = id; state.subtopicId = null; state.themePane = "theory"; state.view = "theme"; render(); window.scrollTo({ top: 0, behavior: "smooth" }); }
function beginQuiz(questions) {
  state.questions = [...questions].sort(() => Math.random() - 0.5);
  state.questionIndex = 0; state.answered = false; state.lastResult = null; state.view = "quizzes"; render();
}
function bindActions() {
  content.querySelectorAll("[data-theme]").forEach((card) => card.addEventListener("click", () => setTheme(card.dataset.theme)));
  content.querySelectorAll("[data-action]").forEach((element) => element.addEventListener("click", async () => {
    const action = element.dataset.action;
    if (action === "back-topics") { state.view = "topics"; state.questions = []; render(); }
    else if (action.startsWith("pane:")) { state.themePane = action.slice(5); render(); }
    else if (action.startsWith("theme-document:")) renderDocument(currentTheme(), action.slice(15)).catch(showError);
    else if (action.startsWith("subtopic-quiz:")) {
      const id = action.slice(14); const theme = currentTheme();
      beginQuiz(theme.subtopics.find((item) => item.id === id)?.questions.map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: id, subtopic_title: theme.subtopics.find((item) => item.id === id).title })) || []);
    }
    else if (action === "construction-quiz" || action.startsWith("construction-quiz:")) {
      const constructionId = action.split(":")[1];
      const questions = currentTheme().subtopics.flatMap((subtopic) => subtopic.questions.filter((question) => question.category === "construction" && (!constructionId || question.id.includes(`.construction-${constructionId}-`))).map((question) => ({ ...question, theme_id: currentTheme().id, theme_title: currentTheme().title, subtopic_id: subtopic.id, subtopic_title: subtopic.title })));
      if (questions.length) beginQuiz(questions); else showError(new Error("В теме пока нет квиз-вопросов по конструкциям."));
    }
    else if (action === "start-theme-quiz") {
      const theme = currentTheme(); const category = document.querySelector("#theme-quiz-kind").value; const count = Number(document.querySelector("#theme-quiz-count").value);
      const questions = theme.subtopics.flatMap((subtopic) => subtopic.questions.filter((question) => category === "all" || question.category === category).map((question) => ({ ...question, theme_id: theme.id, theme_title: theme.title, subtopic_id: subtopic.id, subtopic_title: subtopic.title })));
      beginQuiz(questions.slice(0, count));
    }
    else if (action === "start-global-quiz") {
      const themeId = document.querySelector("#quiz-theme").value; const category = document.querySelector("#quiz-kind").value; const count = Number(document.querySelector("#quiz-count").value);
      const questions = allQuestions().filter((question) => (themeId === "all" || question.theme_id === themeId) && (category === "all" || question.category === category));
      beginQuiz(questions.slice(0, count));
    }
    else if (action === "next-question") {
      state.questionIndex += 1; state.answered = false; state.lastResult = null;
      if (state.questionIndex >= state.questions.length) { state.questions = []; state.view = "quizzes"; }
      render();
    }
    else if (action === "open-answer-theory") {
      const question = state.questions[state.questionIndex]; setTheme(question.theme_id);
      state.themePane = "theory"; state.subtopicId = question.subtopic_id; render();
      document.querySelector(`#knowledge-${CSS.escape(question.knowledge_id)}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    else if (action === "review-errors") await loadReviewQuestions();
  }));
  const form = document.querySelector("#answer-form");
  if (form) form.addEventListener("submit", submitAnswer);
}

async function submitAnswer(event) {
  event.preventDefault();
  const question = state.questions[state.questionIndex];
  const selected = document.querySelector('input[name="answer"]:checked');
  const freeText = document.querySelector('textarea[name="answer"]');
  const answer = selected ? selected.value : freeText?.value.trim();
  if (answer === undefined || answer === "") { showError(new Error("Сначала выбери вариант или введи ответ.")); return; }
  if (state.password === null) state.password = window.prompt("Пароль сайта (WEB_PASSWORD):");
  if (state.password === null) return;
  try {
    const credential = btoa(String.fromCodePoint(...new TextEncoder().encode(`website:${state.password}`)));
    const response = await fetch("/api/answer", { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Basic ${credential}` }, body: JSON.stringify({ question_id: question.id, answer }) });
    const result = await response.json();
    if (!response.ok) { if (response.status === 401) state.password = null; throw new Error(result.error || "Проверка не удалась."); }
    state.answered = true; state.lastResult = result; render();
    state.progress = await fetch("/api/progress").then((reply) => reply.json()).catch(() => state.progress);
  } catch (error) { showError(error); }
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
    beginQuiz(questions);
  } catch (error) { showError(error); }
}

Promise.all([
  fetch("/api/theory").then((response) => { if (!response.ok) throw new Error("Не удалось загрузить учебные темы."); return response.json(); }),
  fetch("/api/progress").then((response) => response.json()).catch(() => ({ available: false, themes: {} })),
]).then(([data, progress]) => {
  state.data = data; state.progress = progress;
  if (!state.data.themes.length) throw new Error("В библиотеке пока нет учебных тем.");
  render();
}).catch(showError);
