// ==========================================
// 🚀 NexusAI Workspace — app.js
// Client-side routing + Chainlit Copilot sidebar integration
// ==========================================

// --- LOGIN REDIRECT INTERCEPTOR ---
// Intercepts Chainlit's React SPA navigation to /login
// and hard-redirects to our custom HTML page in /public/
// (which bypasses Chainlit's Auth Middleware)
if (window.location.pathname === '/login') {
    window.location.href = '/public/login/index.html';
}
const originalPushState = history.pushState;
history.pushState = function() {
    originalPushState.apply(this, arguments);
    if (window.location.pathname === '/login') {
        window.location.href = '/public/login/index.html';
    }
};
window.addEventListener('popstate', function() {
    if (window.location.pathname === '/login') {
        window.location.href = '/public/login/index.html';
    }
});

let stagedFiles = [];          // Array of File objects in staging tray
let previewObjectUrls = {};    // Maps filename → object URL for local previews
let selectedFilename = null;   // Single selected file name for analysis

document.addEventListener('DOMContentLoaded', () => {

    // --- THEME DETECTION ---
    // Reads from localStorage (Chainlit stores 'theme' there)
    const activeTheme = localStorage.getItem("theme") || "dark";
    if (activeTheme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
        document.documentElement.classList.add("light");
    } else {
        document.documentElement.setAttribute("data-theme", "dark");
        document.documentElement.classList.remove("light");
    }

    // Watch for Chainlit theme changes in real-time
    window.addEventListener("storage", (e) => {
        if (e.key === "theme") {
            const newTheme = e.newValue || "dark";
            if (newTheme === "light") {
                document.documentElement.setAttribute("data-theme", "light");
                document.documentElement.classList.add("light");
            } else {
                document.documentElement.setAttribute("data-theme", "dark");
                document.documentElement.classList.remove("light");
            }
        }
    });

    // --- CHAINLIT COPILOT WIDGET ---
    // Using displayMode: "sidebar" — the official Chainlit v2.11+ integration.
    // The sidebar pushes the workspace content from the right edge,
    // providing a clean split-panel experience without Shadow DOM hacks.
    window.mountChainlitWidget({
        chainlitServer: "http://localhost:8000",
        displayMode: "sidebar",
        theme: activeTheme,
        expanded: true,
        opened: true,
    });

    // --- CHAINLIT BACKEND FUNCTION LISTENER ---
    // Handles CopilotFunction calls from the Python backend
    window.addEventListener("chainlit-call-fn", (e) => {
        const { name, args, callback } = e.detail;

        if (name === "new_chat_session") {
            // Clear thread ID and reload workspace for a fresh session
            try {
                if (typeof window.clearChainlitCopilotThreadId === 'function') {
                    window.clearChainlitCopilotThreadId();
                } else {
                    localStorage.removeItem("chainlit-copilot-thread-id");
                }
            } catch (err) {
                console.error("Failed to clear thread ID:", err);
            }
            location.reload();
            if (callback) callback("Success");
        }

        else if (name === "clear_visual_chat") {
            // Visual clear is now handled via Chainlit's own new-chat flow.
            // This handler is kept as a graceful no-op for backward compat.
            showToast("✅ Chat cleared. Memory is intact.", "success");
            if (callback) callback("Success");
        }
    });

    // --- DRAG & DROP LISTENERS ---
    const dropZone = document.getElementById('drop-zone');
    if (dropZone) {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.add('highlight'), false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => dropZone.classList.remove('highlight'), false);
        });

        dropZone.addEventListener('drop', (e) => {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles(files);
        }, false);
    }
});

