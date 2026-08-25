import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  Cpu,
  Database,
  Layers,
  ShieldCheck,
  Zap,
  ArrowRight,
  Server,
  Code2,
  Workflow,
  Search,
  Network,
  CheckCircle2,
  Terminal,
  Sliders,
  Sparkles,
  AlertCircle,
  ChevronRight
} from 'lucide-react'
import {
  QdrantLogo,
  MinIOLogo,
  QwenLogo,
  SigLIPLogo,
  NvidiaLogo,
  PyTorchLogo,
  PostgresLogo,
  RedisLogo,
  FastAPILogo,
  CeleryLogo,
  ReactLogo,
  DockerLogo,
  ViteLogo,
  TailwindLogo,
  PythonLogo,
  YoloLogo
} from './TechLogos'

// Featured Brand Logos Strip
const FEATURED_BRANDS = [
  { name: 'Google SigLIP', category: 'VISUAL EMBEDDINGS', Logo: SigLIPLogo, border: '#4285F4' },
  { name: 'Alibaba Qwen2-VL', category: 'MULTIMODAL VLM', Logo: QwenLogo, border: '#6366F1' },
  { name: 'Qdrant Vector DB', category: 'HNSW GRAPH ENGINE', Logo: QdrantLogo, border: '#DC2626' },
  { name: 'MinIO S3 Storage', category: 'OBJECT STORAGE', Logo: MinIOLogo, border: '#C72C48' },
  { name: 'NVIDIA NIM & CUDA', category: 'GPU ACCELERATION', Logo: NvidiaLogo, border: '#76B900' },
  { name: 'PyTorch 2.x', category: 'DEEP LEARNING', Logo: PyTorchLogo, border: '#EE4C2C' },
  { name: 'FastAPI Async', category: 'REST API GATEWAY', Logo: FastAPILogo, border: '#059669' },
  { name: 'PostgreSQL 16', category: 'ACID DATABASE', Logo: PostgresLogo, border: '#336791' },
  { name: 'Redis In-Memory', category: 'TASK BROKER & CACHE', Logo: RedisLogo, border: '#DC382D' },
  { name: 'React 19', category: 'FRONTEND SPA', Logo: ReactLogo, border: '#61DAFB' }
]

// Tabs Configuration
const ARCH_TABS = [
  { id: 'system', label: 'SYSTEM ARCHITECTURE', icon: Network, color: '#FF5500' },
  { id: 'techstack', label: 'TECH STACK', icon: Code2, color: '#00D084' },
  { id: 'ingestion', label: 'INGESTION PIPELINE', icon: Workflow, color: '#FFD700' },
  { id: 'retrieval', label: 'RETRIEVAL PIPELINE', icon: Search, color: '#7C3AED' }
]

// Tech Stack Categories with Logos
const TECH_STACK_DATA = [
  {
    category: 'FRONTEND INTERFACE',
    color: '#FF5500',
    icon: Layers,
    items: [
      { name: 'React 19', version: 'v19.0.0', desc: 'Modern reactive UI engine with concurrent rendering and hooks', Logo: ReactLogo },
      { name: 'Vite 6', version: 'v6.4.3', desc: 'Next-generation ES module frontend build tool and dev server', Logo: ViteLogo },
      { name: 'TailwindCSS v4', version: 'v4.3.3', desc: 'High-performance utility-first styling with brutalist theme', Logo: TailwindLogo },
      { name: 'Framer Motion', version: 'v13.0.0', desc: 'Physics-based micro-interactions and smooth layout animations', Logo: Sparkles },
      { name: 'Lucide React', version: 'v1.29.0', desc: 'Lightweight, modern SVG icon library', Logo: Code2 },
      { name: 'Vitest + JSDOM', version: 'v3.2.7', desc: 'Unit and component integration testing suite', Logo: Terminal }
    ]
  },
  {
    category: 'BACKEND & ORCHESTRATION',
    color: '#00D084',
    icon: Server,
    items: [
      { name: 'FastAPI', version: 'v0.115+', desc: 'High-throughput async ASGI framework with OpenAPI autodocs', Logo: FastAPILogo },
      { name: 'Python 3.12', version: 'v3.12.13', desc: 'Modern Python runtime with performance enhancements', Logo: PythonLogo },
      { name: 'Celery', version: 'v5.6.3', desc: 'Distributed asynchronous task queue for heavy video processing', Logo: CeleryLogo },
      { name: 'Redis 7', version: 'v7.4.10', desc: 'In-memory broker for Celery queues and live job status caching', Logo: RedisLogo },
      { name: 'SQLAlchemy 2.0', version: 'v2.0.51', desc: 'Async ORM with type-safe queries and connection pooling', Logo: Database },
      { name: 'Alembic', version: 'v1.19.1', desc: 'Database migration management and schema versioning', Logo: Sliders }
    ]
  },
  {
    category: 'AI / ML & EMBEDDINGS',
    color: '#FFD700',
    icon: Cpu,
    items: [
      { name: 'Google SigLIP', version: 'ViT-B-16', desc: '768-dim visual tower for zero-shot text-to-image similarity', Logo: SigLIPLogo },
      { name: 'Qwen2-VL-7B', version: 'Instruct', desc: '2048-dim dense captioning & cross-encoder reranking', Logo: QwenLogo },
      { name: 'NVIDIA NIM / LLaMA 3.1', version: '8B-Instruct', desc: 'Zero-shot domain guardrail & Visual-HyDE synthetic POV captions', Logo: NvidiaLogo },
      { name: 'PyTorch + OpenCLIP', version: 'v2.13 / v3.3', desc: 'Deep learning inference backend with CUDA & Metal MPS acceleration', Logo: PyTorchLogo },
      { name: 'Ultralytics YOLOv8', version: 'v8.4.126', desc: 'Automated privacy anonymization for faces and license plates', Logo: YoloLogo },
      { name: 'PyAV / FFmpeg', version: 'v17.1.0', desc: 'Native C-level video demuxing, scene boundary & keyframe extraction', Logo: Workflow }
    ]
  },
  {
    category: 'STORAGE & VECTOR DATABASE',
    color: '#7C3AED',
    icon: Database,
    items: [
      { name: 'Qdrant Vector DB', version: 'v1.18.2', desc: 'Distributed vector database with HNSW graph index for sub-10ms queries', Logo: QdrantLogo },
      { name: 'MinIO S3 Storage', version: 'RELEASE.2025', desc: 'Dual-bucket S3 object storage (Restricted Raw vs Public Derived)', Logo: MinIOLogo },
      { name: 'PostgreSQL 16', version: 'v16.14-alpine', desc: 'Relational storage for user authentication, corpus index and job telemetry', Logo: PostgresLogo },
      { name: 'Docker Compose v2', version: 'v2.x', desc: 'Container orchestration with healthchecks and isolated networks', Logo: DockerLogo },
      { name: 'uv Package Tool', version: 'v0.11+', desc: 'Ultra-fast Rust-based Python resolver and virtualenv builder', Logo: Zap },
      { name: 'Pydantic v2', version: 'v2.13.4', desc: 'Strict data validation, serialization and settings management', Logo: ShieldCheck }
    ]
  }
]

