const initialTasks = window.adminInitialTasks || [];
const initialAiAllowed = window.adminInitialAiAllowed || [];

const adminTaskList = document.getElementById("adminTaskList");
const adminSearch = document.getElementById("adminSearch");
const adminUserFilter = document.getElementById("adminUserFilter");
const adminSort = document.getElementById("adminSort");
const adminEditor = document.getElementById("adminEditor");
const adminEmpty = document.getElementById("adminEmpty");
const adminTaskTitle = document.getElementById("adminTaskTitle");
const adminTaskSubline = document.getElementById("adminTaskSubline");
const adminHeadingTags = document.getElementById("adminHeadingTags");
const adminFilename = document.getElementById("adminFilename");
const adminDownloadLink = document.getElementById("adminDownloadLink");
const adminPreviewWrap = document.getElementById("adminPreviewWrap");
const previewFitBtn = document.getElementById("previewFitBtn");
const previewScrollBtn = document.getElementById("previewScrollBtn");
const previewZoomInBtn = document.getElementById("previewZoomInBtn");
const previewZoomOutBtn = document.getElementById("previewZoomOutBtn");
const previewRotateBtn = document.getElementById("previewRotateBtn");
const adminFileMeta = document.getElementById("adminFileMeta");
const adminTaskTextBlock = document.getElementById("adminTaskTextBlock");
const adminAnswerText = document.getElementById("adminAnswerText");
const adminInProgressToggle = document.getElementById("adminInProgressToggle");
const adminWorkOwner = document.getElementById("adminWorkOwner");
const releaseWorkBtn = document.getElementById("releaseWorkBtn");
const adminSaveStatus = document.getElementById("adminSaveStatus");
const adminFlash = document.getElementById("adminFlash");
const prevTaskBtn = document.getElementById("prevTaskBtn");
const nextTaskBtn = document.getElementById("nextTaskBtn");
const nextOpenTaskBtn = document.getElementById("nextOpenTaskBtn");
const refreshTasksBtn = document.getElementById("refreshTasksBtn");
const clearFiltersBtn = document.getElementById("clearFiltersBtn");
const sendAnswerBtnAdmin = document.getElementById("sendAnswerBtnAdmin");
const sendAiAnswerBtn = document.getElementById("sendAiAnswerBtn");
const saveAnswerBtnAdmin = document.getElementById("saveAnswerBtnAdmin");
const deleteStudentAnswerBtn = document.getElementById("deleteStudentAnswerBtn");
const clearAnswerBtn = document.getElementById("clearAnswerBtn");
const deleteTaskBtn = document.getElementById("deleteTaskBtn");
const statTotal = document.getElementById("statTotal");
const statSolved = document.getElementById("statSolved");
const statOpen = document.getElementById("statOpen");
const statProcessing = document.getElementById("statProcessing");
const filterButtons = [...document.querySelectorAll(".admin_filter_btn")];
const mobileListBtn = document.getElementById("mobileListBtn");
const mobileEditorBtn = document.getElementById("mobileEditorBtn");
const mobileRefreshBtn = document.getElementById("mobileRefreshBtn");
const adminLogoutForm = document.getElementById("adminLogoutForm");
const adminUnsavedDialog = document.getElementById("adminUnsavedDialog");
const unsavedSaveBtn = document.getElementById("unsavedSaveBtn");
const unsavedDiscardBtn = document.getElementById("unsavedDiscardBtn");
const unsavedCancelBtn = document.getElementById("unsavedCancelBtn");
const AUTO_REFRESH_MS = 8000;

const STATUS_OPEN = "без ответа";
const STATUS_PROCESSING = "в работе";
const STATUS_SOLVED = "с ответом";

const state = {
  tasks: normalizeTasks(initialTasks),
  selectedTaskKey: null,
  filter: "all",
  sort: "priority",
  query: "",
  userFilter: "",
  mobilePane: "list",
  refreshInFlight: false,
  snapshot: "",
  aiAllowed: normalizeAiAllowed(initialAiAllowed),
  answerDirty: false,
  previewMode: "fit",
  previewScale: 1,
  previewRotation: 0,
  pendingUnsavedAction: null,
};

