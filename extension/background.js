// Adds the right-click item and opens the panel window with the selected text.
// The text is kept in session storage (cleared when the browser closes) and is sent only to http://127.0.0.1:5000.
const MENU_ID = "skillcompiler-run";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({ id: MENU_ID, title: "Run a skill on this selection", contexts: ["selection"] });
});

chrome.contextMenus.onClicked.addListener(async (info) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) return;
  await chrome.storage.session.set({ selection: info.selectionText });
  chrome.windows.create({ url: chrome.runtime.getURL("panel.html"), type: "popup", width: 460, height: 720 });
});
