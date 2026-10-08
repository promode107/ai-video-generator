# HelloAlfred · Video Generator

An Azure Functions (Python) pipeline that turns a patient education script into a fully rendered, narrated, animated video.

Given a free-form script or a storyboard, the pipeline:

1. Converts raw text into structured scenes via Azure OpenAI (chat deployment)
2. Synthesizes narration per scene with natural pauses (Azure Speech, SSML)
3. Generates a real animated video clip per scene (Azure OpenAI Sora)
4. Burns on-screen labels and descriptions onto each clip (ffmpeg)
5. Concatenates all scenes into a final MP4 (MoviePy)
6. Saves to `outputs/` locally and optionally uploads to Blob Storage

---

## Project structure

```
video-generator/
├── GenerateVideo/
│   ├── __init__.py          # HTTP-triggered Azure Function — main orchestrator
│   └── function.json        # Binding config
├── shared/
│   ├── script_converter.py  # LLM: raw script → structured scene JSON
│   ├── script_parser.py     # Parses scene JSON into Scene dataclasses
│   ├── tts_client.py        # Azure Speech SSML narration synthesis
│   ├── video_client.py      # Sora video generation + polling
│   ├── video_composer.py    # ffmpeg text overlay + MoviePy clip assembly
│   ├── image_client.py      # Azure OpenAI image generation (fallback)
│   └── blob_uploader.py     # Azure Blob Storage upload
├── scripts/                 # Pre-written script options (pick one to generate)
│   ├── 01_afib_explainer.txt
│   ├── 02_blood_pressure.txt
│   ├── 03_heart_failure.txt
│   ├── 04_diabetes_heart.txt
│   └── 05_heart_medications.txt
├── outputs/                 # Final rendered MP4s land here (created automatically)
├── converted_scripts/       # LLM-converted scene JSON files land here (created automatically)
├── run.ps1                  # PowerShell menu — pick a script and generate
├── host.json                # Functions runtime config
├── local.settings.json.example # Safe configuration template (no secrets)
└── requirements.txt         # Python dependencies
```

---

## Prerequisites

Before running anything, make sure you have these installed:

### 1. Python 3.11
Download from https://www.python.org/downloads/  
During install, check **"Add Python to PATH"**.

Verify:
```powershell
python --version
# Should print: Python 3.11.x
```

### 2. Azure Functions Core Tools v4
Download from https://learn.microsoft.com/azure/azure-functions/functions-run-local  
Choose the **Windows 64-bit** installer.

Verify:
```powershell
func --version
# Should print: 4.x.x
```

### 3. ffmpeg
Download the **essentials build** from https://www.gyan.dev/ffmpeg/builds/  
Extract the zip, then add the `bin/` folder inside it to your system PATH:

1. Extract to e.g. `C:\ffmpeg`
2. Open **Start → Search → "Edit the system environment variables"**
3. Click **Environment Variables**
4. Under **System variables**, select **Path** → **Edit**
5. Click **New** → add `C:\ffmpeg\bin`
6. Click OK on all dialogs
7. **Close and reopen** any PowerShell windows for the change to take effect

Verify:
```powershell
ffmpeg -version
# Should print ffmpeg version info
```

### 4. Cairo native library (for SVG logo rendering)

The pipeline renders the real HelloAlfred logo (`assets/alfredlogo.svg`) onto
the outro card using `cairosvg`. `pip install cairosvg` installs the Python
wrapper, but on Windows it also needs the native Cairo graphics library
(`libcairo-2.dll`), which is **not** installed by pip. Without it, the
pipeline silently falls back to a tiny placeholder text logo instead of the
real artwork.

Pick **one** of these:

**Option A — GTK3 runtime (adds `libcairo-2.dll` to PATH)**
1. Download the installer from the GTK-for-Windows-Runtime-Environment-Installer releases page.
2. Run it, and if offered, check "set up PATH environment variable."
3. **Close and reopen** any PowerShell windows — PATH changes don't apply to already-open shells.
4. Verify:
   ```powershell
   python -c "import cairosvg; print('OK')"
   ```

