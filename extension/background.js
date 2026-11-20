// Right-click a selection -> "Check with BrandProof". The text is kept in session storage (cleared when the browser
// closes) until the popup is opened, and nothing is sent anywhere until the person presses Check.
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: "bp-check", title: "Check with BrandProof", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== "bp-check" || !info.selectionText) return;
  await chrome.storage.session.set({ pending: info.selectionText.slice(0, 20000) });
  chrome.action.setBadgeBackgroundColor({ color: "#0E7C7B" });
  chrome.action.setBadgeText({ text: "1" });
});
