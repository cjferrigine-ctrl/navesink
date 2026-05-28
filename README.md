# Navesink — Red Bank Corpus Ingestion Pipeline

This script reads every PDF in `redbank_corpus/`, breaks each document into
searchable chunks, and loads them into a Pinecone vector database so Navesink
can answer permitting questions using Retrieval-Augmented Generation (RAG).

---

## What you need before starting

| Requirement | Why |
|---|---|
| Python 3.9 or later | Runs the script |
| Tesseract OCR | Reads scanned/image-based PDFs |
| Poppler | Converts PDF pages to images for OCR |
| An OpenAI API key | Generates text embeddings |
| A Pinecone API key | Stores and searches the embeddings |

---

## Step 1 — Install system tools (one-time)

### Mac
Open Terminal and run:
```
brew install tesseract poppler
```
> If you don't have Homebrew, install it first at https://brew.sh

### Windows
1. Download and install **Tesseract** from:
   https://github.com/UB-Mannheim/tesseract/wiki
   During install, note the path (usually `C:\Program Files\Tesseract-OCR\`).
2. Download and install **Poppler for Windows** from:
   https://github.com/oschwartz10612/poppler-windows/releases
   Extract it and add the `bin/` folder to your system PATH.

### Linux (Ubuntu/Debian)
```
sudo apt install tesseract-ocr poppler-utils
```

---

## Step 2 — Get your API keys

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Click **Create new secret key**, name it something like "navesink"
3. Copy the key (starts with `sk-`) — you only see it once

### Pinecone
1. Go to https://app.pinecone.io and create a free account
2. In the left sidebar, click **API Keys**
3. Copy your default API key

---

## Step 3 — Set up the project

Open Terminal, navigate to this folder, then run these commands one at a time:

```bash
# Create a Python virtual environment (keeps dependencies tidy)
python3 -m venv venv

# Activate it
source venv/bin/activate          # Mac / Linux
# venv\Scripts\activate           # Windows — use this line instead

# Install all dependencies
pip install -r requirements.txt
```

---

## Step 4 — Add your API keys

```bash
# Copy the example file
cp .env.example .env
```

Now open `.env` in any text editor and replace the placeholder values with
your real keys:

```
OPENAI_API_KEY=sk-...your-real-key...
PINECONE_API_KEY=...your-real-key...
```

Save the file. **Never share or commit this file.**

---

## Step 5 — Add your PDFs

Place all your Red Bank PDF documents inside the `redbank_corpus/` folder.

The script auto-detects the document type from the filename:

| Filename contains | Detected type |
|---|---|
| `zoning`, `ordinance` | `zoning` |
| `master_plan`, `masterplan` | `master_plan` |
| `historic`, `preservation`, `hpc` | `historic` |
| `minutes`, `meeting`, `agenda`, `board` | `board_minutes` |
| `fee`, `schedule`, `rate` | `fee_schedule` |
| anything else | `other` |

**Tip:** Rename files to match (e.g. `redbank_zoning_2023.pdf`) so each
document gets tagged correctly.

---

## Step 6 — Run the pipeline

Make sure your virtual environment is still active (you'll see `(venv)` in
your prompt), then run:

```bash
python ingest.py
```

You'll see live progress for each file:

```
Found 5 PDF(s) in redbank_corpus/
────────────────────────────────────────────────────────────

[1/5] redbank_zoning_2023.pdf  (type: zoning)
  42 page(s) → 318 chunks
  Embeddings done (318)
  Upserted 318 vectors to Pinecone

[2/5] master_plan_2019.pdf  (type: master_plan)
  ...

════════════════════════════════════════════════════════════
INGESTION COMPLETE
════════════════════════════════════════════════════════════
  PDFs processed : 5 / 5
  Chunks created : 1,402
  Pinecone index : redbank-corpus

  All files processed successfully.
```

---

## Re-running the pipeline

You can run `python ingest.py` again any time you add new PDFs.
Existing chunks are overwritten (not duplicated) because each chunk has a
unique ID derived from its filename, page number, and position.

---

## Troubleshooting

**`tesseract is not installed or it's not in your PATH`**
→ Tesseract isn't installed or wasn't added to PATH. Re-run Step 1.

**`Unable to get page count. Is poppler installed and in PATH?`**
→ Poppler isn't installed. Re-run Step 1.

**`OPENAI_API_KEY and PINECONE_API_KEY must be set`**
→ Your `.env` file is missing or the keys are still placeholders. Re-check Step 4.

**`No PDFs found in redbank_corpus/`**
→ Drop your PDFs into the `redbank_corpus/` folder, then re-run.

**A file shows `[FAILED]` in the summary**
→ The error message next to the filename tells you why. Common causes:
   encrypted PDFs (remove password first), or corrupted files.
