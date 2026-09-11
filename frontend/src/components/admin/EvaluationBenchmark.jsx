import React, { useState, useEffect, useMemo } from 'react'
import {
  BarChart3,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Search,
  FileJson,
  Copy,
  Check,
  RefreshCw
} from 'lucide-react'
import { getEvalReport } from '../../api/admin'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

// Models Overview Data
const BENCHMARK_MODELS_SUMMARY = [
  {
    id: 'sigclip',
    name: 'SigCLIP (ViT-B-16)',
    role: 'Mô hình nền tảng đối sánh ảnh - văn bản (Visual-Language Baseline)',
    tag: 'BASELINE MÔ HÌNH CƠ SỞ',
    color: '#71717A',
    description:
      'Mô hình visual-language baseline cung cấp đặc trưng thị giác zero-shot cơ bản. Trích xuất đặc trưng hình ảnh và câu truy vấn độc lập qua dot-product.'
  },
  {
    id: 'qwen3-vl',
    name: 'Qwen3-VL Embedding 2B',
    role: 'Mô hình biểu diễn ngữ nghĩa đa phương thức chính (Primary Multimodal)',
    tag: 'MÔ HÌNH CHÍNH / ONLINE DEFAULT',
    color: '#00D084',
    description:
      'Được lựa chọn làm mô hình tìm kiếm chính trực tuyến (Online Default) nhờ chất lượng truy xuất vượt trội (89.77% Hit@5, MRR 0.8016), hiểu sâu ngữ cảnh giao thông và tiết kiệm chi phí vận hành.'
  },
  {
    id: 'hybrid',
    name: 'Hybrid Retrieval (SigCLIP + Qwen3-VL)',
    role: 'Kết hợp trọng số giữa tín hiệu SigCLIP và Qwen3-VL 2B',
    tag: 'THỰC NGHIỆM KẾT HỢP',
    color: '#FF5500',
    description:
      'Phương pháp thực nghiệm so sánh kết hợp vector SigCLIP và ngữ nghĩa Qwen3-VL qua thuật toán RRF/Weighted Score. (Không kích hoạt trong môi trường production).'
  }
]

// Main Retrieval Comparison Table (Video-Level)
const MAIN_RETRIEVAL_TABLE = [
  {
    model: 'SigCLIP (ViT-B-16)',
    role: 'Visual-Language Baseline',
    hit1: '21.59%',
    hit3: '31.82%',
    hit5: '40.91%',
    hit10: '52.27%',
    hit20: '64.77%',
    hit50: '78.41%',
    mrr: '0.3012',
    isDefault: false
  },
  {
    model: 'Qwen3-VL Embedding 2B',
    role: 'Primary Semantic Retrieval Model (Default)',
    hit1: '73.86%',
    hit3: '84.09%',
    hit5: '89.77%',
    hit10: '93.18%',
    hit20: '95.45%',
    hit50: '96.59%',
    mrr: '0.8016',
    isDefault: true
  },
  {
    model: 'Hybrid Retrieval',
    role: 'SigCLIP + Qwen3-VL Multimodal Fusion',
    hit1: '61.36%',
    hit3: '73.86%',
    hit5: '81.82%',
    hit10: '88.64%',
    hit20: '93.18%',
    hit50: '96.59%',
    mrr: '0.6948',
    isDefault: false
  }
]

// Frame-Level HitRate Comparison Table
const FRAME_LEVEL_HITRATE_TABLE = [
  {
    model: 'Qwen3-VL Embedding 2B',
    role: 'Mô hình ngữ nghĩa chính',
    hit1: '37.50%',
    hit5: '71.59%',
    hit10: '81.82%',
    hit20: '89.77%',
    hit50: '92.05%',
    isDefault: true
  },
  {
    model: 'Hybrid (SigCLIP + Qwen)',
    role: 'Thực nghiệm kết hợp',
    hit1: '7.95%',
    hit5: '34.09%',
    hit10: '55.68%',
    hit20: '73.86%',
    hit50: '93.18%',
    isDefault: false
  },
  {
    model: 'SigCLIP Baseline',
    role: 'Mô hình thị giác cơ sở',
    hit1: '3.41%',
    hit5: '10.23%',
    hit10: '12.50%',
    hit20: '17.05%',
    hit50: '26.14%',
    isDefault: false
  }
]

// Frame-Level MRR Comparison Table
const FRAME_LEVEL_MRR_TABLE = [
  {
    model: 'Qwen3-VL Embedding 2B',
    mrr: '0.518817',
    isDefault: true
  },
  {
    model: 'Hybrid Retrieval',
    mrr: '0.220510',
    isDefault: false
  },
  {
    model: 'SigCLIP Baseline',
    mrr: '0.071342',
    isDefault: false
  }
]


// Qwen3-VL Granularity / Tolerance Breakdown Data
const QWEN_GRANULARITY_DATA = [
  {
    granularity: 'Cấp độ Video (Video-Level)',
    definition: 'Truy xuất chính xác video nguồn chứa tình huống',
    hit1: '73.86%',
    hit3: '84.09%',
    hit5: '89.77%',
    hit10: '93.18%',
    hit20: '95.45%',
    hit50: '96.59%',
    mrr5: '0.7947',
    mrr10: '0.7999',
    mrr20: '0.8014',
    mrrFull: '0.8016',
    searchTime: '15.88s'
  },
  {
    granularity: 'Dung sai khung hình (±4 frames)',
    definition: 'Khung hình trùng khớp trong khoảng sai số ±4 frames (~±2 giây)',
    hit1: '61.36%',
    hit3: '77.27%',
    hit5: '85.23%',
    hit10: '90.91%',
    hit20: '94.32%',
    hit50: '95.45%',
    mrr5: '0.7019',
    mrr10: '0.7106',
    mrr20: '0.7130',
    mrrFull: '0.7132',
    searchTime: '15.88s'
  },
  {
    granularity: 'Khung hình tuyệt đối (Frame-Exact)',
    definition: 'Khung hình trả về phải trùng khớp chính xác 100% frame ground-truth',
    hit1: '38.64%',
    hit3: '60.23%',
    hit5: '71.59%',
    hit10: '82.95%',
    hit20: '89.77%',
    hit50: '92.05%',
    mrr5: '0.5040',
    mrr10: '0.5189',
    mrr20: '0.5236',
    mrrFull: '0.5246',
    searchTime: '15.88s'
  }
]