**Option B — Inkscape (simpler, no DLL PATH issues)**
1. `winget install Inkscape.Inkscape` (or download from inkscape.org).
2. Verify it's on PATH:
   ```powershell
   inkscape --version
   ```
   The pipeline automatically falls back to Inkscape if `cairosvg` fails to import — no code changes needed.

Either option is sufficient. Check `func start` logs for a line like
`build_logo_outro: SVG converted via cairosvg -> ...` or `via Inkscape -> ...`
to confirm which path is active; if you instead see an `ERROR` line about
both failing, the outro will render with placeholder text only.

### 5. Azure resources
You need the following Azure resources set up with deployments ready:

| Resource | Used for |
|----------|----------|
| Azure OpenAI — chat deployment | Converting raw scripts to structured scenes |
| Azure OpenAI — Sora (`sora-2`) deployment | Generating animated video per scene |
| Azure OpenAI — image deployment (`gpt-image-1-mini`) | Fallback image generation |
| Azure Cognitive Services — Speech | Text-to-speech narration |
| Azure Storage account | Internal Functions bookkeeping + optional video upload |

---

## Setup

### Step 1 — Clone or download the project

```powershell
cd C:\your\projects\folder
# Place the video-generator folder here
cd video-generator
```

### Step 2 — Create and activate a virtual environment

```powershell
python -m venv .venv
```

To activate (run this every time you open a new terminal):
```powershell
.venv\Scripts\Activate.ps1
```

> **If you get an execution policy error**, run this first then try again:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
> ```
>
> **If that still fails** (common on managed/corporate machines where Group Policy blocks it):
> ```powershell
> powershell -ExecutionPolicy Bypass -Command ".venv\Scripts\Activate.ps1"
> ```

### Step 3 — Install dependencies

```powershell
pip install -r requirements.txt
```

### Step 4 — Configure your secrets

Copy `local.settings.json.example` to `local.settings.json`, then fill in your Azure values.
See the [Settings reference](#settings-reference) section below for what each key means.

**Never commit `local.settings.json` to source control** — it contains API keys and connection strings. The example file contains placeholders only.

---

## Running locally

You need **two PowerShell windows** open at the same time.

### Window 1 — Start the function host

```powershell
cd C:\your\projects\folder\video-generator
.venv\Scripts\Activate.ps1
func start
```

Wait until you see:
```
Functions:
    GenerateVideo: [POST] http://localhost:7071/api/GenerateVideo
```

Keep this window open. It shows live logs as each scene is processed.

### Window 2 — Pick a script and generate

```powershell
cd C:\your\projects\folder\video-generator
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

> **Note:** We use `powershell -ExecutionPolicy Bypass -File` instead of `.\run.ps1` directly  
> because many corporate machines have Group Policy that blocks unsigned scripts.  
> This command bypasses the restriction for just this one file without changing any system settings.

You will see a numbered menu:
```
  HelloAlfred · Video Generator
  ─────────────────────────────

  Available scripts:

  [1] Afib Explainer
  [2] Blood Pressure
  [3] Heart Failure
  [4] Diabetes Heart
  [5] Heart Medications

  [0] Cancel

  Enter number:
```

Enter a number and press Enter. The pipeline starts immediately.

### What to watch for

In **Window 1** you will see per-scene progress:
```
Processing scene 1: Animated heart with glowing SA node...
Video video_abc123 status: queued
Video video_abc123 status: in_progress (0s elapsed)
Video video_abc123 status: in_progress (65s elapsed)
Video video_abc123 status: completed (130s elapsed)
Scene 1: burning text overlay — 'SA Node'
Processing scene 2: ...
```

**Expected time: 15–25 minutes for a 10-scene script.**  
Each Sora generation takes roughly 65–90 seconds. Scenes are processed one at a time.

