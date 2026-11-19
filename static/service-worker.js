self.addEventListener('push', event => {
    const data = event.data?.json();
    if (!data?.title) return;
    const week = /^\d{4}-\d{2}-\d{2}$/.test(data.week || '') ? data.week : null;
    event.waitUntil(self.registration.showNotification(data.title, {
        body: data.body,
        icon: '/static/icons/table-192.png',
        badge: '/static/icons/table-badge.png',
        tag: week ? `table-${week}` : 'table-test',
        data: {week}
    }));
});

self.addEventListener('notificationclick', event => {
    event.notification.close();
    const week = event.notification.data?.week;
    const url = new URL('/', self.location.origin);
    if (week) {
        url.searchParams.set('week', week);
        url.searchParams.set('notification', '1');
    }
    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({type:'window', includeUncontrolled:true});
        const existing = windows.find(client => new URL(client.url).origin === url.origin);
        if (existing) {
            const navigated = await existing.navigate(url.href);
            if (navigated) return navigated.focus();
        }
        return self.clients.openWindow(url.href);
    })());
});