function normalizeAiAllowed(nicknames) {
  return [...new Set((nicknames || []).map((item) => String(item || "").trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, "ru", { sensitivity: "base" }));
}

function normalizeTasks(tasks) {
  return [...tasks].map((task) => ({
    ...task,
    task_number: String(task.task_number || ""),
    user_id: Number(task.user_id || 0),
    user_uid: String(task.user_uid || ""),
    user_nickname: task.user_nickname || "",
    user_current_task: String(task.user_current_task || ""),
    task_key: task.task_key || `submission:${task.id}`,
    admin_answer: task.admin_answer || "",
    ai_answer: task.ai_answer || "",
    answer_text: task.answer_text || "",
    task_text: task.task_text || "",
    filename: task.filename || "",
    file_url: task.file_url || "",
    created: task.created || task.created_at || "",
    submitted_at: task.submitted_at || task.created || task.created_at || "",
    answer_source: task.answer_source || "",
    task_priority: Number(task.task_priority || 0),
    tags: Array.isArray(task.tags) ? task.tags : [],
    ai_processing: Boolean(task.ai_processing),
    admin_processing: Boolean(task.admin_processing),
    admin_processing_by: String(task.admin_processing_by || ""),
  })).sort(compareAdminTasks);
}

function compareAdminTasks(a, b) {
  const priorityDiff = Number(b.task_priority || 0) - Number(a.task_priority || 0);
  if (priorityDiff !== 0) return priorityDiff;
  const submittedDiff = String(b.submitted_at || "").localeCompare(String(a.submitted_at || ""));
  if (submittedDiff !== 0) return submittedDiff;
  return String(a.task_number || "").localeCompare(String(b.task_number || ""), "ru", { numeric: true });
}

function compareByCurrentSort(a, b) {
  if (state.sort === "newest") return String(b.submitted_at || "").localeCompare(String(a.submitted_at || ""));
  if (state.sort === "oldest") return String(a.submitted_at || "").localeCompare(String(b.submitted_at || ""));
  if (state.sort === "user") {
    const userDiff = getUserLabel(a).localeCompare(getUserLabel(b), "ru", { sensitivity: "base", numeric: true });
    return userDiff || compareAdminTasks(a, b);
  }
  if (state.sort === "open_first") {
    const openDiff = Number(getVisibleStatus(b) === STATUS_OPEN) - Number(getVisibleStatus(a) === STATUS_OPEN);
    return openDiff || compareAdminTasks(a, b);
  }
  return compareAdminTasks(a, b);
}

function buildTasksSnapshot(tasks) {
  return JSON.stringify(
    (tasks || []).map((task) => [
      String(task.task_key || ""),
      Number(task.user_id || 0),
      String(task.user_uid || ""),
      String(task.user_nickname || ""),
      String(task.user_current_task || ""),
      String(task.task_number || ""),
      String(task.filename || ""),
      String(task.created || ""),
      String(task.submitted_at || ""),
      String(task.answer_text || ""),
      String(task.answer_source || ""),
      Number(task.task_priority || 0),
      String(task.admin_answer || ""),
      String(task.ai_answer || ""),
      Boolean(task.admin_processing),
      Boolean(task.ai_processing),
      String(task.admin_processing_by || ""),
    ]),
  );
}

function getUserLabel(task) {
  const nickname = String(task.user_nickname || "").trim();
  return nickname ? `${nickname} · ID ${task.user_uid || task.user_id}` : `ID ${task.user_uid || task.user_id}`;
}

function getVisibleStatus(task) {
  if (String(task.admin_answer || task.answer_text || "").trim() || String(task.ai_answer || "").trim()) return STATUS_SOLVED;
  if (task.ai_processing || task.admin_processing) return STATUS_PROCESSING;
  return STATUS_OPEN;
}

function getAnswerTags(task) {
  const tags = [];
  if (String(task.ai_answer || "").trim() || task.answer_source === "ai") {
    tags.push({ label: "Ответ ИИ", className: "is-ai" });
  }
  if (String(task.admin_answer || "").trim() || task.answer_source === "admin") {
    tags.push({ label: "Ответ Админа", className: "is-admin" });
  }
  return tags;
}

function getContentType(task) {
  const text = String(task.task_text || "").trim();
  if (task.filename) return "file";
  if (/^(https?:\/\/|www\.|localhost|127\.0\.0\.1)/i.test(text)) return "link";
  if (text) return "text";
  return "empty";
}

function getContentLabel(task) {
  const type = getContentType(task);
  if (type === "file") return "Файл приложен";
  if (type === "link") return "Ссылка";
  if (type === "text") return "Текст";
  return "Без текста и файла";
}

function getContentBadge(task) {
  const type = getContentType(task);
  if (type === "file") return "Файл";
  if (type === "link") return "Ссылка";
  if (type === "text") return "Текст";
  return "Пусто";
}

function isTaskUserAiAllowed(task) {
  const nickname = String(task.user_nickname || "").trim().toLowerCase();
  return Boolean(nickname) && state.aiAllowed.some((item) => item.toLowerCase() === nickname);
}

function hasAnyTaskInAdminProgress(exceptTaskKey = "") {
  return state.tasks.some((task) => task.task_key !== exceptTaskKey && task.admin_processing);
}

function getFilteredTasks() {
  const filtered = state.tasks.filter((task) => {
    if (state.filter === "open" && getVisibleStatus(task) !== STATUS_OPEN) return false;
    if (state.filter === "processing" && getVisibleStatus(task) !== STATUS_PROCESSING) return false;
    if (state.filter === "solved" && getVisibleStatus(task) !== STATUS_SOLVED) return false;
    if (state.userFilter && String(task.user_id) !== state.userFilter) return false;

    if (!state.query) return true;
    const haystack = [
      String(task.user_id),
      task.user_uid,
      task.user_nickname,
      task.task_number,
      task.filename,
      task.created,
      task.submitted_at,
      task.answer_text,
      task.task_text,
    ].join(" ").toLowerCase();
    return haystack.includes(state.query);
  });
  return filtered.sort(compareByCurrentSort);
}

function renderStats() {
  const total = state.tasks.length;
  const open = state.tasks.filter((task) => getVisibleStatus(task) === STATUS_OPEN).length;
  const processing = state.tasks.filter((task) => getVisibleStatus(task) === STATUS_PROCESSING).length;
  const solved = state.tasks.filter((task) => getVisibleStatus(task) === STATUS_SOLVED).length;
  statTotal.textContent = total;
  statOpen.textContent = open;
  statProcessing.textContent = processing;
  statSolved.textContent = solved;
  updateFilterLabels({ total, open, processing, solved });
}

function updateFilterLabels(stats) {
  const labels = {
    all: ["Все", stats.total],
    open: ["Без ответа", stats.open],
    processing: ["В работе", stats.processing],
    solved: ["С ответом", stats.solved],
  };
  filterButtons.forEach((button) => {
    const [label, count] = labels[button.dataset.filter] || ["", 0];
    button.innerHTML = `${label} <span>${count}</span>`;
  });
}

function renderUserFilter() {
  const users = [...new Set(state.tasks.map((task) => String(task.user_id)))].sort((a, b) => Number(a) - Number(b));
  const currentValue = state.userFilter;
  adminUserFilter.innerHTML = '<option value="">Все пользователи</option>';
  users.forEach((userId) => {
    const option = document.createElement("option");
    option.value = userId;
    const userTask = state.tasks.find((task) => String(task.user_id) === userId);
    option.textContent = userTask ? getUserLabel(userTask) : `ID ${userId}`;
    if (userId === currentValue) option.selected = true;
    adminUserFilter.appendChild(option);
  });
}

function renderTaskList() {
  const filtered = getFilteredTasks();
  adminTaskList.innerHTML = "";

  if (!filtered.length) {
    adminTaskList.innerHTML = '<div class="admin_list_empty">Ничего не найдено по текущему фильтру.</div>';
    renderEditor(null);
    return;
  }

  if (!filtered.some((task) => task.task_key === state.selectedTaskKey)) {
    state.selectedTaskKey = filtered[0].task_key;
  }

  filtered.forEach((task) => {
    const item = document.createElement("button");
    const status = getVisibleStatus(task);
    const contentText = task.filename || String(task.task_text || "").trim();
    item.type = "button";
    item.className = "admin_task_item";
    item.classList.toggle("active", task.task_key === state.selectedTaskKey);
    item.classList.toggle("is-solved", status === STATUS_SOLVED);
    item.classList.toggle("is-processing", status === STATUS_PROCESSING);
    const answerTags = getAnswerTags(task)
      .map((tag) => `<span class="admin_task_answer_tag ${tag.className}">${escapeHtml(tag.label)}</span>`)
      .join("");
    item.innerHTML = `
      <span class="admin_task_top">
        <span class="admin_task_num">№${escapeHtml(task.task_number)}</span>
        <span class="admin_task_statuses">
          <span class="admin_task_badge">${escapeHtml(status)}</span>
          ${answerTags}
        </span>
      </span>
      <span class="admin_task_user">${escapeHtml(getUserLabel(task))}</span>
      <span class="admin_task_priority">Приоритет: ${escapeHtml(task.task_priority)}</span>
      <span class="admin_task_type">${escapeHtml(getContentLabel(task))}</span>
      <span class="admin_task_bottom">
        <span class="admin_task_name">${escapeHtml(truncateText(contentText || "Нет содержимого", 78))}</span>
        <span class="admin_task_time">${escapeHtml(formatTime(task.submitted_at))}</span>
      </span>
    `;
    item.addEventListener("click", () => {
      guardUnsaved(() => selectTask(task, { force: true }));
    });
    adminTaskList.appendChild(item);
  });

  renderEditor(filtered.find((task) => task.task_key === state.selectedTaskKey) || null);
}

function setAnswerStatus(text, tone = "") {
  adminSaveStatus.textContent = text;
  adminSaveStatus.classList.toggle("is-dirty", tone === "dirty");
  adminSaveStatus.classList.toggle("is-saving", tone === "saving");
  adminSaveStatus.classList.toggle("is-error", tone === "error");
  adminSaveStatus.classList.toggle("is-filled", tone === "filled");
}

function syncAnswerStatus() {
  const hasText = Boolean(adminAnswerText.value.trim());
  if (state.answerDirty) {
    setAnswerStatus("Есть несохранённые изменения", "dirty");
    return;
  }
  setAnswerStatus(hasText ? "Заполнен" : "Не заполнен", hasText ? "filled" : "");
}

function markAnswerDirty() {
  state.answerDirty = true;
  syncAnswerStatus();
}

function resetPreviewState() {
  state.previewMode = "fit";
  state.previewScale = 1;
  state.previewRotation = 0;
}

function syncPreviewMode() {
  if (!adminPreviewWrap) return;
  const img = adminPreviewWrap.querySelector(".admin_preview_image");
  const isOriginal = state.previewMode === "original";
  adminPreviewWrap.classList.toggle("is-original", isOriginal);
  previewFitBtn.classList.toggle("active", !isOriginal);
  previewScrollBtn.classList.toggle("active", isOriginal);
  if (img) {
    img.style.setProperty("--preview-scale", String(state.previewScale));
    img.style.setProperty("--preview-rotation", `${state.previewRotation}deg`);
  }
}

function getNextOpenTask() {
  const filtered = getFilteredTasks();
  if (!filtered.length) return null;
  const currentIndex = filtered.findIndex((task) => task.task_key === state.selectedTaskKey);
  const splitIndex = currentIndex === -1 ? 0 : currentIndex + 1;
  const ordered = [...filtered.slice(splitIndex), ...filtered.slice(0, splitIndex)];
  return ordered.find((task) => getVisibleStatus(task) === STATUS_OPEN) || null;
}

function selectTask(task, options = {}) {
  if (!task) return;
  if (!options.force && state.answerDirty) {
    guardUnsaved(() => selectTask(task, { force: true }));
    return;
  }
  state.selectedTaskKey = task.task_key;
  state.mobilePane = "editor";
  state.answerDirty = false;
  resetPreviewState();
  renderTaskList();
  requestAnimationFrame(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  });
}