When done, Window 2 shows:
```
  Video saved to:
  C:\...\video-generator\outputs\afib_video_abc123.mp4
```

### Preview mode — check scene conversion without generating video

To verify how the LLM splits your script into scenes before committing to a 20-minute render:

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1 -Preview
```

Returns immediately with the scene structure — no Sora or TTS calls are made.

---

## Adding your own script

1. Create a `.txt` file in the `scripts/` folder, e.g. `06_my_topic.txt`
2. Write your content in any of these formats:

**Plain narration** (the LLM figures out the scenes):
```
Your heart has its own electrical system, like a conductor leading an orchestra.

In a healthy heart, the conductor sends a steady beat...
```

**Markdown storyboard table** (more control over visuals):
```
| Scene | Time | Visual | Audio |
|-------|------|--------|-------|
| 1 | 0:00-0:12 | Animated heart with glowing SA node... | Your heart has... |
```

**Both together** — narration block followed by a storyboard table works best.

3. Run `run.ps1` — your new script appears in the menu automatically.

---

## Settings reference

All settings go in `local.settings.json` under the `"Values"` key.

| Key | Purpose |
|-----|---------|
| `FUNCTIONS_WORKER_RUNTIME` | Always `"python"` |
| `AzureWebJobsStorage` | Storage connection string (required by Functions host for internal bookkeeping) |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint for the chat deployment |
| `AZURE_OPENAI_KEY` | Azure OpenAI key for the chat deployment |
| `OPENAI_DEPLOYMENT_NAME` | Chat deployment name (e.g. `chat`) |
| `OPENAI_API_VERSION` | API version (e.g. `2024-02-01`) |
| `SPEECH_KEY` | Azure Speech resource key |
| `SPEECH_REGION` | Azure Speech region (e.g. `eastus`) |
| `SPEECH_VOICE_NAME` | TTS voice name (e.g. `en-US-JennyNeural`) |
| `AZURE_OPENAI_VIDEO_ENDPOINT` | Azure OpenAI endpoint for the Sora deployment |
| `AZURE_OPENAI_VIDEO_KEY` | Azure OpenAI key for the Sora deployment |
| `VIDEO_DEPLOYMENT_NAME` | Sora deployment name (e.g. `sora-2`) |
| `VIDEO_API_VERSION` | Sora API version (e.g. `preview`) |
| `AZURE_OPENAI_IMAGE_ENDPOINT` | Azure OpenAI endpoint for the image deployment |
| `AZURE_OPENAI_IMAGE_KEY` | Azure OpenAI key for the image deployment |
| `IMAGE_DEPLOYMENT_NAME` | Image deployment name (e.g. `gpt-image-1-mini`) |
| `IMAGE_API_VERSION` | Image API version (e.g. `2025-04-01-preview`) |
| `STORAGE_CONNECTION_STRING` | Azure Storage connection string |
| `STORAGE_CONTAINER_OUTPUT` | Blob container name for video uploads (e.g. `video-outputs`) |
| `LOCAL_OUTPUT_DIR` | Full path to the folder where finished MP4s are saved (e.g. `C:\\...\\outputs`) |
| `SCRIPT_JSON_DIR` | Full path to the folder where converted scene JSON files are saved |
| `UPLOAD_TO_BLOB` | `"true"` to also upload the final video to Blob Storage, `"false"` to skip |

> **Note on paths in JSON:** Windows paths in JSON must use double backslashes.  
> Example: `"C:\\Projects\\video-generator\\outputs"`

---

## Narration tuning

If the narration pacing feels off, adjust these constants:

In `shared/tts_client.py`:
```python
SENTENCE_BREAK_MS = 450   # pause after . ! ?  (milliseconds)
COMMA_BREAK_MS    = 200   # pause after ,       (milliseconds)
```

In `GenerateVideo/__init__.py`:
```python
PAUSE_AFTER_NARRATION_SECONDS = 0.6  # gap between narration end and next scene
```

---

## Troubleshooting

### Script execution policy error
```
run.ps1 cannot be loaded. The file is not digitally signed.
```
**Fix:** Use the bypass command instead:
```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

