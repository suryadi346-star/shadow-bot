# 🤖 ShadowBot

**Unified AI Agent** — menggabungkan arsitektur terbaik dari:
- **[nanobot](https://github.com/HKUDS/nanobot)** — ultra-lightweight agent loop, memory system
- **[Project NOMAD](https://github.com/Crosstalk-Solutions/project-nomad)** — offline knowledge base (RAG)
- **[OpenClaude](https://github.com/Gitlawb/openclaude)** — multi-provider routing (200+ models)

Dioptimasi untuk **Termux di Android** (low-spec, no Docker, no heavy ML).

---

## Features

| Feature | Detail |
|---|---|
| **Agent Loop** | Perceive → Think → Act → Observe (nanobot-style) |
| **Multi-Provider** | Anthropic, OpenAI, Ollama, OpenRouter, DeepSeek, Gemini, Groq, custom |
| **Tool Use** | Web search, bash, read/write file, list dir |
| **Memory** | SQLite + BM25 long-term memory (Termux-safe) |
| **Knowledge Base** | Offline RAG — add files, search local docs |
| **Streaming** | Real-time token streaming |
| **Termux-safe** | No Docker, no heavy ML, pure Python |

---

## Install di Termux

```bash
# 1. Update Termux
pkg update && pkg upgrade -y

# 2. Clone repo
git clone https://github.com/suryadi346-star/shadow-bot.git
cd shadow-bot

# 3. Install (otomatis setup semua)
bash install_termux.sh
```

Atau manual:
```bash
pkg install python git clang make pkg-config libffi openssl
pip install anthropic openai rich prompt_toolkit pydantic click aiohttp aiofiles rank_bm25 sqlite-utils ddgs
pip install -e .
```

---

## Install di Linux/macOS

```bash
git clone https://github.com/suryadi346-star/shadow-bot.git
cd shadow-bot
pip install -e ".[full]"
shadowbot setup
```

---

## Configuration

Config disimpan di `~/.shadowbot/config.json`.

Run wizard: `shadowbot setup`

Atau set via environment variable:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export SHADOWBOT_PROVIDER="anthropic"
shadowbot
```

### Providers yang didukung

| Provider | Base URL | Catatan |
|---|---|---|
| `anthropic` | (native SDK) | Claude models |
| `openai` | https://api.openai.com/v1 | GPT models |
| `ollama` | http://localhost:11434/v1 | Local, no API key |
| `openrouter` | https://openrouter.ai/api/v1 | 200+ models |
| `deepseek` | https://api.deepseek.com/v1 | Murah |
| `gemini` | Google API | Gemini models |
| `groq` | https://api.groq.com/openai/v1 | Fast inference |
| `custom` | URL bebas | OpenAI-compatible apapun |

---

## Usage

```bash
# Start interactive REPL
shadowbot

# Single message
shadowbot agent --message "search for Python tutorials"

# Pilih provider
shadowbot agent --provider ollama --model llama3.1:8b

# Setup wizard
shadowbot setup
```

### Slash Commands

```
/help              — tampilkan help
/provider <name>   — ganti provider
/model <name>      — ganti model
/clear             — clear conversation
/memory            — tampilkan recent memories
/knowledge list    — list knowledge base
/knowledge add <file>     — tambah file ke knowledge base
/knowledge search <query> — cari di knowledge base
/knowledge delete <src>   — hapus dari knowledge base
/config            — tampilkan config aktif
/stats             — tampilkan agent stats
/exit              — keluar
```

---

## Architecture

```
shadowbot/
├── agent/
│   └── loop.py          ← Core agent loop (nanobot-inspired)
├── providers/
│   ├── anthropic_provider.py  ← Native Anthropic SDK
│   └── openai_provider.py     ← OpenAI-compatible (covers 200+ providers)
├── tools/
│   └── __init__.py      ← web_search, bash, read/write file, RAG, memory
├── memory/
│   └── __init__.py      ← SQLite + BM25 long-term memory
├── rag/
│   └── __init__.py      ← Offline knowledge base (NOMAD-inspired)
├── config.py            ← Config management + env var overrides
└── cli.py               ← CLI entry point + REPL
```

---

## Termux Tips

**Battery optimization** — disable untuk Termux agar tidak di-kill:
```
Android Settings → Apps → Termux → Battery → Unrestricted
```

**Keep running** — gunakan `nohup`:
```bash
nohup shadowbot agent --message "monitor my files" &
```

**Ollama di Termux** — install via proot-distro Ubuntu lalu pakai remote:
```json
{
  "provider": "ollama",
  "providers": {
    "ollama": {
      "base_url": "http://localhost:11434/v1",
      "model": "llama3.2:1b"
    }
  }
}
```

---

## License

MIT — bebas fork, modifikasi, redistribute.
# shadow-bot
