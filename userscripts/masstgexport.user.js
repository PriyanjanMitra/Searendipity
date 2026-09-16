// ==UserScript==
// @name         Searendipity Telegram Stats Exporter
// @namespace    https://github.com/Searendipity/Searendipity
// @version      1.0.0
// @description  Export NationStates mass telegram statistics to JSON for Searendipity report generation
// @author       Searendipity Contributors
// @match        https://www.nationstates.net/*page=tg*
// @match        https://www.nationstates.net/*page=tg/tgid=*
// @grant        none
// ==/UserScript==

(function () {
    'use strict';

    function parseTelegramPage() {
        const urlParams = new URLSearchParams(window.location.search);
        let tgid = 0;
        const tgidParam = urlParams.get('tgid');
        if (tgidParam && !isNaN(parseInt(tgidParam, 10))) {
            tgid = parseInt(tgidParam, 10);
        } else {
            const match = window.location.pathname.match(/tgid=(\d+)/);
            if (match) tgid = parseInt(match[1], 10);
        }

        let category = urlParams.get('tgcategory') || 'Uncategorized';
        const senderNation = document.body.getAttribute('data-nname') || 'Unknown';

        // Extract statistics from the page
        let delivered = 0;
        let readCount = 0;
        let recruitCount = 0;
        const recipients = [];
        const recruits = [];

        // Scrape summary tables / dl / stats elements
        const statBoxes = document.querySelectorAll('.tgstats, .content, .tgreport');
        const textContent = document.body.innerText;

        const sentMatch = textContent.match(/(\d[\d,]*)\s+(?:telegrams?\s+)?delivered/i) || textContent.match(/Delivered:\s*(\d[\d,]*)/i);
        if (sentMatch) delivered = parseInt(sentMatch[1].replace(/,/g, ''), 10);

        const readMatch = textContent.match(/(\d[\d,]*)\s+(?:telegrams?\s+)?read/i) || textContent.match(/Read:\s*(\d[\d,]*)/i);
        if (readMatch) readCount = parseInt(readMatch[1].replace(/,/g, ''), 10);

        const recruitMatch = textContent.match(/(\d[\d,]*)\s+recruits?/i) || textContent.match(/Recruited:\s*(\d[\d,]*)/i);
        if (recruitMatch) recruitCount = parseInt(recruitMatch[1].replace(/,/g, ''), 10);

        // Find recipient and recruit nation links
        document.querySelectorAll('a[href*="nation="]').forEach(link => {
            const href = link.getAttribute('href');
            const match = href.match(/nation=([a-z0-9_\-]+)/i);
            if (match) {
                const nation = match[1].toLowerCase().replace(/ /g, '_');
                const isCTE = link.classList.contains('quiet') || link.parentElement?.innerText.includes('ceased to exist');
                if (link.closest('.recruits, .recruit-list') || link.parentElement?.innerText.toLowerCase().includes('joined')) {
                    if (!recruits.some(r => r.name === nation)) {
                        recruits.push({
                            name: nation,
                            timestamp: Math.floor(Date.now() / 1000),
                            cte: isCTE
                        });
                    }
                } else if (!recipients.includes(nation)) {
                    recipients.push(nation);
                }
            }
        });

        const now = Math.floor(Date.now() / 1000);
        return {
            tgid: tgid,
            type: "template",
            category: category,
            nation: senderNation.toLowerCase().replace(/ /g, '_'),
            createdAt: now - 86400,
            generatedAt: now,
            delivered: delivered || recipients.length || 1,
            readCount: readCount,
            recruitCount: recruitCount || recruits.length,
            recipients: recipients,
            recruits: recruits
        };
    }

    function addExportButton() {
        if (document.getElementById('searendipity-export-btn')) return;

        const btn = document.createElement('button');
        btn.id = 'searendipity-export-btn';
        btn.innerText = '📥 Export JSON (Searendipity)';
        btn.style.position = 'fixed';
        btn.style.bottom = '20px';
        btn.style.right = '20px';
        btn.style.zIndex = '99999';
        btn.style.padding = '12px 20px';
        btn.style.backgroundColor = '#1c71d8';
        btn.style.color = '#ffffff';
        btn.style.border = 'none';
        btn.style.borderRadius = '8px';
        btn.style.fontSize = '14px';
        btn.style.fontWeight = 'bold';
        btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.3)';
        btn.style.cursor = 'pointer';
        btn.style.transition = 'all 0.2s ease-in-out';

        btn.onmouseover = () => { btn.style.transform = 'scale(1.05)'; btn.style.backgroundColor = '#1a5fb4'; };
        btn.onmouseout = () => { btn.style.transform = 'scale(1.0)'; btn.style.backgroundColor = '#1c71d8'; };

        btn.onclick = () => {
            const data = parseTelegramPage();
            const filename = `telegram_${data.category}_${data.tgid}.json`;
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            btn.innerText = '✅ Exported!';
            setTimeout(() => { btn.innerText = '📥 Export JSON (Searendipity)'; }, 2500);
        };

        document.body.appendChild(btn);
    }

    window.addEventListener('load', addExportButton);
    setTimeout(addExportButton, 1000);
})();
