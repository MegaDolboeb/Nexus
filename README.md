# Nexus

A fully local and FREE personal research assistant. It monitors selected sources (RSS, arXiv), selects interesting content related to your topics, generates summaries using a local neural network, stores a growing “memory” of topics, and honestly indicates how well the material is supported by independent sources.

No cloud: sources are read from the internet, but only the model running on your computer via your own Ollama instance processes and analyzes the data. The data never leaves your device.

## What it can do

- **Sources.** RSS/Atom and arXiv out of the box; you can add your own — by name and link;
 the model will briefly assess whether it looks reliable (the decision is always yours).
- **Topics.** Your own topics with keywords (cheap selection without the model, before calling it).
- **Reliability according to the rules, not according to the model’s opinion.** Confirmed / Partially confirmed / Not verified /
  Contested — the code is considered, the model only helps with comparison.
- **Memory.** Similar topics are grouped by meaning (embeddings), with a history of changes; the topic
 can be downloaded as a text file.
- **Conductor.** Instructions are given in ordinary words, with a check for potential harm and a notification to
 Windows when it’s ready.
- **Priority program.**** If there is a program on your computer that is more important than the graphics
card (for example, voice assistant or streaming), specify it in the Settings (name, processes,
  ports, optional status file), and the Nexus will yield to it automatically, working
  segments with pauses in between. Leave the field empty if there is no such program — Nexus
  it will just work freely.
- **The panel.** Own window (not browser), tray icon, interface language (Russian/English),
selection and loading of models directly from the Settings, a log of all actions for transparency.

## Requirements

- Windows, Python 3.11+.
- [Ollama](https://ollama.com ) — separately, it does not manage its own instance of the Nexus
  No one else.

## Installation and launch

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m nexus panel
```

Or, after installation, double‑click `Nexus.bat` (without a console window).

On the first launch, Nexus will create `personal/`, `data/`, `logs/` next to itself and take examples of settings/themes/sources from `config/*.example.json`. Edit anything directly from the panel —
Settings, Interests, Sources.

## Building to .exe

```bash
packaging\build.bat
```

The result is the `packaging\dist\Nexus\` folder (not a single file: Nexus stores data alongside itself; you need to move and distribute the entire folder). Details and limitations are in `packaging/README.md`.



 - Quality and speed depend entirely on your hardware — a weak graphics card/low memory.
  This means slower and simpler; there is no cloud backup option and there never will be (that’s the whole point of the project).
