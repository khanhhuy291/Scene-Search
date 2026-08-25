python app/eval/evaluate_qwen.py \
    --csv app/eval/golden_set/eval.csv \
    --base-model Qwen/Qwen3-VL-Embedding-2B \
    --reranker-model Qwen/Qwen3-VL-Reranker-2B \
    --tolerance-frames 4 \
    --device cuda \
    --top-k 50 \
    --eval-rerank \
    --output-markdown app/eval/reports/eval_rerank_report.md \
    --output-json app/eval/reports/eval_results.json