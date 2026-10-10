const App = (() => {
    const { escapeHTML: esc } = window.UnlostSafety;
    // 1. Initialize page load time for metadata tracking
    const loadTime = Date.now(); 

    let state = { files: [], searchQuery: "", pollInterval: null, feedbackImageFile: null };
    const CONFIG = JSON.parse(document.getElementById("uploadConfig").textContent);
    const ICONS = {
        folder: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="folder-icon"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`,
        file: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>`,
        check: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`,
        image: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`
    };

    const DOM = {
        dropzone: document.getElementById('dropzone'), fileInput: document.getElementById('fileInput'),
        meterFill: document.getElementById('meterFill'), meterText: document.getElementById('meterText'),
        flatView: document.getElementById('flatView'), aiView: document.getElementById('aiView'),
        aiFolderDetailView: document.getElementById('aiFolderDetailView'), folderFilesContainer: document.getElementById('folderFilesContainer'),
        tabs: document.querySelectorAll('#viewTabs .tab'), searchInput: document.getElementById('searchInput'),
        uploadModal: document.getElementById('uploadModal'), uploadList: document.getElementById('uploadList'),
        uploadPhaseText: document.getElementById('uploadPhaseText'), toastContainer: document.getElementById('toastContainer'),
        feedbackForm: document.getElementById('feedbackForm'), feedbackText: document.getElementById('feedbackText'),
        imageInput: document.getElementById('feedbackImageInput'), previewContainer: document.getElementById('imagePreviewContainer'),
        imagePreview: document.getElementById('feedbackImagePreview'), removeImageBtn: document.getElementById('removeFeedbackImage'),
        submitBtn: document.getElementById('feedbackSubmitBtn'), btnText: document.getElementById('btnText'), btnSpinner: document.getElementById('btnSpinner')
    };

    const apiFetch = async (endpoint, options = {}) => {
        try {
            const res = await fetch(endpoint, { ...options, headers: { ...options.headers, "X-Unlost-Request": "1" } });
            if (res.status === 413) return showToast("Upload exceeds the request size limit.", true), null;
            const data = await res.json();
            if (!res.ok) return showToast(data.error || `Request failed (${res.status}).`, true), null;
            if (!data.success && data.error) return showToast(data.error, true), null;
            return data;
        } catch (err) { return showToast("Could not connect to Unlost servers.", true), null; }
    };

    const init = () => { setupEventListeners(); refreshDashboard(); };

    const setupEventListeners = () => {
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(evt => DOM.dropzone.addEventListener(evt, (e)=>{e.preventDefault(); e.stopPropagation();}));
        ['dragenter', 'dragover'].forEach(evt => DOM.dropzone.addEventListener(evt, () => DOM.dropzone.classList.add('drag-active')));
        ['dragleave', 'drop'].forEach(evt => DOM.dropzone.addEventListener(evt, () => DOM.dropzone.classList.remove('drag-active')));
        
        DOM.dropzone.addEventListener('drop', (e) => processFiles(e.dataTransfer.files));
        DOM.fileInput.addEventListener('change', (e) => { processFiles(e.target.files); DOM.fileInput.value = ''; });
        DOM.tabs.forEach(t => t.addEventListener('click', (e) => switchTab(e.currentTarget.dataset.target)));

        let searchDebounceTimer;
        DOM.searchInput.addEventListener('input', (e) => {
            state.searchQuery = e.target.value.trim();
            clearTimeout(searchDebounceTimer);
            if (state.searchQuery.length > 2) { searchDebounceTimer = setTimeout(performSearch, 500); } 
            else { renderViews(); }
        });

        DOM.imageInput.addEventListener('change', (e) => {
            if (e.target.files && e.target.files[0]) handleImagePreview(e.target.files[0]);
        });

        DOM.feedbackText.addEventListener('paste', (e) => {
            const items = (e.clipboardData || e.originalEvent.clipboardData).items;
            for (let item of items) {
                if (item.kind === 'file' && item.type.startsWith('image/')) {
                    handleImagePreview(item.getAsFile());
                    e.preventDefault();
                }
            }
        });

        DOM.removeImageBtn.addEventListener('click', () => {
            state.feedbackImageFile = null;
            DOM.imageInput.value = "";
            DOM.previewContainer.classList.add('hidden');
            DOM.imagePreview.src = "";
        });

        DOM.feedbackForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = DOM.feedbackText.value.trim();
            if (!msg && !state.feedbackImageFile) return;

            DOM.submitBtn.disabled = true;
            DOM.btnText.classList.add('hidden');
            DOM.btnSpinner.classList.remove('hidden');

            const formData = new FormData();
            formData.append('message', msg);
            if (state.feedbackImageFile) formData.append('image', state.feedbackImageFile);
            
            // 2. Client-Side Telemetry / Metadata Append
            formData.append("resolution", `${window.innerWidth}x${window.innerHeight}`);
            formData.append("time_on_page", `${Math.floor((Date.now() - loadTime) / 1000)}s`);
            formData.append("current_url", window.location.href);

            const res = await apiFetch('/feedback', { method: 'POST', body: formData }); 
            
            if (res && res.success) { 
                showToast("Feedback received."); 
                DOM.feedbackText.value = ''; 
                DOM.removeImageBtn.click();
            }

            DOM.submitBtn.disabled = false;
            DOM.btnText.classList.remove('hidden');
            DOM.btnSpinner.classList.add('hidden');
        });
    };

    const handleImagePreview = (file) => {
        if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 256 * 1024) {
            return showToast('Use a PNG, JPEG or WebP screenshot up to 256 KB.', true);
        }
        state.feedbackImageFile = file;
        const reader = new FileReader();
        reader.onload = (e) => {
            DOM.imagePreview.src = e.target.result;
            DOM.previewContainer.classList.remove('hidden');
        };
        reader.readAsDataURL(file);
    };

    const refreshDashboard = async () => { await fetchUsage(); await fetchFiles(); };
    
    const fetchUsage = async () => {
        const res = await apiFetch('/usage');
        if (res && res.data) {
            const pct = (res.data.limit > 0 ? Math.min((res.data.used / res.data.limit) * 100, 100) : 100);
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
        const query = state.searchQuery;
        const res = await apiFetch('/search', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ query: state.searchQuery }) });
        if (res && res.results && query === state.searchQuery) renderSearchResults(res.results);
    };

    const processFiles = async (fileList) => {
        if (state.uploading) return showToast("Please wait for the current upload.", true);
        const files = Array.from(fileList);
        if (!files.length) return;
        if (files.length > CONFIG.MAX_BATCH_SIZE) return showToast(`Max ${CONFIG.MAX_BATCH_SIZE} files allowed.`, true);
        if (files.some(file => file.size > CONFIG.MAX_FILE_SIZE)) {
            return showToast(`Each file must be at most ${CONFIG.MAX_FILE_SIZE / 1000000} MB.`, true);
        }
        state.uploading = true;
        const statuses = files.map(file => [file.name, 'Queued']);
        const render = () => { DOM.uploadList.innerHTML = statuses.map(([name, status]) => createUploadItemHTML(name, status)).join(''); };
        DOM.uploadModal.classList.add('show');
        DOM.uploadPhaseText.innerText = "Uploading and processing...";
        render();
        try {
            // A request owns its processing lifetime. Send files separately for Vercel's body limit.
            for (let i = 0; i < files.length; i++) {
                statuses[i][1] = 'Processing...';
                render();
                const formData = new FormData();
                formData.append('files', files[i]);
                const res = await apiFetch('/upload', { method: 'POST', body: formData });
                const status = res && await apiFetch(`/status/${res.batch_id}`);
                if (status && status.data) {
                    statuses[i][1] = Object.values(status.data.files).find(value => value.startsWith('ERROR')) || 'DONE';
                } else {
                    statuses[i][1] = 'ERROR: Upload failed';
                }
                render();
            }
            DOM.uploadPhaseText.innerText = statuses.some(([, status]) => status.startsWith('ERROR')) ? 'Finished with errors' : 'Completed!';
            await refreshDashboard();
        } finally {
            state.uploading = false;
            setTimeout(() => { if (!state.uploading) DOM.uploadModal.classList.remove('show'); }, 5000);
        }
    };

    const switchTab = (targetId) => {
        if (state.searchQuery.length > 0 && targetId !== 'flatView') return showToast("Clear search to browse folders.");
        DOM.tabs.forEach(t => t.classList.remove('active'));
        document.querySelector(`#viewTabs [data-target="${targetId}"]`).classList.add('active');
        DOM.flatView.classList.toggle('hidden', targetId !== 'flatView');
        DOM.aiView.classList.toggle('hidden', targetId !== 'aiView');
        DOM.aiFolderDetailView.classList.add('hidden');
    };

    const renderViews = () => { if(state.searchQuery.length <= 2) { renderFlatView(state.files); renderAIView(state.files); } };
    const renderFlatView = (arr) => DOM.flatView.innerHTML = arr.length ? arr.map(f => createFileCard(f)).join('') : `<div class="empty-state">No documents ingested yet.</div>`;
    
    const renderAIView = (arr) => {
        const folders = arr.reduce((acc, f) => { const fn = f.folder || "Unsorted"; acc[fn] = acc[fn] || []; acc[fn].push(f); return acc; }, Object.create(null));
        const keys = Object.keys(folders).sort();
        
        DOM.aiView.innerHTML = keys.length ? keys.map(k => `
            <div class="folder-card" data-folder="${esc(k)}">
                ${ICONS.folder}
                <div class="folder-details">
                    <h4>${esc(k)}</h4>
                    <p>${folders[k].length} document(s)</p>
                </div>
                <div class="folder-open-icon">→</div>
            </div>
        `).join('') : `<div class="empty-state">No AI folders yet.</div>`;

        document.querySelectorAll('.folder-card').forEach(card => {
            card.addEventListener('click', () => {
                window.App.openFolder(card.dataset.folder);
            });
        });
    };

    const renderSearchResults = (results) => {
        DOM.tabs.forEach(t => t.classList.remove('active'));
        document.querySelector(`#viewTabs [data-target="flatView"]`).classList.add('active');
        DOM.flatView.classList.remove('hidden'); DOM.aiView.classList.add('hidden'); DOM.aiFolderDetailView.classList.add('hidden');
        DOM.flatView.innerHTML = results.length ? results.map(r => createFileCard(r, true)).join('') : `<div class="empty-state">No matches found.</div>`;
    };

    window.App = {
        openFolder: (folderName) => {
            const fFiles = state.files.filter(f => (f.folder || "Unsorted") === folderName);
            DOM.aiView.classList.add('hidden');
            document.getElementById('currentFolderName').innerText = `📂 ${esc(folderName)}`;
            DOM.aiFolderDetailView.classList.remove('hidden');
            DOM.folderFilesContainer.innerHTML = fFiles.map(f => createFileCard(f)).join('');
        },
        closeFolderView: () => { 
            DOM.aiFolderDetailView.classList.add('hidden'); 
            DOM.aiView.classList.remove('hidden'); 
        },
        clearData: async () => {
            if (state.uploading) return showToast("Wait for uploads to finish before clearing data.", true);
            if (confirm("Erase all document metadata and embeddings? Usage limits remain.")) {
                const res = await apiFetch('/clear_data', { method: 'POST' });
                if (res && res.success) { showToast("Storage cleared securely."); state.files = []; state.searchQuery = ""; DOM.searchInput.value = ""; renderViews(); }
            }
        }
    };

    const createFileCard = (data, isSearch = false) => {
        const file = (isSearch && data.metadata) ? data.metadata : data;
        const filename = data.filename || file.document_title || "Unknown File";
        const tagsHTML = (Array.isArray(file.tags) ? file.tags : []).map(t => `<span class="tag">#${esc(t)}</span>`).join('');
        const score = (isSearch && data.similarity) ? `<span class="score-badge">${Math.round(data.similarity * 100)}% Match</span>` : "";
        const folderName = file.suggested_folder || file.folder || data.folder || "Unsorted";
        const folderInfo = `<div class="folder-pill">📂 Folder: ${esc(folderName)}</div>`;
        const ext = filename.split('.').pop().toLowerCase();
        const isImage = ['png','jpg','jpeg','webp','bmp'].includes(ext);
        const iconHTML = isImage ? `<div class="file-icon-img">${ICONS.image}</div>` : `<div class="file-icon">${ICONS.file}</div>`;

        return `
            <div class="card">
                <div class="card-header">
                    <div class="file-title-wrap">
                        ${iconHTML}
                        <div style="min-width: 0;">
                            <h4 class="file-name">${esc(filename)}</h4>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 2px;">${esc(file.date || '')} • ${esc(file.document_type || 'File')}</div>
                            ${folderInfo}
                        </div>
                    </div>
                </div>
                <div class="file-summary">${esc(file.summary || "No summary available.")}</div>
                <div style="display: flex; justify-content: space-between; align-items: flex-end; margin-top: auto; padding-top: 1rem;">
                    <div class="tags">${tagsHTML}</div>
                    <div style="display:flex; flex-direction:column; gap:0.5rem; align-items:flex-end;">${score}</div>
                </div>
            </div>`;
    };

    const createUploadItemHTML = (fname, statStr) => {
        const isError = statStr.startsWith("ERROR");
        const statusClass = isError ? "status-error" : (statStr === "Processing..." ? "status-processing" : (statStr === "DONE" ? "status-done" : "status-queued"));
        return `<div class="upload-item"><span class="upload-name" title="${esc(fname)}">${esc(fname)}</span><span class="upload-status ${statusClass}" ${isError ? `title="${esc(statStr)}"` : ''}>${isError ? 'ERROR' : esc(statStr)}</span></div>`;
    };

    const showToast = (message, isError = false) => {
        const toast = document.createElement('div');
        toast.className = `toast ${isError ? 'error' : ''}`;
        toast.innerHTML = `${isError ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>` : ICONS.check} ${esc(message)}`;
        DOM.toastContainer.appendChild(toast);
        requestAnimationFrame(() => toast.classList.add('show'));
        setTimeout(() => { toast.classList.remove('show'); setTimeout(() => toast.remove(), 300); }, 4000);
    };

    init();
})();