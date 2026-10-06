# E2EAIDEV User Guide

This guide covers everyday tasks for business users and knowledge owners in the E2EAIDEV platform.

## Getting Started

### Logging In

1. Open the E2EAIDEV web application in your browser.
2. Click **Sign in** and authenticate via your organization's SSO (Keycloak OIDC).
   - If SSO is not yet configured, use the local account credentials provided by your administrator.
3. On first login you will see the lifecycle navigation: **Plan > Data > Build > Test > Release > Operate > Improve**.

### Your Profile

After login your profile shows your name, email, role, team, and division. Contact your administrator to correct any details.

### Roles

| Role | Can do |
|------|--------|
| Business User | Upload, share, and chat about documents |
| Knowledge Owner | All of the above plus manage folders and sharing |
| AI Engineer | Configure models, prompts, retrieval, run evaluations |
| Evaluator | Review AI answers, label gold sets |
| Admin | Full platform administration |

---

## Document Upload

### Supported Formats

PDF, DOCX, PPTX, XLSX, TXT, MD, HTML, and image files (PNG, JPG, TIFF).

### Uploading a File

1. Navigate to **Data > Documents**.
2. Click **Upload** or drag files into the upload area.
3. Limits: 100 MB per file, 50 files per batch, 20 GB storage per user (defaults; your admin may adjust these).
4. After upload the document is parsed automatically (layout-aware parsing with table extraction, OCR for scanned pages, figure cropping). You will see a status indicator while processing completes.

### Document Versioning

Re-uploading a file with the same name in the same folder creates a new version. The AI always retrieves from the latest version. Citations in older chats still point to the version they quoted.

### Trash and Deletion

- Deleting a document moves it to **trash**. Within 5 minutes it is excluded from AI retrieval.
- You can restore from trash for 30 days.
- After 30 days (or on "delete permanently"), the file, chunks, and embeddings are purged.

---

## Sharing

### How Sharing Works

E2EAIDEV uses a Google-Drive-style sharing model. You can share a document or folder with:

- A specific **user**
- A **team**
- A **role** (e.g., all AI Engineers)
- A **division**
- The **entire organization**

### Sharing a Document

1. Select a document and click **Share**.
2. Choose the recipient (user, team, role, division, or organization).
3. Choose the permission level: **Viewer** or **Editor**.
4. Click **Confirm**.

The recipient receives an in-app notification that a document has been shared with them.

### Sharing a Folder

Sharing a folder grants the chosen permission to all documents inside it, including documents added later (inherited sharing).

### Revoking Access

1. Open the document or folder's sharing panel.
2. Remove the recipient or change their permission level.
3. Access is revoked immediately; the next AI query will no longer use that document.

### Permission Rules

- Permissions are checked **inside** every vector query, not after retrieval. This prevents information leaks.
- Derived content (e.g., cached answers) inherits the strictest permission of its source documents.
- Sensitivity labels (Public / Internal / Confidential / Restricted) can further limit who a document may be shared with.

---

## Chat

### Asking a Question

1. Navigate to **Chat**.
2. Type your question in natural language. Example: *"What is the revenue share in the WhatsApp partnership?"*
3. The AI searches only documents you have access to, retrieves relevant passages, and responds with an answer and **citations**.

### Citations

Every answer includes citations showing:
- The source document name
- Page number and section
- A clickable link to the source passage (highlighted)

When an answer uses a table or figure, the citation shows that table or figure crop.

### Conversation History

- Your chat history is saved and accessible from the sidebar.
- Each conversation tracks the context so follow-up questions work naturally.
- You can start a new conversation at any time.

### Feedback

- Click **thumbs up** or **thumbs down** on any answer.
- Thumbs-down answers can flow into evaluation datasets to improve future releases.

### What the AI Cannot See

- Documents not shared with you are invisible to the AI, even if they exist in the system.
- If your access to a document is revoked, the AI stops using it from the very next query.
- The system never reveals the existence of documents you cannot access (no existence leaks).

---

## PII and Safety Guardrails

- The platform runs prompt-injection detection on every query. Malicious prompts are blocked and logged.
- PII redaction can be enabled by your administrator to protect sensitive data during ingestion.

---

## Bots

If your organization has published bots (e.g., an HR-policy bot):

1. Go to **Chat > Bots** and select the bot you have access to.
2. Each bot has a defined knowledge scope (specific folders or document sets).
3. **Your effective access = bot scope intersected with your personal permissions.** A bot never shows you documents you would not otherwise be able to see.

---

## Getting Help

- Contact your platform administrator for account issues, access requests, or technical problems.
- Check the **Admin & Operator Guide** for operational details.
