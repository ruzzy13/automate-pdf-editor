# Automate PDF Editor

An interactive, in-browser PDF editor for finding and replacing text —
rendered live with [PDF.js](https://mozilla.github.io/pdf.js/) on a Django
backend, built for serverless deployment on [Vercel](https://vercel.com).

Upload a PDF, browse it like a real viewer (thumbnails, zoom, fit-to-width,
text search), edit the text you need to change, and download the result —
all without installing anything or leaving your browser.

🔗 **website link:** [\[PDF Editorzu\]](https://pdf-editorzu.vercel.app/)

## Features

- Interactive PDF viewer with page thumbnails, zoom, fit-to-width, and
  in-document text search
- Find & replace text directly in the browser
- Edits are applied instantly and previewed in place — no page reload
- Download the edited PDF anytime
- No files stored permanently — everything is processed on the fly

## Tech stack

- **Backend:** Django, PyMuPDF
- **Frontend:** PDF.js, vanilla JavaScript, hand-written CSS
- **Deployment:** Vercel

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.