// Ingestion Pipeline Vertical Stages Data
const INGESTION_STAGES = [
  {
    stage: '01',
    title: 'RAW ACQUISITION & MULTIPART INGEST',
    subtitle: 'Isolated High-Throughput S3 Staging',
    color: '#C72C48',
    Logo: MinIOLogo,
    tag: 'MINIO RAW',
    latency: '< 100ms / chunk',
    desc: 'Video files are ingested via streaming chunked multipart upload into the isolated `scenesearch-raw` bucket. Generates deterministic SHA-256 fingerprint, persists upload record in PostgreSQL, and queues task to Redis broker.',
    input: 'Raw Video MP4 / MOV / MKV (Up to 4K 60FPS)',
    output: 'Raw S3 URI + Task Ingestion Ticket (UUID)',
    tech: 'MinIO S3 API + FastAPI Async Upload + Redis Task Queue',
    contractSnippet: `{"upload_id": "up_7f9a2", "bucket": "scenesearch-raw", "sha256": "e3b0c4429...", "status": "QUEUED"}`
  },
  {
    stage: '02',
    title: 'SCENE BOUNDARY & KEYFRAME SAMPLING',
    subtitle: 'Optical Flow & Temporal Demuxing',
    color: '#FFD700',
    Logo: Sliders,
    tag: 'PYAV / FFMPEG',
    latency: '450 FPS Throughput',
    desc: 'The Celery worker demuxes the raw video using PyAV native C-bindings. Computes optical flow deltas and histogram variance to identify scene transitions, sampling keyframes at adaptive 0.5 - 2.0 FPS while discarding redundant static frames.',
    input: 'Raw Video Stream from Storage',
    output: 'RGB Keyframe Image Arrays + Microsecond Timestamps',
    tech: 'PyAV v17.1 (FFmpeg 6) + NumPy Vectorized Delta Filter',
    contractSnippet: `{"frame_no": 1267, "timestamp_ms": 42250, "fps_sampled": 1.0, "is_scene_boundary": true}`
  },
  {
    stage: '03',
    title: 'AUTOMATED PRIVACY ANONYMIZATION',
    subtitle: 'Zero-Leakage Gaussian Masking',
    color: '#10B981',
    Logo: YoloLogo,
    tag: 'YOLOV8 + OPENCV',
    latency: '~12ms / Keyframe',
    desc: 'Strict ADR-0003 privacy boundary: Runs YOLOv8 detector to locate human faces and vehicle license plates. Applies kernel Gaussian blur with elliptical masking directly on keyframe pixels before any public persistence.',
    input: 'Raw RGB Keyframes',
    output: 'Anonymized Privacy-Safe Keyframes (Faces & Plates Blurred)',
    tech: 'Ultralytics YOLOv8n + OpenCV 4 Gaussian Filtering',
    contractSnippet: `{"anonymized": true, "faces_masked": 2, "plates_masked": 1, "blur_radius": 15}`
  },
  {
    stage: '04',
    title: 'MULTI-TOWER NEURAL ENCODING',
    subtitle: 'Dual Vision & Dense Caption Embeddings',
    color: '#4285F4',
    Logo: SigLIPLogo,
    tag: 'SIGLIP + QWEN2-VL',
    latency: '64 Frames / Batch',
    desc: 'Keyframes are batched through Google SigLIP (ViT-B-16) to generate 768-dimensional visual vectors. Concurrently, Alibaba Qwen2-VL generates detailed dense captions covering weather, lighting, road dynamics, vehicles, and objects.',
    input: 'Anonymized Keyframe Tensors',
    output: '768-dim Visual Embeddings + 2048-dim VLM Captions & Semantic Tags',
    tech: 'Google SigLIP (OpenCLIP) + Alibaba Qwen2-VL-7B + PyTorch 2.x',
    contractSnippet: `{"siglip_vector": [0.0421, -0.0184, "... 768d"], "caption": "Wet highway at night with traffic lights"}`
  },
  {
    stage: '05',
    title: 'DUAL SYNCHRONIZATION & HNSW VECTOR INDEX',
    subtitle: 'Zero Data Loss Durable Persistence',
    color: '#DC2626',
    Logo: QdrantLogo,
    tag: 'QDRANT + MINIO DERIVED',
    latency: '< 5ms Upsert',
    desc: 'Publishes derivative anonymized JPEG keyframes to `scenesearch-derived` MinIO bucket. Upserts normalized dense vectors with full metadata payloads (tags, weather, timestamps, video hash) into Qdrant distributed HNSW collection.',
    input: 'Vectors + Metadata Payload + Anonymized JPEG Images',
    output: 'Durable Searchable Qdrant Points + Public Presigned Keyframe URLs',
    tech: 'Qdrant gRPC Client + MinIO Derived Bucket + PostgreSQL Status Complete',
    contractSnippet: `{"qdrant_point_id": "pt_88204", "collection": "Scences", "status": "INDEXED", "presigned_ttl": 3600}`
  }
]