function renderHeadingTags(task) {
  const status = getVisibleStatus(task);
  const tags = [
    `<span class="admin_tag ${getStatusClass(status)}">${escapeHtml(status)}</span>`,
    `<span class="admin_tag is-info">${escapeHtml(getContentBadge(task))}</span>`,
    `<span class="admin_tag is-info">Приоритет: ${escapeHtml(task.task_priority)}</span>`,
    `<span class="admin_tag ${isTaskUserAiAllowed(task) ? "is-success" : "is-info"}">${isTaskUserAiAllowed(task) ? "AI разрешён" : "AI запрещён"}</span>`,
  ];
  adminHeadingTags.innerHTML = tags.join("");
}

function renderPreview(task) {
  const hasFile = Boolean(task.filename && task.file_url);
  const toolbarButtons = [previewFitBtn, previewScrollBtn, previewZoomInBtn, previewZoomOutBtn, previewRotateBtn];
  adminFileMeta.hidden = !hasFile;
  adminDownloadLink.hidden = !hasFile;
  toolbarButtons.forEach((button) => { button.hidden = true; });
  adminPreviewWrap.hidden = true;
  adminPreviewWrap.innerHTML = "";
  if (!hasFile) return;

  adminFilename.textContent = task.filename || "Без файла";
  adminDownloadLink.href = task.file_url;
  const lowerName = task.filename.toLowerCase();
  const isImage = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"].some((ext) => lowerName.endsWith(ext));

  if (isImage) {
    adminPreviewWrap.hidden = false;
    toolbarButtons.forEach((button) => { button.hidden = false; });
    const img = document.createElement("img");
    img.src = task.file_url;
    img.alt = `Задание ${task.task_number}`;
    img.className = "admin_preview_image";
    adminPreviewWrap.appendChild(img);
    syncPreviewMode();
  }
}

