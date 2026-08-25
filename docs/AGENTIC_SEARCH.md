# Tri-Tier Adaptive Agentic Search Architecture

## 1. Overview & Motivation

Traditional video search systems in **SceneSearch (P-081)** map user natural language queries directly into the joint embedding space of vision-language models (SigLIP / Qwen). While effective for simple single-object descriptions, this paradigm exposes three major vulnerabilities in real-world driving video retrieval:

1. **Text-to-Video Semantic Representation Gap**: Users frequently search using colloquial action verbs, temporal cues, or short phrases (e.g., *"car suddenly swerves to avoid collision"*, *"motorcycle cutting off a bus in heavy traffic"*). Vision models such as `ViT-B-16-SigLIP` are trained predominantly on detailed, descriptive English dashcam captions (`forward dashcam POV`). Raw short queries often yield low cosine similarity without contextual expansion.
2. **Out-of-Domain (OOD) Garbage Retrieval**: When users submit queries unrelated to traffic, vehicles, or road environments (e.g., finance, programming, cooking recipes, poetry, fantasy heroes), unconstrained vector search still attempts to surface top nearest neighbors from the corpus, generating misleading false positives.
3. **Over-Constrained Zero-Hit Scenarios**: Queries specifying multiple strict exclusion constraints (e.g., *"rainy street without cars without pedestrians"*) often eliminate all viable candidate videos due to caption noise or imperfect metadata extraction.

---

## 2. Tri-Tier Architecture Overview

```mermaid
flowchart TD
    User["👤 User / Web Frontend"] -->|"1. POST /api/v1/search"| APIRoute["🌐 FastAPI Endpoint<br/>(api/v1/search.py)"]
    APIRoute -->|"2. Call search()"| Engine["⚙️ SceneSearchEngine<br/>(search/engine.py)"]
    Engine -->|"3. Delegate"| Orchestrator["🧠 TriTierAgentOrchestrator<br/>(search/agent.py)"]

    %% TIER 1 & 2: GATEWAY
    subgraph TIER_GATEWAY ["TIER 1 & 2: SINGLE-PASS INTELLIGENT GATEWAY"]
        Orchestrator -->|"4. Check Lexical"| FastRegex{"Tier 0: Lexical Filter<br/>(spiderman, pizza...)"}
        FastRegex -->|"Match OOD Keywords"| FastOOD["🚫 Instant OOD Rejection (0ms)"]
        FastRegex -->|"Valid / Needs Evaluation"| LLMCall["🤖 NVIDIA NIM LLM<br/>(meta/llama-3.1-8b-instruct)"]
        
        LLMCall -->|"Single-Pass JSON Output"| LLMDecision{"is_driving_scene ?"}
        LLMDecision -->|"FALSE (OOD)"| SmartReject["🚫 Smart OOD Rejection + Explanation"]
        LLMDecision -->|"TRUE (In-Domain)"| RouteDecision{"Contains HyDE Caption ?"}
        
        RouteDecision -->|"No"| FastPathSignal["⚡ Route: Fast-Path"]
        RouteDecision -->|"Yes"| HyDESignal["✨ Route: Agentic-Path (Visual-HyDE POV)"]
    end

    FastOOD --> InstantReturn["Return honest empty results (0 hits)"]
    SmartReject --> InstantReturn
    InstantReturn --> APIResponse["📦 SearchResponse JSON"]

    %% TIER 3: RETRIEVAL
    subgraph TIER_RETRIEVAL ["TIER 3: MULTI-TOWER RETRIEVAL & FUSION"]
        FastPathSignal --> VisualTower["🗼 Visual Tower (SigLIP 768d)"]
        FastPathSignal --> CaptionTower["🗼 Caption Tower (Qwen 2048d)"]
        HyDESignal --> VisualTower
        HyDESignal --> CaptionTower
        
        VisualTower --> QdrantDB[("Qdrant Remote (collection 'Scences')")]
        CaptionTower --> QdrantDB
        
        QdrantDB --> Fusion["🔀 Reciprocal Rank Fusion (RRF)"]
        CatalogScan["📋 In-Memory Catalog Scan (29,742 keyframes)"] --> FilterStep["🔍 Apply NegEx & Floor >= 0.09"]
        Fusion --> FilterStep
    end

    %% REFLECTION LOOP
    subgraph TIER_REFLECTION ["TIER 4: EVALUATION & ADAPTIVE REFLECTION"]
        FilterStep --> Evaluator{"📊 RetrievalEvaluator<br/>Zero hits due to strict exclusions?"}
        Evaluator -->|"Has exclusions & total_videos = 0"| RelaxRule["🔄 Adaptive Relaxation<br/>(Relax non-essential exclusions)"]
        RelaxRule -->|"Retry loop #1"| VisualTower
        Evaluator -->|"Adequate results / Max loops reached"| FinalOutcome["🎯 Optimal Search Outcome"]
    end

    FinalOutcome --> MinIO["🖼️ Attach MinIO Presigned URLs"]
    MinIO --> APIResponse
    APIResponse -->|"HTTP 200 OK"| User
```