// ==========================================
// TOAST NOTIFICATIONS
// ==========================================
function showToast(message, type = 'warning') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);

    setTimeout(() => toast.classList.add('active'), 10);
    setTimeout(() => {
        toast.classList.remove('active');
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}

// ==========================================
// FILE HANDLING — STAGE & UPLOAD
// ==========================================
function handleFiles(files) {
    if (!files || files.length === 0) return;

    const allowedExtensions = [
        '.png', '.jpg', '.jpeg', '.webp',
        '.doc', '.docx', '.pdf', '.ppt', '.pptx',
        '.xls', '.xlsx', '.txt', '.csv',
        '.py', '.js', '.json', '.md'
    ];
    let addedCount = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const filename = file.name.toLowerCase();
        const matchesExtension = allowedExtensions.some(ext => filename.endsWith(ext));

        if (!matchesExtension) {
            showToast(`❌ File type not allowed: ${file.name}`, "error");
            continue;
        }

        const isAlreadyStaged = stagedFiles.some(f => f.name === file.name);
        if (!isAlreadyStaged) {
            stagedFiles.push(file);
            addedCount++;
        }
    }

    if (addedCount > 0) {
        renderStagingTray();
    }
}

function renderStagingTray() {
    const countEl = document.getElementById('staged-count');
    const trayEl = document.getElementById('staging-tray');
    const listEl = document.getElementById('staged-files-list');
    const analyzeBtn = document.getElementById('analyze-btn');

    if (!trayEl || !listEl || !analyzeBtn) return;

    if (countEl) countEl.innerText = `(${stagedFiles.length})`;

    if (stagedFiles.length === 0) {
        trayEl.style.display = 'none';
        analyzeBtn.disabled = true;
        listEl.innerHTML = '';
        closePreview();
        return;
    }

    trayEl.style.display = 'flex';
    analyzeBtn.disabled = !selectedFilename;
    listEl.innerHTML = '';

    stagedFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'staged-file-item' + (selectedFilename === file.name ? ' active' : '');

        let icon = '📄';
        const nameLower = file.name.toLowerCase();
        if (nameLower.endsWith('.pdf')) icon = '📕';
        else if (nameLower.endsWith('.doc') || nameLower.endsWith('.docx')) icon = '📘';
        else if (nameLower.endsWith('.xls') || nameLower.endsWith('.xlsx')) icon = '📗';
        else if (nameLower.endsWith('.ppt') || nameLower.endsWith('.pptx')) icon = '📙';
        else if (['.png', '.jpg', '.jpeg', '.webp'].some(ext => nameLower.endsWith(ext))) icon = '🖼️';
        else if (['.py', '.js', '.json', '.csv', '.txt', '.md'].some(ext => nameLower.endsWith(ext))) icon = '📝';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'file-select-checkbox';
        checkbox.checked = (selectedFilename === file.name);
        checkbox.onchange = (e) => {
            e.stopPropagation();
            handleFileSelectionToggle(file, checkbox.checked);
        };

        const info = document.createElement('div');
        info.className = 'file-info';
        info.style.cursor = 'pointer';
        info.onclick = () => {
            handleFileSelectionToggle(file, !checkbox.checked);
        };
        info.innerHTML = `<span class="file-icon">${icon}</span> <span class="file-name">${file.name}</span> <span class="file-size">(${formatBytes(file.size)})</span>`;

        const removeBtn = document.createElement('button');
        removeBtn.className = 'remove-btn';
        removeBtn.innerHTML = '✖';
        removeBtn.onclick = (e) => {
            e.stopPropagation();
            removeStagedFile(index);
        };

        item.appendChild(checkbox);
        item.appendChild(info);
        item.appendChild(removeBtn);
        listEl.appendChild(item);
    });
}

