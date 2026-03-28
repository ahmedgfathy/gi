# GI — General Intelligence Framework

> An AGI research framework in Python, plus an AI-powered automated photo management system built on top of it.

---

## What This Project Does

This repository contains **two integrated parts**:

### 1. GI Core — AGI Research Framework
A modular Python framework for building, studying, and experimenting with Artificial General Intelligence (AGI) architectures:

- **Memory systems** — working memory (capacity-limited buffer) + FAISS-backed vector memory for semantic retrieval
- **Reasoning engine** — Chain-of-Thought step tracker, priority-based goal stack, symbolic rule engine
- **Agent abstractions** — base agent interface (Observation/Action cycle), LLM agent (LangChain), RL agent (Stable-Baselines3)
- **Perception layer** — unified multi-modal input interface (vision, text, audio)

### 2. Photo Management System — AI Photo Organizer
A fully automated, always-running service that watches a photo folder, deduplicates content, and classifies every image using **CLIP AI** — with no human interaction.

| Step | What Happens |
|---|---|
| **Watch** | Polls `C:\photo\` every 4 seconds for new files |
| **Sort** | Moves images → `Images/`, videos → `Videos/` |
| **Dedup** | SHA-256 hashing removes exact byte-for-byte duplicates across the entire tree |
| **Classify** | OpenAI CLIP (`clip-vit-base-patch32`) categorizes each image into 8 AI-detected labels |

**Classification labels:** People · Animals · Documents · Nature · Food · Vehicles · Architecture · Other

> Processed **25,000+ photos**, removed **457 duplicates**, classified every image automatically.

---

## Project Structure

```
gi/
├── src/
│   ├── core/
│   │   ├── memory.py          # WorkingMemory + VectorMemory (FAISS)
│   │   ├── reasoning.py       # ChainOfThought, GoalStack, RuleEngine
│   │   └── perception.py      # Multi-modal perception interface
│   └── agents/
│       ├── base_agent.py      # Observation/Action base class
│       ├── llm_agent.py       # LangChain-backed LLM agent
│       └── rl_agent.py        # Stable-Baselines3 RL agent
├── photo_service.py           # Unified photo pipeline (dedup + CLIP classify)
├── photo_service.sh           # start / stop / restart / status / log
├── classify_images.py         # Standalone bulk CLIP classifier
├── photo_watcher.py           # Standalone file-mover watcher
├── content_watcher.py         # Standalone CLIP content watcher
├── main.py                    # AGI framework demo (all subsystems)
├── verify.py                  # Package installation verifier
├── requirements.txt           # Full dependency list with annotations
└── pyproject.toml             # PEP 517 build config
```

---

## Technology Stack

### AI / Machine Learning
| Library | Version | Purpose |
|---|---|---|
| **PyTorch** | ≥ 2.2 | Core deep learning backbone |
| **HuggingFace Transformers** | ≥ 5.x | CLIP, LLMs, 100k+ pretrained models |
| **CLIP** (`clip-vit-base-patch32`) | — | Zero-shot image classification |
| **TensorFlow** | ≥ 2.16 | Second DL backend |
| **JAX / Flax** | ≥ 0.4.25 | Functional autodiff + XLA compilation |
| **Stable-Baselines3** | ≥ 2.3 | PPO, SAC, DQN, A2C RL algorithms |
| **Gymnasium** | ≥ 1.0 | OpenAI Gym successor — RL environments |

### NLP & Agents
| Library | Purpose |
|---|---|
| **LangChain** | Chain-of-thought agent orchestration |
| **LangGraph** | Stateful multi-agent graph execution |
| **sentence-transformers** | Semantic text embeddings |
| **spaCy** | Industrial NLP pipeline |
| **tiktoken** | Fast BPE tokenizer (OpenAI) |

### Memory & Search
| Library | Purpose |
|---|---|
| **FAISS** | Facebook AI Similarity Search — vector database |
| **ChromaDB** | Persistent vector store |
| **hnswlib** | Approximate nearest-neighbor search |

### Computer Vision
| Library | Purpose |
|---|---|
| **OpenCV** | Image & video processing |
| **Pillow** | Image I/O and transforms |
| **timm** | Thousands of pretrained vision models |
| **torchvision** | Vision transforms & pretrained models |

### Scientific Computing
- **NumPy**, **SciPy**, **Pandas**, **SymPy**

### Experiment Tracking
- **Weights & Biases**, **TensorBoard**, **MLflow**

### Dev Utilities
- **Pydantic**, **Rich**, **Loguru**, **Python-dotenv**, **einops**, **tqdm**

### Runtime
- **Python 3.12.3** on **WSL2 Ubuntu**
- Works on any Linux / macOS system

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ahmedgfathy/gi.git
cd gi

# 2. Create virtual environment and install all packages
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run the AGI framework demo
python main.py

# 4. Verify all packages installed correctly
python verify.py
```

---

## Photo Service Usage

```bash
# Start the automated photo classifier
bash photo_service.sh start

# Check status
bash photo_service.sh status

# Watch live log
bash photo_service.sh log

# Stop
bash photo_service.sh stop
```

The service auto-detects and processes everything in the watch folder on launch — no manual steps needed.

### Standalone Tools

```bash
# Bulk-classify all images already in Images/ folder
python classify_images.py

# Dry-run: show what would happen without making changes
python classify_images.py --dry-run
```

---

## AGI Framework Demo

```
╭──────────────────────────────────────────────╮
│  GI -- General Intelligence Framework        │
│  Demo: memory + reasoning + agents           │
╰──────────────────────────────────────────────╯

─────────────────── 1. Memory ───────────────────
Working memory (cap=4): ['event_2', 'event_3', 'event_4', 'event_5']
Vector memory size: 5
Top-3 search results: ['fact_2', 'fact_0', 'fact_4']

─────────────────── 2. Reasoning ────────────────
Rule engine fired: ['Go charge immediately!', 'Report success and pick next goal.']

─────────────────── 3. Agent ────────────────────
Observation: modality='text', data='The sky is blue...'
Action: speak(message='I see clear sky.', volume='normal')

All subsystems OK.
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    GI Framework                     │
│                                                     │
│  Perception  →  Memory (working + vector)  →  Reasoning
│       │               │                       │     │
│       └───────── Agent Layer ─────────────────┘     │
│              BaseAgent │ LLMAgent │ RLAgent          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Photo Management Service               │
│                                                     │
│  C:\photo\  (watch dir, polling every 4s)           │
│       │                                             │
│       ▼                                             │
│   Sort (img/vid)  →  SHA-256 Dedup  →  CLIP AI      │
│                                          │          │
│                    Images/People/   ←────┤          │
│                    Images/Animals/       │          │
│                    Images/Documents/ ←───┤          │
│                    Images/Nature/ ...    │          │
│                    Videos/          ←────┘          │
└─────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.11+
- 4 GB RAM minimum (8 GB recommended for CLIP)
- No GPU required — runs fully on CPU
- Linux / WSL2 / macOS

---

## License

MIT

---

## Author

**Ahmed Gomaa** · [ahmedgfathy@gmail.com](mailto:ahmedgfathy@gmail.com)
