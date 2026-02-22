/**
 * PlanarAlly Extension Bridge - Modal dialogs via postMessage
 *
 * Use in extensions that run inside ExtensionModal iframe.
 * Replaces native confirm() and prompt() with styled modals in the parent.
 *
 * Usage:
 *   <script src="../../../../static/extensions/ext-bridge.js"></script>
 *   ...
 *   const ok = await parentConfirm('Title', 'Message');
 *   const name = await parentPrompt('Question', 'Title', 'defaultValue');
 */
(function() {
    function getTarget() {
        return (typeof window !== 'undefined' && window.parent !== window) ? window.parent : null;
    }

    function genId() {
        return 'pa-' + Date.now() + '-' + Math.random().toString(36).slice(2);
    }

    window.parentConfirm = function(title, message) {
        var target = getTarget();
        if (!target) return Promise.resolve(confirm(message));
        return new Promise(function(resolve) {
            var id = genId();
            function handler(e) {
                if (e.data && e.data.type === 'planarally-confirm-response' && e.data.id === id) {
                    window.removeEventListener('message', handler);
                    resolve(e.data.result);
                }
            }
            window.addEventListener('message', handler);
            target.postMessage({ type: 'planarally-confirm', id: id, title: title || '', message: message || '' }, '*');
        });
    };

    window.parentPrompt = function(question, title, defaultValue) {
        var target = getTarget();
        if (!target) return Promise.resolve(prompt(question, defaultValue));
        return new Promise(function(resolve) {
            var id = genId();
            function handler(e) {
                if (e.data && e.data.type === 'planarally-prompt-response' && e.data.id === id) {
                    window.removeEventListener('message', handler);
                    resolve(e.data.result);
                }
            }
            window.addEventListener('message', handler);
            target.postMessage({
                type: 'planarally-prompt',
                id: id,
                question: question || '',
                title: title || '',
                defaultValue: defaultValue != null ? String(defaultValue) : ''
            }, '*');
        });
    };

    window.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            var target = getTarget();
            if (target) {
                target.postMessage({ type: 'planarally-close-extension' }, '*');
            }
        }
    });
})();
