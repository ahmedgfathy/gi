"""
verify.py -- Checks all AGI packages are installed (fast, uses pip list).
Run with:  python verify.py
"""

import subprocess
import sys

# Map: pip package name -> display name
PACKAGES = {
    "torch"                 : "PyTorch",
    "tensorflow"            : "TensorFlow",
    "jax"                   : "JAX",
    "transformers"          : "HuggingFace Transformers",
    "datasets"              : "HuggingFace Datasets",
    "tokenizers"            : "Tokenizers",
    "sentence-transformers" : "Sentence-Transformers",
    "accelerate"            : "Accelerate",
    "peft"                  : "PEFT (LoRA)",
    "trl"                   : "TRL (RLHF)",
    "gymnasium"             : "Gymnasium (RL)",
    "stable_baselines3"     : "Stable-Baselines3",
    "numpy"                 : "NumPy",
    "scipy"                 : "SciPy",
    "pandas"                : "Pandas",
    "sympy"                 : "SymPy",
    "faiss-cpu"             : "FAISS",
    "chromadb"              : "ChromaDB",
    "langchain"             : "LangChain",
    "langgraph"             : "LangGraph",
    "openai"                : "OpenAI SDK",
    "einops"                : "Einops",
    "timm"                  : "TIMM (vision models)",
    "wandb"                 : "Weights & Biases",
    "mlflow"                : "MLflow",
    "tensorboard"           : "TensorBoard",
    "opencv-python"         : "OpenCV",
    "Pillow"                : "Pillow",
    "networkx"              : "NetworkX",
    "matplotlib"            : "Matplotlib",
    "seaborn"               : "Seaborn",
    "plotly"                : "Plotly",
    "tqdm"                  : "tqdm",
    "pydantic"              : "Pydantic",
    "rich"                  : "Rich",
    "loguru"                : "Loguru",
    "python-dotenv"         : "python-dotenv",
    "httpx"                 : "HTTPX",
    "spacy"                 : "spaCy",
    "nltk"                  : "NLTK",
    "tiktoken"              : "tiktoken",
    "flax"                  : "Flax (JAX)",
    "optax"                 : "Optax (JAX)",
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
RESET  = "\033[0m"

# Get installed packages from pip list (fast — no imports needed)
result = subprocess.run(
    [sys.executable, "-m", "pip", "list", "--format=columns"],
    capture_output=True, text=True
)
installed = {}
for line in result.stdout.splitlines()[2:]:   # skip header lines
    parts = line.split()
    if parts:
        installed[parts[0].lower()] = parts[1] if len(parts) > 1 else "?"

ok = failed = 0

print(f"\n{'Package':<35} {'Status'}")
print("-" * 55)

for pkg, label in PACKAGES.items():
    ver = installed.get(pkg.lower())
    if ver:
        print(f"{label:<35} {GREEN}OK  {ver}{RESET}")
        ok += 1
    else:
        print(f"{label:<35} {RED}MISSING{RESET}")
        failed += 1

print("-" * 55)
print(f"\n{GREEN}{ok} installed{RESET}  |  {RED}{failed} missing{RESET}\n")

if failed > 0:
    print(f"{YELLOW}Tip: run  pip install -r requirements.txt{RESET}\n")
    sys.exit(1)
