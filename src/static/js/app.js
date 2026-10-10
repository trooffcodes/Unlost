/**
 * Main Frontend Application Script
 */
const App = (() => {
    let state = { files: [], searchQuery: "", pollInterval: null };

    const CONFIG = { MAX_FILE_SIZE: 15 * 1024 * 1024, MAX_BATCH_SIZE: 50 };

    const ICONS = {
        folder: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="folder-icon"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
        file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
        copy: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,
        check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`
    };

    const DOM = {
        dropzone: document.getElementById('dropzone'),
        fileInput: document.getElementById('fileInput'),
        meterFill: document.getElementById('meterFill'),
        meterText: document.getElementById('meterText'),
        flatView: document.getElementById('flatView'),
        aiView: document.getElementById('aiView'),
        aiFolderDetailView: document.getElementById('aiFolderDetailView'),
        folderFilesContainer: document.getElementById('folderFilesContainer'),
        tabs: document.querySelectorAll('.tab'),
        searchInput: document.getElementById('searchInput'),
        uploadModal: document.getElementById('uploadModal'),
        uploadList: document.getElementById('uploadList'),
        uploadPhaseText: document.getElementById('uploadPhaseText'),
        toastContainer: document.getElementById('toastContainer'),
        feedbackForm: document.getElementById('feedbackForm'),
        feedbackText: document.getElementById('feedbackText')
    };

    const apiFetch = async (endpoint, options = {}) => {
        try {
            const res = await fetch(endpoint, options);
            if (res.status === 403) return showToast("Token quota exhausted. Resets in 48h.", true), null;
            if (res.status === 500) return showToast("Internal Server Error.", true), null;

            const data = await res.json();
            if (!data.success && data.error) return showToast(data.error, true), null;
            return data;
        } catch (err) {
            console.error(`API Error on ${endpoint}:`, err);
            return showToast("Could not connect to Unlost servers.", true), null;
        }
    };

    const init = () => {
        setupEventListeners();
        refreshDashboard();
    };

    const setupEventListeners = () => {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => DOM.dropzone.addEventListener(evt, preventDefaults, false));
        ['dragenter', 'dragover'].forEach(evt => DOM.dropzone.addEventListener(evt, () => DOM.dropzone.classList.add('drag-active'), false));
        ['dragleave', 'drop'].forEach(evt => DOM.dropzone.addEventListener(evt, () => DOM.dropzone.classList.remove('drag-active'), false));
        
        DOM.dropzone.addEventListener('drop', handleDrop, false);
        DOM.fileInput.addEventListener('change', handleFileInput);
        DOM.tabs.forEach(t => t.addEventListener('click', (e) => switchTab(e.target.dataset.target)));

        let searchDebounceTimer;
        DOM.searchInput.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.trim();
            clearTimeout(searchDebounceTimer);
            if (state.searchQuery.length > 2) {
                searchDebounceTimer = setTimeout(() => {
                    performSearch();
                }, 500);
            } else {
                renderViews();
            }
        });


        DOM.feedbackForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = DOM.feedbackText.value.trim();
            if (!msg) return;
            const res = await apiFetch('/feedback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            if (res && res.success) { showToast("Feedback received."); DOM.feedbackText.value = ''; }
        });
    };

    const refreshDashboard = async () => { await fetchUsage(); await fetchFiles(); };

    const fetchUsage = async () => {
        const res = await apiFetch('/usage');
        if (res && res.data) {
            const pct = Math.min((res.data.used / res.data.limit) * 100, 100);
            DOM.meterFill.style.width = `${pct}%`;
            DOM.meterText.innerText = `${Math.round(pct)}%`;
            DOM.meterFill.style.backgroundColor = pct < 70 ? 'var(--success)' : (pct < 90 ? 'var(--warning)' : 'var(--danger)');
        }
    };

    const fetchFiles = async () => {
        const res = await apiFetch('/files');
        if (res && res.files) { state.files = res.files; renderViews(); }
    };

    const performSearch = async () => {
        const res = await apiFetch('/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: state.searchQuery })
        });
        if (res && res.results) renderSearchResults(res.results);
    };

    const handleDrop = (e) => processFiles(e.dataTransfer.files);
    const handleFileInput = (e) => { processFiles(e.target.files); DOM.fileInput.value = ''; };

    const processFiles = async (fileList) => {
        const files = Array.from(fileList);
        if (!files.length) return;
        if (files.length > CONFIG.MAX_BATCH_SIZE) return showToast(`Max ${CONFIG.MAX_BATCH_SIZE} files allowed.`, true);

        const formData = new FormData();
        for (const file of files) {
            if (file.size > CONFIG.MAX_FILE_SIZE) { showToast(`${file.name} > 15MB limit. Skipped.`, true); continue; }
            formData.append('files', file);
        }

        DOM.uploadModal.classList.add('show');
        DOM.uploadList.innerHTML = files.map(f => createUploadItemHTML(f.name, "Queued")).join('');
        DOM.uploadPhaseText.innerText = "Uploading...";

        const res = await apiFetch('/upload', { method: 'POST', body: formData });
        res && res.batch_id ? startPolling(res.batch_id) : DOM.uploadModal.classList.remove('show');
    };

    const startPolling = (batchId) => {
        DOM.uploadPhaseText.innerText = "Processing Details...";
        if (state.pollInterval) clearInterval(state.pollInterval);

        state.pollInterval = setInterval(async () => {
            const res = await apiFetch(`/status/${batchId}`);
            if (res && res.data) {
                updateUploadModal(res.data.files);
                if (res.data.status === 'completed') {
                    clearInterval(state.pollInterval);
                    DOM.uploadPhaseText.innerText = "Completed!";
                    setTimeout(() => DOM.uploadModal.classList.remove('show'), 4000);
                    refreshDashboard();
                }
            } else { clearInterval(state.pollInterval); }
        }, 1200);
    };

    const switchTab = (targetId) => {
        if (state.searchQuery.length > 0 && targetId !== 'flatView') return showToast("Clear search to browse folders.");
        DOM.tabs.forEach(t => t.classList.remove('active'));
        document.querySelector(`[data-target="${targetId}"]`).classList.add('active');
        
        DOM.flatView.classList.toggle('hidden', targetId !== 'flatView');
        DOM.aiView.classList.toggle('hidden', targetId !== 'aiView');
        DOM.aiFolderDetailView.classList.add('hidden');
    };

    const renderViews = () => { if(state.searchQuery.length === 0) { renderFlatView(state.files); renderAIView(state.files); } };

    const renderFlatView = (arr) => {
        DOM.flatView.innerHTML = arr.length ? arr.map(f => createFileCard(f)).join('') : `<div class="empty-state">No documents ingested yet.</div>`;
    };

    const renderAIView = (arr) => {
        const folders = arr.reduce((acc, f) => { const fn = f.folder || "Unsorted"; acc[fn] = acc[fn] || []; acc[fn].push(f); return acc; }, {});
        const keys = Object.keys(folders).sort();
        DOM.aiView.innerHTML = keys.length ? keys.map(k => createFolderCard(k, folders[k].length)).join('') : `<div class="empty-state">No AI folders yet.</div>`;
    };

    const renderSearchResults = (results) => {
        DOM.tabs.forEach(t => t.classList.remove('active'));
        document.querySelector(`[data-target="flatView"]`).classList.add('active');
        DOM.flatView.classList.remove('hidden');
        DOM.aiView.classList.add('hidden');
        DOM.aiFolderDetailView.classList.add('hidden');
        DOM.flatView.innerHTML = results.length ? results.map(r => createFileCard(r, true)).join('') : `<div class="empty-state">No semantic matches found.</div>`;
    };

    window.App = {
        openFolder: (folderName) => {
            const fFiles = state.files.filter(f => (f.folder || "Unsorted") === folderName);
            DOM.aiView.classList.add('hidden');
            DOM.aiFolderDetailView.classList.remove('hidden');
            DOM.folderFilesContainer.innerHTML = fFiles.map(f => createFileCard(f)).join('');
        },
        closeFolderView: () => { DOM.aiFolderDetailView.classList.add('hidden'); DOM.aiView.classList.remove('hidden'); },
        clearData: async () => {
            if (confirm("Erase all device files and embeddings? Usage limits remain.")) {
                const res = await apiFetch('/clear_data', { method: 'POST' });
                if (res && res.success) { showToast("Storage cleared securely."); state.files = []; renderViews(); }
            }
        },
        copyPath: (btn, path) => {
            navigator.clipboard.writeText(path);
            const originalHTML = btn.innerHTML;
            btn.innerHTML = `${ICONS.check} Copied`;
            setTimeout(() => btn.innerHTML = originalHTML, 2000);
        }
    };

    const createFileCard = (data, isSearch = false) => {
        const file = (isSearch && data.metadata) ? data.metadata : data;
        const filename = data.filename || file.document_title || "Unknown File";
        const tagsHTML = (file.tags || []).map(t => `<span class="tag">#${t}</span>`).join('');
        let relHTML = (isSearch && data.similarity) ? `<span class="score-badge">${Math.round(data.similarity * 100)}% Match</span>` : "";
        const path = data.file_path || file.file_path || "";
        const copyBtn = path ? `<button class="copy-btn" onclick="App.copyPath(this, '${path}')">${ICONS.copy} Path</button>` : '';

        return `
            <div class="card">
                <div class="card-header">
                    <div class="file-title-wrap">
                        <div class="file-icon">${ICONS.file}</div>
                        <div style="min-width: 0;">
                            <h4 class="file-name">${filename}</h4>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">${file.date || ''} • ${file.document_type || 'File'}</div>
                        </div>
                    </div>
                </div>
                <div class="file-summary">${file.summary || "No summary available."}</div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-top: auto; padding-top: 1rem;">
                    <div class="tags">${tagsHTML}</div>
                    <div style="display:flex; flex-direction:column; gap:0.5rem; align-items:flex-end;">${relHTML}${copyBtn}</div>
                </div>
            </div>`;
    };

    const createFolderCard = (fName, count) => `
        <div class="folder-card" onclick="App.openFolder('${fName}')">
            ${ICONS.folder}
            <div class="folder-details"><h4>${fName}</h4><p>${count} document${count !== 1 ? 's' : ''}</p></div>
        </div>`;

    const createUploadItemHTML = (fname, statStr) => {
        const isError = statStr.startsWith("ERROR");
        const statusClass = isError ? "status-error" : (statStr === "Processing..." ? "status-processing" : (statStr === "DONE" ? "status-done" : "status-queued"));
        return `<div class="upload-item"><span class="upload-name" title="${fname}">${fname}</span><span class="upload-status ${statusClass}" ${isError ? `title="${statStr}"` : ''}>${isError ? 'ERROR' : statStr}</span></div>`;
    };

    const updateUploadModal = (filesDict) => DOM.uploadList.innerHTML = Object.entries(filesDict).map(([fn, stat]) => createUploadItemHTML(fn, stat)).join('');

    const showToast = (message, isError = false) => {
        const toast = document.createElement('div');
        toast.className = `toast ${isError ? 'error' : ''}`;
        toast.innerHTML = `${isError ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>` : ICONS.check} ${message}`;
        DOM.toastContainer.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 4000);
    };

    const preventDefaults = (e) => { e.preventDefault(); e.stopPropagation(); };

    init();
})();