function renderEditor(task) {
  if (!task) {
    adminEditor.hidden = true;
    adminEmpty.hidden = false;
    adminHeadingTags.innerHTML = "";
    syncMobilePane();
    return;
  }

  adminEditor.hidden = false;
  adminEmpty.hidden = true;
  adminTaskTitle.textContent = `№${task.task_number}${task.user_nickname ? ` — ${task.user_nickname}` : ""}`;
  adminTaskSubline.textContent = `ID ${task.user_uid || task.user_id} · Отправлено: ${formatDateTime(task.submitted_at)}`;
  adminAnswerText.value = task.answer_text || "";
  state.answerDirty = false;
  syncAnswerStatus();
  adminInProgressToggle.checked = Boolean(task.admin_processing);
  adminInProgressToggle.disabled = Boolean(String(task.admin_answer || "").trim()) || (
    !task.admin_processing && hasAnyTaskInAdminProgress(task.task_key)
  );
  adminWorkOwner.textContent = task.admin_processing_by ? `В работе: ${task.admin_processing_by}` : "";
  releaseWorkBtn.hidden = !task.admin_processing;

  const taskText = String(task.task_text || "").trim();
  adminTaskTextBlock.hidden = !taskText;
  adminTaskTextBlock.textContent = taskText;

  renderHeadingTags(task);
  renderPreview(task);
  syncNavigation();
  syncMobilePane();
}

