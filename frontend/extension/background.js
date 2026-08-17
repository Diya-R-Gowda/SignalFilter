// Tiny service worker — its only job is making the toolbar icon open the side panel
// instead of doing nothing. It does NOT fetch or relay any API calls: the side panel
// page (sidepanel.html) talks to http://localhost:8000 directly, since extension pages
// with host_permissions are exempt from CORS/Same-Origin Policy.
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .then(() => console.log("Signal Filter: side panel opens on toolbar click"))
  .catch((error) => console.error("Signal Filter: failed to set side panel behavior", error));
