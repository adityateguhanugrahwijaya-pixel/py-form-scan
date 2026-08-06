# Form Scanner — Student Lifestyle & Aspirations Survey


Turns phone photos of your 50 filled-in paper forms into structured data,
the same way exam-scanning machines work: corner markers align/flatten the
photo, checkbox/radio fill is detected automatically, and handwritten
answers are cropped out as clean images.

## How it works

1. **`prepare_template.py`** — one-time step. Adds a white margin + 4
   corner markers to your form and outputs `output/printable_form.pdf`.
   **Print/photocopy this version**, not the original — the markers are
   what make phone-photo alignment reliable.

2. **Students fill in the printed forms** by hand as normal.

3. **Photograph each form**, either:
   - **One at a time from a phone browser** — run `python3 app.py`, then
     open `http://<your-computer's-ip>:5001` on your phone (same wifi), or
     the public HTTPS URL if deployed (see below). Take the photo, tap
     upload, get results instantly.
   - **In bulk** — take all photos with your phone's normal camera app,
     transfer them into one folder, then run:
     ```
     python3 batch_scan.py photos_folder/ --out results.xlsx
     ```

4. **Results**:
   - `results.xlsx` — one row per form: gender, social media time, study
     time, which platforms were checked, and a link to each handwritten
     answer's cropped image.
   - `crops/<form_id>_<field>.png` — cropped image of each handwritten
     answer (name, class, age, "other" specify, career, career reason).
     Open these to transcribe by eye, or feed them into an OCR/handwriting
     model later if you want full text automatically.

## Setup (local, no Docker)

```bash
pip install opencv-contrib-python pymupdf flask pandas openpyxl
python3 app.py
```

## Deploying to a server (with existing Host Nginx)

Runs the Flask app container in Docker on port `5001`, intended to sit behind your server's existing host **Nginx**.

### 1. Build and start the container

```bash
cd form_scanner
docker compose up -d --build
```

### 2. Configure Host Nginx

In your host Nginx configuration (e.g. `/etc/nginx/sites-available/scanner.conf` or `/etc/nginx/conf.d/scanner.conf`):

```nginx
server {
    listen 80;
    server_name scanner.agentkikir.cloud;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
```

Reload host Nginx:
```bash
sudo nginx -t && sudo nginx -s reload
```

And issue/renew your cert on the host with certbot if needed:
```bash
sudo certbot --nginx -d scanner.agentkikir.cloud
```

### Updating the app later

```bash
docker compose up -d --build
```

### Where data lives / logs

- Uploaded photos + cropped answers: `./data/uploads`, `./data/crops` on the host (Docker volumes — survive rebuilds/restarts).
- Logs: `docker compose logs -f app`

## Files

| File | Purpose |
|---|---|
| `template_config.py` | Exact pixel/point coordinates of every field, extracted directly from your PDF |
| `prepare_template.py` | Adds corner markers → printable PDF |
| `scan_form.py` | Core pipeline: align one photo → detect checks → crop answers |
| `batch_scan.py` | Run `scan_form` over a whole folder → one spreadsheet |
| `app.py` + `capture.html` | Phone-browser camera capture → instant scan |
| `Dockerfile` | Container image for `app.py` (served via gunicorn) |
| `docker-compose.yml` | Runs `app` container on port 5001 |

## Photo-taking tips (matters more than anything else)

- All **4 corner markers must be visible** and roughly flat/undistorted.
- Even lighting, no strong shadow across the page.
- Fill checkboxes/circles with a solid dark mark, not a light tick.
- If a scan fails alignment, `batch_scan.py` logs it to
  `results_failures.csv` instead of silently giving wrong data — retake
  those specific photos.

## If your form design changes

The regions in `template_config.py` are specific to
`student_survey_form.pdf`'s exact layout. If you edit the form (move
fields, add/remove questions), you'll need to re-extract coordinates:

```python
import fitz
doc = fitz.open("your_form.pdf")
for d in doc[0].get_drawings():
    print(d["rect"], d.get("type"))
```

and update the `offset(...)` calls in `template_config.py` to match.

