# 📊 SceneSearch (P-081) — Comprehensive Evaluation Evidence Report

> 🌐 **Official Live Domain:** [https://c3-app-081.vinai.io.vn/](https://c3-app-081.vinai.io.vn/) *(Cloud Run: [https://scenesearch-604840409374.asia-southeast1.run.app](https://scenesearch-604840409374.asia-southeast1.run.app))*  
> 🎥 **Video Demo (5 Mins):** [https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing](https://drive.google.com/file/d/1gXYMA_KUQKXAMoWqEM4tfmlxS2FZBpq8/view?usp=sharing)  
> 📊 **Pitch Deck Slides:** [https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing](https://drive.google.com/file/d/12VwYiEgA-HEAYQIE1Vo7gIWLeQOJIMpq/view?usp=sharing)  
> **Target Benchmark:** Autonomous Driving Multi-Modal Scene Retrieval  
> **Ground Truth Evaluation Harness:** `app/eval/golden_set/eval.csv` (88 Curated Natural Language Queries)  
> **Corpus Testbed:** Berkeley DeepDrive BDD-100K 20GB Subset (29,504+ Indexed Keyframes)  
> **Evaluated Models:** `Qwen/Qwen3-VL-Embedding-2B` (Selected Online Default), `ViT-B-16-SigLIP` (Baseline), `Hybrid Retrieval` (SigCLIP + Qwen)

---

## 1. Executive Summary

| Evaluation Dimension | Primary Metric | Result | Benchmark Target | Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **Video-Level Retrieval** | **Hit@5 / MRR** | **89.77% / 0.8016** | ≥ 75.0% / ≥ 0.650 | 🏆 **EXCEEDS TARGET** |
| **Frame-Tolerant (±4f / ~2s)** | **Hit@5 / MRR** | **85.23% / 0.7132** | ≥ 70.0% / ≥ 0.600 | 🏆 **EXCEEDS TARGET** |
| **Frame-Exact Matching** | **Hit@5 / MRR** | **71.59% / 0.5246** | ≥ 50.0% / ≥ 0.400 | 🏆 **EXCEEDS TARGET** |
| **Online Search Latency** | **P50 / P95** | **180 ms / 420 ms** | ≤ 500 ms / ≤ 1500 ms | ⚡ **OPTIMAL PERFORMANCE** |
| **Unit Test Suite Coverage** | **Passing Tests** | **421 / 421 (100%)** | ≥ 95.0% | 🛡️ **VERIFIED** |

---

## 2. Multi-Model Retrieval Benchmark Comparison

Evaluated on 88 test queries against the 20GB BDD-100K dataset corpus:

| Model Architecture | Role | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@20 | Hit@50 | MRR Full |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Qwen3-VL Embedding 2B** | **Primary Online Default** | **73.86%** | **84.09%** | **89.77%** | **93.18%** | **95.45%** | **96.59%** | **0.8016** |
| **Hybrid (SigCLIP + Qwen)** | Experimental Fusion | 61.36% | 73.86% | 81.82% | 88.64% | 93.18% | 96.59% | 0.6948 |
| **SigCLIP (ViT-B-16)** | Visual-Language Baseline | 21.59% | 31.82% | 40.91% | 52.27% | 64.77% | 78.41% | 0.3012 |

---

## 3. Frame-Level Accuracy Breakdown

In autonomous driving video search, finding the exact timestamp moment of an event (e.g. cut-in, emergency brake, pedestrian crossing) is critical:

### 3.1. Frame-Level HitRate (Hit@K)
| Model | Hit@1 | Hit@5 | Hit@10 | Hit@20 | Hit@50 |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Qwen3-VL Embedding 2B** | **37.50%** | **71.59%** | **81.82%** | **89.77%** | **92.05%** |
| **Hybrid Retrieval** | 7.95% | 34.09% | 55.68% | 73.86% | 93.18% |
| **SigCLIP Baseline** | 3.41% | 10.23% | 12.50% | 17.05% | 26.14% |

### 3.2. Frame-Level MRR
| Model | Frame-Level MRR | Relative Advantage vs Baseline |
| :--- | :---: | :---: |
| **Qwen3-VL Embedding 2B** | **0.518817** | **+627% over SigCLIP** |
| **Hybrid Retrieval** | 0.220510 | +209% over SigCLIP |
| **SigCLIP Baseline** | 0.071342 | Baseline |

---

## 4. Granularity & Temporal Tolerance Analysis (Qwen3-VL 2B)

| Granularity Tier | Definition | Hit@1 | Hit@3 | Hit@5 | Hit@10 | Hit@50 | MRR | Search Time |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Video-Level** | Correct source video identified | 73.86% | 84.09% | 89.77% | 93.18% | 96.59% | 0.8016 | 15.88s |
| **Frame-Tolerant (±4f)** | Frame matched within ±2s window | 61.36% | 77.27% | 85.23% | 90.91% | 95.45% | 0.7132 | 15.88s |
| **Frame-Exact** | Exact ground-truth frame index | 38.64% | 60.23% | 71.59% | 82.95% | 92.05% | 0.5246 | 15.88s |

---

## 5. Reranker Ablation Study (`Qwen3-VL-Reranker-2B`)

We conducted an empirical ablation study to evaluate if adding a heavy Cross-Encoder Reranker (`Qwen/Qwen3-VL-Reranker-2B`) improves first-stage vector search results.

| Metric | Vector Search Only (Qwen3-VL 2B) | Cross-Encoder Rerank (Top-10) | Delta | Impact |
| :--- | :---: | :---: | :---: | :---: |
| **Hit@1** | **73.86%** | 55.68% | -18.18% | ⚠️ Degraded |
| **Hit@3** | **84.09%** | 72.73% | -11.36% | ⚠️ Degraded |
| **Hit@5** | **89.77%** | 78.41% | -11.36% | ⚠️ Degraded |
| **Hit@10** | **93.18%** | 87.50% | -5.68% | ⚠️ Degraded |
| **MRR Full** | **0.8016** | 0.6535 | -0.1481 | ⚠️ Degraded |
| **Latency Overhead**| **0 ms** | **+116.32s (1320 ms/query)** | +1320ms | ⚠️ Degraded |

### Key Takeaway & Architecture Decision
The standalone dense embedding representation of **Qwen3-VL-Embedding-2B** retains temporal dashcam context across sequential frames. The image-pair cross-encoder disrupts this temporal alignment and introduces significant latency. **The production system disables Cross-Encoder reranking by default**, delivering higher precision and sub-second response times.

---

## 6. User Experience & RLHF In-Loop Validation

- **RLHF Feedback Capture**: Native feedback mechanism (👍 Relevant / 👎 Irrelevant) in the Search UI directly persists user preference pairs into PostgreSQL and Redis.
- **Dataset Draft & Slicing**: Users can stage scenes into a live **Dataset Draft tray**, inspect bounding boxes/keyframes, and export standardized JSONL manifests alongside anonymized image zips.
- **APM System Traces**: 100% of search queries record granular latency waterfalls across parser, LLM, embedding, vector DB, and cache stages in the Admin Console.
