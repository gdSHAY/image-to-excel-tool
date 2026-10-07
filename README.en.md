<div align="center">

[简体中文](./README.md) | **English**

<img src="./docs/poster-features.png" width="680" alt="Feature poster: confidence filtering, image correction, visual editing, numeric export">

<h1>Image to Excel Tool</h1>
<b>Windows · CamScanner integration · Visual proofreading · Numeric Excel export</b><br>
Filter low-confidence cells first, then correct them against the image.

![Release](https://img.shields.io/github/v/release/gdSHAY/image-to-excel-tool)
![Stars](https://img.shields.io/github/stars/gdSHAY/image-to-excel-tool)
![Issues](https://img.shields.io/github/issues/gdSHAY/image-to-excel-tool)
![Windows](https://img.shields.io/badge/Windows-10%2F11%20x64-blue)
![Python](https://img.shields.io/badge/Python-3.13-blue)
![License](https://img.shields.io/badge/License-All%20rights%20reserved-lightgrey)
</div>

This local browser application converts photographed tables into Excel with visual proofreading. It uses the official CamScanner CLI for cloud recognition and AI enhancement, and local OCR candidate confidence to prioritize cells for review.

Public source, screenshots and downloads exclude the author's credentials and task history. Identifying names and customer IDs in runtime screenshots have been redacted. The poster is an AI-generated feature illustration; the three screenshots below show the actual running application.

> ⚠️ Cloud recognition and AI enhancement require **your own account** and an internet connection, and may consume provider credits. Local candidate confidence **is not an accuracy percentage**.

## 🎬 Runtime screenshots

<img src="./docs/screenshot-grid.png" width="950" alt="Image overlay and color filters">
<br><sub>Actual interface: cell outlines on the image and color filters for prioritizing review; identifying names are masked.</sub>

<img src="./docs/screenshot-proof.png" width="810" alt="Cell crop editing and automatic save">
<br><sub>Actual interface: inspect the original cell crop, reference local confidence and edit text; clicking outside saves and closes.</sub>

<img src="./docs/screenshot-export.png" width="825" alt="File naming and direct export">
<br><sub>Actual interface: customize the filename and export directly; edits are saved even when some cells remain unconfirmed.</sub>

## 📥 Download and installation

Download `image-to-excel-tool-v1.0.0-win-x64.zip` from [Releases](https://github.com/gdSHAY/image-to-excel-tool/releases/latest), approximately 128 MB.

1. Extract the entire archive into a writable folder and double-click the included workbench EXE.
2. Open **Configuration** in the header and sign in to your own CamScanner account.
3. Select an image, recognize, review and export. Python, Node.js and local OCR models do not need separate installation.

Keep the `runtime/`, `node_modules/` and `web/` directories; do not copy the EXE alone. Closing the browser does not stop the service. Use the launcher's stop button to exit it.

### Run from source

Prepare Windows x64, Python 3.13 and Node.js, then run:

```powershell
git clone https://github.com/gdSHAY/image-to-excel-tool.git
cd image-to-excel-tool
powershell -ExecutionPolicy Bypass -File .\setup.ps1
.\start.cmd
```

The local address is `http://127.0.0.1:8788/`. Compile the Windows launcher using `build-launcher.ps1`.

## ✨ Four core features

| Feature | Benefit |
| --- | --- |
| Confidence scoring and targeted review | Local candidate confidence and consistency checks identify suspicious cells; filter red cells and edit them together |
| Perspective correction and clearer text | Local planar correction, manual corners and contrast enhancement; the official CamScanner service provides an AI filter |
| Edit cells directly on the image | Original/processed-image outlines open cell crop editing; mouse wheel zoom and middle-button pan |
| Custom filenames and numeric Excel cells | Name the output; ordinary integers and decimals are exported as numbers for user-created Excel formulas |

Leading-zero identifiers, long identifiers, text and expressions remain literal strings. The first worksheet contains the recognized table; the second contains the original image. The application does not generate formulas automatically.

## ⚙️ Start in three steps

1. **Configure and recognize**: defaults enable automatic perspective correction, natural enhancement, CamScanner and its AI filter. Image selection displays a thumbnail; completion switches to the processed image and large-image review.
2. **Review by color**: check gray empty cells for omissions, then red low-confidence/inconsistent cells, then yellow unconfirmed cells. Click the same filter again to clear it; next-item navigation follows the active filter. Region selection draws a live purple box with a left drag; right-click or Esc exits selection.
3. **Name and export**: clicking outside the edit dialog saves and closes it. Choose whether saving leaves the status unchanged or marks the cell green. Direct export saves current edits without a separate save click or full confirmation. Green means human-confirmed. Instructions can stay collapsed; history supports expand, open, delete and undo.

## ⚠️ Requirements and limitations

- The verified platform is Windows 10/11 x64. Other operating systems have not been validated.
- CamScanner authorization, credits and service availability are provider-controlled. Public packages contain no shared account.
- Scores come from local RapidOCR / PP-OCRv6 candidates, not official CamScanner cell scores or correctness percentages. Empty cells can have no score.
- The original is retained and processing uses a separate image. Selected images are sent to a provider only when cloud services are invoked. Tasks and authorization are stored locally in `data/`.
- Local correction uses OpenCV planar perspective processing, not curved-page dewarping. Folds, curved paper and difficult handwriting still need review.
- Unreliable image registration may require manual region binding. Check titles, numbers, rows, columns, merges and notes.
- TextIn is optional and requires your own credentials; this documentation does not claim verified live TextIn results.

## 🧱 Technology stack

FastAPI, HTML/JavaScript, OpenCV, RapidOCR / PP-OCRv6, ONNX Runtime, Pillow, openpyxl, the official CamScanner CLI and a Windows .NET/WinForms launcher.

Components: [RapidOCR](https://github.com/RapidAI/RapidOCR), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [CamScanner integration documentation](https://v4.camscanner.com/agent-docs/zh/platforms/for-agents/cli/).

## 🗂 Project layout

```text
app.py              Local API and task workflow
imaging.py          Perspective processing and original-image mapping
assessment.py       Local candidate review and scoring
providers.py        Provider integration and authorization
tables.py           Cell structure and Excel export
web/                Upload, filtering and visual editing UI
launcher/           Windows launcher source
tests/              Offline regressions
docs/               Redacted poster and runtime screenshots
```

## 🔌 REST API

These endpoints are intended for the local interface. Do not expose the service directly to the internet.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET / POST | `/api/jobs` | Task history / image upload |
| GET / PUT / DELETE | `/api/jobs/{id}` | Read / save edits / recoverable removal |
| POST | `/api/jobs/{id}/recognize` | Provider recognition |
| POST | `/api/jobs/{id}/assess` | Local confidence review |
| POST | `/api/jobs/{id}/warp` | Manual corner correction |
| GET | `/api/jobs/{id}/image/{kind}` | Original or processed image |
| GET | `/api/jobs/{id}/excel` | Excel download |
| GET | `/api/auth/status` | Authorization status |
| POST | `/api/auth/login` | Official authorization entry |

## ❓ FAQ

<details><summary>Must every cell be confirmed before export?</summary>
No. Direct export saves current edits. Unconfirmed cells retain their current recognition text and are not automatically confirmed.
</details>

<details><summary>Why can cells have no score, and why can high-score text be wrong?</summary>
Only valid local candidates have reference confidence. Confidence is not accuracy; empty cells, omissions and difficult handwriting still require image inspection.
</details>

<details><summary>Can exported numbers be used in Excel formulas?</summary>
Ordinary numeric values can be used in formulas that you enter or fill down in Excel. Leading-zero identifiers and formula-like recognized strings are not executed.
</details>

## 📄 Responsible use and disclaimer

Process only materials you are authorized to use. Rights to uploaded materials remain with their owners; remove unauthorized test materials within 24 hours. The project is intended for personal learning and research; review recognition results and bear the risks of use. Third-party components and cloud services retain their own terms and licenses. This project is not officially affiliated with its providers.

## 📮 Contact

Use [GitHub Issues](https://github.com/gdSHAY/image-to-excel-tool/issues). Never submit secrets, authorization files, sensitive source images or unredacted task data.

## ⭐ Star history

[View Star History](https://star-history.com/#gdSHAY/image-to-excel-tool&Date).

## 📄 License

No open-source license is currently granted; the author reserves all rights. See [LICENSE](./LICENSE). Third-party dependencies retain their respective licenses.

<div align="center"><sub>The README switches between Chinese and English; the application UI currently remains Chinese.</sub></div>
