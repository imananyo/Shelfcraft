# Installing Shelfcraft

Shelfcraft runs on **Windows 10/11, macOS (Intel or Apple Silicon) and Linux**. All local AI
runs on the CPU, so you don't need a GPU or any paid API keys.

| | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Free disk | ~3 GB (no local image model) | ~8 GB (with the local image and text models) |
| Software | Python 3.12 (3.11–3.13 also work), Node.js 20+, FFmpeg, Ollama | the setup scripts can install all of these for you |

Jump to: [macOS](#macos) · [Linux](#linux) · [Windows](#windows) · [Updating](#updating) · [Troubleshooting](#troubleshooting)

---

## macOS

### 1. Install the tools

Install [Homebrew](https://brew.sh) if you don't have it, then open **Terminal** and run:

```bash
brew install git
git clone <your-repo-url> shelfcraft
cd shelfcraft
```

### 2. Run setup

```bash
bash scripts/setup.sh --install-prereqs --pull-ollama-models
```

This command:

* installs Python 3.12, Node.js, FFmpeg and Ollama with Homebrew (`--install-prereqs`),
* creates the Python environment in `backend/.venv` and installs the backend packages,
* installs the web app's packages,
* creates `backend/.env` (every setting in it is optional),
* downloads the local text model `qwen2.5:3b` (~1.9 GB) (`--pull-ollama-models`).

If you already have the tools, skip that flag: `bash scripts/setup.sh`.

### 3. (Optional) local image generation

```bash
bash scripts/install-local-image-model.sh
```

This downloads PyTorch, diffusers and the SD-Turbo model, about 3 GB in total. It works on Intel and
Apple Silicon Macs.

### 4. Start and stop

```bash
bash scripts/start.sh          # dev mode, opens http://127.0.0.1:3000
bash scripts/start.sh --prod   # faster optimized build (first build takes ~1–2 min)
bash scripts/stop.sh
```

The first time you start it, macOS may ask whether Python or Node can accept incoming network
connections. Shelfcraft listens only on `127.0.0.1`, so you can click **Deny** unless you use `--lan`.

---

## Linux

Tested distributions: Ubuntu 24.04+ / Debian 13, Fedora, Arch and openSUSE. The setup script detects
`apt`, `dnf`, `pacman` or `zypper`.

### 1. Get the code

```bash
sudo apt install -y git        # or: sudo dnf install git / sudo pacman -S git
git clone <your-repo-url> shelfcraft
cd shelfcraft
```

### 2. Run setup

```bash
bash scripts/setup.sh --install-prereqs --pull-ollama-models
```

`--install-prereqs` uses `sudo` with your package manager to install Python, Node.js, FFmpeg, build
tools, **espeak-ng** (offline voices for video voiceovers) and the DejaVu fonts. It installs Ollama
with Ollama's official installer.

Some distributions need a little extra:

* **Ubuntu 22.04 / Debian 12:** these ship Python 3.10 and Node 12–18, which are too old.
  * For Python, use 3.12 from the [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa):
    `sudo add-apt-repository ppa:deadsnakes/ppa && sudo apt install python3.12 python3.12-venv python3.12-dev`.
  * For Node 20+, use [nvm](https://github.com/nvm-sh/nvm) or [NodeSource](https://github.com/nodesource/distributions).

  The setup script checks both versions and tells you if either one is too old.
* **Fedora:** the full FFmpeg is in [RPM Fusion](https://rpmfusion.org/Configuration). If RPM Fusion
  isn't enabled, the script falls back to `ffmpeg-free`.

### 3. (Optional) local image generation

```bash
bash scripts/install-local-image-model.sh   # CPU-only PyTorch build + SD-Turbo, ~3 GB
```

### 4. Start and stop

```bash
bash scripts/start.sh          # opens http://127.0.0.1:3000 (xdg-open)
bash scripts/start.sh --prod
bash scripts/stop.sh
```

On a server with no desktop, add `--no-browser` and open `http://127.0.0.1:3000` yourself, for
example through an SSH tunnel: `ssh -L 3000:127.0.0.1:3000 you@server`.

---

## Windows

Open **PowerShell** in the project folder:

```powershell
# one-time setup (installs Python 3.12 / Node / FFmpeg / Ollama / VC++ runtime via winget)
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -InstallPrereqs -PullOllamaModels

# optional: local image generation
powershell -ExecutionPolicy Bypass -File scripts\install-local-image-model.ps1

# start / stop
powershell -ExecutionPolicy Bypass -File scripts\start.ps1 -Prod
powershell -ExecutionPolicy Bypass -File scripts\stop.ps1
```

---

## Script options (all platforms)

| macOS / Linux (`scripts/*.sh`) | Windows (`scripts\*.ps1`) | What it does |
|---|---|---|
| `setup.sh --install-prereqs` | `setup.ps1 -InstallPrereqs` | Install Python, Node, FFmpeg and Ollama |
| `setup.sh --pull-ollama-models` | `setup.ps1 -PullOllamaModels` | Download the local text models |
| `setup.sh --with-local-image-model` | `setup.ps1 -WithLocalImageModel` | Also install local image generation |
| `start.sh --prod` | `start.ps1 -Prod` | Optimized production build |
| `start.sh --lan` | `start.ps1 -Lan` | Let teammates on your Wi-Fi connect (only when team mode is on) |
| `start.sh --api-port 8001 --web-port 3001` | `start.ps1 -ApiPort 8001 -WebPort 3001` | Use other ports |
| `start.sh --no-browser` | `start.ps1 -NoBrowser` | Don't open a browser tab |
| `restore.sh <zip>` | `restore.ps1 -Backup <zip>` | Restore a backup (stop the app first) |

To make a backup on any OS, go to **Settings → Storage & data → Create backup now**. Backups are
saved in `data/backups/`.

Optional demo data, loaded while the app is running:

```bash
backend/.venv/bin/python backend/scripts/seed_demo.py          # macOS / Linux
backend\.venv\Scripts\python.exe backend\scripts\seed_demo.py  # Windows
```

## Running it by hand (any OS)

Use this if the scripts don't suit your setup, for example inside a container or under systemd:

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt            # Windows: .venv\Scripts\pip
.venv/bin/pip install --no-deps rapidocr-onnxruntime
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# second terminal
cd frontend
npm install
SHELFCRAFT_API_ORIGIN=http://127.0.0.1:8000 npm run dev -- -p 3000
```

Then open http://127.0.0.1:3000.

## Updating

```bash
git pull
bash scripts/setup.sh        # Windows: scripts\setup.ps1
```

Database migrations run automatically on the next start. Your data in `data/` is never touched by
updates.

## Moving between computers

A Python environment (`backend/.venv`) only works on the operating system that created it.
`setup.sh` notices a Windows-made `.venv` and rebuilds it. To move your work to a new machine:

1. Create a backup in Settings.
2. Install Shelfcraft on the new machine.
3. Run `restore.sh` (or `restore.ps1`) with the backup ZIP.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Permission denied` when running a script | Run it with `bash scripts/start.sh`, or once run `chmod +x scripts/*.sh` |
| "Python 3.12 not found" | macOS: `brew install python@3.12`. Linux: see the distro notes above |
| "Node.js … is too old" | Install Node 20+ with [nvm](https://github.com/nvm-sh/nvm): `nvm install 22` |
| "No text AI is reachable" | Run `ollama serve` (or open the Ollama app), then `ollama pull qwen2.5:3b`, or add a free key in Settings |
| Video export unavailable | Install FFmpeg (`brew install ffmpeg` / `sudo apt install ffmpeg`) and restart |
| Voiceover fails on Linux | `sudo apt install espeak-ng` (or your distro's `espeak-ng` package) |
| Text in images uses a plain font | Fonts download automatically when online. Offline on Linux, install `fonts-dejavu` or `fonts-liberation` |
| `pip install` fails building a package | Install build tools: `xcode-select --install` (macOS) or `sudo apt install build-essential python3-dev` |
| Port already in use | `bash scripts/stop.sh`, or start with `--api-port` / `--web-port` |
| Logs | `data/logs/api-stderr.log`, `data/logs/backend.log`, `data/logs/web.log` |