### Missing environment variable
```
KeyError: 'AZURE_OPENAI_VIDEO_ENDPOINT'
```
**Fix:** You edited `local.settings.json` while `func start` was already running. Stop it (Ctrl+C), then restart `func start`. It only reads settings once at startup.

### Script converted into 1 scene
```
Converted script into 1 scenes.
```
**Fix:** The LLM didn't split your script into separate scenes. Run with `-Preview` to inspect the output. Try formatting your script as a storyboard table or adding clearer scene breaks.

### JSON payload error from Azure OpenAI
```
Invalid type for 'messages[1].content': expected a string
```
**Fix:** You called the function manually using `Get-Content -Raw`, which adds PowerShell metadata that corrupts the JSON. Always use `run.ps1` or the exact `[System.IO.File]::ReadAllText(...)` pattern shown in this README.

### 404 on video generation
```
404 Not Found for url: .../openai/v1/videos
```
**Fix:** The `VIDEO_DEPLOYMENT_NAME` in `local.settings.json` doesn't match the exact deployment name in Azure AI Foundry. Check Azure Portal → your OpenAI resource → Deployments tab.

### 400 Bad Request on video generation
```
400 Bad Request — seconds invalid
```
**Fix:** The requested clip duration isn't supported. `SUPPORTED_DURATIONS` in `shared/video_client.py` is set to `[4, 8, 12]` — confirmed working for `sora-2`.

### ffmpeg drawtext error
```
No such filter: '<text fragment>:fontsize=...'
```
**Fix:** The on-screen description text contains a comma that broke the ffmpeg filter chain. The `esc()` function in `shared/video_composer.py` should escape commas with `\,`. Make sure your local copy is up to date.

### Pillow error
```
AttributeError: module 'PIL.Image' has no attribute 'ANTIALIAS'
```
**Fix:** Pillow 10+ removed `ANTIALIAS`. Pin to the required version:
```powershell
pip install Pillow==9.5.0
```

### Logo outro shows tiny placeholder text instead of the real logo
```
OSError: no library called "cairo-2" was found
no library called "libcairo-2.dll" was found
```
**Fix:** `cairosvg` is installed but can't find the native Cairo graphics
library on Windows — this is expected out of the box, `pip install cairosvg`
alone does not provide it. See [Cairo native library](#4-cairo-native-library-for-svg-logo-rendering)
in Prerequisites and install either the GTK3 runtime or Inkscape. Confirm the
fix worked by checking `func start` logs for `SVG converted via cairosvg` or
`SVG converted via Inkscape` — if you instead see an `ERROR` about both
failing, the code caught the exception and silently fell back to plain text,
which is why the video still renders successfully but with the wrong logo.

### AzureWebJobsStorage unhealthy
```
azure.functions.webjobs.storage: Unhealthy
```
**Fix:** The Functions host can't reach the Azure Storage account it uses internally. Check the storage account's Networking → Firewall rules in Azure Portal and add your local IP address.

### Function times out
```
Timeout value of 00:10:00 exceeded
```
**Fix:** `host.json` is set to 35 minutes for local dev — this shouldn't happen locally. If it does, a previous `func start` is still running somewhere and the new one is hitting a conflict. Kill all `func` processes and restart cleanly.

---

## Important notes for production

- **Azure Functions Consumption plan** hard-caps execution at **10 minutes** regardless of `host.json`. A full 10-scene Sora render takes 15–25 minutes, so Consumption plan will not work for production. Use a **Premium or Dedicated plan**.
- **Sora concurrency**: Azure enforces a 2-concurrent-job cap per deployment in preview. Scenes are generated serially — there is no quick win from parallelizing without a quota increase from Microsoft.
- **API keys**: rotate all keys before deploying to any shared or production environment.