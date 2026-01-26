# Rifai Scholar Downloader

Resumable, idempotent downloader for **openly available** PDFs from a Google Scholar author profile. Default target: [Dr. Abdalla Rifai](https://scholar.google.com/citations?hl=en&user=tOH4TiwAAAAJ) (user id `tOH4TiwAAAAJ`). No paywall bypass; only public PDFs are downloaded.

## Setup

From the project root (or anywhere with this package on `PYTHONPATH`):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Or with pipenv:

```bash
pipenv install -r requirements.txt
pipenv run python -m rifai_scholar_downloader.cli
```

## Usage

- **Basic run** (output under `downloads/abdalla_rifai_publications_open_pdfs/`, ZIP and manifest):

  ```bash
  python -m rifai_scholar_downloader.cli
  ```

- **Custom output directory:**

  ```bash
  python -m rifai_scholar_downloader.cli --outdir /path/to/my_pdfs
  ```

- **Debug mode** (first 5 publications only):

  ```bash
  python -m rifai_scholar_downloader.cli --max-pubs 5 --log-level DEBUG
  ```

- **Resume** (default: on; skips already-downloaded PDFs per manifest):

  ```bash
  python -m rifai_scholar_downloader.cli
  ```

- **Fresh run** (ignore existing manifest; re-download all):

  ```bash
  python -m rifai_scholar_downloader.cli --no-resume
  ```

- **Different author** (by Google Scholar user id):

  ```bash
  python -m rifai_scholar_downloader.cli --user-id <SCHOLAR_USER_ID>
  ```

- **No ZIP:**

  ```bash
  python -m rifai_scholar_downloader.cli --no-zip
  ```

## Output layout

- `outdir/` (default: `downloads/abdalla_rifai_publications_open_pdfs/`)
  - `1988/`, `1994/`, … `unknown/` – PDFs by year
  - `manifest.json` – per-item status, URLs, hashes, timestamps
  - `citations.bib` – BibTeX (best-effort from Scholar)
  - `citations.ris` – RIS (best-effort)
- `outdir.zip` – ZIP of the output folder (default: on)

## Limitations

- **Paywalls**: Only public, open-access PDFs are downloaded. No bypass of paid or institutional access.
- **Google Scholar rate limits / CAPTCHA**: If Scholar blocks or shows a CAPTCHA, the script fails with a clear message. Retry later; do not attempt to circumvent CAPTCHA.
- **Landing-page discovery**: PDF links are taken from Scholar’s `eprint_url` when available, or discovered on the publication landing page (e.g. links containing “pdf”, “full text”). Some sites hide PDFs behind JavaScript or require login; those are not supported.
- **Metadata**: BibTeX and RIS are best-effort from Scholar’s bib fields; quality depends on Scholar’s data.

## Requirements

- Python 3.11+
- `requests`, `beautifulsoup4`, `scholarly` (see `requirements.txt`)