function syncNavigation() {
  const filtered = getFilteredTasks();
  const index = filtered.findIndex((task) => task.task_key === state.selectedTaskKey);
  prevTaskBtn.disabled = index <= 0;
  nextTaskBtn.disabled = index === -1 || index >= filtered.length - 1;
  nextOpenTaskBtn.disabled = !getNextOpenTask();
}

function updateTaskInState(updatedTask) {
  const normalized = normalizeTasks([updatedTask])[0];
  const index = state.tasks.findIndex((task) => task.task_key === normalized.task_key);
  if (index === -1) state.tasks.push(normalized);
  else state.tasks[index] = normalized;
  state.tasks.sort(compareAdminTasks);
  state.snapshot = buildTasksSnapshot(state.tasks);
}

async function saveCurrentTask(fields, options = {}) {
  const task = state.tasks.find((item) => item.task_key === state.selectedTaskKey);
  if (!task) return false;

  try {
    setAnswerStatus("Сохраняю...", "saving");
    const response = await fetch(`/api/tasks/${encodeURIComponent(task.task_key)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showFlash(data.error || "Не удалось сохранить", true);
      renderEditor(task);
      setAnswerStatus("Ошибка сохранения", "error");
      return false;
    }
    if (Array.isArray(data.tasks)) {
      state.tasks = normalizeTasks(data.tasks);
      state.snapshot = buildTasksSnapshot(state.tasks);
    } else {
      updateTaskInState(data.task);
    }
    renderStats();
    renderUserFilter();
    renderTaskList();
    state.mobilePane = "editor";
    state.answerDirty = false;
    syncMobilePane();
    syncAnswerStatus();
    showFlash(options.successMessage || "Сохранено");
    return true;
  } catch (error) {
    showFlash("Не удалось сохранить", true);
    setAnswerStatus("Ошибка сохранения", "error");
    return false;
  }
}

async function deleteCurrentTask() {
  const task = state.tasks.find((item) => item.task_key === state.selectedTaskKey);
  if (!task) return false;
  if (!confirm(`Полностью удалить задание №${task.task_number} из выдачи?`)) return false;

  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(task.task_key)}`, {
      method: "DELETE",
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showFlash(data.error || "Не удалось удалить задание", true);
      return false;
    }
    state.tasks = normalizeTasks(data.tasks || []);
    state.snapshot = buildTasksSnapshot(state.tasks);
    const filtered = getFilteredTasks();
    state.selectedTaskKey = filtered[0] ? filtered[0].task_key : null;
    state.answerDirty = false;
    renderStats();
    renderUserFilter();
    renderTaskList();
    showFlash("Задание удалено");
    return true;
  } catch (error) {
    showFlash("Не удалось удалить задание", true);
    return false;
  }
}

async function refreshTasks(options = {}) {
  const { silent = false, preserveDraft = false } = options;
  if (state.refreshInFlight) return;
  if (state.answerDirty && preserveDraft) return;

  const keepAnswer = preserveDraft && document.activeElement === adminAnswerText;
  const answerDraft = keepAnswer ? adminAnswerText.value : null;

  state.refreshInFlight = true;
  try {
    const response = await fetch("/api/tasks");
    const data = await response.json();
    if (!response.ok || !data.ok) {
      if (!silent) showFlash(data.error || "Не удалось обновить список", true);
      return;
    }
    const nextTasks = normalizeTasks(data.tasks || []);
    const nextSnapshot = buildTasksSnapshot(nextTasks);
    if (nextSnapshot === state.snapshot) return;
    state.tasks = nextTasks;
    state.snapshot = nextSnapshot;
    if (!state.tasks.some((task) => task.task_key === state.selectedTaskKey)) {
      state.selectedTaskKey = state.tasks[0] ? state.tasks[0].task_key : null;
    }
    renderStats();
    renderUserFilter();
    renderTaskList();
    if (keepAnswer) {
      adminAnswerText.focus();
      adminAnswerText.value = answerDraft;
      markAnswerDirty();
    }
    if (!silent) showFlash("Список обновлён");
  } catch (error) {
    if (!silent) showFlash("Не удалось обновить список", true);
  } finally {
    state.refreshInFlight = false;
  }
}

function showFlash(text, isError = false) {
  adminFlash.textContent = text;
  adminFlash.classList.toggle("is-error", isError);
  adminFlash.classList.add("visible");
  clearTimeout(showFlash._timer);
  showFlash._timer = setTimeout(() => {
    adminFlash.classList.remove("visible");
  }, 1800);
}

function setActiveFilter(filter) {
  state.filter = filter;
  filterButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.filter === filter);
  });
}