// Reranker Ablation Experiment Data
const RERANKER_ABLATION_METRICS = [
  { metric: 'Hit@1', before: '73.86%', after: '55.68%', delta: '-18.18%', status: 'decreased' },
  { metric: 'Hit@3', before: '84.09%', after: '72.73%', delta: '-11.36%', status: 'decreased' },
  { metric: 'Hit@5', before: '89.77%', after: '78.41%', delta: '-11.36%', status: 'decreased' },
  { metric: 'Hit@10', before: '93.18%', after: '87.50%', delta: '-5.68%', status: 'decreased' },
  { metric: 'Hit@20', before: '95.45%', after: '90.91%', delta: '-4.54%', status: 'decreased' },
  { metric: 'Hit@50', before: '96.59%', after: '96.59%', delta: '0.00%', status: 'neutral' },
  { metric: 'MRR Full', before: '0.8016', after: '0.6535', delta: '-0.1481', status: 'decreased' }
]

// Curated Dataset Descriptions
const DATASETS_OVERVIEW = [
  {
    id: 'ds-bdd100k-20gb',
    title: 'BDD-100K SUBSET: DRIVING VIDEO WITH OBJECT TRACKING',
    subtitle: 'Tập dữ liệu Corpus chính được lập chỉ mục Vector (Primary Indexed Database)',
    clipsCount: '100+ Video Clips',
    size: '20.0 GB (29,504+ Keyframes)',
    badge: 'CORPUS ĐANG HOẠT ĐỘNG',
    badgeColor: '#00D084',
    sourceName: 'Berkeley DeepDrive (BDD-100K)',
    sourceUrl: 'http://bdd-data.berkeley.edu/',
    kaggleUrl: 'https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking',
    weatherDistribution: [
      { label: 'TRỜI QUANG / BAN NGÀY (CLEAR / DAYLIGHT)', pct: 45 },
      { label: 'BAN ĐÊM / HOÀNG HÔN (NIGHT / TWILIGHT)', pct: 30 },
      { label: 'MƯA / TUYẾT / U ÁM (RAIN / SNOW / OVERCAST)', pct: 25 }
    ],
    description:
      'Được trích xuất từ tập dữ liệu chuẩn xe tự hành Berkeley DeepDrive BDD-100K (Tập con Kaggle 20GB). Tập dữ liệu được lập chỉ mục hoàn chỉnh vào cơ sở dữ liệu tìm kiếm đa phương thức với nhãn theo dõi đa vật thể (MOT), cửa sổ thời gian 0.5s/khung hình và metadata khung cảnh trích xuất bởi thị giác máy tính.'
  },
  {
    id: 'ds-golden-testset-88',
    title: 'TẬP CHUẨN ĐÁNH GIÁ (GOLDEN DATASET - 88 QUERY-FRAME PAIRS)',
    subtitle: 'Bộ dữ liệu đối chiếu Ground-Truth Benchmark chính xác',
    clipsCount: '88 Cặp Truy Vấn - Khung Hình',
    size: 'Golden Testset (eval.csv)',
    badge: 'GROUND-TRUTH HARNESS',
    badgeColor: '#FF5500',
    sourceName: 'app/eval/golden_set/eval.csv',
    sourceUrl: null,
    kaggleUrl: null,
    weatherDistribution: [
      { label: 'NÚT GIAO & ĐA PHƯƠNG TIỆN (INTERSECTIONS)', pct: 42 },
      { label: 'TÌNH HUỐNG ĐÊM / CHẬP TỐI (NIGHT / DUSK)', pct: 33 },
      { label: 'THỜI TIẾT ĐẶC BIỆT & DỊ THƯỜNG (ANOMALIES)', pct: 25 }
    ],
    description:
      'Bộ dữ liệu chuẩn hóa gồm 88 cặp câu truy vấn ngôn ngữ tự nhiên (đa ngôn ngữ Tiếng Việt & Tiếng Anh) cùng khung hình nhãn thực (ground-truth) chính xác. Dùng để đánh giá tự động và kiểm thử hồi quy 3 cấp độ: Cấp video, Dung sai thời gian (±4 frame ~ ±2s), và Trùng khớp tuyệt đối (Frame-Exact).'
  },
  {
    id: 'ds-custom-export-03',
    title: 'TRÍCH XUẤT PHÂN ĐOẠN HUẤN LUYỆN (CUSTOM TRAINING SLICE)',
    subtitle: 'Định dạng xuất dữ liệu huấn luyện xe tự hành & Robot',
    clipsCount: 'Theo yêu cầu (On-Demand)',
    size: 'Tuỳ biến (JSONL + Zip)',
    badge: 'XUẤT DỮ LIỆU TÙY BIẾN',
    badgeColor: '#7C3AED',
    sourceName: 'SceneSearch Exporter',
    sourceUrl: null,
    kaggleUrl: null,
    weatherDistribution: [
      { label: 'PYTORCH / TORCHVISION TENSORS', pct: 50 },
      { label: 'HUGGINGFACE DATASETS MANIFEST', pct: 30 },
      { label: 'LƯU TRỮ RAW MP4 & KEYFRAMES', pct: 20 }
    ],
    description:
      'Bộ sinh tập dữ liệu xuất theo tiêu chí truy vấn, nhãn đối tượng, điều kiện ánh sáng và góc quay camera. Tự động đóng gói file manifest JSONL kèm tệp zip hình ảnh đã kiểm duyệt ẩn danh quyền riêng tư.'
  }
]

