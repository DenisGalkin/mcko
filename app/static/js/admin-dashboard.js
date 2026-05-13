const initialTasks = window.adminInitialTasks || [];
const initialAiAllowed = window.adminInitialAiAllowed || [];

const adminTaskList = document.getElementById("adminTaskList");
const adminListMeta = document.getElementById("adminListMeta");
const adminSearch = document.getElementById("adminSearch");
const adminUserFilter = document.getElementById("adminUserFilter");
const adminEditor = document.getElementById("adminEditor");
const adminEmpty = document.getElementById("adminEmpty");
const adminTaskTitle = document.getElementById("adminTaskTitle");
const adminHeadingTags = document.getElementById("adminHeadingTags");
const adminTaskCreated = document.getElementById("adminTaskCreated");
const adminTaskStatus = document.getElementById("adminTaskStatus");
const adminFilename = document.getElementById("adminFilename");
const adminDownloadLink = document.getElementById("adminDownloadLink");
const adminPreviewWrap = document.getElementById("adminPreviewWrap");
const adminFileMeta = document.getElementById("adminFileMeta");
const adminTaskTextBlock = document.getElementById("adminTaskTextBlock");
const adminAnswerText = document.getElementById("adminAnswerText");
const adminInProgressToggle = document.getElementById("adminInProgressToggle");
const adminFlash = document.getElementById("adminFlash");
const prevTaskBtn = document.getElementById("prevTaskBtn");
const nextTaskBtn = document.getElementById("nextTaskBtn");
const refreshTasksBtn = document.getElementById("refreshTasksBtn");
const clearFiltersBtn = document.getElementById("clearFiltersBtn");
const saveAnswerBtnAdmin = document.getElementById("saveAnswerBtnAdmin");
const clearAnswerBtn = document.getElementById("clearAnswerBtn");
const statTotal = document.getElementById("statTotal");
const statSolved = document.getElementById("statSolved");
const statOpen = document.getElementById("statOpen");
const filterButtons = [...document.querySelectorAll(".admin_filter_btn")];
const mobileListBtn = document.getElementById("mobileListBtn");
const mobileEditorBtn = document.getElementById("mobileEditorBtn");
const mobileRefreshBtn = document.getElementById("mobileRefreshBtn");
const AUTO_REFRESH_MS = 8000;

const state = {
  tasks: normalizeTasks(initialTasks),
  selectedTaskKey: null,
  filter: "all",
  query: "",
  userFilter: "",
  mobilePane: "list",
  refreshInFlight: false,
  snapshot: "",
  aiAllowed: normalizeAiAllowed(initialAiAllowed),
};

