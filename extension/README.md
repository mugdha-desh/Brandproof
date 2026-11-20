# BrandProof browser extension (pre-flight check)

Check text against your organisation's BrandProof guidelines and Fact Vault while you are still writing it, without leaving the page.
It uses the same review engine, Claim Ledger, Trust Layer and Intent Lock as the web app: it is a second door into the same server, not a second system.

## Install (Chrome, Edge, Brave)
1. Open `chrome://extensions` and switch on **Developer mode**.
2. Choose **Load unpacked** and select this `extension` folder.
3. Click the BrandProof icon, enter your server address (for example `https://brandproof.example.com`), and sign in.
   The browser asks once for permission to contact that server only.

## Use
- Select text on a page, click the icon, write what the text is for in one line, and press **Check**.
- Or right-click a selection and choose **Check with BrandProof**, then open the popup.
- You see findings with severity, the rule or fact behind them, and verified suggestions you can copy. **Open the full review** continues in BrandProof.

## What it does not do
- It never approves, applies or publishes anything. Approval stays with a person in the web app.
- It keeps no copy of your text. Each check creates a normal asset in BrandProof (titled "Browser check: ...") so it appears in the history and audit log like any other.
- Guideline owners cannot submit content, so the owner role is refused by the server.
- It cannot read Google Docs, Figma or other canvas-based editors. Select-and-check only works on ordinary web text. In those tools, paste the text into the popup.
- Images and PDFs are not checked here; use the web app or the command-line gate.

## Privacy and security
- The sign-in token is held in browser session storage and is cleared when the browser closes. The password is never stored.
- The only network address contacted is the server you enter. The extension asks for no access to other sites.
- Text from the server is shown as plain text, never as markup, and the extension loads no remote code.
- Use https. Plain http is accepted only for `localhost` during development.

## Limits
- Messages are subject to the server's upload rate limit. The popup says so if you hit it.
- Not yet tested on Firefox or Safari. It uses Manifest V3 and `chrome.*` APIs.
- Not published to a web store; it is loaded unpacked for the demo.