// Retrieval Pipeline Vertical Tiers Data
const RETRIEVAL_TIERS = [
  {
    tier: 'TIER 0 & 1',
    title: 'SINGLE-PASS GATEWAY & DOMAIN GUARDRAIL',
    subtitle: 'Zero-Latency Lexical Filter + LLM Domain Classifier',
    color: '#76B900',
    Logo: NvidiaLogo,
    badge: '< 5ms DECISION',
    desc: 'Every search query first passes through a zero-latency lexical regex filter (< 1ms). For ambiguous or abstract queries, the NVIDIA NIM LLaMA-3.1 LLM evaluates domain relevance. Queries unrelated to traffic, vehicles, or road environments are rejected instantly with an honest, informative explanation.',
    decisionTitle: 'Domain Intent Validation',
    branchTrue: 'Passes to Tier 2 for Visual-HyDE Expansion',
    branchFalse: 'Instant honest rejection (0 hits returned, no wasteful vector compute)',
    tech: 'Fast Regex Filter + NVIDIA NIM (meta/llama-3.1-8b-instruct)',
    snippet: `{"is_driving_scene": true, "confidence": 0.99, "route": "agentic_hyde"}`
  },
  {
    tier: 'TIER 2',
    title: 'VISUAL-HyDE SYNTHETIC POV EXPANSION',
    subtitle: 'Colloquial to Multi-Modal Prompt Synthesis',
    color: '#4285F4',
    Logo: SigLIPLogo,
    badge: 'POV SYNTHESIS',
    desc: 'Translates colloquial phrases, action verbs, and multilingual queries (Tiếng Việt / English) into a rich 2-3 sentence synthetic dashcam POV description. Expands atmospheric details (e.g. "wet asphalt reflections", "overcast sunset", "dusk headlights") to maximize cosine overlap with SigLIP visual weights.',
    decisionTitle: 'Hypothetical Dashcam Generation',
    branchTrue: 'Synthesizes high-fidelity POV caption (e.g. "Forward dashcam view on wet asphalt road...")',
    branchFalse: 'Direct fast-path for exact attribute matching',
    tech: 'NVIDIA NIM LLM + Zero-shot Prompt Engineering',
    snippet: `{"hyde_caption": "Forward dashcam POV driving along rainy highway at night with wet asphalt reflections..."}`
  },
  {
    tier: 'TIER 3',
    title: 'MULTI-TOWER VECTOR RETRIEVAL & RRF FUSION',
    subtitle: 'Visual Dot-Product + Dense Caption + In-Memory NegEx',
    color: '#DC2626',
    Logo: QdrantLogo,
    badge: 'SUB-10MS RETRIEVAL',
    desc: 'Queries execute in parallel across SigLIP 768d and Qwen 2048d vector indexes in Qdrant. Performs instantaneous in-memory filtering across 29,742 keyframe catalogs in RAM to enforce exact NegEx constraints (e.g. "without pedestrians"). Results are unified using Reciprocal Rank Fusion with a calibrated visual floor (θ = 0.09).',
    formula: 'Score(d) = Σ [ w_i / (60 + rank_i(d)) ]  ∀ modality i ∈ {Visual_SigLIP, Caption_Qwen, BM25}',
    tech: 'Qdrant HNSW Graph + Reciprocal Rank Fusion (RRF) + RAM Catalog Scan',
    snippet: `{"scores": {"siglip": 0.342, "qwen": 0.418, "rrf": 0.0162}, "floor_passed": true, "negex_passed": true}`
  },
  {
    tier: 'TIER 4',
    title: 'ADAPTIVE REFLECTION & CROSS-ENCODER RERANKER',
    subtitle: 'Dynamic Constraint Relaxation & VLM Reranking',
    color: '#6366F1',
    Logo: QwenLogo,
    badge: 'CROSS-ENCODER',
    desc: 'If an over-constrained query yields 0 hits due to strict exclusions, the Adaptive Evaluator softens non-essential constraints and retries retrieval (capped at 1 reflection loop, <= 1.2s latency). Top candidate frames are reranked via Qwen2-VL multimodal cross-encoder for peak relevance.',
    decisionTitle: 'Over-Constrained Zero-Hit Check',
    branchTrue: 'Triggers Adaptive Relaxation (Softens exclusions & retries once)',
    branchFalse: 'Passes top-K candidate frames to Qwen2-VL Cross-Encoder Reranker',
    tech: 'RetrievalEvaluator Agent + Qwen2-VL Cross-Encoder Reranker',
    snippet: `{"rerank_score": 0.962, "reflection_loops": 0, "final_rank": 1}`
  }
]