function clearFilters() {
  state.query = "";
  state.userFilter = "";
  state.sort = "priority";
  setActiveFilter("all");
  adminSearch.value = "";
  adminUserFilter.value = "";
  adminSort.value = "priority";
  renderTaskList();
}

function syncMobilePane() {
  const isMobile = window.matchMedia("(max-width: 860px)").matches;
  document.body.classList.toggle("admin_mobile_list", isMobile && state.mobilePane === "list");
  document.body.classList.toggle("admin_mobile_editor", isMobile && state.mobilePane === "editor");
  mobileListBtn.classList.toggle("active", !isMobile || state.mobilePane === "list");
  mobileEditorBtn.classList.toggle("active", isMobile && state.mobilePane === "editor");
}

function guardUnsaved(action) {
  if (!state.answerDirty) {
    action();
    return;
  }
  state.pendingUnsavedAction = action;
  adminUnsavedDialog.hidden = false;
}

function closeUnsavedDialog() {
  adminUnsavedDialog.hidden = true;
  state.pendingUnsavedAction = null;
}

async function saveAndContinuePendingAction() {
  const action = state.pendingUnsavedAction;
  const saved = await saveCurrentTask({ answer_text: adminAnswerText.value });
  adminUnsavedDialog.hidden = true;
  state.pendingUnsavedAction = null;
  if (saved && action) action();
}

