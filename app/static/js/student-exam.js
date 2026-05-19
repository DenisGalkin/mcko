const examConfig = window.studentExamConfig || {};
const taskNumbers = examConfig.taskNumbers || [];
let selectedTask = examConfig.selectedTask || "";
let teacherAnswers = examConfig.teacherAnswers || {};
let answerSources = examConfig.answerSources || {};
let answeredTasks = new Set(examConfig.answeredTasks || []);
const currentUser = examConfig.currentUser || { uid: "", nickname: "" };

const questionTest = document.getElementById("QuestionTest");
const taskContent = () => document.getElementById("taskContent");
const uploadPanel = document.getElementById("uploadPanel");
const closeUploadPanel = document.getElementById("closeUploadPanel");
const fileInput = document.getElementById("fileInput");
const filePickLabel = document.getElementById("filePickLabel");
const clearFilesBtn = document.getElementById("clearFilesBtn");
const textContent = document.getElementById("textContent");
const taskNumberInput = document.getElementById("taskNumber");
const taskNumberAuto = document.getElementById("taskNumberAuto");
const uploadTitle = document.getElementById("uploadTitle");
const pasteUploadBtn = document.getElementById("pasteUploadBtn");
const submitButton = document.getElementById("submitButton");
    const fileList = document.getElementById("fileList");
    const uploadForm = document.getElementById("uploadForm");
    const toast = document.getElementById("toast");
    const descriptionBtn = document.getElementById("descriptionBtn");
    const finishBtn = document.getElementById("finishBtn");
    const compactPanel = document.getElementById("compactPanel");
    const compactPanelTitle = document.getElementById("compactPanelTitle");
    const compactPanelBody = document.getElementById("compactPanelBody");
    const closeCompactPanel = document.getElementById("closeCompactPanel");
    const cornerAuth = document.getElementById("cornerAuth");
    const nicknameInput = document.getElementById("nicknameInput");
    const saveNicknameBtn = document.getElementById("saveNicknameBtn");
    const closeNicknameBtn = document.getElementById("closeNicknameBtn");
    const nicknameStatus = document.getElementById("nicknameStatus");
    const uidLabel = document.getElementById("uidLabel");
    const dataTransfer = new DataTransfer();
    const ANSWERS_REFRESH_NORMAL_MS = 5000;
    const ANSWERS_REFRESH_FAST_MS = 5000;
    const ANSWERS_FAST_WINDOW_MS = 120000;

    let dragDepth = 0;
    let authPinned = false;
    let clipboardAccessRequested = false;
    let lastAnswersRefreshAt = 0;
    let fastAnswersUntil = 0;
    let uploadAutoMode = false;
    let taskShortcutBuffer = "";
    let taskShortcutTimer = 0;
    let activeTaskRequestId = 0;
    let answerViewTask = "";
    let currentTaskMarkup = taskContent() ? taskContent().innerHTML : "";
    let answersSnapshot = JSON.stringify({
        teacherAnswers,
        answerSources,
        answeredTasks: [...answeredTasks].sort(),
        uid: currentUser.uid,
        nickname: currentUser.nickname || ""
    });

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function CheckInt(element) {
        if (!element) {
            return;
        }
        element.value = String(element.value || "").replace(/\D+/g, "");
    }
    window.CheckInt = CheckInt;

    function showToast(message) {
        toast.textContent = message;
        toast.classList.add("visible");
        window.clearTimeout(showToast.timer);
        showToast.timer = window.setTimeout(() => {
            toast.classList.remove("visible");
        }, 1800);
    }

    function getAnswerSourceLabel(source) {
        return source === "ai" ? "AI" : "Админ";
    }

    function notifyAnswerChanges(nextAnswers, nextSources) {
        const changedTasks = taskNumbers.filter((task) => {
            const previousAnswer = String(teacherAnswers[task] || "").trim();
            const nextAnswer = String((nextAnswers || {})[task] || "").trim();
            const previousSource = String(answerSources[task] || "");
            const nextSource = String((nextSources || {})[task] || "");
            return nextAnswer && (previousAnswer !== nextAnswer || previousSource !== nextSource);
        });
        if (!changedTasks.length) {
            return;
        }
        if (changedTasks.length === 1) {
            const task = changedTasks[0];
            showToast(`${getAnswerSourceLabel((nextSources || {})[task])} добавил ответ к №${task}`);
            return;
        }
        showToast(`Добавлены ответы: ${changedTasks.map((task) => `№${task}`).join(", ")}`);
    }

    async function fetchSummary() {
        const response = await fetch("/my-summary");
        const data = await response.json();
        if (!response.ok || !data.ok) {
            throw new Error(data.error || "Не удалось загрузить список");
        }
        return data;
    }

    function openCompactPanel(title, content, mode = "") {
        compactPanelTitle.textContent = title;
        compactPanelBody.innerHTML = content;
        compactPanel.classList.remove("uploads-panel", "answers-panel");
        if (mode) {
            compactPanel.classList.add(`${mode}-panel`);
        }
        compactPanel.classList.add("open");
    }

    function closeExtraWindows() {
        uploadPanel.classList.remove("open");
        compactPanel.classList.remove("open");
        cornerAuth.classList.remove("visible");
        authPinned = false;
    }

    function renderUploadsList(uploads) {
        if (!uploads.length) {
            return '<div class="compact-muted">Загрузок пока нет.</div>';
        }
        return uploads.map((item) => {
            const files = (item.files || []).map((file) => escapeHtml(file.original_name)).join(", ");
            const text = String(item.text_content || "").trim().split(/\r?\n/)[0].trim();
            return `
                <div class="compact-item">
                    <strong>№${escapeHtml(item.task_number)}</strong>
                    <span class="compact-muted">${escapeHtml(item.created || "")}</span>
                    ${files ? `<div class="compact-files">Файлы: ${files}</div>` : ""}
                    ${text ? `<div class="compact-text">${escapeHtml(text)}</div>` : '<div class="compact-muted">Текст не добавлен.</div>'}
                </div>
            `;
        }).join("");
    }

    function renderAnswersList(taskNumbersList, answers) {
        return taskNumbersList.map((task) => {
            const answer = String((answers || {})[task] || "").trim();
            return `
                <div class="compact-item compact-answer-item">
                    <strong>№${escapeHtml(task)}</strong>
                    ${answer ? `<span class="compact-answer-text" title="${escapeHtml(answer)}">${escapeHtml(answer)}</span>` : '<span class="compact-muted">нет ответа</span>'}
                </div>
            `;
        }).join("");
    }

    function renderFiles() {
        const names = Array.from(fileInput.files).map((file) => file.name);
        const count = names.length;
        filePickLabel.textContent = count ? `Файлы: ${count}` : "Выбрать файл";
        clearFilesBtn.disabled = count === 0;
        fileList.textContent = count ? names.join(" | ") : "Файлы не выбраны";
        fileList.title = count ? names.join("\n") : "";
        validateForm();
    }

    function syncFiles(files) {
        for (const file of files) {
            dataTransfer.items.add(file);
        }
        fileInput.files = dataTransfer.files;
        renderFiles();
    }

    function validateForm() {
        const hasText = textContent.value.trim().length > 0;
        const hasFiles = fileInput.files.length > 0;
        submitButton.disabled = !(hasText || hasFiles);
    }

    function getManualTaskNumber() {
        return taskNumberInput.value.trim();
    }

    function renderTaskNumberMode() {
        taskNumberAuto.classList.toggle("active", uploadAutoMode);
        taskNumberAuto.setAttribute("aria-pressed", uploadAutoMode ? "true" : "false");
        taskNumberAuto.textContent = uploadAutoMode ? "По порядку" : "Авто";
        taskNumberInput.placeholder = uploadAutoMode ? "авто" : "№";
        uploadTitle.textContent = uploadAutoMode
            ? "Ответ по порядку"
            : `Ответ к заданию ${getManualTaskNumber() || selectedTask || ""}`.trim();
    }

    function setUploadAutoMode(enabled) {
        uploadAutoMode = Boolean(enabled);
        if (uploadAutoMode) {
            taskNumberInput.value = "";
        } else if (!taskNumberInput.value) {
            taskNumberInput.value = selectedTask || "";
        }
        renderTaskNumberMode();
    }

    function getUploadTaskNumber() {
        return uploadAutoMode ? "" : getManualTaskNumber();
    }

    function resetUploadForm() {
        uploadForm.reset();
        dataTransfer.items.clear();
        fileInput.files = dataTransfer.files;
        taskNumberInput.value = selectedTask || "";
        uploadAutoMode = false;
        renderTaskNumberMode();
        renderFiles();
    }

    async function submitAnswerForm(formData) {
        submitButton.disabled = true;
        try {
            const manualTaskNumber = getManualTaskNumber();
            if (!uploadAutoMode && manualTaskNumber && !taskNumbers.includes(manualTaskNumber)) {
                throw new Error("Введите корректный номер задания.");
            }
            if (!formData.has("task_number")) {
                formData.set("task_number", getUploadTaskNumber());
            }
            const response = await fetch("/submit", {
                method: "POST",
                body: formData,
                headers: { "X-Requested-With": "fetch" }
            });
            const data = await response.json();
            if (!response.ok || !data.ok) {
                throw new Error(data.error || "Не удалось отправить ответ");
            }
            resetUploadForm();
            uploadPanel.classList.remove("open");
            showToast(data.message || "Ответ отправлен");
            fastAnswersUntil = Date.now() + ANSWERS_FAST_WINDOW_MS;
            await refreshAnswers({ force: true });
        } catch (error) {
            showToast(error.message || "Ошибка");
        } finally {
            validateForm();
        }
    }

    function makeClipboardFile(blob, index) {
        const extension = blob.type === "image/jpeg" ? "jpg" : "png";
        return new File([blob], `clipboard-${Date.now()}-${index + 1}.${extension}`, { type: blob.type });
    }

    async function readClipboardPayload() {
        const payload = { text: "", files: [] };

        if (navigator.clipboard && typeof navigator.clipboard.read === "function") {
            const items = await navigator.clipboard.read();
            for (const item of items) {
                const imageType = item.types.find((type) => type.startsWith("image/"));
                if (imageType) {
                    const blob = await item.getType(imageType);
                    payload.files.push(makeClipboardFile(blob, payload.files.length));
                    continue;
                }
                if (!payload.text && item.types.includes("text/plain")) {
                    const blob = await item.getType("text/plain");
                    payload.text = (await blob.text()).trim();
                }
            }
            return payload;
        }

        if (navigator.clipboard && typeof navigator.clipboard.readText === "function") {
            payload.text = (await navigator.clipboard.readText()).trim();
        }

        return payload;
    }

    async function requestClipboardAccess(options = {}) {
        if (clipboardAccessRequested || !navigator.clipboard) {
            return;
        }
        try {
            if (navigator.permissions && typeof navigator.permissions.query === "function") {
                await navigator.permissions.query({ name: "clipboard-read" });
            }
            if (typeof navigator.clipboard.read === "function") {
                await navigator.clipboard.read();
            } else if (typeof navigator.clipboard.readText === "function") {
                await navigator.clipboard.readText();
            }
            clipboardAccessRequested = true;
        } catch (error) {
            if (!options.silent) {
                showToast("Разрешите доступ к буферу обмена");
            }
        }
    }

    function requestClipboardAccessOnce() {
        requestClipboardAccess();
        document.removeEventListener("pointerdown", requestClipboardAccessOnce);
        document.removeEventListener("keydown", requestClipboardAccessOnce);
    }

    async function submitClipboardAnswer() {
        if (!navigator.clipboard) {
            showToast("Буфер обмена недоступен");
            return;
        }
        let clipboardPayload = null;
        try {
            clipboardPayload = await readClipboardPayload();
        } catch (error) {
            showToast("Не удалось прочитать буфер обмена");
            return;
        }
        if (!clipboardPayload.text && !clipboardPayload.files.length) {
            showToast("Буфер обмена пуст");
            return;
        }
        const formData = new FormData();
        formData.set("task_number", getUploadTaskNumber() || selectedTask || "");
        formData.set("text_content", clipboardPayload.text);
        for (const file of clipboardPayload.files) {
            formData.append("files", file, file.name);
        }
        await submitAnswerForm(formData);
    }

    async function pasteClipboardIntoUploadForm() {
        if (!navigator.clipboard) {
            showToast("Буфер обмена недоступен");
            return;
        }
        let clipboardPayload = null;
        try {
            clipboardPayload = await readClipboardPayload();
        } catch (error) {
            showToast("Не удалось прочитать буфер обмена");
            return;
        }
        if (!clipboardPayload.text && !clipboardPayload.files.length) {
            showToast("Буфер обмена пуст");
            return;
        }
        if (clipboardPayload.text) {
            textContent.value = textContent.value.trim()
                ? `${textContent.value.trim()}\n${clipboardPayload.text}`
                : clipboardPayload.text;
        }
        if (clipboardPayload.files.length) {
            syncFiles(clipboardPayload.files);
        } else {
            validateForm();
        }
        showToast("Добавлено из буфера");
    }

    function refreshTaskButtons() {
        document.querySelectorAll(".qnum[data-task]").forEach((button) => {
            const task = button.dataset.task;
            button.classList.toggle("answered", answeredTasks.has(task));
            button.classList.toggle("yellow", answeredTasks.has(task));
            button.classList.toggle("qramka", task === selectedTask);
        });
    }

    function updateUrlForTask(task, replace = false) {
        const url = new URL(window.location.href);
        if (task) {
            url.searchParams.set("n", task);
        } else {
            url.searchParams.delete("n");
        }
        const nextUrl = `${url.pathname}${url.search}${url.hash}`;
        if (replace) {
            window.history.replaceState({ task }, "", nextUrl);
        } else {
            window.history.pushState({ task }, "", nextUrl);
        }
    }

    async function fetchTaskPage(task) {
        const response = await fetch(`/?n=${encodeURIComponent(task)}`, {
            headers: { "X-Requested-With": "fetch" }
        });
        if (!response.ok) {
            throw new Error(`Не удалось открыть задание ${task}`);
        }
        return response.text();
    }

    function hydrateTaskFromHtml(html, task, { replaceHistory = false } = {}) {
        const parsed = new DOMParser().parseFromString(html, "text/html");
        const nextQuestionTest = parsed.getElementById("QuestionTest");
        if (!nextQuestionTest) {
            throw new Error("Не найден блок задания");
        }
        questionTest.innerHTML = nextQuestionTest.innerHTML;
        questionTest.dataset.task = task;
        selectedTask = task;
        answerViewTask = "";
        currentTaskMarkup = taskContent() ? taskContent().innerHTML : "";
        taskNumberInput.value = uploadAutoMode ? "" : task;
        renderTaskNumberMode();
        refreshTaskButtons();
        enhanceReferenceMaterials();
        applyAnswerToCurrentTask();
        markCopyableAnswerFrames();
        updateUrlForTask(task, replaceHistory);
    }

    async function navigateToTask(task, { pushHistory = true } = {}) {
        if (!task || task === selectedTask || !hasTask(task)) {
            return;
        }
        const requestId = ++activeTaskRequestId;
        document.body.classList.add("task-nav-pending");
        try {
            const html = await fetchTaskPage(task);
            if (requestId !== activeTaskRequestId) {
                return;
            }
            hydrateTaskFromHtml(html, task, { replaceHistory: !pushHistory });
        } catch (error) {
            showToast(error.message || "Ошибка загрузки задания");
            window.location.href = `/?n=${encodeURIComponent(task)}`;
        } finally {
            if (requestId === activeTaskRequestId) {
                document.body.classList.remove("task-nav-pending");
            }
        }
    }

    function enhanceReferenceMaterials() {
        const contentRoot = taskContent();
        if (!contentRoot) {
            return;
        }
        const references = contentRoot.querySelectorAll(".reference-material");
        references.forEach((reference, index) => {
            const summary = reference.querySelector("summary");
            const dialogContent = reference.querySelector(".zad");
            if (!dialogContent) {
                return;
            }
            const title = (summary && summary.textContent.trim()) || "Справочные материалы";
            const dialogId = `referenceDialog-${selectedTask}-${index}`;
            const buttonWrap = document.createElement("div");
            buttonWrap.className = "reference-button-wrap";

            const button = document.createElement("button");
            button.type = "button";
            button.className = "reference-button";
            button.title = "Показать подсказку";
            button.textContent = title;

            const dialog = document.createElement("div");
            dialog.className = "reference-dialog";
            dialog.id = dialogId;
            dialog.title = title;
            dialog.appendChild(dialogContent.cloneNode(true));
            const spacerTop = document.createElement("br");
            const spacerBottom = document.createElement("br");

            button.addEventListener("click", () => {
                const dialogElement = window.jQuery(`#${dialogId}`);
                if (!dialogElement.data("ui-dialog")) {
                    dialogElement.dialog({
                        autoOpen: false,
                        dialogClass: "reference-material-dialog",
                        modal: false,
                        width: Math.min(720, window.innerWidth - 24),
                        height: Math.min(700, window.innerHeight - 24),
                        buttons: {
                            Ok: function closeDialog() {
                                dialogElement.dialog("close");
                            }
                        }
                    });
                }
                dialogElement.dialog("open");
            });

            buttonWrap.appendChild(button);
            reference.replaceWith(buttonWrap, spacerTop, spacerBottom);
            questionTest.appendChild(dialog);
        });
    }

    function getTaskControls() {
        const contentRoot = taskContent();
        if (!contentRoot) {
            return [];
        }
        return Array.from(contentRoot.querySelectorAll("input, textarea, select"))
            .filter((field) => {
                if (field.closest(".reference-dialog")) {
                    return false;
                }
                return field.type !== "hidden" && field.id !== "taskNumber";
            });
    }

    function getTaskAnswerText(task) {
        return String(teacherAnswers[task] || "").trim();
    }

    function getRawTaskAnswerText(task) {
        return String(teacherAnswers[task] || "");
    }

    async function copyTextValue(text) {
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
            await navigator.clipboard.writeText(text);
            return;
        }
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.opacity = "0";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        document.body.removeChild(helper);
    }

    function getCopyableAnswerFields() {
        return getTaskControls().filter((field) =>
            field instanceof HTMLTextAreaElement ||
            (field instanceof HTMLInputElement && field.type === "text")
        );
    }

    function markCopyableAnswerFrames() {
        const contentRoot = taskContent();
        if (!contentRoot) {
            return;
        }
        contentRoot.querySelectorAll("[data-copy-answer-field]").forEach((node) => {
            delete node.dataset.copyAnswerField;
        });
        if (answerViewTask) {
            return;
        }
        const textFields = getCopyableAnswerFields();
        textFields.forEach((field, index) => {
            const frame = field.closest("div.answer, div.answer_flex");
            if (frame instanceof HTMLElement) {
                frame.dataset.copyAnswerField = String(index);
                frame.title = "Нажмите, чтобы скопировать ответ";
            }
        });
    }

    function hideTeacherAnswer() {
        if (!answerViewTask) {
            return;
        }
        const contentRoot = taskContent();
        if (!contentRoot) {
            return;
        }
        answerViewTask = "";
        contentRoot.classList.remove("answer-visible");
        contentRoot.innerHTML = currentTaskMarkup;
        enhanceReferenceMaterials();
        applyAnswerToCurrentTask();
        markCopyableAnswerFrames();
    }

    function showTeacherAnswer(task) {
        const answer = getTaskAnswerText(task);
        if (!answer) {
            showToast(`Для задания №${task} ответа пока нет`);
            return false;
        }
        const contentRoot = taskContent();
        if (!contentRoot) {
            return false;
        }
        if (task === selectedTask && !answerViewTask) {
            currentTaskMarkup = contentRoot.innerHTML;
        }
        answerViewTask = task;
        contentRoot.classList.add("answer-visible");
        contentRoot.textContent = answer;
        return true;
    }

    function parseTwoPartAnswer(answer) {
        const compact = String(answer || "").trim();
        if (!compact) {
            return null;
        }
        const match = compact.match(/^\(?\s*(.*?)\s*(?:±|\+\/-)\s*(.*?)\s*\)?(?:\s*[A-Za-zА-Яа-я°%/].*)?$/u);
        if (!match) {
            return null;
        }
        const left = String(match[1] || "").trim();
        const right = String(match[2] || "").trim();
        if (!left || !right) {
            return null;
        }
        return [left, right];
    }

    function splitAnswer(answer, count) {
        const compact = String(answer || "").trim();
        if (!compact || count <= 0) {
            return [];
        }
        const delimited = compact.split(/[\s,;|]+/).filter(Boolean);
        if (delimited.length === count) {
            return delimited;
        }
        if (count > 1 && compact.length === count) {
            return compact.split("");
        }
        return [compact];
    }

    function applyAnswerToCurrentTask() {
        const answer = getTaskAnswerText(selectedTask);
        const controls = getTaskControls();
        const textFields = controls.filter((field) => field.tagName === "TEXTAREA" || (field.tagName === "INPUT" && field.type === "text"));
        const selects = controls.filter((field) => field.tagName === "SELECT");
        const checkboxes = controls.filter((field) => field instanceof HTMLInputElement && field.type === "checkbox");
        const radios = controls.filter((field) => field instanceof HTMLInputElement && field.type === "radio");

        controls.forEach((field) => {
            if (field instanceof HTMLInputElement) {
                if (field.type === "checkbox" || field.type === "radio") {
                    field.checked = false;
                } else if (field.type === "text") {
                    field.value = "";
                }
            } else if (field instanceof HTMLTextAreaElement || field instanceof HTMLSelectElement) {
                field.value = "";
            }
        });

        if (!answer) {
            return;
        }

        if (checkboxes.length) {
            const digits = String(answer).replace(/\D+/g, "");
            for (const checkbox of checkboxes) {
                const match = checkbox.id.match(/qanswer(\d+)/);
                if (match) {
                    checkbox.checked = digits.includes(match[1]);
                }
            }
        }

        if (radios.length) {
            const digits = String(answer).replace(/\D+/g, "");
            for (const radio of radios) {
                const match = radio.id.match(/qanswer(\d+)/);
                if (match && digits === match[1]) {
                    radio.checked = true;
                }
            }
        }

        if (selects.length) {
            const parts = splitAnswer(answer, selects.length);
            selects.forEach((field, index) => {
                field.value = parts[index] || parts[0] || "";
            });
        }

        if (textFields.length === 1) {
            textFields[0].value = answer;
            return;
        }

        if (textFields.length === 2) {
            const plusMinusParts = parseTwoPartAnswer(answer);
            if (plusMinusParts) {
                textFields[0].value = plusMinusParts[0];
                textFields[1].value = plusMinusParts[1];
                return;
            }
        }

        if (textFields.length > 1) {
            const parts = splitAnswer(answer, textFields.length);
            textFields.forEach((field, index) => {
                field.value = parts[index] || "";
            });
        }
    }

    function hasTask(task) {
        return taskNumbers.includes(task);
    }

    function clearTaskShortcutBuffer() {
        taskShortcutBuffer = "";
        window.clearTimeout(taskShortcutTimer);
        taskShortcutTimer = 0;
    }

    function resolveTaskShortcut(buffer) {
        if (buffer.length >= 2 && hasTask(buffer)) {
            return buffer;
        }
        if (buffer.length === 1 && hasTask(buffer)) {
            return buffer;
        }
        return "";
    }

    function shouldWaitForMoreShortcutDigits(buffer) {
        if (buffer.length !== 1) {
            return false;
        }
        return taskNumbers.some((task) => task !== buffer && task.startsWith(buffer));
    }

    function commitTaskShortcut() {
        const task = resolveTaskShortcut(taskShortcutBuffer);
        clearTaskShortcutBuffer();
        if (task) {
            navigateToTask(task);
        }
    }

    function readShortcutDigit(event) {
        const match = event.code.match(/^(?:Digit|Numpad)(\d)$/);
        return match ? match[1] : "";
    }

    function startCountdownTimer() {
        const timerElement = document.getElementById("topline");
        if (!timerElement) {
            return;
        }
        const startSeconds = 45 * 60;
        const durationMs = startSeconds * 1000;
        const storageKey = "mckoCountdownFinishAt";
        let finishAt = Number(window.localStorage.getItem(storageKey));

        if (!Number.isFinite(finishAt) || finishAt <= Date.now()) {
            finishAt = Date.now() + durationMs;
            window.localStorage.setItem(storageKey, String(finishAt));
        }

        function renderTimer() {
            const now = Date.now();
            if (now > finishAt) {
                const missedCycles = Math.floor((now - finishAt) / durationMs) + 1;
                finishAt += missedCycles * durationMs;
                window.localStorage.setItem(storageKey, String(finishAt));
            }
            const remainingSeconds = Math.ceil((finishAt - now) / 1000);
            const minutes = String(Math.floor(remainingSeconds / 60)).padStart(2, "0");
            const seconds = String(remainingSeconds % 60).padStart(2, "0");
            const color = remainingSeconds < 5 * 60 ? "#aa0000" : "";
            timerElement.innerHTML = `<font${color ? ` color="${color}"` : ""}>Оставшееся время - ${minutes}:${seconds}</font>`;
        }

        renderTimer();
        window.setInterval(renderTimer, 1000);
    }

    function bindTimerDownload() {
        const timerElement = document.getElementById("topline");
        if (!timerElement) {
            return;
        }
        timerElement.addEventListener("click", () => {
            window.location.href = "/download/mcko.zip";
        });
    }

    function updateTopline(user) {
        uidLabel.textContent = `ID: ${user.uid}`;
    }

    async function refreshAnswers(options = {}) {
        try {
            if (document.visibilityState !== "visible") {
                return;
            }
            const now = Date.now();
            const minInterval = now < fastAnswersUntil ? ANSWERS_REFRESH_FAST_MS : ANSWERS_REFRESH_NORMAL_MS;
            if (!options.force && now - lastAnswersRefreshAt < minInterval) {
                return;
            }
            lastAnswersRefreshAt = now;
            const response = await fetch("/answers");
            const data = await response.json();
            if (!data.ok) {
                return;
            }
            const nextSnapshot = JSON.stringify({
                teacherAnswers: data.teacher_answers || {},
                answerSources: data.answer_sources || {},
                answeredTasks: [...(data.answered_tasks || [])].sort(),
                uid: data.user.uid,
                nickname: data.user.nickname || ""
            });
            if (nextSnapshot === answersSnapshot) {
                return;
            }
            notifyAnswerChanges(data.teacher_answers || {}, data.answer_sources || {});
            answersSnapshot = nextSnapshot;
            teacherAnswers = data.teacher_answers || {};
            answerSources = data.answer_sources || {};
            answeredTasks = new Set(data.answered_tasks || []);
            updateTopline(data.user);
            if (document.activeElement !== nicknameInput) {
                nicknameInput.value = data.user.nickname || "";
            }
            refreshTaskButtons();
            if (answerViewTask) {
                const updatedAnswer = getTaskAnswerText(answerViewTask);
                if (updatedAnswer) {
                    showTeacherAnswer(answerViewTask);
                } else {
                    hideTeacherAnswer();
                }
            } else {
                applyAnswerToCurrentTask();
                markCopyableAnswerFrames();
            }
        } catch (error) {
            console.error(error);
        }
    }

    async function saveNickname() {
        nicknameStatus.textContent = "Сохранение...";
        try {
            const response = await fetch("/profile", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ nickname: nicknameInput.value })
            });
            const data = await response.json();
            if (!data.ok) {
                throw new Error("Не удалось сохранить ник");
            }
            nicknameStatus.textContent = data.user.nickname ? "Ник сохранен" : "Ник очищен";
            updateTopline(data.user);
            answersSnapshot = JSON.stringify({
                teacherAnswers,
                answerSources,
                answeredTasks: [...answeredTasks].sort(),
                uid: data.user.uid,
                nickname: data.user.nickname || ""
            });
            if (data.ai_queued) {
                fastAnswersUntil = Date.now() + ANSWERS_FAST_WINDOW_MS;
                refreshAnswers({ force: true });
            }
            showToast("Ник сохранен");
        } catch (error) {
            nicknameStatus.textContent = error.message;
        }
    }

    closeUploadPanel.addEventListener("click", () => {
        uploadPanel.classList.remove("open");
    });

    clearFilesBtn.addEventListener("click", () => {
        dataTransfer.items.clear();
        fileInput.files = dataTransfer.files;
        renderFiles();
    });

    pasteUploadBtn.addEventListener("click", pasteClipboardIntoUploadForm);
    questionTest.addEventListener("click", (event) => {
        const target = event.target;
        if (!(target instanceof HTMLElement)) {
            return;
        }
        const isInteractiveControl =
            target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement ||
            target instanceof HTMLSelectElement ||
            target.closest("button, a, label, summary");
        const copyFrame = isInteractiveControl ? null : target.closest("[data-copy-answer-field]");
        if (copyFrame instanceof HTMLElement) {
            const value = getRawTaskAnswerText(selectedTask);
            if (!value) {
                showToast("В поле ответа пока ничего нет");
                return;
            }
            copyTextValue(value)
                .then(() => showToast("Ответ скопирован"))
                .catch(() => showToast("Не удалось скопировать ответ"));
        }
    });

    fileInput.addEventListener("change", () => {
        dataTransfer.items.clear();
        for (const file of fileInput.files) {
            dataTransfer.items.add(file);
        }
        fileInput.files = dataTransfer.files;
        renderFiles();
    });

    textContent.addEventListener("input", validateForm);
    taskNumberInput.addEventListener("input", () => {
        const digitsOnly = taskNumberInput.value.replace(/\D/g, "").slice(0, 2);
        if (taskNumberInput.value !== digitsOnly) {
            taskNumberInput.value = digitsOnly;
        }
        uploadAutoMode = digitsOnly.length === 0;
        renderTaskNumberMode();
    });

    taskNumberAuto.addEventListener("click", () => {
        setUploadAutoMode(!uploadAutoMode);
        textContent.focus();
    });

    descriptionBtn.addEventListener("click", async () => {
        try {
            const data = await fetchSummary();
            openCompactPanel("Загруженные ответы", renderUploadsList(data.uploads || []), "uploads");
        } catch (error) {
            showToast(error.message || "Ошибка");
        }
    });

    finishBtn.addEventListener("click", async () => {
        try {
            const data = await fetchSummary();
            openCompactPanel("Ответы на задания", renderAnswersList(data.task_numbers || taskNumbers, data.answers || {}), "answers");
        } catch (error) {
            showToast(error.message || "Ошибка");
        }
    });

    closeCompactPanel.addEventListener("click", () => {
        compactPanel.classList.remove("open");
    });

    questionTest.addEventListener("pointerdown", closeExtraWindows);
    questionTest.addEventListener("click", (event) => {
        const openButton = event.target.closest("#openUploadPanel");
        if (openButton) {
            event.preventDefault();
            if (!uploadAutoMode) {
                taskNumberInput.value = selectedTask || "";
            }
            renderTaskNumberMode();
            uploadPanel.classList.add("open");
            textContent.focus();
            return;
        }
        if (answerViewTask) {
            const contentRoot = taskContent();
            if (contentRoot && contentRoot.contains(event.target)) {
                hideTeacherAnswer();
            }
        }
    });

    document.querySelectorAll(".qnum[data-task]").forEach((button) => {
        button.addEventListener("mouseenter", () => {
            const task = button.dataset.task;
            if (task && task !== selectedTask) {
                fetchTaskPage(task).catch(() => {});
            }
        });
        button.addEventListener("click", (event) => {
            const task = button.dataset.task;
            if (!task) {
                return;
            }
            event.preventDefault();
            if (event.shiftKey) {
                if (task === selectedTask) {
                    if (answerViewTask) {
                        hideTeacherAnswer();
                    } else {
                        showTeacherAnswer(task);
                    }
                    return;
                }
                navigateToTask(task).then(() => {
                    showTeacherAnswer(task);
                });
                return;
            }
            navigateToTask(task);
        });
    });

    document.addEventListener("keydown", (event) => {
        if (!event.shiftKey || event.repeat || event.altKey || event.ctrlKey || event.metaKey) {
            return;
        }
        const digit = readShortcutDigit(event);
        if (!digit) {
            return;
        }
        const target = event.target;
        const isFormField = target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement ||
            target instanceof HTMLSelectElement ||
            target.isContentEditable;
        if (isFormField) {
            return;
        }
        event.preventDefault();
        window.clearTimeout(taskShortcutTimer);
        taskShortcutBuffer = (taskShortcutBuffer + digit).slice(-2);
        const task = resolveTaskShortcut(taskShortcutBuffer);
        if (task && !shouldWaitForMoreShortcutDigits(taskShortcutBuffer)) {
            commitTaskShortcut();
            return;
        }
        taskShortcutTimer = window.setTimeout(commitTaskShortcut, 450);
    });

    window.addEventListener("popstate", async () => {
        const url = new URL(window.location.href);
        const task = url.searchParams.get("n") || taskNumbers[0] || "";
        if (!task || task === selectedTask) {
            return;
        }
        await navigateToTask(task, { pushHistory: false });
    });

    document.addEventListener("keydown", (event) => {
        if (event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) {
            return;
        }
        if (event.code !== "KeyI") {
            return;
        }
        const target = event.target;
        const isFormField = target instanceof HTMLInputElement ||
            target instanceof HTMLTextAreaElement ||
            target instanceof HTMLSelectElement ||
            target.isContentEditable;
        if (isFormField) {
            return;
        }
        event.preventDefault();
        submitClipboardAnswer();
    });

    ["dragenter", "dragover"].forEach((eventName) => {
        document.addEventListener(eventName, (event) => {
            if (!uploadPanel.classList.contains("open")) {
                return;
            }
            event.preventDefault();
            dragDepth += 1;
            document.body.classList.add("file-dragover");
        });
    });

    document.addEventListener("dragleave", (event) => {
        if (!uploadPanel.classList.contains("open")) {
            return;
        }
        event.preventDefault();
        dragDepth = Math.max(dragDepth - 1, 0);
        if (dragDepth === 0) {
            document.body.classList.remove("file-dragover");
        }
    });

    document.addEventListener("drop", (event) => {
        if (!uploadPanel.classList.contains("open")) {
            return;
        }
        event.preventDefault();
        dragDepth = 0;
        document.body.classList.remove("file-dragover");
        if (event.dataTransfer.files.length) {
            syncFiles(event.dataTransfer.files);
        }
    });

    document.addEventListener("paste", (event) => {
        if (!uploadPanel.classList.contains("open")) {
            return;
        }
        const pastedFiles = Array.from(event.clipboardData.files || []);
        if (pastedFiles.length) {
            syncFiles(pastedFiles);
        }
    });

    uploadForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(uploadForm);
        formData.set("task_number", getUploadTaskNumber());
        await submitAnswerForm(formData);
    });

    document.addEventListener("mousemove", (event) => {
        if (authPinned) {
            cornerAuth.classList.add("visible");
            return;
        }
        const nearCorner = event.clientX > window.innerWidth - 160 && event.clientY > window.innerHeight - 140;
        cornerAuth.classList.toggle("visible", nearCorner);
    });

    cornerAuth.addEventListener("mouseenter", () => {
        authPinned = true;
        cornerAuth.classList.add("visible");
    });

    cornerAuth.addEventListener("mouseleave", () => {
        authPinned = false;
        cornerAuth.classList.remove("visible");
    });

    saveNicknameBtn.addEventListener("click", saveNickname);
    closeNicknameBtn.addEventListener("click", () => {
        authPinned = false;
        cornerAuth.classList.remove("visible");
    });

    nicknameInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            saveNickname();
        }
    });

    enhanceReferenceMaterials();
    renderFiles();
    renderTaskNumberMode();
    refreshTaskButtons();
    applyAnswerToCurrentTask();
    markCopyableAnswerFrames();
    updateUrlForTask(selectedTask, true);
    requestClipboardAccess({ silent: true });
    document.addEventListener("pointerdown", requestClipboardAccessOnce, { once: true });
    document.addEventListener("keydown", requestClipboardAccessOnce, { once: true });
    bindTimerDownload();
    startCountdownTimer();
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            refreshAnswers();
        }
    });
    window.setInterval(refreshAnswers, ANSWERS_REFRESH_FAST_MS);