function normalizeAiAllowed(nicknames) {
  return [...new Set((nicknames || []).map((item) => String(item || "").trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

function normalizeTasks(tasks) {
  return [...tasks]
    .map((task) => ({
      ...task,
      task_number: String(task.task_number || ""),
      user_id: Number(task.user_id || 0),
      user_uid: String(task.user_uid || ""),
      user_nickname: task.user_nickname || "",
      user_current_task: String(task.user_current_task || ""),
      task_key: task.task_key || `submission:${task.id}`,
      answer_text: task.answer_text || "",
      task_text: task.task_text || "",
      filename: task.filename || "",
      file_url: task.file_url || "",
      created: task.created || task.created_at || "",
      answer_source: task.answer_source || "",
      task_priority: Number(task.task_priority || 0),
      visible_status: task.visible_status || getVisibleStatus(task),
      tags: Array.isArray(task.tags) ? task.tags : [],
      ai_processing: Boolean(task.ai_processing),
      admin_processing: Boolean(task.admin_processing),
      admin_processing_by: String(task.admin_processing_by || ""),
    }))
    .sort(compareAdminTasks);
}

function compareAdminTasks(a, b) {
  const priorityDiff = Number(b.task_priority || 0) - Number(a.task_priority || 0);
  if (priorityDiff !== 0) return priorityDiff;
  return String(a.task_number || "").localeCompare(String(b.task_number || ""), undefined, {
    numeric: true,
  });
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
      String(task.answer_text || ""),
      String(task.answer_source || ""),
      Number(task.task_priority || 0),
      String(task.visible_status || ""),
      (task.tags || []).join("|"),
      Boolean(task.admin_processing),
      Boolean(task.ai_processing),
      String(task.admin_processing_by || ""),
    ]),
  );
}

function getUserLabel(task) {
  const nickname = String(task.user_nickname || "").trim();
  return nickname ? `${nickname} (ID ${task.user_uid})` : `ID ${task.user_uid}`;
}

function getAnswerStatusLabel(task) {
  return getVisibleStatus(task);
}

function getVisibleStatus(task) {
  if (String(task.admin_answer || "").trim() || String(task.ai_answer || "").trim() || String(task.answer_text || "").trim()) {
    return "с ответом";
  }
  if (task.ai_processing || task.admin_processing) return "в обработке";
  return "без ответа";
}

function isTaskUserAiAllowed(task) {
  const nickname = String(task.user_nickname || "").trim().toLowerCase();
  return Boolean(nickname) && state.aiAllowed.some((item) => item.toLowerCase() === nickname);
}

function getFilteredTasks() {
  return state.tasks.filter((task) => {
    const answer = task.answer_text.trim();
    if (state.filter === "open" && getVisibleStatus(task) !== "без ответа") return false;
    if (state.filter === "processing" && getVisibleStatus(task) !== "в обработке") return false;
    if (state.filter === "solved" && getVisibleStatus(task) !== "с ответом") return false;
    if (state.userFilter && String(task.user_id) !== state.userFilter) return false;

    if (!state.query) return true;
    const haystack = [
      String(task.user_id),
      task.user_uid,
      task.user_nickname,
      task.task_number,
      task.filename,
      task.created,
      task.answer_text,
      task.task_text,
    ].join(" ").toLowerCase();
    return haystack.includes(state.query);
  });
}

function renderStats() {
  statTotal.textContent = state.tasks.length;
  statSolved.textContent = state.tasks.filter((task) => task.answer_text.trim()).length;
  statOpen.textContent = state.tasks.filter((task) => getVisibleStatus(task) === "без ответа").length;
}

function renderUserFilter() {
  const users = [...new Set(state.tasks.map((task) => String(task.user_id)))].sort((a, b) => Number(a) - Number(b));
  const currentValue = state.userFilter;
  adminUserFilter.innerHTML = '<option value="">Все пользователи</option>';
  users.forEach((userId) => {
    const option = document.createElement("option");
    option.value = userId;
    const userTask = state.tasks.find((task) => String(task.user_id) === userId);
    option.textContent = userTask && userTask.user_nickname
      ? `${userTask.user_nickname} (ID ${userTask.user_uid})`
      : `ID ${userTask ? userTask.user_uid : userId}`;
    if (userId === currentValue) option.selected = true;
    adminUserFilter.appendChild(option);
  });
}

function renderTaskList() {
  const filtered = getFilteredTasks();
  adminTaskList.innerHTML = "";
  adminListMeta.textContent = filtered.length ? `Найдено ${filtered.length} заданий` : "Ничего не найдено";

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
    item.type = "button";
    item.className = "admin_task_item";
    if (task.task_key === state.selectedTaskKey) item.classList.add("active");
    if (task.answer_text.trim()) item.classList.add("is-solved");
    if (getVisibleStatus(task) === "в обработке") item.classList.add("is-processing");
    const preview = String(task.task_text || "").trim();
    const shortPreview = preview.length > 96 ? `${preview.slice(0, 96)}...` : preview;
    item.innerHTML = `
      <span class="admin_task_top">
        <span class="admin_task_num">№${escapeHtml(task.task_number)} · ${escapeHtml(getUserLabel(task))}</span>
        <span class="admin_task_badge">${escapeHtml(getVisibleStatus(task))}</span>
      </span>
      <span class="admin_task_name">${escapeHtml(shortPreview || (task.filename ? task.filename : "Без текста и файла"))}</span>
      <span class="admin_task_state">
        <span>${escapeHtml(task.user_current_task ? `Сейчас: №${task.user_current_task}` : getVisibleStatus(task))}</span>
        <span>Приоритет: ${escapeHtml(task.task_priority)}</span>
        <span>${task.filename ? "Файл приложен" : "Файл не приложен"}</span>
      </span>
    `;
    item.addEventListener("click", () => {
      state.selectedTaskKey = task.task_key;
      state.mobilePane = "editor";
      renderTaskList();
      renderEditor(task);
    });
    adminTaskList.appendChild(item);
  });

  renderEditor(filtered.find((task) => task.task_key === state.selectedTaskKey) || null);
}

function renderHeadingTags(task) {
  const tags = [];
  tags.push(`<span class="admin_tag">${escapeHtml(getUserLabel(task))}</span>`);
  tags.push(`<span class="admin_tag">№${task.task_number}</span>`);
  if (task.user_current_task) {
    tags.push(`<span class="admin_tag is-active">Сейчас: №${escapeHtml(task.user_current_task)}</span>`);
  }
  if (task.filename) {
    tags.push('<span class="admin_tag is-active">Есть файл</span>');
  }
  if ((task.task_text || "").trim()) {
    tags.push('<span class="admin_tag is-active">Есть текст</span>');
  }
  if ((task.answer_text || "").trim()) {
    tags.push(`<span class="admin_tag is-active">${escapeHtml(getVisibleStatus(task))}</span>`);
  }
  (task.tags || []).forEach((tag) => {
    tags.push(`<span class="admin_tag is-active">${escapeHtml(tag)}</span>`);
  });
  tags.push(`<span class="admin_tag">Приоритет: ${escapeHtml(task.task_priority)}</span>`);
  tags.push(`<span class="admin_tag ${isTaskUserAiAllowed(task) ? "is-active" : ""}">${isTaskUserAiAllowed(task) ? "AI разрешен" : "AI запрещен"}</span>`);
  adminHeadingTags.innerHTML = tags.join("");
}