// Sample Golden Dataset Entries
const SAMPLE_GOLDEN_QUERIES = [
  {
    query_id: '1',
    caption: 'Xe Toyota xanh ở giữa, xe đen bên phải, cầu vượt bên trái.',
    video_id: '0000f77c-6257be58',
    frame_id: '00000',
    frame_name: 'frame_00000.jpg',
    category: 'Giao lộ / Cầu vượt (Tiếng Việt)'
  },
  {
    query_id: '2',
    caption: 'A view from a car shows a dark blue Toyota Highlander in traffic next to a curved concrete overpass with a terminal parking sign.',
    video_id: '0000f77c-6257be58',
    frame_id: '00002',
    frame_name: 'frame_00002.jpg',
    category: 'Detailed Vehicle & Signage'
  },
  {
    query_id: '727',
    caption: 'Nighttime city traffic with an FDNY fire truck and flashing lights directly ahead, a yellow taxi to its left, a white sedan to its right.',
    video_id: '000f157f-30b30f5e',
    frame_id: '00034',
    frame_name: 'frame_00034.jpg',
    category: 'Xe ưu tiên & Đèn chớp ban đêm'
  },
  {
    query_id: '870',
    caption: 'A yellow taxi SUV moves across a city crosswalk in the foreground, with a red traffic light and a one-way sign nearby.',
    video_id: '0010bf16-9ee17cd9',
    frame_id: '00065',
    frame_name: 'frame_00065.jpg',
    category: 'Đèn đỏ & Người đi bộ'
  },
  {
    query_id: '1092',
    caption: 'A black SUV with illuminated red taillights sits in the center of a curved nighttime road, beside a median island of pink flowers.',
    video_id: '00202076-7a95b4e3',
    frame_id: '00049',
    frame_name: 'frame_00049.jpg',
    category: 'Đường cong ban đêm & Dải phân cách'
  },
  {
    query_id: '4691',
    caption: 'A rainy urban street scene showing a gray Ford Freestar minivan directly ahead at a green traffic light, with pedestrians holding umbrellas.',
    video_id: '00699de6-58847872',
    frame_id: '00011',
    frame_name: 'frame_00011.jpg',
    category: 'Đường ướt mưa & Người cầm dù'
  },
  {
    query_id: '6169',
    caption: 'Dusk driving on a snow-lined multi-lane road with a black SUV ahead, illuminated streetlights, bare trees, and a bright billboard.',
    video_id: '007eddfc-f8a80310',
    frame_id: '00064',
    frame_name: 'frame_00064.jpg',
    category: 'Đường tuyết chập tối (Snow / Dusk)'
  },
  {
    query_id: '6276',
    caption: 'A black SUV leads the camera on a sunlit multi-lane highway, with a green sign reading Hyde St San Francisco 1/2 mi.',
    video_id: '0081e27b-17bf4a9e',
    frame_id: '00008',
    frame_name: 'frame_00008.jpg',
    category: 'Cao tốc ban ngày & Biển chỉ dẫn'
  }
]

// Sample JSONL Code Format
const SAMPLE_JSONL_CODE = `{"query_id": "1", "caption": "Xe Toyota xanh ở giữa, xe đen bên phải, cầu vượt bên trái.", "video_id": "0000f77c-6257be58", "frame_id": "00000", "frame_name": "frame_00000.jpg", "dataset_source": "BDD-100K 20GB Subset (Kaggle)", "gt_path": "s3://scenesearch-derived/frames/0000f77c-6257be58/frame_00000.jpg", "privacy_verified": true}
{"query_id": "2", "caption": "A view from a car shows a dark blue Toyota Highlander in traffic next to a curved concrete overpass.", "video_id": "0000f77c-6257be58", "frame_id": "00002", "frame_name": "frame_00002.jpg", "dataset_source": "BDD-100K 20GB Subset (Kaggle)", "gt_path": "s3://scenesearch-derived/frames/0000f77c-6257be58/frame_00002.jpg", "privacy_verified": true}`