function discardAndContinuePendingAction() {
  const action = state.pendingUnsavedAction;
  state.answerDirty = false;
  adminUnsavedDialog.hidden = true;
  state.pendingUnsavedAction = null;
  if (action) action();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function truncateText(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function formatDateTime(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (match) return `${match[3]}.${match[2]}.${match[1]}, ${match[4]}:${match[5]}`;
  return text || "не указано";
}

function formatTime(value) {
  const text = String(value || "").trim();
  const match = text.match(/[ T](\d{2}):(\d{2})/);
  return match ? `${match[1]}:${match[2]}` : "";
}

function getStatusClass(status) {
  if (status === STATUS_SOLVED) return "is-success";
  if (status === STATUS_PROCESSING) return "is-warning";
  return "is-danger";
}

adminSearch.addEventListener("input", () => {
  state.query = adminSearch.value.trim().toLowerCase();
  renderTaskList();
});

adminUserFilter.addEventListener("change", () => {
  state.userFilter = adminUserFilter.value;
  renderTaskList();
});

adminSort.addEventListener("change", () => {
  state.sort = adminSort.value;
  renderTaskList();
});

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setActiveFilter(button.dataset.filter);
    renderTaskList();
  });
});

prevTaskBtn.addEventListener("click", () => {
  const filtered = getFilteredTasks();
  const index = filtered.findIndex((task) => task.task_key === state.selectedTaskKey);
  if (index > 0) guardUnsaved(() => selectTask(filtered[index - 1], { force: true }));
});

nextTaskBtn.addEventListener("click", () => {
  const filtered = getFilteredTasks();
  const index = filtered.findIndex((task) => task.task_key === state.selectedTaskKey);
  if (index !== -1 && index < filtered.length - 1) {
    guardUnsaved(() => selectTask(filtered[index + 1], { force: true }));
  }
});

nextOpenTaskBtn.addEventListener("click", () => {
  const task = getNextOpenTask();
  if (task) guardUnsaved(() => selectTask(task, { force: true }));
});

