# Navesink — Municipal Permitting Assistant

Navesink is a RAG-based (Retrieval-Augmented Generation) permitting assistant
that answers questions about zoning, historic preservation, and municipal
regulations using a town's own official documents.

Currently supported towns:

| Town | Corpus folder | Pinecone index |
|---|---|---|
| Red Bank, NJ | `redbank_corpus/` | `redbank-corpus` |
| Fair Haven, NJ | `fairhaven_corpus/` | `fairhaven-corpus` |

---

## Architecture

```
navesink/
├── config/
│   ├── redbank.json       ← town name, corpus dir, Pinecone index, system prompt
│   └── fairhaven.json
├── redbank_corpus/        ← drop Red Bank PDFs here
├── fairhaven_corpus/      ← drop Fair Haven PDFs here
├── ingest.py              ← ingestion pipeline (--town flag)
├── query.py               ← query CLI (--town flag)
├── requirements.txt
├── .env                   ← your API keys (never committed)
└── .env.example
```

**Adding a new town** requires only two things:
1. Add a `config/<townslug>.json` file
2. Create a `<townslug>_corpus/` folder and drop PDFs into it

---

## What you need before starting

| Requirement | Why |
|---|---|
| Python 3.9 or later | Runs the scripts |
| Tesseract OCR | Reads scanned/image-based PDFs |
| An OpenAI API key | Generates text embeddings |
| A Pinecone API key | Stores and searches the embeddings |
| An Anthropic API key | Powers the answer generation |

---

## Step 1 — Install system tools (one-time)

### Mac
```bash
brew install tesseract
```
> If you don't have Homebrew, install it first at https://brew.sh

### Windows
Download and install **Tesseract** from:
https://github.com/UB-Mannheim/tesseract/wiki

### Linux (Ubuntu/Debian)
```bash
sudo apt install tesseract-ocr
```

---

## Step 2 — Get your API keys

### OpenAI
1. Go to https://platform.openai.com/api-keys
2. Click **Create new secret key**, name it "navesink"
3. Copy the key (starts with `sk-`) — you only see it once

### Pinecone
1. Go to https://app.pinecone.io and create a free account
2. In the left sidebar, click **API Keys** and copy your key

### Anthropic
1. Go to https://console.anthropic.com/settings/keys
2. Click **Create Key**, name it "navesink"
3. Copy the key (starts with `sk-ant-`)

---

## Step 3 — Set up the project

```bash
python3 -m venv venv
source venv/bin/activate       # Mac / Linux
# venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

---

## Step 4 — Add your API keys

```bash
cp .env.example .env
```

Open `.env` and fill in all three keys:

```
OPENAI_API_KEY=sk-...
PINECONE_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

**Never share or commit this file.**

---

## Step 5 — Add PDFs and run ingestion

Drop your PDFs into the appropriate corpus folder, then run:

```bash
# Ingest Red Bank documents (default)
python ingest.py

# Ingest Fair Haven documents
python ingest.py --town fairhaven
```

The script auto-detects document type from the filename:

| Filename contains | Detected type |
|---|---|
| `zoning`, `ordinance` | `zoning` |
| `master_plan`, `masterplan` | `master_plan` |
| `historic`, `preservation`, `hpc` | `historic` |
| `minutes`, `meeting`, `agenda`, `board` | `board_minutes` |
| `fee`, `schedule`, `rate` | `fee_schedule` |
| anything else | `other` |

---

## Step 6 — Run the query assistant

```bash
# Query Red Bank (default)
python query.py

# Query Fair Haven
python query.py --town fairhaven
```

Type your question at the prompt and receive a cited answer drawn from the
town's official documents. Type `quit` to exit.

---

## Adding a new town

1. Create `config/<townslug>.json` (copy `config/redbank.json` as a template):
   ```json
   {
     "town": "Town Name",
     "state": "NJ",
     "corpus_dir": "<townslug>_corpus",
     "pinecone_index": "<townslug>-corpus",
     "system_prompt": "You are a municipal permitting assistant for Town Name, NJ..."
   }
   ```
2. Create the corpus folder: `mkdir <townslug>_corpus`
3. Drop PDFs into it
4. Run `python ingest.py --town <townslug>`
5. Query with `python query.py --town <townslug>`

---

## Re-running ingestion

Run `python ingest.py --town <town>` any time you add new PDFs.
Existing chunks are overwritten (not duplicated) because each chunk has a
unique ID derived from its filename, page number, and position.

---

## Troubleshooting

**`No config found for '<town>'`**
→ Check that `config/<town>.json` exists and the spelling matches.

**`No PDFs found in <corpus>/`**
→ Drop PDFs into the correct corpus folder and re-run.

**`tesseract is not installed or it's not in your PATH`**
→ Re-run Step 1 to install Tesseract.

**`OPENAI_API_KEY ... must be set`**
→ Check that `.env` exists and all three keys are filled in.

**A file shows `[FAILED]` in the summary**
→ The error next to the filename tells you why. Common causes:
   encrypted PDFs (remove password protection first) or corrupted files.
