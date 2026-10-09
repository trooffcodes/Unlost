const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const dropText = document.getElementById("dropText");
const uploadForm = document.getElementById("uploadForm");
const uploadStatus = document.getElementById("uploadStatus");
const uploadBtn = document.getElementById("uploadBtn");

const searchInput = document.getElementById("searchInput");
const searchBtn = document.getElementById("searchBtn");
const searchResults = document.getElementById("searchResults");

// Handling Upload Styles
dropZone.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) dropText.textContent = fileInput.files[0].name;
});
dropZone.addEventListener("dragover", (e) => { e.preventDefault(); dropZone.classList.add("dragover"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("dragover"));
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        dropText.textContent = e.dataTransfer.files[0].name;
    }
});

// Submit Asynchronous Upload
uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (fileInput.files.length === 0) return;

    const formData = new FormData();
    formData.append("file", fileInput.files[0]);

    uploadStatus.innerHTML = "<p>Processing image and generating vector embeddings... (Please wait)</p>";
    uploadBtn.disabled = true;

    try {
        const response = await fetch("/upload", { method: "POST", body: formData });
        const result = await response.json();

        if (result.success) {
            uploadStatus.innerHTML = `
                <div class="success-msg">Success! Processed ${result.filename}</div>
                <pre>${JSON.stringify(result.metadata, null, 2)}</pre>`;
        } else {
            uploadStatus.innerHTML = `<div class="error-msg">Error: ${result.error}</div>`;
        }
    } catch (error) {
        uploadStatus.innerHTML = `<div class="error-msg">Failed: ${error.message}</div>`;
    } finally {
        uploadBtn.disabled = false;
        fileInput.value = "";
        dropText.textContent = "Drag & drop a file here, or click to browse";
    }
});

// Handle Asynchronous AI Search
const performSearch = async () => {
    const query = searchInput.value.trim();
    if (!query) return;

    searchBtn.disabled = true;
    searchResults.innerHTML = "<p>Searching vector space...</p>";

    try {
        const response = await fetch("/search", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ query })
        });
        const result = await response.json();

        if (result.success) {
            if (result.results.length === 0) {
                searchResults.innerHTML = "<p>No matching documents found.</p>";
            } else {
                searchResults.innerHTML = result.results.map(r => `
                    <div class="result-card">
                        <div class="header">
                            <strong>${r.filename}</strong>
                            <span class="score">Score: ${(r.similarity * 100).toFixed(1)}%</span>
                        </div>
                        <p class="summary"><strong>Summary:</strong> ${r.metadata.summary}</p>
                        <div class="tags">${(r.metadata.tags || []).map(t => `<span class="tag">${t}</span>`).join("")}</div>
                    </div>
                `).join("");
            }
        } else {
            searchResults.innerHTML = `<div class="error-msg">Error: ${result.error}</div>`;
        }
    } catch (error) {
        searchResults.innerHTML = `<div class="error-msg">Request failed: ${error.message}</div>`;
    } finally {
        searchBtn.disabled = false;
    }
};

searchBtn.addEventListener("click", performSearch);
searchInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") performSearch();
});