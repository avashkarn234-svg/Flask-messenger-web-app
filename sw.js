// static/sw.js
self.addEventListener('push', function(event) {
    let title = 'Secure Core Workspace';
    let options = {
        body: 'New secure encrypted payload transmitted via end-to-end node links.',
        icon: '/static/uploads/favicon.ico',
        badge: '/static/uploads/favicon.ico',
        tag: 'e2ee-chat-alert',
        renotify: true,
        data: { url: '/messenger' }
    };

    if (event.data) {
        try {
            const payload = event.data.json();
            if (payload.title) title = payload.title;
            if (payload.body) options.body = payload.body;
        } catch (e) {
            options.body = event.data.text();
        }
    }

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

// Handle clicking on the sliding notification banner
self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes('/messenger') && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow('/messenger');
            }
        })
    );
});
