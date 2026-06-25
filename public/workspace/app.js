// ==========================================
// 🚀 CLIENT-SIDE ROUTING INTERCEPTOR
// Chainlit's React SPA tries to hijack /login.
// We intercept it here and hard-redirect to our custom HTML pages.
// We use the /public/ path because it bypasses Chainlit's Auth Middleware!
// ==========================================
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

let stagedFiles = []; // Array of File objects
let previewObjectUrls = {}; // Maps filename to object URL for previews
let selectedFilename = null; // Tracks the single selected file name

document.addEventListener('DOMContentLoaded', () => {
    // 1. Initialize the Chainlit Copilot Widget
    window.mountChainlitWidget({
        chainlitServer: "http://localhost:8000",
        theme: "dark",
        button: {
            style: {
                bgcolor: "#00d4ff",
                color: "#060b16",
                border: "none"
            }
        }
    });

    // Auto-open Copilot, reparent to #copilot-root, & inject style overrides into Shadow DOM
    // FIX P2-18: Improved clearInterval guard — check both computed style AND class/hidden attribute
    let copilotInjected = false;
    const openCopilotInterval = setInterval(() => {
        const copilotHost = document.getElementById('chainlit-copilot');
        const copilotRoot = document.getElementById('copilot-root');

        // Reparent inside the dedicated split column
        if (copilotHost && copilotRoot && copilotHost.parentNode !== copilotRoot) {
            copilotRoot.appendChild(copilotHost);
        }

        if (copilotHost && copilotHost.shadowRoot) {
            const popover = copilotHost.shadowRoot.getElementById('chainlit-copilot-popover');
            const copilotBtn = copilotHost.shadowRoot.getElementById('chainlit-copilot-button');

            // Inject custom styles directly into the shadow root to force panel open
            if (!copilotHost.shadowRoot.getElementById('custom-copilot-styles')) {
                const style = document.createElement('style');
                style.id = 'custom-copilot-styles';
                style.textContent = `
                    #chainlit-copilot-button { display: none !important; }
                    #chainlit-copilot-popover {
                        display: block !important;
                        width: 100% !important;
                        height: 100vh !important;
                        position: relative !important;
                        right: 0 !important;
                        left: auto !important;
                        border-radius: 0 !important;
                        box-shadow: none !important;
                        margin: 0 !important;
                        padding: 0 !important;
                        border: none !important;
                        background: transparent !important;
                        transform: none !important;
                    }
                    #chainlit-copilot-popover iframe {
                        position: relative !important;
                        width: 100% !important;
                        height: 100% !important;
                        border: none !important;
                        right: 0 !important;
                        left: auto !important;
                    }
                `;
                copilotHost.shadowRoot.appendChild(style);
            }

            // Click button to initialize open state if popover is hidden
            // FIX P2-18: Check computed style AND visibility state properly
            if (copilotBtn && popover) {
                const computedDisplay = window.getComputedStyle(popover).display;
                const isHidden = (
                    popover.hidden ||
                    computedDisplay === 'none' ||
                    popover.classList.contains('hidden')
                );
                if (isHidden && !copilotInjected) {
                    copilotBtn.click();
                }
            }

            // Always clear interval once shadow DOM is ready and injected
            copilotInjected = true;
            clearInterval(openCopilotInterval);

        } else {
            // Fallback for Light DOM if widget script mounts without shadow DOM
            const copilotBtn = document.getElementById('chainlit-copilot-button');
            const popover = document.getElementById('chainlit-copilot-popover');
            if (copilotBtn && (!popover || popover.style.display === 'none')) {
                copilotBtn.click();
                clearInterval(openCopilotInterval);
            }
        }
    }, 200);

    // Setup drag & drop listeners on the dropzone
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

    // Listener for CopilotFunction calls from Chainlit backend
    window.addEventListener("chainlit-call-fn", (e) => {
        const { name, args, callback } = e.detail;

        if (name === "new_chat_session") {
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

        // FIX P2-19: clear_visual_chat — documented as fragile internal DOM surgery,
        // graceful fallback if the DOM structure has changed
        else if (name === "clear_visual_chat") {
            try {
                const copilotHost = document.getElementById('chainlit-copilot');
                let iframe = null;

                if (copilotHost && copilotHost.shadowRoot) {
                    iframe = copilotHost.shadowRoot.querySelector('#chainlit-copilot-popover iframe');
                } else {
                    iframe = document.querySelector('#chainlit-copilot-popover iframe');
                }

                if (iframe && iframe.contentDocument) {
                    const doc = iframe.contentDocument;
                    // Attempt to hide messages via various selector patterns (fragile — Chainlit internals can change)
                    const containers = doc.querySelectorAll(
                        '.step-container, [class*="step-container"], [class*="message-list"], .message-list, [data-testid="message-list"]'
                    );
                    let cleared = false;
                    containers.forEach(container => {
                        Array.from(container.children).forEach(child => {
                            child.style.display = 'none';
                        });
                        cleared = true;
                    });
                    if (!cleared) {
                        // Wider fallback
                        const messages = doc.querySelectorAll(
                            '[data-testid="message"], [id^="step-"], [class*="message-container"], [class*="Message"]'
                        );
                        messages.forEach(m => m.style.display = 'none');
                    }
                } else {
                    // Graceful fallback: tell user it's not possible via toast
                    showToast("⚠️ Could not access Copilot iframe for visual clear. Memory is intact.", "warning");
                }
            } catch (err) {
                console.error("Failed to visually clear chat:", err);
                showToast("Could not clear visual chat history.", "error");
            }
            if (callback) callback("Success");
        }
    });
});

function showToast(message, type = 'warning') {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = message;
    container.appendChild(toast);

    // Animate slide-in
    setTimeout(() => toast.classList.add('active'), 10);

    // Auto dismiss after 4 seconds
    setTimeout(() => {
        toast.classList.remove('active');
        toast.classList.add('fade-out');
        setTimeout(() => toast.remove(), 500);
    }, 4000);
}

function handleFiles(files) {
    if (!files || files.length === 0) return;

    const allowedExtensions = ['.png', '.jpg', '.jpeg', '.webp', '.doc', '.docx', '.pdf', '.ppt', '.pptx', '.xls', '.xlsx', '.txt', '.csv', '.py', '.js', '.json', '.md'];
    let addedCount = 0;

    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const filename = file.name.toLowerCase();
        const matchesExtension = allowedExtensions.some(ext => filename.endsWith(ext));

        if (!matchesExtension) {
            showToast(`❌ File type not allowed: ${file.name}`, "error");
            continue;
        }

        // Check if already staged
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
        // FIX P2-22: Use display: 'none' (not 'flex' for hidden)
        trayEl.style.display = 'none';
        analyzeBtn.disabled = true;
        listEl.innerHTML = '';
        closePreview();
        return;
    }

    // FIX P2-22: Use 'flex' to preserve flex layout when showing tray
    trayEl.style.display = 'flex';
    analyzeBtn.disabled = !selectedFilename;
    listEl.innerHTML = '';

    stagedFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'staged-file-item' + (selectedFilename === file.name ? ' active' : '');

        // Choose appropriate icon
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
        // STRICT 1-FILE SELECTION: Warning Toast if another file is already checked
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

        // If it's a document, upload and index in background
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

        // FIX P0-3: Use "user_message" type so on_message handler fires correctly
        try {
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

            // FIX P0-3: Use "user_message" type for FILE_DESELECTED too
            try {
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

    // Revoke object URL if exists
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

function previewStagedFile(file) {
    const docViewer = document.getElementById('doc-viewer');
    const placeholder = document.getElementById('viewer-placeholder');
    const scriptContainer = document.getElementById('script-preview-container');
    const scriptCode = document.getElementById('script-preview-code');

    if (!docViewer || !placeholder || !scriptContainer || !scriptCode) return;

    // Reset views
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
            // FIX P2-20: For image analysis, upload via /api/upload first instead of embedding giant base64 in WebSocket
            // Show a preview locally using object URL, but send the server URL to the AI
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

    if (docViewer) {
        docViewer.src = '';
        docViewer.style.display = 'none';
    }
    if (scriptContainer) {
        scriptContainer.style.display = 'none';
    }
    if (scriptCode) {
        scriptCode.textContent = '';
    }
    if (placeholder) {
        placeholder.innerHTML = `
            <div class="placeholder-icon">📚</div>
            <h2>Native Document Workspace</h2>
            <p>Upload files and select a PDF file below to read inline here.</p>
        `;
        placeholder.style.display = 'flex';
    }
}

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
            // FIX P2-20: Upload image via /api/upload first, pass filename URL to AI
            // Avoid giant base64 blobs in WebSocket messages
            if (statusText) statusText.innerText = "Uploading image to server...";
            try {
                const formData = new FormData();
                formData.append('file', file);
                const uploadRes = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                const uploadData = await uploadRes.json();
                const imageUrl = uploadData.url || `/public/elements/${file.name}`;
                promptText = `Please analyze this image file: ${file.name} (server path: ${imageUrl})`;
            } catch (uploadErr) {
                // Fallback: send small base64 for small images only
                if (file.size < 500 * 1024) { // Under 500KB: OK to embed
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
        window.sendChainlitMessage({
            type: "user_message",
            output: promptText
        });

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

function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}