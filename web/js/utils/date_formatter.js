/**
 * Format date utility
 */
const DateFormatter = {
    /**
     * Format date for Card/Message display
     * Today: hh:mm
     * Yesterday: 昨天 hh:mm
     * This year: mm-dd hh:mm
     * Older: yyyy-mm-dd hh:mm
     */
    formatSmart: (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return '';

        const now = new Date();
        const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const yesterday = new Date(today);
        yesterday.setDate(yesterday.getDate() - 1);

        const dDate = new Date(d.getFullYear(), d.getMonth(), d.getDate());

        const pad = n => n.toString().padStart(2, '0');
        const timeStr = `${pad(d.getHours())}:${pad(d.getMinutes())}`;

        // Today
        if (dDate.getTime() === today.getTime()) {
            return timeStr;
        }

        // Yesterday
        if (dDate.getTime() === yesterday.getTime()) {
            return `昨天 ${timeStr}`;
        }

        // This year
        if (d.getFullYear() === now.getFullYear()) {
            return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${timeStr}`;
        }

        // Older
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${timeStr}`;
    },

    /**
     * Generate ID with date (card_YYYYMMDD_uuid)
     */
    generateId: (prefix) => {
        const now = new Date();
        const y = now.getFullYear();
        const m = (now.getMonth() + 1).toString().padStart(2, '0');
        const d = now.getDate().toString().padStart(2, '0');
        const shortUuid = crypto.randomUUID().split('-')[0];
        return `${prefix}_${y}${m}${d}_${shortUuid}`;
    }
};

window.DateFormatter = DateFormatter;