export function ArchitectureSection() {
  const [activeTab, setActiveTab] = useState('system')
  const [selectedIngestIndex, setSelectedIngestIndex] = useState(0)
  const [selectedRetrievalIndex, setSelectedRetrievalIndex] = useState(0)

  const activeIngestStage = INGESTION_STAGES[selectedIngestIndex]
  const activeRetrievalTier = RETRIEVAL_TIERS[selectedRetrievalIndex]

  return (
    <section
      id="architecture-section"
      className="max-w-[1700px] mx-auto px-4 sm:px-8 py-20 border-t-3 border-black space-y-10"
    >
      {/* Section Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-6 font-mono">
        <div className="space-y-1">
          <span className="px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
            [SECTION // SYSTEM ARCHITECTURE & DESIGN]
          </span>
          <h2 className="text-3xl sm:text-5xl font-black uppercase tracking-tight text-black dark:text-white">
            ARCHITECTURE & TECHNOLOGY
          </h2>
          <p className="text-xs text-stone-600 dark:text-stone-400 max-w-2xl font-sans font-medium">
            Explore SceneSearch’s end-to-end distributed infrastructure, multi-tower neural pipelines, and high-throughput retrieval stack.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
          {ARCH_TABS.map((tab) => {
            const Icon = tab.icon
            const isActive = activeTab === tab.id
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-3.5 py-2 border-2 font-black uppercase transition-all flex items-center gap-2 cursor-pointer ${
                  isActive
                    ? 'bg-black text-white border-black shadow-[3px_3px_0px_0px_#000] dark:shadow-[3px_3px_0px_0px_#fff]'
                    : 'bg-white dark:bg-[#1C1A17] text-black dark:text-white border-black hover:bg-black hover:text-white hover:border-black'
                }`}
                style={isActive ? { borderBottomColor: tab.color } : {}}
              >
                <Icon className="w-3.5 h-3.5" style={{ color: isActive ? tab.color : 'inherit' }} />
                <span>{tab.label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Featured Technology Logos Strip */}
      <div className="p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono">
        <div className="flex items-center justify-between pb-3 border-b border-black/15 text-[10px] font-black uppercase text-stone-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-[#00D084] animate-pulse" />
            <span>INTEGRATED NEURAL STACK & CORE INFRASTRUCTURE</span>
          </div>
          <span className="hidden sm:inline">10 CORE PLATFORMS</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 pt-3">
          {FEATURED_BRANDS.map((item) => {
            const Logo = item.Logo
            return (
              <div
                key={item.name}
                className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black flex items-center gap-2.5 hover:-translate-y-0.5 hover:shadow-[3px_3px_0px_0px_#000] transition-all group"
              >
                <div className="w-8 h-8 rounded shrink-0 flex items-center justify-center p-1 bg-white dark:bg-black border border-black shadow-sm group-hover:scale-105 transition-transform">
                  <Logo className="w-6 h-6" />
                </div>
                <div className="overflow-hidden">
                  <p className="font-black text-xs text-black dark:text-white truncate">
                    {item.name}
                  </p>
                  <p className="text-[9px] text-stone-500 uppercase font-bold truncate">
                    {item.category}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Tab Contents */}
      <AnimatePresence mode="wait">
        {/* ========================================================================= */}
        {/* TAB 1: SYSTEM ARCHITECTURE */}
        {/* ========================================================================= */}
        {activeTab === 'system' && (
          <motion.div
            key="system"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="space-y-8 font-mono"
          >
            {/* Top Interactive Diagram Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
              {/* Layer 1: Client & Ingestion Gateway */}
              <div className="lg:col-span-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 flex flex-col justify-between space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b-2 border-black">
                    <span className="text-[10px] font-black uppercase text-stone-500">LAYER 01 // CLIENT & GATEWAY</span>
                    <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[9px] font-black uppercase border border-black">
                      HTTP / WS
                    </span>
                  </div>

                  <div className="space-y-3">
                    <div className="p-3.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <ReactLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">REACT 19 SPA (VITE)</span>
                        </div>
                        <span className="text-[10px] text-[#00D084] font-bold">PORT 5173</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        Zero-shot search interface, real-time keyframe inspection tray, video dropzone, and admin dashboard.
                      </p>
                    </div>

                    <div className="flex justify-center text-stone-400 dark:text-stone-500">
                      <ArrowRight className="w-5 h-5 rotate-90" />
                    </div>

                    <div className="p-3.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <FastAPILogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">FASTAPI ASYNC GATEWAY</span>
                        </div>
                        <span className="text-[10px] text-[#FF5500] font-bold">PORT 8000</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        JWT Authentication, rate limiting, request validation via Pydantic v2, and async endpoints.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-black text-white text-[11px] font-sans flex items-center gap-2 border border-black">
                  <ShieldCheck className="w-4 h-4 text-[#00D084] shrink-0" />
                  <span>Strict JWT Role-Based Access Control (Admin / Engineer)</span>
                </div>
              </div>

              {/* Layer 2: Async Processing & Workers */}
              <div className="lg:col-span-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 flex flex-col justify-between space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b-2 border-black">
                    <span className="text-[10px] font-black uppercase text-stone-500">LAYER 02 // ASYNC PROCESSING</span>
                    <span className="px-2 py-0.5 bg-[#FFD700] text-black text-[9px] font-black uppercase border border-black">
                      CELERY + REDIS
                    </span>
                  </div>

                  <div className="space-y-3">
                    <div className="p-3.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <RedisLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">REDIS 7 BROKER</span>
                        </div>
                        <span className="text-[10px] text-[#FFD700] font-bold">PORT 6379</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        Task queue message distribution, live job progress pub/sub, and ephemeral search cache.
                      </p>
                    </div>

                    <div className="flex justify-center text-stone-400 dark:text-stone-500">
                      <ArrowRight className="w-5 h-5 rotate-90" />
                    </div>

                    <div className="p-3.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <CeleryLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">CELERY WORKER DAEMON</span>
                        </div>
                        <span className="text-[10px] text-[#00D084] font-bold">Q: INGESTION</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        PyAV video demuxing, scene sampling, YOLOv8 face/plate anonymization, and SigLIP neural embedding.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-black text-white text-[11px] font-sans flex items-center justify-between border border-black">
                  <div className="flex items-center gap-2">
                    <NvidiaLogo className="w-4 h-4" />
                    <span>NVIDIA CUDA & Metal MPS</span>
                  </div>
                  <span className="text-[#00D084] font-mono font-bold">HW ACCEL</span>
                </div>
              </div>

              {/* Layer 3: Storage & Search Layer */}
              <div className="lg:col-span-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 flex flex-col justify-between space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b-2 border-black">
                    <span className="text-[10px] font-black uppercase text-stone-500">LAYER 03 // STORAGE & VECTOR DB</span>
                    <span className="px-2 py-0.5 bg-[#7C3AED] text-white text-[9px] font-black uppercase border border-black">
                      PERSISTENCE
                    </span>
                  </div>

                  <div className="space-y-2.5">
                    <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <QdrantLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">QDRANT VECTOR DB</span>
                        </div>
                        <span className="text-[10px] text-[#7C3AED] font-bold">PORT 6333</span>
                      </div>
                      <p className="text-[10px] text-stone-600 dark:text-stone-400 font-sans">
                        HNSW cosine similarity graph indexing 768d SigLIP & 2048d Qwen vectors.
                      </p>
                    </div>

                    <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <MinIOLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">MINIO S3 OBJECT STORE</span>
                        </div>
                        <span className="text-[10px] text-[#FF5500] font-bold">PORT 9000/9001</span>
                      </div>
                      <p className="text-[10px] text-stone-600 dark:text-stone-400 font-sans">
                        Dual buckets: <code>scenesearch-raw</code> (restricted) & <code>scenesearch-derived</code> (public).
                      </p>
                    </div>

                    <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <PostgresLogo className="w-5 h-5" />
                          <span className="font-black text-xs text-black dark:text-white">POSTGRESQL 16</span>
                        </div>
                        <span className="text-[10px] text-[#00D084] font-bold">PORT 5432</span>
                      </div>
                      <p className="text-[10px] text-stone-600 dark:text-stone-400 font-sans">
                        ACID relational storage for users, dataset manifests, and ingestion audit records.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-black text-white text-[11px] font-sans flex items-center gap-2 border border-black">
                  <Database className="w-4 h-4 text-[#FF5500] shrink-0" />
                  <span>Zero Data Loss Architecture with container volume persistence</span>
                </div>
              </div>
            </div>

            {/* Architecture Principles Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000] space-y-2">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 bg-[#FF5500] border border-black" />
                  <h4 className="font-black text-xs uppercase text-black dark:text-white">ADR-0001 // HYBRID MPS/CUDA RUNTIME</h4>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  Decoupled container architecture: backing infrastructure (DB, Qdrant, MinIO) runs containerized, while ML encoding and query paths execute natively to utilize host Apple Metal (MPS) or NVIDIA Tensor Cores.
                </p>
              </div>

              <div className="p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000] space-y-2">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 bg-[#00D084] border border-black" />
                  <h4 className="font-black text-xs uppercase text-black dark:text-white">ADR-0003 // STRICT PRIVACY ANONYMIZATION</h4>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  Raw un-anonymized video resides in restricted isolation. Only privacy-filtered frames (faces and vehicle license plates masked) are ever persisted into the derived bucket or exposed to public presigned endpoints.
                </p>
              </div>

              <div className="p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000] space-y-2">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 bg-[#FFD700] border border-black" />
                  <h4 className="font-black text-xs uppercase text-black dark:text-white">ADR-0005 // SINGLE-CORPUS PRECISION</h4>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  Keyframe-level granularity indexing 29,742+ curated moments. NegEx constraints (e.g. "without pedestrians") are evaluated per-keyframe rather than per-video to prevent false rejections.
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: TECH STACK */}
        {/* ========================================================================= */}
        {activeTab === 'techstack' && (
          <motion.div
            key="techstack"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="space-y-8 font-mono"
          >
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {TECH_STACK_DATA.map((group) => {
                const Icon = group.icon
                return (
                  <div
                    key={group.category}
                    className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-5"
                  >
                    <div className="flex items-center justify-between pb-3 border-b-2 border-black">
                      <div className="flex items-center gap-2">
                        <div
                          className="p-1.5 border border-black shadow-[1.5px_1.5px_0px_0px_#000]"
                          style={{ backgroundColor: group.color }}
                        >
                          <Icon className="w-4 h-4 text-black" />
                        </div>
                        <h3 className="font-black text-xs uppercase tracking-wider text-black dark:text-white">
                          {group.category}
                        </h3>
                      </div>
                      <span className="text-[10px] font-bold text-stone-500">
                        {group.items.length} MODULES
                      </span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {group.items.map((item) => {
                        const ItemLogo = item.Logo
                        return (
                          <div
                            key={item.name}
                            className="p-3.5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1.5 hover:border-[#FF5500] hover:shadow-[2px_2px_0px_0px_#000] transition-all group"
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <div className="w-5 h-5 rounded flex items-center justify-center p-0.5 bg-white dark:bg-black border border-black shrink-0">
                                  <ItemLogo className="w-3.5 h-3.5" />
                                </div>
                                <span className="font-black text-xs text-black dark:text-white group-hover:text-[#FF5500] transition-colors">
                                  {item.name}
                                </span>
                              </div>
                              <span className="px-1.5 py-0.2 bg-white dark:bg-stone-800 text-[9px] font-bold border border-black">
                                {item.version}
                              </span>
                            </div>
                            <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-snug">
                              {item.desc}
                            </p>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: INGESTION PIPELINE (COMPACT MASTER-DETAIL SPLIT VIEW) */}
        {/* ========================================================================= */}
        {activeTab === 'ingestion' && (
          <motion.div
            key="ingestion"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="space-y-6 font-mono"
          >
            {/* Compact Header Bar */}
            <div className="p-3.5 bg-black text-white border-2 border-black flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="px-2 py-0.5 bg-[#FFD700] text-black font-black text-[10px] uppercase border border-black">
                  STAGE {activeIngestStage.stage} / 05
                </span>
                <span className="text-xs font-black uppercase tracking-wider">
                  INGESTION PIPELINE // INTERACTIVE STAGE INSPECTOR
                </span>
              </div>
              <div className="flex items-center gap-3 text-[11px] text-stone-300">
                <span>CLICK ANY STAGE TO INSPECT ARCHITECTURE</span>
              </div>
            </div>

            {/* Master-Detail Split Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left Column (5 Cols): Compact Vertical Stepper */}
              <div className="lg:col-span-5 space-y-2">
                {INGESTION_STAGES.map((stage, idx) => {
                  const Logo = stage.Logo
                  const isSelected = selectedIngestIndex === idx
                  return (
                    <button
                      key={stage.stage}
                      onClick={() => setSelectedIngestIndex(idx)}
                      className={`w-full p-3 border-2 transition-all flex items-center justify-between gap-3 text-left cursor-pointer group ${
                        isSelected
                          ? 'bg-black text-white border-black shadow-[4px_4px_0px_0px_#FF5500] translate-x-1'
                          : 'bg-white dark:bg-[#1C1A17] text-black dark:text-white border-black/60 hover:border-black hover:bg-[#F7F4EE] dark:hover:bg-stone-900'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Number Badge */}
                        <div
                          className="w-7 h-7 rounded-full border-2 border-black flex items-center justify-center font-black text-xs text-black shrink-0"
                          style={{ backgroundColor: stage.color }}
                        >
                          {stage.stage}
                        </div>

                        {/* Stage Info */}
                        <div className="truncate">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-[9px] font-black uppercase px-1 py-0.2 border ${
                                isSelected
                                  ? 'bg-white text-black border-white'
                                  : 'bg-black text-white border-black'
                              }`}
                            >
                              {stage.tag}
                            </span>
                          </div>
                          <p className="font-black text-xs uppercase truncate pt-0.5">
                            {stage.title}
                          </p>
                        </div>
                      </div>

                      {/* Right Logo & Indicator */}
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="w-6 h-6 rounded flex items-center justify-center p-0.5 bg-white dark:bg-black border border-black">
                          <Logo className="w-4 h-4" />
                        </div>
                        <ChevronRight
                          className={`w-4 h-4 transition-transform ${
                            isSelected
                              ? 'text-[#FF5500] translate-x-0.5'
                              : 'text-stone-400 group-hover:translate-x-0.5'
                          }`}
                        />
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Right Column (7 Cols): Active Stage Detail Inspector */}
              <div className="lg:col-span-7 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-5">
                {/* Stage Header */}
                <div className="flex items-start justify-between pb-3 border-b-2 border-black gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="px-2 py-0.5 text-[10px] font-black uppercase border border-black"
                        style={{ backgroundColor: activeIngestStage.color, color: '#000' }}
                      >
                        STAGE {activeIngestStage.stage} // {activeIngestStage.tag}
                      </span>
                      <span className="text-[10px] font-bold text-stone-500">
                        LATENCY: <strong className="text-[#FF5500]">{activeIngestStage.latency}</strong>
                      </span>
                    </div>
                    <h3 className="text-base sm:text-lg font-black uppercase text-black dark:text-white">
                      {activeIngestStage.title}
                    </h3>
                    <p className="text-xs text-stone-500 font-bold uppercase">
                      {activeIngestStage.subtitle}
                    </p>
                  </div>

                  <div className="w-10 h-10 rounded border-2 border-black flex items-center justify-center p-1.5 bg-[#F7F4EE] dark:bg-stone-900 shadow-[2px_2px_0px_0px_#000] shrink-0">
                    <activeIngestStage.Logo className="w-7 h-7" />
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs sm:text-sm text-stone-700 dark:text-stone-300 font-sans leading-relaxed">
                  {activeIngestStage.desc}
                </p>

                {/* Input & Output Contracts */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                    <span className="text-[9px] font-black uppercase text-stone-500 flex items-center gap-1">
                      <ArrowRight className="w-3 h-3 text-[#FF5500]" /> INPUT CONTRACT
                    </span>
                    <p className="text-xs font-bold text-black dark:text-white">
                      {activeIngestStage.input}
                    </p>
                  </div>

                  <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                    <span className="text-[9px] font-black uppercase text-stone-500 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3 text-[#00D084]" /> OUTPUT ARTIFACT
                    </span>
                    <p className="text-xs font-bold text-black dark:text-white">
                      {activeIngestStage.output}
                    </p>
                  </div>
                </div>

                {/* Live Data Contract Code Preview */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-black text-stone-500 uppercase">
                    DATA CONTRACT / JSON PAYLOAD:
                  </span>
                  <pre className="p-3 bg-black text-[#00D084] border-2 border-black text-[11px] font-mono overflow-x-auto shadow-inner">
                    {activeIngestStage.contractSnippet}
                  </pre>
                </div>

                {/* Tech & Engine Spec */}
                <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black flex items-center justify-between text-[11px]">
                  <span className="text-stone-500 font-bold uppercase">ENGINE / STACK:</span>
                  <span className="font-bold text-black dark:text-white truncate pl-2">{activeIngestStage.tech}</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}

        {/* ========================================================================= */}
        {/* TAB 4: RETRIEVAL PIPELINE (COMPACT MASTER-DETAIL SPLIT VIEW) */}
        {/* ========================================================================= */}
        {activeTab === 'retrieval' && (
          <motion.div
            key="retrieval"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
            className="space-y-6 font-mono"
          >
            {/* Compact Header Bar */}
            <div className="p-3.5 bg-black text-white border-2 border-black flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="px-2 py-0.5 bg-[#7C3AED] text-white font-black text-[10px] uppercase border border-black">
                  {activeRetrievalTier.tier}
                </span>
                <span className="text-xs font-black uppercase tracking-wider">
                  TRI-TIER ADAPTIVE SEARCH // INTERACTIVE TIER INSPECTOR
                </span>
              </div>
              <div className="flex items-center gap-2 text-xs font-bold shrink-0">
                <span className="px-2 py-0.5 bg-stone-800 border border-stone-600 text-[#00D084]">
                  Hit@5: 89.8%
                </span>
                <span className="px-2 py-0.5 bg-stone-800 border border-stone-600 text-[#FF5500]">
                  P50: 8.4ms
                </span>
              </div>
            </div>

            {/* Master-Detail Split Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left Column (5 Cols): Compact Vertical Stepper */}
              <div className="lg:col-span-5 space-y-2">
                {RETRIEVAL_TIERS.map((tier, idx) => {
                  const Logo = tier.Logo
                  const isSelected = selectedRetrievalIndex === idx
                  return (
                    <button
                      key={tier.tier}
                      onClick={() => setSelectedRetrievalIndex(idx)}
                      className={`w-full p-3 border-2 transition-all flex items-center justify-between gap-3 text-left cursor-pointer group ${
                        isSelected
                          ? 'bg-black text-white border-black shadow-[4px_4px_0px_0px_#7C3AED] translate-x-1'
                          : 'bg-white dark:bg-[#1C1A17] text-black dark:text-white border-black/60 hover:border-black hover:bg-[#F7F4EE] dark:hover:bg-stone-900'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        {/* Tier Badge */}
                        <div
                          className="w-7 h-7 rounded-full border-2 border-black flex items-center justify-center font-black text-xs text-black shrink-0"
                          style={{ backgroundColor: tier.color }}
                        >
                          {idx + 1}
                        </div>

                        {/* Tier Info */}
                        <div className="truncate">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-[9px] font-black uppercase px-1 py-0.2 border ${
                                isSelected
                                  ? 'bg-white text-black border-white'
                                  : 'bg-black text-white border-black'
                              }`}
                            >
                              {tier.badge}
                            </span>
                          </div>
                          <p className="font-black text-xs uppercase truncate pt-0.5">
                            {tier.title}
                          </p>
                        </div>
                      </div>

                      {/* Right Logo & Indicator */}
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="w-6 h-6 rounded flex items-center justify-center p-0.5 bg-white dark:bg-black border border-black">
                          <Logo className="w-4 h-4" />
                        </div>
                        <ChevronRight
                          className={`w-4 h-4 transition-transform ${
                            isSelected
                              ? 'text-[#7C3AED] translate-x-0.5'
                              : 'text-stone-400 group-hover:translate-x-0.5'
                          }`}
                        />
                      </div>
                    </button>
                  )
                })}
              </div>

              {/* Right Column (7 Cols): Active Tier Detail Inspector */}
              <div className="lg:col-span-7 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-5">
                {/* Tier Header */}
                <div className="flex items-start justify-between pb-3 border-b-2 border-black gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="px-2 py-0.5 text-[10px] font-black uppercase border border-black"
                        style={{ backgroundColor: activeRetrievalTier.color, color: '#000' }}
                      >
                        {activeRetrievalTier.tier} // {activeRetrievalTier.badge}
                      </span>
                    </div>
                    <h3 className="text-base sm:text-lg font-black uppercase text-black dark:text-white">
                      {activeRetrievalTier.title}
                    </h3>
                    <p className="text-xs text-stone-500 font-bold uppercase">
                      {activeRetrievalTier.subtitle}
                    </p>
                  </div>

                  <div className="w-10 h-10 rounded border-2 border-black flex items-center justify-center p-1.5 bg-[#F7F4EE] dark:bg-stone-900 shadow-[2px_2px_0px_0px_#000] shrink-0">
                    <activeRetrievalTier.Logo className="w-7 h-7" />
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs sm:text-sm text-stone-700 dark:text-stone-300 font-sans leading-relaxed">
                  {activeRetrievalTier.desc}
                </p>

                {/* Formula or Decision Branch */}
                {activeRetrievalTier.formula ? (
                  <div className="p-3.5 bg-black text-[#00D084] font-mono text-xs border-2 border-black space-y-1">
                    <p className="text-stone-400 font-bold"># Multi-Tower RRF Scoring Formula:</p>
                    <p className="text-xs sm:text-sm font-bold text-white">{activeRetrievalTier.formula}</p>
                    <p className="text-stone-400 text-[10px] pt-1">
                      Calibrated visual floor θ = 0.09 + exact 29,742 keyframe NegEx exclusion check in RAM.
                    </p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                      <div className="flex items-center gap-1.5 text-xs font-black text-[#00D084]">
                        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                        <span>IN-DOMAIN PATH (TRUE)</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        {activeRetrievalTier.branchTrue}
                      </p>
                    </div>

                    <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                      <div className="flex items-center gap-1.5 text-xs font-black text-[#FF5500]">
                        <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                        <span>GUARDRAIL / RETRY</span>
                      </div>
                      <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                        {activeRetrievalTier.branchFalse}
                      </p>
                    </div>
                  </div>
                )}

                {/* Payload Snippet */}
                <div className="space-y-1.5">
                  <span className="text-[10px] font-black text-stone-500 uppercase">
                    EVALUATION SCHEMA / PAYLOAD:
                  </span>
                  <pre className="p-3 bg-black text-[#00D084] border-2 border-black text-[11px] font-mono overflow-x-auto shadow-inner">
                    {activeRetrievalTier.snippet}
                  </pre>
                </div>

                {/* Tech & Engine Spec */}
                <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black flex items-center justify-between text-[11px]">
                  <span className="text-stone-500 font-bold uppercase">TECH STACK:</span>
                  <span className="font-bold text-black dark:text-white truncate pl-2">{activeRetrievalTier.tech}</span>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  )
}
