# JARVIS

A J.A.R.V.I.S.-style voice assistant for the macOS desktop, built as a thin Python client over [opencode](https://opencode.ai) serve.

> "Yes, sir."

## Status

[See issues.](https://github.com/adit-prawira/jarvis/issues)

## What it is

JARVIS listens for "hey jarvis" via openWakeWord, transcribes via mlx-whisper, sends the text to a local `opencode serve` (already part of your stack) over HTTP, streams the LLM response via SSE, splits it into sentences, and speaks each through ElevenLabs TTS using a community "JARVIS" voice. A small MCP wrapper exposes system and developer actions.

You can open apps, check the battery, run tests, grep code, switch projects — all hands-free, in a dry British butler persona.

## What it is NOT

- Not multi-user. Single macOS machine, single voice.
- Not cross-platform. macOS only (uses `osascript`, AppleScript, `pmset`).
- Not real-time. ~3-5s first-token latency accepted for the persona.
- Not push-to-talk. Wake word only (push-to-talk deferred).
- Not a product. Personal tool.

## Architecture

```
mic → wake (openWakeWord)
     → STT (mlx-whisper)
     → turn end (silence detector)
     → brain (httpx → opencode serve :4096 → LLM)
     → SSE stream
     → sentence splitter
     → TTS (ElevenLabs streaming)
     → speaker
```

The voice client is thin. The brain, the tools, the session, the LLM — all inherited from `opencode serve`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

## Requirements

- **Hardware:** Apple Silicon Mac (M1/M2/M3/M4). mlx-whisper is Apple Silicon native.
- **OS:** macOS 14+ (Sonoma or later).
- **opencode:** installed and authenticated (`opencode auth list` shows an active provider).
- **Python:** 3.11+.
- **API keys:** `ELEVENLABS_API_KEY` (free tier works for dev). Community "JARVIS" voice ID from [ElevenLabs voice library](https://elevenlabs.io/voice-library).

## Setup

### 1. Clone and install

```bash
git clone https://github.com/adit-prawira/jarvis.git
cd jarvis
uv sync
uv run pre-commit install
```

### 2. Generate a fixed server password

`opencode serve` requires a password for its HTTP API. Since both server and
client run on `127.0.0.1`, a static password is fine — generate it once and
reuse it forever.

```bash
openssl rand -hex 16
# Save the output — you'll need it in the next two steps.
```

### 3. Create `.env`

```bash
cp .env.example .env
# Edit .env:
#   OPENCODE_SERVER_PASSWORD=<the hex string from step 2>
#   ELEVENLABS_API_KEY=<your ElevenLabs API key>
```

### 4. Add the server alias to your shell config

Add this to `~/.zshrc` (or `~/.bashrc`). The password is read from your
`.env` file by `source .env && ...`:

```bash
alias jarvis-server='source ~/Documents/projects/jarvis/.env && opencode serve --port 4096 --hostname 127.0.0.1'
```

Then reload: `source ~/.zshrc`

## Usage

```bash
# Terminal 1: start opencode serve
jarvis-server

# Terminal 2: start JARVIS
cd ~/Documents/projects/jarvis
uv run python main.py
```

Put on headphones. Say "hey jarvis" followed by a command. Try:

- "what time is it"
- "open Spotify"
- "find TODO in monoflow"
- "run the tests in JARVIS"

## Development

This project uses **vertical slicing** — each slice is a thin end-to-end user journey, not a horizontal layer. See the GitHub issues for the breakdown:

- [Phase 0 — Foundation](https://github.com/adit-prawira/jarvis/issues/1) (V1: text-only command)
- [Phase 1 — Voice in](https://github.com/adit-prawira/jarvis/issues/2) (V3: speak → text)
- [Phase 2 — Voice out](https://github.com/adit-prawira/jarvis/issues/3) (V2: type → spoken)
- [Phase 3 — Conversation dynamics](https://github.com/adit-prawira/jarvis/issues/4) (V4–V12: voice loop + refinements)
- [Phase 4 — System actions](https://github.com/adit-prawira/jarvis/issues/5) (V13–V18: apps, volume, battery, time)
- [Phase 5 — Dev actions](https://github.com/adit-prawira/jarvis/issues/6) (V19–V26: file, project, show, find/grep, git, run tests)
- [Phase 6 — Memory & long-term](https://github.com/adit-prawira/jarvis/issues/7) (V27, V28: write notes, read notes)
- [Phase 7 — Production polish](https://github.com/adit-prawira/jarvis/issues/8) (V29–V35: auto-start, update, logging, fallbacks, README)

### Workflow

1. Pick a slice issue from the [issue list](https://github.com/adit-prawira/jarvis/issues)
2. Read the parent phase PRD for context
3. Branch, implement, test, PR
4. Mark the slice issue closed

### Test seam

The `brain` module's interface with `opencode serve` is the primary test seam — mockable with `respx`. Pure functions (sentence splitter, event stream parser) have their own unit tests.

### Code style

`ruff` for linting, `pytest` + `pytest-asyncio` for tests, `respx` for mocking httpx, type hints throughout.

## Planned project structure

```
jarvis/
├── main.py                 # entry point
├── jarvis/
│   ├── brain.py            # opencode HTTP client
│   ├── event_stream.py     # SSE parser
│   ├── sentence_splitter.py
│   ├── ear.py              # mic + wake + STT
│   ├── mouth.py            # TTS
│   ├── ui.py               # Rich terminal panels
│   └── mcp/
│       ├── system_actions/ # apps, volume, battery, time
│       └── dev_actions/    # file, project, show, find/grep, git, run tests
├── jarvis_home/            # opencode project dir
│   ├── AGENTS.md           # persona, refusal patterns
│   ├── notes/              # long-term memory
│   │   ├── user.md
│   │   ├── preferences.md
│   │   └── projects.md
│   └── docs/adr/           # architectural decisions
├── tests/
├── launchd/
│   └── com.user.jarvis.plist
├── scripts/
│   └── update.sh
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── BACKGROUND.md
│   ├── CONTEXT.md          # TBD
│   └── adr/                # TBD
├── requirements.txt
├── .env.example
└── README.md
```

## Troubleshooting

### `opencode serve` won't start

Check `opencode auth list` shows an active provider. The server binds to `127.0.0.1:4096` by default.

### mlx-whisper is slow on first run

The first invocation downloads the model. Subsequent runs use the cache.

### macOS microphone permission denied

System Settings → Privacy & Security → Microphone → enable for your terminal app (Terminal.app, iTerm, Ghostty, etc). Restart JARVIS.

### ElevenLabs quota exhausted

JARVIS falls back to macOS `say` (system TTS). Persona is lost but functionality remains. Upgrade your ElevenLabs plan or wait for quota reset.

### JARVIS isn't responding to "hey jarvis"

- Check mic input is working (System Settings → Sound → Input)
- Try lowering the wake word threshold in `ear.py` (default 0.5)
- Check for false-positive ambient noise

### Slash command auto-compression appears

This was the `@tarquinen/opencode-dcp` plugin — already removed from `~/.config/opencode/opencode.json`. If you see compression prompts, check that file.

## Design decisions

- **Why opencode as the brain, not direct LLM API?** opencode already has tools, sessions, and SSE streaming. JARVIS is a thin voice skin, not a from-scratch agent.
- **Why MCP wrappers instead of letting the LLM call tools directly?** The wrappers enforce the policy boundary — the LLM sees only the tool names we expose; the wrapper filters before execution.

Full context in [docs/BACKGROUND.md](docs/BACKGROUND.md).

## Contributing

This is a personal project. Not accepting contributions. But if you fork it and build something cool, I'd love to hear about it.

## License

Personal use. No license granted.

## Credits

- opencode — the brain, the tools, the session model
- mlx-whisper — Apple Silicon STT
- openWakeWord — wake word detection
- ElevenLabs — TTS with a community "JARVIS" voice
- Iron Man — the aesthetic
