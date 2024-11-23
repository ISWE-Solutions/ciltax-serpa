console.log("Favicon JS is being executed");
(function () {
    const link = document.querySelector("link[rel~='icon']");
    const faviconPath = '/zra_smart_invoice/static/description/logo.png';
    const timestamp = new Date().getTime(); // Add cache-busting timestamp
    if (!link) {
        const newLink = document.createElement('link');
        newLink.rel = 'icon';
        newLink.href = `${faviconPath}?v=${timestamp}`;
        document.head.appendChild(newLink);
    } else {
        link.href = `${faviconPath}?v=${timestamp}`;
    }
    console.log("Favicon updated to:", link.href);
})();