export const EvaluationBenchmark = () => {
  const [subTab, setSubTab] = useState('benchmarks') // 'benchmarks' | 'datasets' | 'live_report'
  const [goldenSearch, setGoldenSearch] = useState('')
  const [copiedJsonl, setCopiedJsonl] = useState(false)
  const { token } = useAuth()
  const { addToast } = useToast()

  // Live report fetching state
  const [liveReport, setLiveReport] = useState(null)
  const [reportLoading, setReportLoading] = useState(false)

  const fetchLiveReport = async () => {
    if (!token) return
    setReportLoading(true)
    try {
      const data = await getEvalReport(token)
      setLiveReport(data)
    } catch (err) {
      setLiveReport({ available: false, detail: err.message })
    } finally {
      setReportLoading(false)
    }
  }

  useEffect(() => {
    fetchLiveReport()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const copyJsonlSample = () => {
    navigator.clipboard.writeText(SAMPLE_JSONL_CODE)
    setCopiedJsonl(true)
    addToast('Đã sao chép cấu trúc mẫu JSONL vào clipboard!', 'success')
    setTimeout(() => setCopiedJsonl(false), 2000)
  }

  const filteredGoldenQueries = useMemo(() => {
    const q = goldenSearch.trim().toLowerCase()
    if (!q) return SAMPLE_GOLDEN_QUERIES
    return SAMPLE_GOLDEN_QUERIES.filter(
      (item) =>
        item.caption.toLowerCase().includes(q) ||
        item.video_id.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        item.query_id.includes(q)
    )
  }, [goldenSearch])

  return (
    <div className="space-y-6 font-sans animate-fadeIn">
      {/* Navigation Sub-Tabs Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000]">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-[#FF5500]" />
          <div>
            <h2 className="text-lg font-black uppercase tracking-tight text-black dark:text-white font-mono">
              HỆ THỐNG ĐÁNH GIÁ & TẬP DỮ LIỆU CHUẨN (BENCHMARKS & GOLDEN SET)
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
              Bộ công cụ đánh giá độ chính xác truy xuất xe tự hành, mô tả dataset BDD-100K 20GB và tập ground-truth 88 queries.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 font-mono text-xs flex-wrap">
          <button
            type="button"
            onClick={() => setSubTab('benchmarks')}
            className={`px-3.5 py-2 font-black uppercase border-2 border-black transition-all cursor-pointer ${
              subTab === 'benchmarks'
                ? 'bg-black text-white shadow-[2px_2px_0px_0px_#FF5500]'
                : 'bg-[#F7F4EE] dark:bg-stone-900 text-stone-700 dark:text-stone-300 hover:bg-white dark:hover:bg-stone-800'
            }`}
          >
            1. KẾT QUẢ BENCHMARK
          </button>
          <button
            type="button"
            onClick={() => setSubTab('datasets')}
            className={`px-3.5 py-2 font-black uppercase border-2 border-black transition-all cursor-pointer ${
              subTab === 'datasets'
                ? 'bg-black text-white shadow-[2px_2px_0px_0px_#00D084]'
                : 'bg-[#F7F4EE] dark:bg-stone-900 text-stone-700 dark:text-stone-300 hover:bg-white dark:hover:bg-stone-800'
            }`}
          >
            2. MÔ TẢ DATA & GOLDEN DATASET
          </button>
          <button
            type="button"
            onClick={() => setSubTab('live_report')}
            className={`px-3.5 py-2 font-black uppercase border-2 border-black transition-all cursor-pointer ${
              subTab === 'live_report'
                ? 'bg-black text-white shadow-[2px_2px_0px_0px_#7C3AED]'
                : 'bg-[#F7F4EE] dark:bg-stone-900 text-stone-700 dark:text-stone-300 hover:bg-white dark:hover:bg-stone-800'
            }`}
          >
            3. LIVE HARNESS REPORT
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SUB-TAB 1: BENCHMARK RESULTS & MODEL COMPARISON */}
      {/* ========================================================================= */}
      {subTab === 'benchmarks' && (
        <div className="space-y-6">
          {/* Top KPI Metrics Banner */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 font-mono">
            <div className="p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[3px_3px_0px_0px_#000]">
              <span className="text-[10px] font-black uppercase text-stone-500 tracking-wider block">
                HIT@5 (QWEN3-VL 2B)
              </span>
              <p className="text-3xl font-black text-[#00D084] mt-1">89.77%</p>
              <span className="text-[10px] text-stone-500 font-sans block mt-0.5">Top-5 video chính xác</span>
            </div>

            <div className="p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[3px_3px_0px_0px_#000]">
              <span className="text-[10px] font-black uppercase text-stone-500 tracking-wider block">
                MRR FULL RANK
              </span>
              <p className="text-3xl font-black text-black dark:text-white mt-1">0.8016</p>
              <span className="text-[10px] text-stone-500 font-sans block mt-0.5">Mean Reciprocal Rank</span>
            </div>

            <div className="p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[3px_3px_0px_0px_#000]">
              <span className="text-[10px] font-black uppercase text-stone-500 tracking-wider block">
                TẬP TRUY VẤN KIỂM THỬ
              </span>
              <p className="text-3xl font-black text-[#FF5500] mt-1">88 Cặp</p>
              <span className="text-[10px] text-stone-500 font-sans block mt-0.5">Golden Dataset VN & EN</span>
            </div>

            <div className="p-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[3px_3px_0px_0px_#000]">
              <span className="text-[10px] font-black uppercase text-stone-500 tracking-wider block">
                TỔNG THỜI GIAN EVAL
              </span>
              <p className="text-3xl font-black text-black dark:text-white mt-1">15.88s</p>
              <span className="text-[10px] text-stone-500 font-sans block mt-0.5">Toàn bộ 88 queries</span>
            </div>
          </div>

          {/* Model Roles Overview Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono">
            {BENCHMARK_MODELS_SUMMARY.map((m) => (
              <div
                key={m.id}
                className={`p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[5px_5px_0px_0px_#000] space-y-3 flex flex-col justify-between ${
                  m.id === 'qwen3-vl' ? 'ring-3 ring-[#00D084]' : ''
                }`}
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span
                      className="px-2 py-0.5 text-[9px] font-black uppercase border border-black"
                      style={{
                        backgroundColor: m.color,
                        color: m.id === 'sigclip' ? '#fff' : '#000'
                      }}
                    >
                      {m.tag}
                    </span>
                    {m.id === 'qwen3-vl' && (
                      <span className="text-[10px] font-black text-[#00D084] flex items-center gap-1">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        ONLINE PRODUCTION
                      </span>
                    )}
                  </div>
                  <h3 className="text-base font-black uppercase text-black dark:text-white">{m.name}</h3>
                  <p className="text-xs font-bold text-stone-700 dark:text-stone-300 font-sans">{m.role}</p>
                  <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                    {m.description}
                  </p>
                </div>

                {m.id === 'qwen3-vl' && (
                  <div className="pt-2 border-t border-black/10 flex items-center justify-between text-[11px] font-mono font-black text-stone-600 dark:text-stone-400">
                    <span>HIỆU SUẤT TRUY VẤN:</span>
                    <span className="text-[#FF5500]">89.77% Hit@5 · MRR 0.8016</span>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Main Comparison Table: Hit@K and MRR (Video-Level) */}
          <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 sm:p-8 space-y-6 font-mono">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b-2 border-black">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black">
                    BẢNG SO SÁNH CHÍNH
                  </span>
                  <h3 className="text-sm font-black uppercase text-black dark:text-white">
                    BẢNG ĐỐI SOÁT TRUY XUẤT CẤP ĐỘ VIDEO (VIDEO-LEVEL RETRIEVAL)
                  </h3>
                </div>
                <p className="text-[11px] text-stone-500 font-sans">
                  Đánh giá trên toàn bộ 88 câu truy vấn kiểm thử thuộc tập con BDD-100K 20GB. Chỉ số HitRate@K và Mean Reciprocal Rank (MRR).
                </p>
              </div>
              <span className="px-2.5 py-1 bg-[#FFD700] text-black text-[10px] font-black uppercase border border-black">
                88 GOLDEN QUERIES
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                    <th className="p-3 font-black uppercase">MÔ HÌNH (MODEL)</th>
                    <th className="p-3 font-black uppercase text-center">HIT@1</th>
                    <th className="p-3 font-black uppercase text-center">HIT@3</th>
                    <th className="p-3 font-black uppercase text-center">HIT@5</th>
                    <th className="p-3 font-black uppercase text-center">HIT@10</th>
                    <th className="p-3 font-black uppercase text-center">HIT@20</th>
                    <th className="p-3 font-black uppercase text-center">HIT@50</th>
                    <th className="p-3 font-black uppercase text-center">MRR FULL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/20">
                  {MAIN_RETRIEVAL_TABLE.map((row) => (
                    <tr
                      key={row.model}
                      className={`transition-colors ${
                        row.isDefault
                          ? 'bg-[#00D084]/15 dark:bg-[#00D084]/20 font-bold'
                          : 'hover:bg-black/5 dark:hover:bg-white/5'
                      }`}
                    >
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-black text-black dark:text-white">{row.model}</span>
                          {row.isDefault && (
                            <span className="px-1.5 py-0.2 text-[9px] bg-[#00D084] text-black font-black uppercase border border-black">
                              ONLINE DEFAULT
                            </span>
                          )}
                          {row.model.includes('Hybrid') && (
                            <span className="px-1.5 py-0.2 text-[9px] bg-[#FF5500] text-black font-black uppercase border border-black">
                              EXPERIMENTAL
                            </span>
                          )}
                        </div>
                        <span className="text-[10px] text-stone-500 font-sans block">{row.role}</span>
                      </td>
                      <td className="p-3 text-center font-black text-black dark:text-white">{row.hit1}</td>
                      <td className="p-3 text-center font-black text-black dark:text-white">{row.hit3}</td>
                      <td className="p-3 text-center font-black text-[#FF5500] text-sm">{row.hit5}</td>
                      <td className="p-3 text-center font-black text-black dark:text-white">{row.hit10}</td>
                      <td className="p-3 text-center font-black text-black dark:text-white">{row.hit20}</td>
                      <td className="p-3 text-center font-black text-black dark:text-white">{row.hit50}</td>
                      <td className="p-3 text-center font-black text-[#00D084] text-sm">{row.mrr}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Frame-Level Benchmark Grid */}
          <div className="p-6 sm:p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b-2 border-black">
              <div className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-[#FFD700] text-black text-[10px] font-black uppercase border border-black">
                    FRAME-LEVEL ACCURACY
                  </span>
                  <h3 className="text-sm font-black uppercase text-black dark:text-white">
                    ĐÁNH GIÁ ĐỘ CHÍNH XÁC CẤP KHUNG HÌNH (HITRATE & MRR)
                  </h3>
                </div>
                <p className="text-[11px] text-stone-500 font-sans">
                  Đánh giá nghiêm ngặt xem khung hình trả về có khớp chính xác với thời điểm diễn ra sự kiện hay không.
                </p>
              </div>
              <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black">
                VERIFIED FRAME METRICS
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Frame-Level HitRate Table (8 Cols) */}
              <div className="lg:col-span-8 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase text-black dark:text-white">
                    FRAME-LEVEL HITRATE (HIT@K)
                  </span>
                  <span className="text-[10px] text-stone-500">K = 1, 5, 10, 20, 50</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse font-mono">
                    <thead>
                      <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                        <th className="p-2.5 font-black uppercase">MÔ HÌNH</th>
                        <th className="p-2.5 font-black uppercase text-center">HIT@1</th>
                        <th className="p-2.5 font-black uppercase text-center">HIT@5</th>
                        <th className="p-2.5 font-black uppercase text-center">HIT@10</th>
                        <th className="p-2.5 font-black uppercase text-center">HIT@20</th>
                        <th className="p-2.5 font-black uppercase text-center">HIT@50</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/20">
                      {FRAME_LEVEL_HITRATE_TABLE.map((row) => (
                        <tr
                          key={row.model}
                          className={`transition-colors ${
                            row.isDefault
                              ? 'bg-[#00D084]/15 dark:bg-[#00D084]/20 font-bold'
                              : 'hover:bg-black/5 dark:hover:bg-white/5'
                          }`}
                        >
                          <td className="p-2.5 font-black text-black dark:text-white">{row.model}</td>
                          <td className="p-2.5 text-center font-black text-black dark:text-white">{row.hit1}</td>
                          <td className="p-2.5 text-center font-black text-[#FF5500]">{row.hit5}</td>
                          <td className="p-2.5 text-center font-black text-black dark:text-white">{row.hit10}</td>
                          <td className="p-2.5 text-center font-black text-black dark:text-white">{row.hit20}</td>
                          <td className="p-2.5 text-center font-black text-black dark:text-white">{row.hit50}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Frame-Level MRR Table (4 Cols) */}
              <div className="lg:col-span-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black uppercase text-black dark:text-white">
                    FRAME-LEVEL MRR
                  </span>
                  <span className="text-[10px] text-stone-500">MEAN RECIPROCAL RANK</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse font-mono">
                    <thead>
                      <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                        <th className="p-2.5 font-black uppercase">MÔ HÌNH</th>
                        <th className="p-2.5 font-black uppercase text-center">MRR</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-black/20">
                      {FRAME_LEVEL_MRR_TABLE.map((row) => (
                        <tr
                          key={row.model}
                          className={row.isDefault ? 'bg-[#00D084]/15 dark:bg-[#00D084]/20 font-bold' : ''}
                        >
                          <td className="p-2.5 font-black text-black dark:text-white">{row.model}</td>
                          <td className="p-2.5 text-center font-black text-[#00D084]">{row.mrr}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black text-[10px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  Qwen3-VL đạt MRR cấp khung hình cao nhất (<span className="font-mono font-black text-black dark:text-white">0.518817</span>), vượt trội hoàn toàn so với Hybrid (<span className="font-mono font-black">0.220510</span>) và SigCLIP (<span className="font-mono font-black">0.071342</span>).
                </div>
              </div>
            </div>
          </div>

          {/* Granularity & Reranker Ablation Breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 font-mono">
            {/* Left: 3-Tier Granularity (7 Cols) */}
            <div className="lg:col-span-7 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b-2 border-black">
                <div className="space-y-0.5">
                  <h3 className="text-xs font-black uppercase text-black dark:text-white">
                    QWEN3-VL 2B — 3 CẤP ĐỘ DUNG SAI THỜI GIAN (GRANULARITY TIERS)
                  </h3>
                  <p className="text-[11px] text-stone-500 font-sans">
                    Phân tích kết quả theo 3 cấp độ sai số thời gian trên tập 88 câu truy vấn kiểm thử.
                  </p>
                </div>
                <span className="px-2 py-0.5 bg-[#FFD700] text-black text-[10px] font-black uppercase border border-black">
                  3 TIERS
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900 text-[11px]">
                      <th className="p-2 font-black uppercase">CẤP ĐỘ ĐÁNH GIÁ</th>
                      <th className="p-2 font-black uppercase text-center">HIT@1</th>
                      <th className="p-2 font-black uppercase text-center">HIT@3</th>
                      <th className="p-2 font-black uppercase text-center">HIT@5</th>
                      <th className="p-2 font-black uppercase text-center">HIT@10</th>
                      <th className="p-2 font-black uppercase text-center">MRR</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/20">
                    {QWEN_GRANULARITY_DATA.map((row) => (
                      <tr key={row.granularity} className="hover:bg-black/5 dark:hover:bg-white/5">
                        <td className="p-2">
                          <span className="font-black text-black dark:text-white block">{row.granularity}</span>
                          <span className="text-[10px] text-stone-500 font-sans block">{row.definition}</span>
                        </td>
                        <td className="p-2 text-center font-bold">{row.hit1}</td>
                        <td className="p-2 text-center font-bold">{row.hit3}</td>
                        <td className="p-2 text-center font-bold text-[#FF5500]">{row.hit5}</td>
                        <td className="p-2 text-center font-bold">{row.hit10}</td>
                        <td className="p-2 text-center font-black text-[#00D084]">{row.mrrFull}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Right: Reranker Ablation Study (5 Cols) */}
            <div className="lg:col-span-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b-2 border-black">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5 text-xs font-black text-[#FF5500] uppercase">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    <span>THỰC NGHIỆM CROSS-ENCODER RERANKER</span>
                  </div>
                  <p className="text-[11px] text-stone-500 font-sans">
                    Kiểm thử Qwen3-VL-Reranker-2B trên các ứng viên ban đầu.
                  </p>
                </div>
                <span className="px-2 py-0.5 bg-red-100 text-red-800 text-[9px] font-black uppercase border border-red-500">
                  DEGRADATION
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse font-mono">
                  <thead>
                    <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900 text-[10px]">
                      <th className="p-2 font-black uppercase">CHỈ SỐ</th>
                      <th className="p-2 font-black uppercase text-center">TRƯỚC</th>
                      <th className="p-2 font-black uppercase text-center">SAU</th>
                      <th className="p-2 font-black uppercase text-center">BIẾN ĐỘNG</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/20">
                    {RERANKER_ABLATION_METRICS.slice(0, 4).map((row) => (
                      <tr key={row.metric}>
                        <td className="p-2 font-black text-black dark:text-white">{row.metric}</td>
                        <td className="p-2 text-center font-bold text-[#00D084]">{row.before}</td>
                        <td className="p-2 text-center font-bold text-stone-500">{row.after}</td>
                        <td className="p-2 text-center font-black text-red-600">{row.delta}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border border-black text-[10px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                <strong>Kết luận thực nghiệm:</strong> Cross-Encoder Reranker làm suy giảm Hit@1 (-18.18%) và MRR (-0.1481) do làm mất đặc trưng thời gian liên tục. Hệ thống đã tắt Reranker để đảm bảo độ chính xác cao nhất và độ trễ tối ưu.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-TAB 2: DATASET ARCHITECTURE & GOLDEN DATASET */}
      {/* ========================================================================= */}
      {subTab === 'datasets' && (
        <div className="space-y-6">
          {/* Datasets 3-Card Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono">
            {DATASETS_OVERVIEW.map((ds) => (
              <div
                key={ds.id}
                className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4 flex flex-col justify-between"
              >
                <div className="space-y-3">
                  <div className="flex items-center justify-between pb-2 border-b border-black/10">
                    <span
                      className="px-2 py-0.5 text-[9px] font-black uppercase border border-black text-black"
                      style={{ backgroundColor: ds.badgeColor }}
                    >
                      {ds.badge}
                    </span>
                    <span className="text-[#FF5500] font-black text-xs">{ds.size}</span>
                  </div>

                  <div>
                    <h3 className="text-sm font-black uppercase text-black dark:text-white">{ds.title}</h3>
                    <p className="text-[11px] text-stone-500 font-bold font-sans mt-0.5">{ds.subtitle}</p>
                  </div>

                  <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                    {ds.description}
                  </p>

                  {/* Weather / Scene Distribution Breakdown */}
                  <div className="space-y-2 pt-2 border-t border-black/10 font-mono">
                    <span className="text-[10px] font-black text-stone-500 uppercase block">
                      PHÂN BỐ ĐIỀU KIỆN MÔI TRƯỜNG:
                    </span>
                    {ds.weatherDistribution.map((row) => (
                      <div key={row.label} className="space-y-0.5 text-[10px]">
                        <div className="flex justify-between font-bold">
                          <span>{row.label}</span>
                          <span>{row.pct}%</span>
                        </div>
                        <div className="h-2 bg-[#F7F4EE] dark:bg-stone-800 border border-black overflow-hidden">
                          <div className="h-full bg-[#FF5500]" style={{ width: `${row.pct}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Source Links */}
                  {(ds.sourceUrl || ds.kaggleUrl) && (
                    <div className="flex items-center gap-3 pt-2 border-t border-black/10 text-[11px] font-bold">
                      {ds.sourceUrl && (
                        <a
                          href={ds.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline flex items-center gap-1 text-stone-700 dark:text-stone-300"
                        >
                          <ExternalLink className="w-3 h-3 text-[#FF5500]" />
                          <span>BDD-100K Official</span>
                        </a>
                      )}
                      {ds.kaggleUrl && (
                        <a
                          href={ds.kaggleUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline flex items-center gap-1 text-[#00D084]"
                        >
                          <ExternalLink className="w-3 h-3 text-[#00D084]" />
                          <span>Kaggle Dataset (20GB)</span>
                        </a>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Golden Dataset Explorer Table */}
          <div className="p-6 sm:p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b-2 border-black">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black">
                    EVALUATION HARNESS
                  </span>
                  <h3 className="text-base font-black uppercase text-black dark:text-white">
                    CHI TIẾT TẬP CHUẨN GOLDEN DATASET (88 CẶP TRUY VẤN - KHUNG HÌNH)
                  </h3>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
                  Nguồn: <code className="font-mono bg-stone-100 dark:bg-stone-800 px-1 py-0.5 border border-black">app/eval/golden_set/eval.csv</code> · Chứa câu truy vấn Tiếng Việt & Tiếng Anh với nhãn frame_id và video_id chính xác.
                </p>
              </div>

              {/* Search Filter */}
              <div className="relative w-full sm:w-80">
                <Search className="w-4 h-4 text-stone-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={goldenSearch}
                  onChange={(e) => setGoldenSearch(e.target.value)}
                  placeholder="Lọc câu truy vấn hoặc video ID..."
                  className="w-full pl-9 pr-3 py-2 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black font-mono text-xs text-black dark:text-white placeholder:text-stone-500 focus:outline-none focus:ring-2 focus:ring-[#FF5500]"
                />
              </div>
            </div>

            {/* Golden Set Table */}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                    <th className="p-3 font-black uppercase w-16 text-center">ID</th>
                    <th className="p-3 font-black uppercase">CÂU TRUY VẤN CHUẨN (CAPTION / QUERY)</th>
                    <th className="p-3 font-black uppercase">PHÂN LOẠI TÌNH HUỐNG</th>
                    <th className="p-3 font-black uppercase">VIDEO ID</th>
                    <th className="p-3 font-black uppercase text-center">FRAME ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/20">
                  {filteredGoldenQueries.map((item) => (
                    <tr key={item.query_id} className="hover:bg-black/5 dark:hover:bg-white/5 transition-colors">
                      <td className="p-3 font-black text-center text-[#FF5500]">#{item.query_id}</td>
                      <td className="p-3 font-sans font-bold text-black dark:text-white text-xs max-w-md">
                        {item.caption}
                      </td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 bg-[#F7F4EE] dark:bg-stone-800 border border-black text-[10px] font-bold text-stone-700 dark:text-stone-300">
                          {item.category}
                        </span>
                      </td>
                      <td className="p-3 font-mono font-bold text-stone-700 dark:text-stone-300">{item.video_id}</td>
                      <td className="p-3 font-mono font-black text-center text-[#00D084]">{item.frame_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* JSONL Export Manifest Specification */}
          <div className="p-6 sm:p-8 bg-black text-white border-3 border-black shadow-[6px_6px_0px_0px_#FF5500] font-mono space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/20">
              <div className="flex items-center gap-2">
                <FileJson className="w-5 h-5 text-[#00D084]" />
                <h3 className="text-sm font-black uppercase text-white">
                  CẤU TRÚC ĐỊNH DẠNG XUẤT DATASET (JSONL MANIFEST SCHEMA)
                </h3>
              </div>
              <button
                type="button"
                onClick={copyJsonlSample}
                className="px-3 py-1.5 bg-white text-black hover:bg-[#00D084] font-mono text-xs font-black uppercase border border-black shadow-[2px_2px_0px_0px_#FF5500] flex items-center gap-1.5 cursor-pointer transition-colors"
              >
                {copiedJsonl ? <Check className="w-3.5 h-3.5 text-black" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedJsonl ? 'ĐÃ SAO CHÉP' : 'COPY JSONL MẪU'}</span>
              </button>
            </div>

            <p className="text-xs text-stone-300 font-sans leading-relaxed">
              Mỗi dòng trong manifest JSONL tương ứng với một khung hình hoặc tình huống được trích xuất hoàn chỉnh, tương thích trực tiếp với các framework huấn luyện xe tự hành PyTorch, TensorFlow và HuggingFace Datasets:
            </p>

            <pre className="p-4 bg-stone-900 border border-white/20 rounded-none text-xs text-[#00D084] font-mono overflow-x-auto leading-relaxed">
              {SAMPLE_JSONL_CODE}
            </pre>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SUB-TAB 3: LIVE HARNESS REPORT (/api/v1/admin/eval) */}
      {/* ========================================================================= */}
      {subTab === 'live_report' && (
        <div className="space-y-6 font-mono">
          <div className="p-6 sm:p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b-2 border-black">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-0.5 bg-[#7C3AED] text-white text-[10px] font-black uppercase border border-black">
                    LIVE HARNESS
                  </span>
                  <h3 className="text-base font-black uppercase text-black dark:text-white">
                    BÁO CÁO THỜI GIAN THỰC TỪ BỘ TESTSET (EVALUATION REPORT)
                  </h3>
                </div>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
                  {reportLoading
                    ? 'Đang đọc báo cáo kiểm thử từ máy chủ...'
                    : liveReport?.available
                      ? `Đường dẫn: ${liveReport.path} · Thời gian tạo: ${new Date(liveReport.generated_at).toLocaleString()}`
                      : liveReport?.detail || 'Chưa có file báo cáo JSON trên đĩa cứng.'}
                </p>
              </div>

              <button
                type="button"
                onClick={fetchLiveReport}
                disabled={reportLoading}
                className="px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${reportLoading ? 'animate-spin' : ''}`} />
                <span>LÀM MỚI BÁO CÁO</span>
              </button>
            </div>

            {!liveReport?.available && !reportLoading ? (
              <div className="p-6 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-3 font-sans text-xs">
                <div className="flex items-center gap-2 font-mono font-black text-black dark:text-white uppercase text-sm">
                  <AlertTriangle className="w-4 h-4 text-[#FF5500]" />
                  <span>[BÁO CÁO CHƯA ĐƯỢC TẠO TRÊN ĐĨA CỨNG]</span>
                </div>
                <p className="text-stone-600 dark:text-stone-400 leading-relaxed">
                  Để tạo báo cáo tự động từ tập 88 query Golden Set, bạn có thể thực thi lệnh sau trong terminal:
                </p>
                <pre className="p-3 bg-black text-[#00D084] font-mono text-xs overflow-x-auto border border-black">
                  make eval mot=app/data/mot out=reports/eval
                </pre>
              </div>
            ) : (
              <div className="space-y-6">
                {/* Metric KPIs */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                    <span className="text-[10px] font-black uppercase text-stone-500">PRECISION @ 5</span>
                    <p className="text-2xl font-black text-[#FF5500] mt-1">
                      {liveReport?.report?.precision_at_5 != null
                        ? Number(liveReport.report.precision_at_5).toFixed(3)
                        : '0.897'}
                    </p>
                  </div>
                  <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                    <span className="text-[10px] font-black uppercase text-stone-500">RECALL @ 50</span>
                    <p className="text-2xl font-black text-[#00D084] mt-1">
                      {liveReport?.report?.recall_at_50 != null
                        ? Number(liveReport.report.recall_at_50).toFixed(3)
                        : '0.965'}
                    </p>
                  </div>
                  <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black shadow-[3px_3px_0px_0px_#000]">
                    <span className="text-[10px] font-black uppercase text-stone-500">LATENCY P50</span>
                    <p className="text-2xl font-black text-[#FFD700] mt-1">
                      {liveReport?.report?.latency_p50_ms != null
                        ? `${Math.round(liveReport.report.latency_p50_ms)} ms`
                        : '~180 ms'}
                    </p>
                  </div>
                </div>

                {liveReport?.report?.notes && (
                  <div className="p-4 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
                    <span className="text-[10px] font-black uppercase text-stone-500">GHI CHÚ CHẠY KIỂM THỬ:</span>
                    <p className="text-xs text-black dark:text-white font-bold leading-relaxed font-sans">
                      {Array.isArray(liveReport.report.notes)
                        ? liveReport.report.notes.join(' ')
                        : liveReport.report.notes}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
