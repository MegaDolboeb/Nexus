# Nexus

**Download link (Google Drive):** https://drive.google.com/file/d/1l97_fL38il5rYBIi0n4ZiJOeavChZ7Vf/view?usp=sharing

A fully local and FREE personal research assistant. It watches the sources you give it (RSS,
arXiv), picks out what's actually relevant to your topics, writes summaries with a local neural
network, keeps a growing "memory" of each topic, and honestly flags how well a piece of material
is actually backed up by independent sources.

No cloud: sources are fetched from the internet, but the thinking and analysis is done entirely
by the model running on your own machine, through your own copy of Ollama. Nothing you read or
write ever leaves your computer.

## What it can do

- **Sources.** RSS/Atom and arXiv out of the box; you can add your own by name and link — the
  model gives a quick opinion on whether it looks trustworthy, but the decision is always yours.
- **Topics.** Your own topics with keywords (cheap filtering without the model, before it's even
  called).
- **Credibility by rule, not by the model's mood.** Confirmed / Partially confirmed / Unverified /
  Disputed — the label is decided by actual logic in the code; the model only helps compare
  sources, it doesn't get to just declare something true.
- **Memory.** Similar material gets grouped by meaning (embeddings), with a history of how a topic
  evolved; any topic can be exported as a plain text file.
- **Conductor.** Give it instructions in plain words — it checks them for potential harm first,
  then runs them, and pings Windows when it's done.
- **Priority program.** If you've got something on your PC that needs the GPU more than Nexus does
  (a voice assistant, streaming, whatever), name it in Settings — process name, ports, an optional
  status file — and Nexus will automatically get out of its way, working in short segments with
  pauses in between. Leave it empty and Nexus just runs freely, no waiting on anyone.
- **The panel.** Its own window (not a browser tab), a tray icon, a language switch (Russian/
  English), picking and downloading models straight from Settings, and an activity log so you can
  see exactly what it's been doing.

## Requirements

Windows. That's it, if you grab the ready-made build — it already has its own copy of Ollama
bundled inside, nothing else to install. Download it, unzip it, run `Nexus.exe`.

If you're running it from source instead, you'll also need Python 3.11+ and
[Ollama](https://ollama.com/) installed separately (it runs its own instance, on its own port — it
won't interfere with any other copy of Ollama you might already have).

## Running from source

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m nexus panel
```

Or, after installing, just double-click `Nexus.bat` (no console window).

On first launch Nexus creates `personal/`, `data/`, `logs/` next to itself, and takes its starting
settings/topics/sources from `config/*.example.json`. Change any of it straight from the panel —
Settings, Interests, Sources.

## Building the .exe yourself

```
packaging\build.bat
```

The result lands in `packaging\dist\Nexus\` — not a single file, because Nexus keeps its data
right next to itself, so you need to copy and share that whole folder. To bundle your own copy of
Ollama into the build, run `packaging\fetch_ollama.ps1` first.

---

Quality and speed depend entirely on your own hardware — weak GPU or little memory means slower
and simpler results. There's no cloud fallback option, and there never will be — that's kind of
the whole point of this project.