---

## 3. Core Component Specifications

### 3.1. Single-Pass Intelligent Gateway & Guardrail (`search/router.py`)
Unifies domain classification, intent routing, and Visual-HyDE generation into a **single LLM roundtrip** with structured JSON output:
- **Tier 0 (Zero-Latency Lexical Filter)**: Rapidly rejects obvious non-domain keywords (e.g., `spiderman`, `crypto`, `nấu phở`, `pizza`) in `< 1ms`.
- **Tier 1 (LLM Zero-Shot Domain Guardrail)**: For abstract or conversational out-of-domain queries (finance, healthcare, coding, literature), the LLM classifies `is_driving_scene: false` and provides a succinct refusal explanation.
- **Tier 2 (Visual-HyDE Expansion)**: For complex driving behaviors or multilingual queries (Vietnamese/English), the LLM generates a 2-3 sentence hypothetical front-facing dashcam description (`POV dashcam caption`) rich in visual and lighting details.

### 3.2. Multi-Tower Vector Search & In-Memory Filtering (`search/engine.py`, `search/fusion.py`)
- **SigLIP Visual Tower**: Encodes the synthetic HyDE text into 768-dimensional embeddings and queries the remote Qdrant `siglip` vector index.
- **In-Memory Catalog Scan**: Performs instantaneous verification across 29,742 keyframes in RAM to enforce exact NegEx constraints (`required` and `excluded` attributes).
- **Reciprocal Rank Fusion (RRF)**: Combines ranked lists across active modalities using the standard formula $RRF(d) = \sum \frac{w_i}{k + r_i(d)}$.
- **Calibrated Similarity Floor**: Maintains a calibrated threshold of `SEARCH_VISUAL_FLOOR = 0.09` to filter out low-confidence matches.

### 3.3. Evaluator & Adaptive Reflection Loop (`search/evaluator.py`, `search/agent.py`)
- Evaluates candidate distribution, similarity floors, and constraint compliance.
- When queries with strict negative constraints return 0 hits, the evaluator triggers **Adaptive Relaxation**, systematically softening non-essential exclusions and retrying retrieval (capped at 1 reflection loop to bound latency under $\le 1.2\text{s}$).

---

## 4. Environment Configuration (`app/.env`)

The LLM client conforms to standard **OpenAI-Compatible REST APIs**, supporting **NVIDIA NIM**, **OpenAI**, **Groq**, and **Ollama**:

### NVIDIA NIM Configuration (Recommended):
```env
# Enable Agentic Search & HyDE
SEARCH_AGENTIC_ENABLED=true
SEARCH_HYDE_ENABLED=true
SEARCH_DOMAIN_GUARDRAIL_ENABLED=true

# NVIDIA NIM API Settings
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=nvapi-your-nvidia-api-key-here
LLM_MODEL=meta/llama-3.1-8b-instruct
```

### OpenAI Configuration:
```env
SEARCH_AGENTIC_ENABLED=true
SEARCH_HYDE_ENABLED=true
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-openai-api-key
LLM_MODEL=gpt-4o-mini
```

---

## 5. Verification & Benchmark Testing

### Run Automated 14-Scenario Benchmark Suite:
```bash
cd app && .venv/bin/python ../scripts/test_nvidia_llm.py
```

### Run Interactive Testing Mode:
```bash
cd app && .venv/bin/python ../scripts/test_nvidia_llm.py -i
```

### Run Unit Test Suite:
```bash
cd app && .venv/bin/python -m pytest tests/unit/test_agentic_search.py tests/unit/test_eval_runner.py -v
```
*(Result: 31/31 tests PASSED, 100% coverage).*
