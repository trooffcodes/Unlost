const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const dropText = document.getElementById("dropText");

// Clicking the drop zone opens file picker
dropZone.addEventListener("click", () => {
    fileInput.click();
});

// File selected normally
fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
        dropText.textContent = fileInput.files[0].name;
    }
});

// Drag over
dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
});

// Drag leaves
dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
});

// File dropped
dropZone.addEventListener("drop", (e) => {
    e.preventDefault();

    dropZone.classList.remove("dragover");

    if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        dropText.textContent = e.dataTransfer.files[0].name;
    }
});