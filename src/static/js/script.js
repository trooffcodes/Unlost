document.addEventListener("DOMContentLoaded", () => {
    // Dropzone & Upload
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const dropText = document.getElementById("dropText");
    const uploadForm = document.getElementById("uploadForm");
    const uploadBtn = document.getElementById("uploadBtn");
    const uploadStatus = document.getElementById("uploadStatus");

    // Search Elements
    const searchInput = document.getElementById("searchInput");
    const searchBtn = document.getElementById("searchBtn");
    const searchResults = document.getElementById("searchResults");

    // Dual-Tab Elements
    const tabUnorg = document.getElementById("tabUnorganized");
    const tabOrg = document.getElementById("tabOrganized");
    const viewUnorg = document.getElementById("viewUnorganized");
    const viewOrg = document.getElementById("viewOrganized");
    const refreshBtn = document.getElementById("refreshLibraryBtn");

    // Tab Switching
    function setTab(activeTab, activeView, inactiveTab, inactiveView) {
        activeTab.classList.add("active");
        inactiveTab.classList.remove("active");
        activeView.style.display = "block";
        inactiveView.style.display = "none";
    }

    tabUnorg.addEventListener("click", () => setTab(tabUnorg, viewUnorg, tabOrg, viewOrg));
    tabOrg.addEventListener("click", () => setTab(tabOrg, viewOrg, tabUnorg, viewUnorg));

    // Drag and Drop
    dropZone.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
        const count = fileInput.files.length;
        dropText.textContent = count > 1 ? `${count} files queued` : (count === 1 ? fileInput.files[0].name : "Select files");
    });

    ["dragover", "dragenter"].forEach(ev => dropZone.addEventListener(ev, (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    }));
    ["dragleave", "drop"].forEach(ev => dropZone.addEventListener(ev, (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
    }));
    dropZone.addEventListener("drop", (e) => {
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            const count = fileInput.files.length;
            dropText.textContent = count > 1 ? `${count} files queued` : fileInput.files[0].name;
        }
    });

    // Ingestion Poller
    function pollJobStatus(batchId) {
        const interval = setInterval(async () => {
            try {
                const res = await fetch(`/status/${batchId}`);
                const json = await res.json();
                if (!json.success) return clearInterval(interval);

                const info = json.data;
                let html = `<strong>Job State: ${info.status.toUpperCase()}</strong><br>`;
                for (const [name, state] of Object.entries(info.files || {})) {
                    const color = state.includes("ERROR") ? "#ef4444" : (state === "DONE" ? "#16a34a" : "#eab308");
                    html += `<div style="font-size:12px; margin-top:3px;">📄 ${name} <span style="color:${color}; float:right;">${state}</span></div>`;
                }
                uploadStatus.innerHTML = html;

                if (info.status === "completed") {
                    clearInterval(interval);
                    uploadBtn.disabled = false;
                    fileInput.value = "";
                    dropText.textContent = "Drag & drop files or ZIP archive here";
                    loadLibrary();
                    loadUsage();
                }
            } catch (err) {
                console.error("Status polling error", err);
            }
        }, 1200);
    }

    uploadForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (!fileInput.files.length) return;

        const data = new FormData();
        for (const file of fileInput.files) data.append("files", file);

        uploadBtn.disabled = true;
        uploadStatus.innerHTML = "<p>Dispatching documents to ingestion queue...</p>";

        try {
            const res = await fetch("/upload", { method: "POST", body: data });
            const result = await res.json();
            if (result.success) {
                pollJobStatus(result.batch_id);
            } else {
                uploadStatus.innerHTML = `<div style="color:#ef4444;">Upload error: ${result.error}</div>`;
                uploadBtn.disabled = false;
            }
        } catch (err) {
            uploadStatus.innerHTML = `<div style="color:#ef4444;">Network failure: ${err.message}</div>`;
            uploadBtn.disabled = false;
        }
    });

    // Dual-Tab Library Rendering
    async function loadLibrary() {
        try {
            const res = await fetch("/files");
            const data = await res.json();
            if (!data.success) return;

            const files = data.files || [];
            if (files.length === 0) {
                viewUnorg.innerHTML = "<p style='color:#94a3b8;'>No ingested files found in memory.</p>";
                viewOrg.innerHTML = "<p style='color:#94a3b8;'>No categories discovered.</p>";
                return;
            }

            // Flat View
            viewUnorg.innerHTML = files.map(f => `
                <div class="file-item">
                    <div>
                        <strong>📄 ${f.filename}</strong>
                        <div class="file-meta">${f.summary ? f.summary.substring(0, 110) + '...' : 'No summary generated.'}</div>
                    </div>
                    <div class="tag">${f.folder}</div>
                </div>
            `).join("");

            // Grouped Category View
            const grouped = files.reduce((acc, f) => {
                const folder = f.folder || "General";
                if (!acc[folder]) acc[folder] = [];
                acc[folder].push(f);
                return acc;
            }, {});

            viewOrg.innerHTML = Object.entries(grouped).map(([folderName, folderFiles]) => `
                <div class="folder-block">
                    <div class="folder-title">📁 ${folderName} (${folderFiles.length})</div>
                    ${folderFiles.map(f => `
                        <div class="file-item" style="border:none; padding:4px 0;">
                            <span>📄 ${f.filename}</span>
                            <span style="font-size:11px; color:#94a3b8;">${f.date}</span>
                        </div>
                    `).join("")}
                </div>
            `).join("");
        } catch (err) {
            console.error("Library render error", err);
        }
    }

    refreshBtn.addEventListener("click", loadLibrary);

    // Deep Semantic Search
    async function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;

        searchBtn.disabled = true;
        searchResults.innerHTML = "<p>Searching semantic memory...</p>";

        try {
            const res = await fetch("/search", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ query })
            });
            const data = await res.json();

            if (data.success) {
                const results = data.results || [];
                if (results.length === 0) {
                    searchResults.innerHTML = "<p style='color:#94a3b8;'>No documents matched this semantic query.</p>";
                } else {
                    searchResults.innerHTML = results.map(r => `
                        <div class="result-card">
                            <div class="result-header">
                                <span>📄 ${r.filename}</span>
                                <span class="score-badge">${(r.similarity * 100).toFixed(1)}% match</span>
                            </div>
                            <p style="font-size:13px; margin: 4px 0;">${r.metadata.summary || ""}</p>
                            <div class="tags">
                                <span class="tag">📁 ${r.metadata.suggested_folder || 'General'}</span>
                                ${(r.metadata.tags || []).map(t => `<span class="tag">#${t}</span>`).join("")}
                            </div>
                        </div>
                    `).join("");
                }
            } else {
                searchResults.innerHTML = `<p style="color:#ef4444;">${data.error}</p>`;
            }
        } catch (err) {
            searchResults.innerHTML = `<p style="color:#ef4444;">Search failed: ${err.message}</p>`;
        } finally {
            searchBtn.disabled = false;
        }
    }

    searchBtn.addEventListener("click", performSearch);
    searchInput.addEventListener("keypress", (e) => { if (e.key === "Enter") performSearch(); });

    // Quota Tracker
    async function loadUsage() {
        try {
            const res = await fetch("/usage");
            const json = await res.json();
            if (json.success) {
                const info = json.data;
                const perc = Math.min((info.used / info.limit) * 100, 100);
                document.getElementById("usageText").textContent = `${info.used.toLocaleString()} / ${info.limit.toLocaleString()} Tokens`;
                const bar = document.getElementById("usageBar");
                bar.style.width = `${perc}%`;
                bar.style.background = perc > 85 ? "#ef4444" : (perc > 65 ? "#f59e0b" : "#22c55e");
            }
        } catch (err) {
            console.error("Usage refresh failure", err);
        }
    }

    document.getElementById("clearDataBtn").addEventListener("click", async () => {
        if (!confirm("Permanently wipe your indexed files and semantic embeddings?")) return;
        try {
            const res = await fetch("/clear_data", { method: "POST" });
            const json = await res.json();
            alert(json.message || "Data cleared.");
            loadLibrary();
            loadUsage();
        } catch (e) {
            alert("Error purging data.");
        }
    });

    document.getElementById("feedbackForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = document.getElementById("feedbackText");
        const status = document.getElementById("feedbackStatus");
        try {
            await fetch("/feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: input.value.trim() })
            });
            status.textContent = "✅ Feedback sent.";
            input.value = "";
        } catch (err) {
            status.textContent = "❌ Transmission error.";
        }
        setTimeout(() => { status.textContent = ""; }, 3000);
    });

    // Initial Execution
    loadLibrary();
    loadUsage();
});