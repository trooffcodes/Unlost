/**
 * Admin Dashboard Logic
 */
const AdminApp = (() => {
    
    const DOM = {
        userTable: document.getElementById('userTable'),
        logView: document.getElementById('logView')
    };

    const fetchAdminData = async () => {
        try {
            // Note: HTTP Basic Auth natively requested by browser due to route setup on backend.
            const res = await fetch("/admin/api/data");
            
            if(!res.ok) {
                if(res.status === 401) throw new Error("Unauthorized (Basic Auth required).");
                throw new Error("Failed fetching admin data.");
            }

            const data = await res.json();
            
            renderUsers(data.users || {});
            renderTelemetry(data.telemetry || []);

        } catch (err) {
            console.error("Admin Shield Error:", err);
            DOM.userTable.innerHTML = `<tr><td colspan='3' style="color: var(--danger)">Connection restricted or failed. See console.</td></tr>`;
        }
    };

    const renderUsers = (usersData) => {
        DOM.userTable.innerHTML = Object.entries(usersData).map(([id, u]) => `
            <tr>
                <td><code>${id}</code></td>
                <td><strong>${u.used}</strong> / ${u.custom_limit || 20000}</td>
                <td>
                    <button class="btn btn-sm bg-red" onclick="AdminApp.execAction('${id}', 'reset')">Reset Quota</button>
                    <button class="btn btn-sm bg-blue" onclick="AdminApp.setLimit('${id}')">Set Max Ceiling</button>
                </td>
            </tr>
        `).join("") || "<tr><td colspan='3'>No devices active in backend store.</td></tr>";
    };

    const renderTelemetry = (telemetryData) => {
        DOM.logView.innerHTML = telemetryData.map(t =>
            `[${new Date(t.timestamp * 1000).toLocaleTimeString()}] [ID: ${t.device_id.substring(0,8)}...] <span style="color:var(--text-main)">${t.event.toUpperCase()}</span> ${JSON.stringify(t.details || {})}`
        ).join("\n") || "No telemetry captured during current runtime.";
        
        // Auto-scroll to bottom of logview to simulate real terminal behavior.
        DOM.logView.scrollTop = DOM.logView.scrollHeight;
    };

    // Make functions globally accessible via mapping to the AdminApp namespace.
    window.AdminApp = {
        execAction: async (device_id, action, limit = null) => {
            if (!confirm(`Are you sure you want to execute [${action.toUpperCase()}] on device: ${device_id}?`)) return;
            
            try {
                const res = await fetch("/admin/api/user", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ device_id, action, limit })
                });

                if(res.ok) fetchAdminData();
                else alert(`Action failed. Status: ${res.status}`);

            } catch(e) {
                alert("Network error processing administrative action.");
            }
        },

        setLimit: (id) => {
            const limit = prompt(`Enter new exact token limit for device ${id}:`);
            if (limit && !isNaN(limit)) {
                AdminApp.execAction(id, "set_limit", parseInt(limit));
            }
        }
    };

    // Init Sequence
    fetchAdminData();
    setInterval(fetchAdminData, 8000);

})();