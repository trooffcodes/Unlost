const AdminApp = (() => {
    const DOM = {
        tabs: document.querySelectorAll('.admin-tab'),
        sections: document.querySelectorAll('.admin-section'),
        userTable: document.getElementById('userTable'),
        logView: document.getElementById('logView'),
        feedbackContainer: document.getElementById('feedbackContainer'),
        lightbox: document.getElementById('lightbox'),
        lightboxImg: document.getElementById('lightboxImg')
    };

    const setupTabs = () => {
        DOM.tabs.forEach(tab => {
            tab.addEventListener('click', (e) => {
                DOM.tabs.forEach(t => t.classList.remove('active'));
                DOM.sections.forEach(s => s.classList.add('hidden'));
                e.target.classList.add('active');
                document.getElementById(e.target.dataset.target).classList.remove('hidden');
            });
        });
    };

    const fetchAdminData = async () => {
        try {
            const res = await fetch("/admin/api/data");
            if(!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
            const data = await res.json();
            
            renderUsers(data.users || {});
            renderTelemetry(data.telemetry || []);
            renderFeedback(data.feedback || []);

        } catch (err) {
            console.error("Admin Data Error:", err);
            DOM.userTable.innerHTML = `<tr><td colspan='3' style="color: var(--danger)">Connection restricted. See console.</td></tr>`;
        }
    };

    const renderUsers = (usersData) => {
        DOM.userTable.innerHTML = Object.entries(usersData).map(([id, u], i) => {
            const meta = u.metadata || u || {};
            const ip = meta.ip || 'Unknown';
            const os = meta.os || 'Unknown OS';
            const browser = meta.browser || 'Unknown Browser';
            
            return `
                <tr class="main-row">
                    <td>
                        <button class="expand-btn" onclick="AdminApp.toggleRow('user-detail-${i}', this)" title="Show Metadata">▼</button>
                        <code>${id.substring(0,8)}...</code>
                    </td>
                    <td><strong>${u.used}</strong> / ${u.custom_limit || 20000}</td>
                    <td>
                        <button class="btn-sm bg-red" onclick="AdminApp.execAction('${id}', 'reset')">Reset</button>
                        <button class="btn-sm bg-blue" onclick="AdminApp.setLimit('${id}')">Set Limit</button>
                    </td>
                </tr>
                <tr id="user-detail-${i}" class="details-row hidden">
                    <td colspan="3">
                        <div class="details-panel">
                            <div class="details-grid">
                                <div class="meta-item"><span>Device ID:</span> <span>${id} <button class="copy-icon-btn" onclick="AdminApp.copyTxt(this, '${id}')">📋</button></span></div>
                                <div class="meta-item"><span>IP Address:</span> <span>${ip} <button class="copy-icon-btn" onclick="AdminApp.copyTxt(this, '${ip}')">📋</button></span></div>
                                <div class="meta-item"><span>OS:</span> <span>${os}</span></div>
                                <div class="meta-item"><span>Browser:</span> <span>${browser}</span></div>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join("") || "<tr><td colspan='3'>No devices active.</td></tr>";
    };

    const renderTelemetry = (telemetryData) => {
        DOM.logView.innerHTML = telemetryData.map(t =>
            `[${new Date(t.timestamp * 1000).toLocaleTimeString()}] [ID: ${t.device_id.substring(0,8)}...] <span style="color:var(--text-main)">${t.event.toUpperCase()}</span> ${JSON.stringify(t.details || {})}`
        ).join("\n") || "No telemetry captured.";
        DOM.logView.scrollTop = DOM.logView.scrollHeight;
    };

    const renderFeedback = (feedbackData) => {
        DOM.feedbackContainer.innerHTML = feedbackData.map((f, i) => {
            const meta = f.metadata || f || {};
            
            const dateStr = new Date(f.timestamp * 1000).toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            const statusBadge = f.status === 'new' ? `<span class="badge badge-new">NEW</span>` : '';
            
            // Derive mobile status for primary icon
            const userAgent = meta.user_agent || meta.userAgent || f.user_agent || '';
            const isMobile = /Mobi|Android|iPhone|iPad/i.test(userAgent) || meta.device_type === 'mobile';
            const deviceIcon = isMobile ? '📱' : '💻';
            
            const imgHTML = f.image ? `<img src="/admin/feedback/image/${f.image}" class="feedback-thumb" onclick="AdminApp.openLightbox('/admin/feedback/image/${f.image}', event)" loading="lazy" alt="Screenshot">` : '';
            
            return `
                <div class="card feedback-card">
                    <div class="feedback-card-header">
                        <div class="header-left">
                            ${statusBadge}
                            <span class="feedback-date">${dateStr}</span>
                            <span class="device-icon" title="Device Platform">${deviceIcon}</span>
                        </div>
                        <button class="expand-btn" onclick="AdminApp.toggleRow('fb-detail-${i}', this)">[+] Details</button>
                    </div>
                    <div class="feedback-msg">${f.message}</div>
                    ${imgHTML}
                    
                    <div id="fb-detail-${i}" class="details-panel hidden">
                        <div class="details-grid">
                            <div class="meta-item"><span>IP Address:</span> <span>${meta.ip || 'Unknown'} <button class="copy-icon-btn" onclick="AdminApp.copyTxt(this, '${meta.ip}')">📋</button></span></div>
                            <div class="meta-item"><span>OS:</span> <span>${meta.os || 'Unknown OS'}</span></div>
                            <div class="meta-item"><span>Browser:</span> <span>${meta.browser || 'Unknown Browser'}</span></div>
                            <div class="meta-item"><span>Resolution:</span> <span>${meta.resolution || 'N/A'}</span></div>
                            <div class="meta-item"><span>Time on Page:</span> <span>${meta.time_on_page || 'N/A'}</span></div>
                            <div class="meta-item full-width" style="word-break: break-all;"><span>URL:</span> <a href="${meta.current_url || '#'}" target="_blank" style="color:var(--info); text-decoration:underline;">${meta.current_url || 'N/A'}</a></div>
                            <div class="meta-item full-width" style="margin-top: 0.5rem; border-top: 1px dashed var(--border); padding-top: 0.5rem;">
                                <span>Raw User-Agent:</span> 
                                <span style="font-family: monospace; font-size: 0.7rem; color: var(--text-muted);">${userAgent || 'N/A'}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join("") || "<div style='color: var(--text-muted); padding: 1rem;'>No feedback available.</div>";
    };

    window.AdminApp = {
        execAction: async (device_id, action, limit = null) => {
            if (!confirm(`Execute [${action.toUpperCase()}] on device: ${device_id}?`)) return;
            try {
                const res = await fetch("/admin/api/user", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({ device_id, action, limit }) });
                if(res.ok) fetchAdminData();
            } catch(e) { alert("Network error processing administrative action."); }
        },
        setLimit: (id) => {
            const limit = prompt(`Enter new token limit for ${id}:`);
            if (limit && !isNaN(limit)) AdminApp.execAction(id, "set_limit", parseInt(limit));
        },
        openLightbox: (src, e) => {
            e.stopPropagation();
            DOM.lightboxImg.src = src;
            DOM.lightbox.classList.remove('hidden');
        },
        closeLightbox: () => {
            DOM.lightbox.classList.add('hidden');
            setTimeout(() => DOM.lightboxImg.src = "", 300);
        },
        toggleRow: (elementId, btn) => {
            const el = document.getElementById(elementId);
            if(el) {
                const isHidden = el.classList.contains('hidden');
                el.classList.toggle('hidden');
                
                // Flip chevron visually based on context
                if (btn.innerText.includes('▼')) btn.innerText = isHidden ? '▲' : '▼';
                else if (btn.innerText.includes('Details')) btn.innerText = isHidden ? '[-] Hide Details' : '[+] Details';
            }
        },
        copyTxt: (btn, txt) => {
            if(!txt || txt === 'undefined') return;
            navigator.clipboard.writeText(txt);
            const originalHTML = btn.innerHTML;
            btn.innerHTML = '✅';
            setTimeout(() => btn.innerHTML = originalHTML, 1500);
        }
    };

    setupTabs();
    fetchAdminData();
    setInterval(fetchAdminData, 8000);
})();