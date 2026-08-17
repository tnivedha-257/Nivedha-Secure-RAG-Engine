let token = "";

// ------------------ ADMIN LOGIN ------------------
async function loginAdmin() {
    const username = document.getElementById("adminUser").value;
    const password = document.getElementById("adminPass").value;

    if (!username || !password) {
        alert("Please enter username and password");
        return;
    }

    const formData = new URLSearchParams();
    formData.append("username", username);
    formData.append("password", password);

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {"Content-Type":"application/x-www-form-urlencoded"},
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            token = data.access_token;
            localStorage.setItem("token", token);

            alert("Login Successful");
            document.getElementById("authSection").style.display = "none";
            document.getElementById("adminPanel").style.display = "block";
            loadDocs();
        } else {
            alert(data.detail || "Login Failed");
        }
    } catch (err) {
        console.error(err);
        alert("Login request failed");
    }
}

// ------------------ UPLOAD DOCUMENT ------------------
async function uploadDocument() {
    const fileInput = document.getElementById("fileInput");
    const file = fileInput.files[0];

    if (!file) {
        alert("Please select a file");
        return;
    }

    alert("File is being uploaded and indexed. Please wait ...");

    const formData = new FormData();
    formData.append("file", file);

    try {
        const res = await fetch("/admin/upload-document", {
            headers: {"Authorization": "Bearer " + token},
            method: "POST",
            body: formData
        });

        const data = await res.json();

        if (data.message) {
            alert(data.message);
        } else if (data.error) {
            alert(data.error);
        }

        loadDocs();
    } catch (err) {
        console.error(err);
        alert("Upload failed");
    }
}

// ------------------ OTHER EXISTING FUNCTIONS ------------------
async function loadDocs() {
    try {
        const response = await fetch("/admin/list-documents", {
            headers: {"Authorization": "Bearer " + token}
        });

        if (!response.ok) throw new Error("Failed to fetch documents");

        const data = await response.json();
        const table = document.getElementById("docTable");
        if (!table) return;

        let rows = `<tr><th>Document</th><th>Chunks</th><th>Action</th></tr>`;

        if (data.documents.length === 0) {
            rows += `<tr><td colspan="3">No documents found</td></tr>`;
        } else {
            data.documents.forEach(doc => {
                rows += `<tr>
                    <td><a href="/uploads/${encodeURIComponent(doc.document)}" target="_blank">${doc.document}</a></td>
                    <td>${doc.chunks}</td>
                    <td><button onclick='deleteDocument(${JSON.stringify(doc.document)}, event)'>Delete</button></td>
                </tr>`;
            });
        }

        table.innerHTML = rows;
    } catch (err) {
        console.error(err);
    }
}

async function deleteDocument(name, event) {
    if (!confirm("Delete " + name + " ?")) return;

    try {
        const btn = event.target;
        btn.disabled = true;
        btn.innerText = "Deleting...";

        const params = new URLSearchParams({ filename: name });
        const res = await fetch(`/admin/delete-document?${params.toString()}`, {
            headers: {"Authorization": "Bearer " + token},
            method: "DELETE"
        });

        const data = await res.json();
        alert(data.message || "Deleted successfully");
        await loadDocs();
    } catch (err) {
        console.error(err);
        alert("Error deleting file");
    }
}

async function deleteFolder() {
    const folder = prompt("Enter folder name to delete");
    if (!folder) return;

    await fetch(`/admin/delete-folder?folder=${encodeURIComponent(folder)}`, {
        method: "DELETE",
        headers: {"Authorization": "Bearer " + token}
    });

    loadDocs();
}

async function resetIndex() {
    if (!confirm("Reset entire index?")) return;

    await fetch("/admin/reset-index?confirm=true", {
        headers: {"Authorization": "Bearer " + token},
        method: "DELETE"
    });

    loadDocs();
}