function renderPreview(task) {
  const hasFile = Boolean(task.filename && task.file_url);
  adminFileMeta.hidden = !hasFile;
  adminDownloadLink.hidden = !hasFile;
  adminPreviewWrap.hidden = true;
  adminPreviewWrap.innerHTML = "";
  if (!hasFile) {
    return;
  }

  adminFilename.textContent = task.filename || "Без файла";
  adminDownloadLink.href = task.file_url;
  const lowerName = task.filename.toLowerCase();
  const isImage = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"].some((ext) => lowerName.endsWith(ext));

  if (isImage) {
    adminPreviewWrap.hidden = false;
    const img = document.createElement("img");
    img.src = task.file_url;
    img.alt = `Задание ${task.task_number}`;
    img.className = "admin_preview_image";
    adminPreviewWrap.appendChild(img);
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
  adminTaskTitle.textContent = `№${task.task_number}`;
  adminTaskCreated.textContent = task.created ? `Создано: ${task.created}` : "";
  adminTaskStatus.textContent = getAnswerStatusLabel(task);
  adminTaskStatus.classList.toggle("is-solved", Boolean(task.answer_text.trim()));
  adminTaskStatus.classList.toggle("is-processing", getVisibleStatus(task) === "в обработке");
  adminAnswerText.value = task.answer_text || "";
  adminInProgressToggle.checked = Boolean(task.admin_processing);
  adminInProgressToggle.disabled = Boolean(String(task.admin_answer || "").trim());
  if (adminTaskTextBlock) {
    const taskText = String(task.task_text || "").trim();
    adminTaskTextBlock.hidden = !taskText;
    adminTaskTextBlock.textContent = taskText;
  }
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
}

function updateTaskInState(updatedTask) {
  const normalized = normalizeTasks([updatedTask])[0];
  const index = state.tasks.findIndex((task) => task.task_key === normalized.task_key);
  if (index === -1) state.tasks.push(normalized);
  else state.tasks[index] = normalized;
  state.tasks.sort(compareAdminTasks);
  state.snapshot = buildTasksSnapshot(state.tasks);
}

async function saveCurrentTask(fields) {
  const task = state.tasks.find((item) => item.task_key === state.selectedTaskKey);
  if (!task) return;

  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(task.task_key)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showFlash(data.error || "Не удалось сохранить", true);
      return;
    }
    updateTaskInState(data.task);
    renderStats();
    renderUserFilter();
    renderTaskList();
    state.mobilePane = "editor";
    syncMobilePane();
    showFlash("Сохранено");
  } catch (error) {
    showFlash("Не удалось сохранить", true);
  }
}

async function refreshTasks(options = {}) {
  const { silent = false, preserveDraft = false } = options;
  if (state.refreshInFlight) return;

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
    }
    if (!silent) showFlash("Список обновлен");
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
  setActiveFilter("all");
  adminSearch.value = "";
  adminUserFilter.value = "";
  renderTaskList();
}

function syncMobilePane() {
  const isMobile = window.matchMedia("(max-width: 860px)").matches;
  document.body.classList.toggle("admin_mobile_list", isMobile && state.mobilePane === "list");
  document.body.classList.toggle("admin_mobile_editor", isMobile && state.mobilePane === "editor");
  mobileListBtn.classList.toggle("active", !isMobile || state.mobilePane === "list");
  mobileEditorBtn.classList.toggle("active", isMobile && state.mobilePane === "editor");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

adminSearch.addEventListener("input", () => {
  state.query = adminSearch.value.trim().toLowerCase();
  renderTaskList();
});

adminUserFilter.addEventListener("change", () => {
  state.userFilter = adminUserFilter.value;
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
  if (index > 0) {
    state.selectedTaskKey = filtered[index - 1].task_key;
    state.mobilePane = "editor";
    renderTaskList();
  }
});

nextTaskBtn.addEventListener("click", () => {
  const filtered = getFilteredTasks();
  const index = filtered.findIndex((task) => task.task_key === state.selectedTaskKey);
  if (index !== -1 && index < filtered.length - 1) {
    state.selectedTaskKey = filtered[index + 1].task_key;
    state.mobilePane = "editor";
    renderTaskList();
  }
});

clearFiltersBtn.addEventListener("click", clearFilters);
refreshTasksBtn.addEventListener("click", () => refreshTasks());
mobileRefreshBtn.addEventListener("click", () => refreshTasks());
saveAnswerBtnAdmin.addEventListener("click", () =>
  saveCurrentTask({
    answer_text: adminAnswerText.value,
  }),
);
clearAnswerBtn.addEventListener("click", () => {
  adminAnswerText.value = "";
  saveCurrentTask({ answer_text: "" });
});
adminInProgressToggle.addEventListener("change", () => {
  saveCurrentTask({ admin_in_progress: adminInProgressToggle.checked });
});
mobileListBtn.addEventListener("click", () => {
  state.mobilePane = "list";
  syncMobilePane();
});
mobileEditorBtn.addEventListener("click", () => {
  state.mobilePane = "editor";
  syncMobilePane();
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
