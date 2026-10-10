window.UnlostSafety = {
    escapeHTML(value) {
        return String(value ?? '').replace(/[&<>"']/g, char => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        }[char]));
    },
    safeURL(value) {
        try {
            const url = new URL(value);
            return ['https:', 'http:'].includes(url.protocol) ? url.href : '#';
        } catch { return '#'; }
    }
};