async function handleFileSelectionToggle(file, isChecked) {
    if (isChecked) {
        // STRICT 1-FILE SELECTION: warn if another file is already selected
        if (selectedFilename && selectedFilename !== file.name) {
            showToast("⚠️ Please uncheck the current file first.", "error");
            renderStagingTray();
            return;
        }

        selectedFilename = file.name;
        renderStagingTray();
        previewStagedFile(file);

        const nameLower = file.name.toLowerCase();
        let isImage = ['.png', '.jpg', '.jpeg', '.webp'].some(ext => nameLower.endsWith(ext));

        // Upload documents to the neural index in the background
        if (!isImage) {
            try {
                showToast(`Staging "${file.name}" to neural index...`, "success");
                const formData = new FormData();
                formData.append('file', file);
                const uploadRes = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                if (!uploadRes.ok) throw new Error("Upload failed");
                await fetch('/api/build-index', { method: 'POST' });
            } catch (err) {
                console.error("Background staging failed:", err);
                showToast(`⚠️ Staging failed for "${file.name}".`, "error");
            }
        }

        // Notify Chainlit backend of file selection
        try {
            if (typeof window.sendChainlitMessage !== 'function') {
                throw new Error("sendChainlitMessage not available");
            }
            window.sendChainlitMessage({
                type: "user_message",
                output: `[FILE_SELECTED:${file.name}]`
            });
            showToast(`🎯 Focused: "${file.name}"`, "success");
        } catch (err) {
            console.error(err);
            showToast("⚠️ Failed to focus file in Copilot.", "error");
        }

    } else {
        if (selectedFilename === file.name) {
            selectedFilename = null;
            renderStagingTray();
            closePreview();

            try {
                if (typeof window.sendChainlitMessage !== 'function') {
                    throw new Error("sendChainlitMessage not available");
                }
                window.sendChainlitMessage({
                    type: "user_message",
                    output: `[FILE_DESELECTED:${file.name}]`
                });
                showToast(`🔓 Unfocused: "${file.name}"`, "success");
            } catch (err) {
                console.error(err);
            }
        }
    }
}

function removeStagedFile(index) {
    const removedFile = stagedFiles[index];
    stagedFiles.splice(index, 1);

    if (previewObjectUrls[removedFile.name]) {
        URL.revokeObjectURL(previewObjectUrls[removedFile.name]);
        delete previewObjectUrls[removedFile.name];
    }

    if (selectedFilename === removedFile.name) {
        selectedFilename = null;
        closePreview();
    }

    renderStagingTray();
}

// ==========================================
// FILE PREVIEW
// ==========================================
function previewStagedFile(file) {
    const docViewer = document.getElementById('doc-viewer');
    const placeholder = document.getElementById('viewer-placeholder');
    const scriptContainer = document.getElementById('script-preview-container');
    const scriptCode = document.getElementById('script-preview-code');

    if (!docViewer || !placeholder || !scriptContainer || !scriptCode) return;

    docViewer.style.display = 'none';
    scriptContainer.style.display = 'none';
    placeholder.style.display = 'none';

    const nameLower = file.name.toLowerCase();

    try {
        if (nameLower.endsWith('.pdf')) {
            if (!previewObjectUrls[file.name]) {
                previewObjectUrls[file.name] = URL.createObjectURL(file);
            }
            docViewer.src = previewObjectUrls[file.name];
            docViewer.style.display = 'block';
        }
        else if (['.txt', '.py', '.js', '.json', '.csv', '.html', '.css', '.md', '.sh'].some(ext => nameLower.endsWith(ext))) {
            const reader = new FileReader();
            reader.onload = (e) => {
                scriptCode.textContent = e.target.result;
                scriptContainer.style.display = 'block';
            };
            reader.onerror = () => {
                showToast(`❌ Error reading "${file.name}"`, "error");
                placeholder.style.display = 'flex';
            };
            reader.readAsText(file);
        }
        else if (['.png', '.jpg', '.jpeg', '.webp'].some(ext => nameLower.endsWith(ext))) {
            if (!previewObjectUrls[file.name]) {
                previewObjectUrls[file.name] = URL.createObjectURL(file);
            }
            placeholder.innerHTML = `
                <img src="${previewObjectUrls[file.name]}" alt="${file.name}"
                    style="max-width:100%;max-height:100%;border-radius:12px;object-fit:contain;" />
            `;
            placeholder.style.display = 'flex';
        }
        else {
            placeholder.innerHTML = `
                <div class="placeholder-icon">📦</div>
                <h2>${file.name} Loaded</h2>
                <p>Document focused. Ready for query_academic_textbooks analysis.</p>
            `;
            placeholder.style.display = 'flex';
        }
    } catch (err) {
        console.error("Preview rendering failed:", err);
        showToast(`❌ Preview error: ${err.message}`, "error");
        placeholder.style.display = 'flex';
    }
}