clearFiltersBtn.addEventListener("click", clearFilters);
refreshTasksBtn.addEventListener("click", () => guardUnsaved(() => refreshTasks()));
mobileRefreshBtn.addEventListener("click", () => guardUnsaved(() => refreshTasks()));

sendAnswerBtnAdmin.addEventListener("click", () =>
  saveCurrentTask({ answer_text: adminAnswerText.value }, { successMessage: "Ответ отправлен ученику" }),
);

if (sendAiAnswerBtn) {
  sendAiAnswerBtn.addEventListener("click", () =>
    saveCurrentTask({ ai_answer_text: adminAnswerText.value }, { successMessage: "Ответ отправлен как ИИ" }),
  );
}

saveAnswerBtnAdmin.addEventListener("click", () =>
  saveCurrentTask({ answer_text: adminAnswerText.value }),
);

deleteStudentAnswerBtn.addEventListener("click", () => {
  if (!confirm("Удалить сохранённый ответ у ученика?")) return;
  adminAnswerText.value = "";
  saveCurrentTask({ answer_text: "", ai_answer_text: "" }, { successMessage: "Ответ удалён у ученика" });
});

clearAnswerBtn.addEventListener("click", () => {
  adminAnswerText.value = "";
  markAnswerDirty();
  adminAnswerText.focus();
});

if (deleteTaskBtn) {
  deleteTaskBtn.addEventListener("click", () => {
    guardUnsaved(deleteCurrentTask);
  });
}

adminAnswerText.addEventListener("input", markAnswerDirty);

adminInProgressToggle.addEventListener("change", () => {
  saveCurrentTask({ admin_in_progress: adminInProgressToggle.checked });
});

releaseWorkBtn.addEventListener("click", () => {
  adminInProgressToggle.checked = false;
  saveCurrentTask({ admin_in_progress: false });
});

previewFitBtn.addEventListener("click", () => {
  state.previewMode = "fit";
  state.previewScale = 1;
  syncPreviewMode();
});

previewScrollBtn.addEventListener("click", () => {
  state.previewMode = "original";
  state.previewScale = 1;
  syncPreviewMode();
});

previewZoomInBtn.addEventListener("click", () => {
  state.previewMode = "original";
  state.previewScale = Math.min(state.previewScale + 0.15, 3);
  syncPreviewMode();
});

previewZoomOutBtn.addEventListener("click", () => {
  state.previewMode = "original";
  state.previewScale = Math.max(state.previewScale - 0.15, 0.35);
  syncPreviewMode();
});

previewRotateBtn.addEventListener("click", () => {
  state.previewRotation = (state.previewRotation + 90) % 360;
  syncPreviewMode();
});

mobileListBtn.addEventListener("click", () => {
  state.mobilePane = "list";
  syncMobilePane();
});

mobileEditorBtn.addEventListener("click", () => {
  state.mobilePane = "editor";
  syncMobilePane();
});

adminLogoutForm.addEventListener("submit", (event) => {
  if (!state.answerDirty) return;
  event.preventDefault();
  guardUnsaved(() => adminLogoutForm.submit());
});

unsavedSaveBtn.addEventListener("click", saveAndContinuePendingAction);
unsavedDiscardBtn.addEventListener("click", discardAndContinuePendingAction);
unsavedCancelBtn.addEventListener("click", closeUnsavedDialog);

window.addEventListener("beforeunload", (event) => {
  if (!state.answerDirty) return;
  event.preventDefault();
  event.returnValue = "У вас есть несохранённый ответ.";
});

window.addEventListener("resize", syncMobilePane);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshTasks({ silent: true, preserveDraft: true });
  }
});

state.selectedTaskKey = state.tasks[0] ? state.tasks[0].task_key : null;
state.snapshot = buildTasksSnapshot(state.tasks);
renderStats();
renderUserFilter();
renderTaskList();
syncMobilePane();
setInterval(() => {
  if (document.visibilityState !== "visible") return;
  refreshTasks({ silent: true, preserveDraft: true });
}, AUTO_REFRESH_MS);