function closePreview() {
    const docViewer = document.getElementById('doc-viewer');
    const placeholder = document.getElementById('viewer-placeholder');
    const scriptContainer = document.getElementById('script-preview-container');
    const scriptCode = document.getElementById('script-preview-code');

    if (docViewer) { docViewer.src = ''; docViewer.style.display = 'none'; }
    if (scriptContainer) scriptContainer.style.display = 'none';
    if (scriptCode) scriptCode.textContent = '';
    if (placeholder) {
        placeholder.innerHTML = `
            <div class="placeholder-icon">📚</div>
            <h2>Native Document Workspace</h2>
            <p>Upload files and select a PDF file below to read inline here.</p>
        `;
        placeholder.style.display = 'flex';
    }
}

// ==========================================
// ANALYZE STAGED FILE
// ==========================================
async function analyzeStagedFiles() {
    if (!selectedFilename) {
        showToast("⚠️ Please select a file from the staging tray to analyze.", "warning");
        return;
    }

    const file = stagedFiles.find(f => f.name === selectedFilename);
    if (!file) return;

    const analyzeBtn = document.getElementById('analyze-btn');
    const statusText = document.getElementById('status-text');

    analyzeBtn.disabled = true;
    analyzeBtn.innerText = "Analyzing...";
    if (statusText) statusText.innerText = "Preparing analysis...";

    try {
        const nameLower = file.name.toLowerCase();
        let isImage = ['.png', '.jpg', '.jpeg', '.webp'].some(ext => nameLower.endsWith(ext));

        let promptText = "";
        if (isImage) {
            if (statusText) statusText.innerText = "Uploading image to server...";
            try {
                const formData = new FormData();
                formData.append('file', file);
                const uploadRes = await fetch('/api/upload', { method: 'POST', body: formData });
                const uploadData = await uploadRes.json();
                const imageUrl = uploadData.url || `/public/elements/${file.name}`;
                promptText = `Please analyze this image file: ${file.name} (server path: ${imageUrl})`;
            } catch (uploadErr) {
                // Fallback: embed base64 only for small images
                if (file.size < 500 * 1024) {
                    const dataUrl = await new Promise((resolve, reject) => {
                        const reader = new FileReader();
                        reader.onload = () => resolve(reader.result);
                        reader.onerror = () => reject(new Error("Image read error"));
                        reader.readAsDataURL(file);
                    });
                    promptText = `Please analyze this image: ${file.name}\n[IMAGE_DATA:${file.name}:${dataUrl}]`;
                } else {
                    showToast("⚠️ Image too large for direct analysis. Upload to server first.", "error");
                    return;
                }
            }
        } else {
            promptText = `Please analyze the focused file: ${file.name}`;
        }

        if (statusText) statusText.innerText = "Sending to Copilot...";

        if (typeof window.sendChainlitMessage !== 'function') {
            throw new Error("sendChainlitMessage not available — Copilot not yet initialized.");
        }
        window.sendChainlitMessage({ type: "user_message", output: promptText });

        if (statusText) statusText.innerText = "Analysis request sent!";
        showToast(`⚡ Analysis started for "${file.name}".`, "success");

    } catch (e) {
        console.error(e);
        if (statusText) statusText.innerText = `Error: ${e.message}`;
        showToast(`❌ Error: ${e.message}`, "error");
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.innerText = "Analyze Selected File";
    }
}

// ==========================================
// UTILITIES
// ==========================================
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}