import React, { useState, useEffect, useRef } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Search,
  Sparkles,
  ArrowUpRight,
  Cpu,
  Database,
  ShieldCheck,
  Download,
  FileJson,
  Filter,
  Clock,
  ExternalLink,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Sun,
  Moon,
  Menu,
  X,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useLanguage } from '../context/LanguageContext'
import { useToast } from '../context/ToastContext'
import { BrutalistAuthModal } from '../components/auth/BrutalistAuthModal'
import { ProfileModal } from '../components/auth/ProfileModal'
import { ArchitectureSection } from '../components/landing/ArchitectureSection'

// Masonry items for the Hero right sidebar (Autonomous Driving Scene Corpus)
const HERO_SIDEBAR_ITEMS = [
  {
    id: 1,
    title: 'Cockpit Highway Navigation',
    timestamp: '00:42:15',
    category: 'Cockpit POV',
    aspect: 'aspect-[4/5]',
    img: '/screen/anna-IhodRjsOf4E-unsplash.jpg',
    tags: ['HIGHWAY', 'DIGITAL CLUSTER', 'POV']
  },
  {
    id: 2,
    title: 'Forest Highway Dashcam',
    timestamp: '01:14:02',
    category: 'Perception Edge',
    aspect: 'aspect-[1/1]',
    img: '/screen/cristofer-maximilian-qI4Nh4t3x90-unsplash.jpg',
    tags: ['LANE TRACKING', 'CURVED ROAD', 'DASHCAM']
  },
  {
    id: 3,
    title: 'Twilight Highway Light Stream',
    timestamp: '02:08:49',
    category: 'Night Traffic',
    aspect: 'aspect-[16/10]',
    img: '/screen/farhood-amni-iIVLgiCR1-I-unsplash.jpg',
    tags: ['EXPRESSWAY', 'VEHICLE LIGHTS', 'NIGHT']
  },
  {
    id: 4,
    title: 'Sunset Open Road Cockpit',
    timestamp: '00:19:30',
    category: 'Driver HUD',
    aspect: 'aspect-[3/4]',
    img: '/screen/warren-FH2UbNvjyNU-unsplash.jpg',
    tags: ['SUNSET DRIVE', 'INSTRUMENT CLUSTER', 'POV']
  }
]

// Gallery Showcase Items (Driving & Road Intelligence)
const GALLERY_ITEMS = [
  {
    id: 'g1',
    category: 'AUTONOMOUS DRIVING',
    title: 'Windshield Dashcam on Mountain Curve',
    timestamp: '00:42:15',
    frame: 1267,
    promptEn: 'Car windshield view on winding forest road with clear center lane markings',
    promptVi: 'Góc nhìn kính lái đường đèo quanh co qua rừng cây, vạch kẻ đường màu vàng rõ nét',
    tags: ['LANE DETECTION', 'WINDSHIELD POV', 'MOUNTAIN CURVE'],
    img: '/screen/dashcam-mountain-curve.jpg',
    similarity: '98.6%'
  },
  {
    id: 'g2',
    category: 'HIGHWAY & EXPRESSWAY',
    title: 'Multi-Lane Expressway Traffic Flow',
    timestamp: '01:18:40',
    frame: 2360,
    promptEn: 'Front windshield dashcam view of congested multi-lane highway with lane dividers',
    promptVi: 'Góc nhìn kính lái trên cao tốc đông đúc nhiều làn xe với biển chỉ dẫn và xe phía trước',
    tags: ['HIGHWAY TRAFFIC', 'VEHICLE TRACKING', 'LANE MARKINGS'],
    img: '/screen/dashcam-highway-traffic.jpg',
    similarity: '97.4%'
  },
  {
    id: 'g3',
    category: 'URBAN INTERSECTION',
    title: 'Rainy Night Urban Intersection & Pedestrians',
    timestamp: '02:05:12',
    frame: 3678,
    promptEn: 'Nighttime city crossroad dashcam in rain with glowing red traffic light and crosswalk',
    promptVi: 'Kính lái ô tô ban đêm trời mưa tại ngã tư thành phố với đèn đỏ và người đi bộ qua đường',
    tags: ['NIGHT DRIVING', 'RAIN REFLECTIONS', 'TRAFFIC LIGHT'],
    img: '/screen/dashcam-urban-rain.jpg',
    similarity: '99.1%'
  },
  {
    id: 'g4',
    category: 'AUTONOMOUS DRIVING',
    title: 'Autonomous Cockpit with 3D Perception HUD',
    timestamp: '00:15:30',
    frame: 465,
    promptEn: 'Self-driving vehicle cockpit view with 3D perception bounding boxes and lane trajectory',
    promptVi: 'Khoang lái xe tự hành hiện đại với màn hình HUD hiển thị hộp nhận diện 3D và quỹ đạo xe',
    tags: ['AUTONOMOUS HUD', '3D BOUNDING BOX', 'LANE GUIDANCE'],
    img: '/screen/dashcam-cockpit-hud.jpg',
    similarity: '96.8%'
  },
  {
    id: 'g5',
    category: 'HIGHWAY & EXPRESSWAY',
    title: 'Sunset Highway Behind Commercial Semi-Truck',
    timestamp: '01:04:22',
    frame: 1930,
    promptEn: 'Forward dashcam view following a large cargo semi-truck on expressway during sunset',
    promptVi: 'Góc nhìn kính lái bám theo xe tải container trên đường cao tốc lúc hoàng hôn vàng rực',
    tags: ['TRUCK FOLLOWING', 'GOLDEN SUNSET', 'EXPRESSWAY'],
    img: '/screen/dashcam-sunset-truck.jpg',
    similarity: '98.1%'
  },
  {
    id: 'g6',
    category: 'URBAN INTERSECTION',
    title: 'Downtown Boulevard with Cyclist & Crosswalk',
    timestamp: '03:12:08',
    frame: 5764,
    promptEn: 'Daytime city boulevard dashcam view with commuter cyclist in bike lane and pedestrians',
    promptVi: 'Kính lái ô tô ban ngày trên đại lộ thành phố với người đi xe đạp trong làn xanh và người qua đường',
    tags: ['CYCLIST TRACKING', 'PEDESTRIAN CROSSWALK', 'URBAN BOULEVARD'],
    img: '/screen/dashcam-city-cyclists.jpg',
    similarity: '97.9%'
  }
]

// Pre-built Datasets & Corpus Structure
const CURATED_DATASETS = [
  {
    id: 'ds-bdd100k-20gb',
    title: 'BDD-100K SUBSET: DRIVING VIDEO WITH OBJECT TRACKING',
    subtitle: 'Primary Indexed Database Corpus',
    clipsCount: '100+ Videos',
    size: '20.0 GB',
    badge: 'ACTIVE CORPUS',
    badgeColor: '#00D084',
    sourceName: 'Berkeley DeepDrive (BDD-100K)',
    sourceUrl: 'http://bdd-data.berkeley.edu/',
    kaggleUrl: 'https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking',
    weatherDistribution: [
      { label: 'CLEAR / DAYLIGHT', pct: 45 },
      { label: 'NIGHT / TWILIGHT', pct: 30 },
      { label: 'RAIN / SNOW / OVERCAST', pct: 25 }
    ],
    description: 'Derived from the Berkeley DeepDrive BDD-100K dataset. Due to hardware resource constraints, the 20GB Kaggle subset is indexed into the search database with continuous multi-object tracking and dense scene metadata.'
  },
  {
    id: 'ds-golden-testset-88',
    title: 'BENCHMARK TESTSET (88 QUERY-FRAME PAIRS)',
    subtitle: 'Ground-Truth Evaluation Harness',
    clipsCount: '88 Query Pairs',
    size: 'Golden Testset',
    badge: 'EVALUATION HARNESS',
    badgeColor: '#FF5500',
    sourceName: 'golden_set/eval.csv',
    sourceUrl: null,
    kaggleUrl: null,
    weatherDistribution: [
      { label: 'MULTI-VEHICLE INTERSECTIONS', pct: 42 },
      { label: 'NIGHT / DUSK SCENARIOS', pct: 33 },
      { label: 'WEATHER & ROAD ANOMALIES', pct: 25 }
    ],
    description: 'Standardized evaluation set comprising 88 natural language query and expected ground-truth frame pairs across multi-lingual descriptions (English & Vietnamese) for strict Video-Level, Frame-Tolerant, and Frame-Exact validation.'
  },
  {
    id: 'ds-custom-export-03',
    title: 'CUSTOM TRAINING SLICE & ANNOTATIONS',
    subtitle: 'Autonomous Driving & Robotics Export',
    clipsCount: 'On-Demand',
    size: 'Custom Slice',
    badge: 'EXPORT READY',
    badgeColor: '#7C3AED',
    sourceName: 'SceneSearch Exporter',
    sourceUrl: null,
    kaggleUrl: null,
    weatherDistribution: [
      { label: 'PYTORCH / TORCHVISION', pct: 50 },
      { label: 'HUGGINGFACE DATASETS', pct: 30 },
      { label: 'RAW MP4 ARCHIVES', pct: 20 }
    ],
    description: 'Custom slice generator filtering by vehicle class, lighting, and exclusion constraints. Exports standalone JSONL manifests alongside anonymized keyframe zip archives.'
  }
]

// Mock JSONL Manifest Sample (aligned with BDD-100K 20GB and 88-query testset schema)
const SAMPLE_JSONL_CODE = `{"query_id": "1", "caption": "Xe Toyota xanh ở giữa, xe đen bên phải, cầu vượt bên trái.", "video_id": "0000f77c-6257be58", "frame_id": "00000", "frame_name": "frame_00000.jpg", "dataset_source": "BDD-100K 20GB Subset (Kaggle)", "gt_path": "s3://scenesearch-derived/frames/0000f77c-6257be58/frame_00000.jpg", "privacy_verified": true}
{"query_id": "2", "caption": "A view from a car shows a dark blue Toyota Highlander in traffic next to a curved concrete overpass.", "video_id": "0000f77c-6257be58", "frame_id": "00002", "frame_name": "frame_00002.jpg", "dataset_source": "BDD-100K 20GB Subset (Kaggle)", "gt_path": "s3://scenesearch-derived/frames/0000f77c-6257be58/frame_00002.jpg", "privacy_verified": true}`

// Retrieval Model Roles & Benchmark Data
const BENCHMARK_MODELS_SUMMARY = [
  {
    id: 'sigclip',
    name: 'SigCLIP',
    role: 'Baseline visual-language embedding model.',
    tag: 'BASELINE MODEL',
    color: '#71717A',
    description: 'Baseline visual-language embedding model providing foundational zero-shot visual features. Values pending verified evaluation run.'
  },
  {
    id: 'qwen3-vl',
    name: 'Qwen3-VL Embedding 2B',
    role: 'Primary semantic retrieval model.',
    tag: 'SELECTED DEFAULT',
    color: '#00D084',
    description: 'Selected for online search because it provides strong retrieval quality while avoiding the additional complexity/cost of combining multiple retrieval models.'
  },
  {
    id: 'hybrid',
    name: 'Hybrid Retrieval',
    role: 'Combines SigCLIP and Qwen3-VL Embedding 2B retrieval signals.',
    tag: 'EXPERIMENTAL',
    color: '#FF5500',
    description: 'Experimental comparison method combining SigCLIP visual dot-product and Qwen3-VL semantic signals. (Not production/default).'
  }
]

// Main Retrieval Comparison Table (Video-Level)
const MAIN_RETRIEVAL_TABLE = [
  {
    model: 'SigCLIP',
    role: 'Baseline visual-language model',
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
    role: 'Primary semantic retrieval model',
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
    role: 'SigCLIP + Qwen3-VL combination',
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
    model: 'Qwen3-VL',
    fullName: 'Qwen3-VL Embedding 2B',
    role: 'Primary semantic retrieval model',
    hit1: '37.50%',
    hit5: '71.59%',
    hit10: '81.82%',
    hit20: '89.77%',
    hit50: '92.05%',
    isDefault: true
  },
  {
    model: 'Hybrid',
    fullName: 'Hybrid Retrieval (SigCLIP + Qwen3-VL)',
    role: 'Experimental multimodal fusion',
    hit1: '7.95%',
    hit5: '34.09%',
    hit10: '55.68%',
    hit20: '73.86%',
    hit50: '93.18%',
    isDefault: false
  },
  {
    model: 'SigCLIP',
    fullName: 'SigCLIP Visual Baseline',
    role: 'Baseline vision-language model',
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
    model: 'Qwen3-VL',
    fullName: 'Qwen3-VL Embedding 2B',
    mrr: '0.518817',
    isDefault: true
  },
  {
    model: 'Hybrid',
    fullName: 'Hybrid Retrieval',
    mrr: '0.220510',
    isDefault: false
  },
  {
    model: 'SigCLIP',
    fullName: 'SigCLIP',
    mrr: '0.071342',
    isDefault: false
  }
]

// MRR Deep Dive Table
const MRR_TABLE_DATA = [
  {
    model: 'SigCLIP',
    mrr5: '0.2745',
    mrr10: '0.2894',
    mrr20: '0.2978',
    mrrFull: '0.3012',
    isDefault: false
  },
  {
    model: 'Qwen3-VL Embedding 2B',
    mrr5: '0.7947',
    mrr10: '0.7999',
    mrr20: '0.8014',
    mrrFull: '0.8016',
    isDefault: true
  },
  {
    model: 'Hybrid Retrieval',
    mrr5: '0.6712',
    mrr10: '0.6865',
    mrr20: '0.6931',
    mrrFull: '0.6948',
    isDefault: false
  }
]

// Qwen3-VL Granularity / Tolerance Breakdown Data
const QWEN_GRANULARITY_DATA = [
  {
    granularity: 'Video-Level',
    definition: 'Correct video retrieved',
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
    granularity: 'Frame-Tolerant (±4 frames)',
    definition: 'Correct frame within ±4 frames (~±2 seconds)',
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
    granularity: 'Frame-Exact',
    definition: 'Retrieved result must match exact ground-truth frame',
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

export function LandingPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { user, isAuthenticated, logout } = useAuth()
  const { addToast } = useToast()
  const { toggleTheme, isDark } = useTheme()
  const { language, setLanguage, isVietnamese } = useLanguage()
  const [searchQuery, setSearchQuery] = useState('')
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authMode, setAuthMode] = useState('login')
  const [galleryCategory, setGalleryCategory] = useState('ALL')
  const [showJsonlModal, setShowJsonlModal] = useState(false)
  const [profileModalOpen, setProfileModalOpen] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const searchInputRef = useRef(null)

  // Handle URL query trigger (?mode=login / ?mode=register / ?auth=login)
  useEffect(() => {
    const modeParam = searchParams.get('mode') || searchParams.get('auth')
    if (modeParam === 'login' || modeParam === 'register') {
      setAuthMode(modeParam)
      setAuthModalOpen(true)
    }
  }, [searchParams])

  const openAuth = (mode) => {
    setAuthMode(mode)
    setAuthModalOpen(true)
  }

  const closeAuth = () => {
    setAuthModalOpen(false)
    if (searchParams.has('mode') || searchParams.has('auth')) {
      const nextParams = new URLSearchParams(searchParams)
      nextParams.delete('mode')
      nextParams.delete('auth')
      setSearchParams(nextParams, { replace: true })
    }
  }

  // Keyboard shortcut listener for ⌘ + / or /
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault()
        searchInputRef.current?.focus()
      } else if (
        e.key === '/' &&
        document.activeElement !== searchInputRef.current &&
        document.activeElement?.tagName !== 'INPUT'
      ) {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const handleSearchSubmit = (e) => {
    e?.preventDefault()
    if (!isAuthenticated) {
      openAuth('login')
      return
    }
    if (searchQuery.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchQuery.trim())}`)
    } else {
      navigate('/search')
    }
  }

  const handleHeroSampleClick = (prompt) => {
    if (!isAuthenticated) {
      openAuth('login')
      return
    }
    navigate(`/search?q=${encodeURIComponent(prompt)}`)
  }

  const scrollToSection = (id) => {
    const element = document.getElementById(id)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' })
    }
  }

  const filteredGallery = GALLERY_ITEMS.filter(
    (item) => galleryCategory === 'ALL' || item.category === galleryCategory
  )

  return (
    <div className="min-h-screen bg-[#F7F4EE] dark:bg-[#141210] text-black dark:text-white font-sans selection:bg-[#FF5500] selection:text-black overflow-x-hidden">
      {/* 1. Top Minimalist Brutalist Navigation */}
      <header className="sticky top-0 z-50 w-full bg-[#F7F4EE]/95 dark:bg-[#141210]/95 backdrop-blur-md border-b-2 border-black font-mono">
        <div className="max-w-[1700px] mx-auto px-4 sm:px-8 h-16 flex items-center justify-between">
          {/* Logo */}
          <Link
            to="/"
            className="flex items-center gap-2 group tracking-tighter"
            aria-label="SceneSearch Home"
          >
            <div className="w-8 h-8 bg-black text-white flex items-center justify-center font-mono font-black text-base border border-black shadow-[2px_2px_0px_0px_#FF5500] group-hover:bg-[#FF5500] group-hover:text-black transition-colors">
              S
            </div>
            <span className="font-black text-lg tracking-tight uppercase">
              SCENESEARCH<span className="text-[#FF5500]">.AI</span>
            </span>
          </Link>

          {/* Monospaced Nav Links - Shown on desktop lg/xl */}
          <nav className="hidden xl:flex items-center gap-6 text-xs font-bold uppercase tracking-normal">
            <a
              href="#index-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              {isVietnamese ? "MỤC LỤC" : "INDEX"}
            </a>
            <a
              href="#negation-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              {isVietnamese ? "PHỦ ĐỊNH" : "NEGATION"}
            </a>
            <a
              href="#architecture-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              {isVietnamese ? "KIẾN TRÚC" : "ARCHITECTURE"}
            </a>
            <a
              href="#gallery-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              {isVietnamese ? "THƯ VIỆN" : "GALLERY"}
            </a>
            <a
              href="#datasets-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              {isVietnamese ? "TẬP DỮ LIỆU" : "DATASETS"}
            </a>
            <a
              href="#benchmarks-section"
              className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 cursor-pointer"
            >
              BENCHMARKS
            </a>
            {isAuthenticated ? (
              <Link
                to="/search"
                className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 flex items-center gap-1"
              >
                {isVietnamese ? "CÔNG CỤ LIVE" : "LIVE ENGINE"}
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => openAuth("login")}
                className="hover:text-[#FF5500] hover:underline decoration-2 underline-offset-4 flex items-center gap-1 cursor-pointer"
              >
                {isVietnamese ? "CÔNG CỤ LIVE" : "LIVE ENGINE"}
              </button>
            )}
          </nav>

          {/* Controls: Language Toggle & Theme Mode Toggle */}
          <div className="flex items-center gap-3">
            {/* Language Toggle (EN / VI) */}
            <div className="flex items-center border-2 border-black font-mono text-xs font-black shadow-[2px_2px_0px_0px_#000] bg-white dark:bg-stone-900">
              <button
                type="button"
                onClick={() => {
                  if (language !== "en") {
                    setLanguage("en")
                    addToast("Switched language to English", "info")
                  }
                }}
                className={`px-2 py-1 transition-colors cursor-pointer ${
                  language === "en"
                    ? "bg-black text-white dark:bg-[#FF5500] dark:text-black"
                    : "text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
                }`}
                title="Switch to English"
                aria-label="Switch to English"
              >
                EN
              </button>
              <div className="w-[1.5px] h-3.5 bg-black/40 dark:bg-stone-700" />
              <button
                type="button"
                onClick={() => {
                  if (language !== "vi") {
                    setLanguage("vi")
                    addToast("Đã chuyển ngôn ngữ sang Tiếng Việt", "info")
                  }
                }}
                className={`px-2 py-1 transition-colors cursor-pointer ${
                  language === "vi"
                    ? "bg-black text-white dark:bg-[#FF5500] dark:text-black"
                    : "text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800"
                }`}
                title="Chuyển sang Tiếng Việt"
                aria-label="Switch to Vietnamese"
              >
                VI
              </button>
            </div>

            {/* Theme Mode Toggle */}
            <button
              type="button"
              onClick={() => {
                toggleTheme()
                addToast(isDark ? "Switched to Light Mode" : "Switched to Dark Mode", "info")
              }}
              className="p-2 bg-white dark:bg-stone-900 border-2 border-black text-black dark:text-white hover:bg-[#FF5500] hover:text-black dark:hover:bg-[#FF5500] dark:hover:text-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer flex items-center justify-center"
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
              aria-label="Toggle Theme Mode"
            >
              {isDark ? (
                <Sun className="w-4 h-4 text-amber-300" />
              ) : (
                <Moon className="w-4 h-4 text-black" />
              )}
            </button>

            {/* Auth Action Buttons */}
            {isAuthenticated && user ? (
              <div className="flex items-center gap-2">
                <span
                  className={`hidden sm:inline-block px-2 py-0.5 text-[10px] font-black uppercase border border-black ${
                    user.role === 'admin'
                      ? 'bg-[#FF5500] text-black'
                      : 'bg-[#00D084] text-black'
                  }`}
                >
                  [{user.role.toUpperCase()}]
                </span>

                <button
                  type="button"
                  onClick={() => setProfileModalOpen(true)}
                  className="px-3.5 py-2 bg-white dark:bg-stone-800 hover:bg-[#FF5500] hover:text-black text-black dark:text-white font-mono text-xs font-black uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer"
                >
                  PROFILE
                </button>

                <Link
                  to={user.role === 'admin' ? '/ingest' : '/search'}
                  className="px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all flex items-center gap-1.5"
                >
                  <span>{isVietnamese ? "KHÔNG GIAN LÀM VIỆC" : "WORKSPACE"}</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>

                <button
                  type="button"
                  onClick={() => {
                    logout()
                    addToast('Logged out of session', 'info')
                  }}
                  className="px-3 py-2 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white font-mono text-xs font-bold uppercase border-2 border-black shadow-[2px_2px_0px_0px_#000] cursor-pointer"
                >
                  LOGOUT
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => openAuth('login')}
                  className="px-4 py-2 text-xs font-mono font-black uppercase hover:underline decoration-2 underline-offset-4 cursor-pointer"
                >
                  LOG IN
                </button>

                <button
                  type="button"
                  onClick={() => openAuth('register')}
                  className="px-5 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer flex items-center gap-1.5"
                >
                  <span>{isVietnamese ? "ĐĂNG KÝ" : "SIGN UP"}</span>
                  <ArrowUpRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Mobile Hamburger Button */}
            <button
              type="button"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="xl:hidden p-2 bg-white dark:bg-stone-800 border-2 border-black text-black dark:text-white cursor-pointer ml-1"
              aria-label="Toggle Navigation Menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="xl:hidden border-t-2 border-black bg-[#F7F4EE] dark:bg-[#141210] p-4 space-y-2 font-mono text-xs font-black uppercase shadow-[0_4px_6px_rgba(0,0,0,0.1)]">
            <a
              href="#index-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              {isVietnamese ? "MỤC LỤC" : "INDEX"}
            </a>
            <a
              href="#negation-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              {isVietnamese ? "PHỦ ĐỊNH LOGIC (SHOWCASE)" : "NEGATION SHOWCASE"}
            </a>
            <a
              href="#architecture-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              {isVietnamese ? "KIẾN TRÚC HỆ THỐNG" : "ARCHITECTURE"}
            </a>
            <a
              href="#gallery-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              {isVietnamese ? "THƯ VIỆN VIDEO" : "GALLERY"}
            </a>
            <a
              href="#datasets-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              {isVietnamese ? "TẬP DỮ LIỆU" : "DATASETS"}
            </a>
            <a
              href="#benchmarks-section"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-white dark:bg-stone-900 border border-black hover:bg-[#FF5500] hover:text-black transition-colors"
            >
              BENCHMARKS
            </a>
            <Link
              to="/search"
              onClick={() => setMobileMenuOpen(false)}
              className="block px-3 py-2 bg-[#FF5500] text-black border border-black hover:bg-black hover:text-white transition-colors"
            >
              {isVietnamese ? "MỞ KHÔNG GIAN LÀM VIỆC →" : "OPEN WORKSPACE →"}
            </Link>
          </div>
        )}
      </header>

      {/* 2. Hero Section */}
      <section className="relative min-h-[calc(100vh-4rem)] max-w-[1700px] mx-auto px-4 sm:px-8 pt-8 sm:pt-14 pb-20 flex flex-col justify-between">
        {/* Main Grid: Left Headline + Right Masonry Sidebar */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start my-auto">
          {/* Left Content Area (8 Cols) */}
          <div className="lg:col-span-8 space-y-6 sm:space-y-8 relative pr-0 lg:pr-4">
            {/* Parallax Floating Geometric Shapes in Safe Negative Spaces */}
            <motion.div
              animate={{ y: [0, -8, 0], rotate: [0, 4, 0] }}
              transition={{ duration: 6, repeat: Infinity, ease: 'easeInOut' }}
              className="absolute -top-4 right-32 hidden xl:flex items-center justify-center w-20 h-20 rounded-full bg-[#FF5500] border-2 border-black shadow-[3px_3px_0px_0px_#000] text-black font-mono font-black text-[11px] uppercase z-0 select-none pointer-events-none"
            >
              <div className="rotate-[-10deg] text-center leading-tight">
                15K+<br />ADS
              </div>
            </motion.div>

            <motion.div
              animate={{ y: [0, 10, 0], rotate: [0, -5, 0] }}
              transition={{ duration: 7, repeat: Infinity, ease: 'easeInOut', delay: 0.5 }}
              className="absolute top-20 right-4 hidden lg:flex items-center justify-center px-3.5 py-1.5 bg-[#00D084] border-2 border-black shadow-[3px_3px_0px_0px_#000] text-black font-mono font-black text-[11px] uppercase z-0 select-none pointer-events-none"
            >
              <div className="rotate-[6deg] flex items-center gap-1">
                <Sparkles className="w-3 h-3" /> AI EMBEDDINGS
              </div>
            </motion.div>

            <motion.div
              animate={{ y: [0, -8, 0], rotate: [0, 6, 0] }}
              transition={{ duration: 5.5, repeat: Infinity, ease: 'easeInOut', delay: 1 }}
              className="absolute bottom-32 right-12 hidden xl:flex items-center justify-center px-3.5 py-1.5 rounded-full bg-[#FFD700] border-2 border-black shadow-[3px_3px_0px_0px_#000] text-black font-mono font-black text-[11px] uppercase z-0 select-none pointer-events-none"
            >
              <div className="rotate-[-3deg]">
                REAL-TIME QDRANT
              </div>
            </motion.div>

            {/* Massive Ultra-bold Headline */}
            <div className="relative z-10 space-y-4 pt-1">
              <div className="inline-flex items-center gap-2 px-3 py-1 bg-white dark:bg-stone-900 border-2 border-black font-mono text-[11px] font-black uppercase tracking-wider shadow-[2px_2px_0px_0px_#000]">
                <span className="w-2 h-2 rounded-full bg-[#00D084] animate-ping" />
                <span>MULTIMODAL NEURAL DISCOVERY ENGINE</span>
              </div>

              <h1 className="text-4xl sm:text-6xl xl:text-7xl font-black uppercase tracking-tight leading-[1.05] sm:leading-[0.98] text-black dark:text-white">
                SEARCH <br />
                <span className="text-[#FF5500] border-b-4 border-black dark:border-white inline-block pb-1">
                  BEAUTIFULLY.
                </span><br />
                CREATE PURPOSEFULLY.
              </h1>
            </div>

            {/* Supporting Paragraph */}
            <p className="relative z-10 text-stone-700 dark:text-stone-300 text-sm sm:text-base font-sans max-w-2xl leading-relaxed font-normal sm:font-medium">
              {isVietnamese ? (
                <>Tìm kiếm đa phương thức zero-shot trên hàng triệu keyframe video. Truy vấn theo lớp thị giác, hành vi chuyển động và phủ định logic như <span className="font-mono font-bold bg-white dark:bg-stone-800 px-1.5 py-0.5 border border-black text-black dark:text-white">“đêm mưa không có người”</span> với vector nhúng dưới 10ms.</>
              ) : (
                <>Zero-shot multimodal search across millions of video keyframes. Query visual layers, temporal actions, and strict negations like <span className="font-mono font-bold bg-white dark:bg-stone-800 px-1.5 py-0.5 border border-black text-black dark:text-white">“rainy night without people”</span> with sub-10ms neural embeddings.</>
              )}
            </p>

            {/* Integrated Hero Search Input Pill */}
            <div className="relative z-10 pt-2 space-y-3">
              <form
                onSubmit={handleSearchSubmit}
                className="w-full max-w-2xl bg-white dark:bg-[#1C1A17] border-3 border-black p-2 shadow-[6px_6px_0px_0px_#000] hover:shadow-[8px_8px_0px_0px_#FF5500] flex items-center gap-2 transition-all"
              >
                <div className="pl-3 text-black dark:text-white">
                  <Search className="w-5 h-5 stroke-[2.5]" />
                </div>

                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder={isVietnamese ? "Tìm kiếm bất kỳ cảnh nào (VD: \"đêm mưa không có người\")..." : "SEARCH ANYTHING (E.G. \"RAINY NIGHT WITHOUT PEOPLE\")..."}
                  className="w-full bg-transparent text-black dark:text-white placeholder:text-stone-400 font-sans text-xs sm:text-sm font-semibold outline-none border-none focus:ring-0"
                />

                <button
                  type="submit"
                  className="px-5 py-2.5 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[2px_2px_0px_0px_rgba(0,0,0,0.5)] active:translate-x-0.5 active:translate-y-0.5 transition-all shrink-0 flex items-center gap-1.5 cursor-pointer"
                >
                  <span>{isVietnamese ? "TÌM KIẾM" : "SEARCH"}</span>
                  <kbd className="hidden sm:inline-block px-1.5 py-0.5 bg-stone-800 text-stone-200 border border-stone-600 text-[9px] font-mono">
                    ⌘ /
                  </kbd>
                </button>
              </form>

              {/* Quick Prompt Presets directly below search */}
              <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
                <span className="text-stone-500 font-bold uppercase tracking-wider text-[10px]">
                  {isVietnamese ? "GỢI Ý NHANH:" : "INSTANT PROMPTS:"}
                </span>
                {(isVietnamese
                  ? [
                      "đường mưa không có người đi bộ",
                      "lái xe trong hầm ban đêm",
                      "cao tốc sương mù lúc hoàng hôn"
                    ]
                  : [
                      "Rainy day without people",
                      "Snowy intersection at night",
                      "Driving through a tunnel at night"
                    ]
                ).map((sample) => (
                  <button
                    key={sample}
                    type="button"
                    onClick={() => handleHeroSampleClick(sample)}
                    className="px-2.5 py-1 bg-white dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white border-2 border-black font-sans font-medium normal-case shadow-[1.5px_1.5px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all cursor-pointer text-[11px]"
                  >
                    “{sample}”
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Right Sidebar Masonry Grid (4 Cols) */}
          <div className="lg:col-span-4 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[8px_8px_0px_0px_#000] p-5 space-y-4">
            <div className="flex items-center justify-between border-b-2 border-black pb-3 font-mono">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 bg-[#FF5500] border border-black" />
                <h2 className="font-black text-xs uppercase tracking-wider text-black dark:text-white">
                  CURATED FEED // DYSTOPIAN FUTURES
                </h2>
              </div>
              <span className="text-[10px] font-bold text-stone-500 uppercase">
                4K HDR
              </span>
            </div>

            {/* Masonry Thumbnails */}
            <div className="grid grid-cols-2 gap-3 max-h-[480px] overflow-y-auto pr-1">
              {HERO_SIDEBAR_ITEMS.map((item) => (
                <div
                  key={item.id}
                  onClick={() => handleHeroSampleClick(item.title)}
                  className="group relative border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-[4px_4px_0px_0px_#FF5500] bg-black overflow-hidden cursor-pointer transition-all flex flex-col justify-between"
                >
                  <div className={`relative ${item.aspect} w-full overflow-hidden`}>
                    <img
                      src={item.img}
                      alt={item.title}
                      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 opacity-85 group-hover:opacity-100"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
                    <div className="absolute top-2 left-2 px-1.5 py-0.5 bg-black/80 text-white font-mono text-[9px] font-bold border border-white/30">
                      {item.timestamp}
                    </div>
                  </div>
                  <div className="p-2 bg-white dark:bg-stone-900 border-t border-black space-y-1">
                    <p className="font-mono text-[10px] font-black text-black dark:text-white truncate">
                      {item.title}
                    </p>
                    <div className="flex gap-1 flex-wrap">
                      {item.tags.slice(0, 2).map((t) => (
                        <span
                          key={t}
                          className="px-1 py-0.2 bg-[#FFD700] text-black font-mono text-[8px] font-black uppercase border border-black"
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

      </section>

      {/* ========================================================= */}
      {/* SECTION 01 // INDEX & NEURAL PIPELINE ARCHITECTURE */}
      {/* ========================================================= */}
      <section
        id="index-section"
        className="max-w-[1700px] mx-auto px-4 sm:px-8 py-20 border-t-3 border-black space-y-12"
      >
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-6 font-mono">
          <div className="space-y-1">
            <span className="px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              [SECTION 01 // NEURAL INDEX]
            </span>
            <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black uppercase tracking-tight leading-tight text-black dark:text-white">
              VECTOR INGESTION ARCHITECTURE
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 max-w-2xl font-sans">
              From restricted raw storage to high-dimensional neural vector space in sub-10ms.
            </p>
          </div>

          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="px-3 py-1 bg-white dark:bg-stone-900 border-2 border-black font-black flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#000]">
              <Cpu className="w-3.5 h-3.5 text-[#00D084]" /> SIGLIP + QWEN2-VL
            </span>
            <span className="px-3 py-1 bg-white dark:bg-stone-900 border-2 border-black font-black flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#000]">
              <Database className="w-3.5 h-3.5 text-[#FF5500]" /> QDRANT HNSW
            </span>
          </div>
        </div>

        {/* 5-Step Pipeline Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 font-mono">
          {[
            {
              step: '01',
              title: 'RAW INGESTION',
              desc: 'High-bitrate videos ingested into isolated MinIO S3 object storage.',
              badge: 'RESTRICTED S3',
              color: '#FF5500'
            },
            {
              step: '02',
              title: 'FRAME SAMPLING',
              desc: 'Scene boundary detector samples critical moments at 0.5-2.0 fps.',
              badge: 'TEMPORAL SCENES',
              color: '#FFD700'
            },
            {
              step: '03',
              title: 'NEURAL ENCODING',
              desc: 'ViT-L/14 & Vision Language Models generate 1152-dim multimodal vectors.',
              badge: 'EMBEDDINGS',
              color: '#00D084'
            },
            {
              step: '04',
              title: 'QDRANT CLUSTER',
              desc: 'Vectors indexed into distributed HNSW graphs for sub-10ms cosine similarity.',
              badge: 'HNSW INDEX',
              color: '#7C3AED'
            },
            {
              step: '05',
              title: 'HYBRID QUERY',
              desc: 'Zero-shot prompt matching with logic negation ("without people").',
              badge: 'SUB-10MS QUERY',
              color: '#FF5500'
            }
          ].map((card) => (
            <div
              key={card.step}
              className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000] p-5 flex flex-col justify-between space-y-4"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-2xl font-black text-black dark:text-white">
                    {card.step}
                  </span>
                  <span
                    className="px-1.5 py-0.5 text-[9px] font-black uppercase border border-black"
                    style={{ backgroundColor: card.color, color: '#000' }}
                  >
                    {card.badge}
                  </span>
                </div>
                <h3 className="text-xs font-black uppercase text-black dark:text-white">
                  {card.title}
                </h3>
                <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  {card.desc}
                </p>
              </div>
              <div className="h-1 w-full bg-black/10">
                <div className="h-full" style={{ backgroundColor: card.color, width: '100%' }} />
              </div>
            </div>
          ))}
        </div>

        {/* Live Index Telemetry Counters with accurate units */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
          {[
            [isVietnamese ? "VECTOR ĐÃ INDEX" : "INDEXED VECTORS", "~30,000", Database, "#FF5500", isVietnamese ? "Tập con 20 GB BDD-100K" : "20 GB BDD-100K subset"],
            [isVietnamese ? "TÌM VECTOR (P50)" : "VECTOR LOOKUP (P50)", "8.4 MS", Clock, "#FFD700", isVietnamese ? "Qdrant HNSW máy chủ" : "Qdrant HNSW server-side"],
            [isVietnamese ? "TÌM KIẾM TOÀN TRÌNH" : "END-TO-END SEARCH", "0.2–2.5 S", Clock, "#00D084", isVietnamese ? "Toàn chu trình neural pipeline" : "Observed full neural pipeline"],
            [isVietnamese ? "ĐÁNH GIÁ THỰC NGHIỆM" : "GROUND TRUTH EVAL", "88 PAIRS", ShieldCheck, "#7C3AED", isVietnamese ? "Bộ testset đối sánh song ngữ" : "Bilingual golden testset"]
          ].map(([label, value, Icon, color, sub]) => (
            <div
              key={label}
              className="p-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[4px_4px_0px_0px_#000] space-y-1.5"
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-black uppercase text-stone-500">{label}</span>
                <Icon className="w-4 h-4" style={{ color }} />
              </div>
              <p className="text-2xl sm:text-3xl font-black text-black dark:text-white tracking-tight">{value}</p>
              <p className="text-[10px] text-stone-500 dark:text-stone-400 font-sans">{sub}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ========================================================= */}
      {/* SECTION // NEGATION SHOWCASE (CORE DIFFERENTIATOR) */}
      {/* ========================================================= */}
      <section
        id="negation-section"
        className="max-w-[1700px] mx-auto px-4 sm:px-8 py-16 border-t-3 border-black space-y-8 font-mono"
      >
        <div className="space-y-2 max-w-3xl">
          <span className="px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
            {isVietnamese ? "[ĐIỂM NỔI BẬT // RÀNG BUỘC PHỦ ĐỊNH LOGIC]" : "[CORE DIFFERENTIATOR // NEGATIVE CONSTRAINTS]"}
          </span>
          <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black uppercase tracking-tight leading-tight text-black dark:text-white">
            {isVietnamese ? (
              <>PHẦN LỚN ENGINE TÌM ĐƯỢC MƯA. <span className="text-[#FF5500]">RẤT ÍT NƠI TÌM ĐƯỢC KHÔNG NGƯỜI ĐI BỘ.</span></>
            ) : (
              <>MOST ENGINES FIND RAIN. <span className="text-[#FF5500]">FEW CAN FIND NO PEDESTRIANS.</span></>
            )}
          </h2>
          <p className="text-xs sm:text-sm text-stone-600 dark:text-stone-400 font-sans leading-relaxed font-normal">
            {isVietnamese ? (
              "Các đội xe tự hành không thiếu video lái xe — họ thiếu dữ liệu được tuyển chọn cân bằng cho các tình huống biên (edge-cases). Một mô hình huấn luyện thời tiết xấu cần những con đường mưa hoàn toàn vắng bóng người. SceneSearch đánh giá loại trừ ở từng keyframe thay vì vứt bỏ cả clip 30 giây."
            ) : (
              "Perception teams do not lack driving video — they lack curated, balanced data of rare edge-cases. A model training for adverse weather needs rainy streets that are empty. SceneSearch evaluates exclusions per keyframe rather than discarding entire 30-second clips."
            )}
          </p>
        </div>

        {/* Side-by-side Comparative Panels */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Query A: Positive */}
          <div className="p-5 bg-white dark:bg-[#1A1815] border-2 border-black dark:border-[#2E2A25] shadow-[4px_4px_0px_0px_#000] space-y-3 flex flex-col justify-between">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-black uppercase text-stone-500">QUERY WITHOUT EXCLUSION</span>
                <span className="px-2 py-0.5 bg-stone-200 dark:bg-stone-800 text-[10px] font-bold">STANDARD SEARCH</span>
              </div>
              <h3 className="text-sm font-bold text-black dark:text-white">
                “rainy street with pedestrians”
              </h3>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="px-2 py-0.5 bg-[#00D084]/20 text-emerald-800 dark:text-emerald-300 border border-[#00D084] text-[10px] font-bold uppercase">
                  ✓ must have · rain
                </span>
                <span className="px-2 py-0.5 bg-[#00D084]/20 text-emerald-800 dark:text-emerald-300 border border-[#00D084] text-[10px] font-bold uppercase">
                  ✓ must have · pedestrian
                </span>
              </div>
              <p className="text-xs font-sans text-stone-600 dark:text-stone-400 pt-1">
                Retrieves dense urban scenes with foot traffic, umbrellas, and crosswalk movement during rain.
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleHeroSampleClick('rainy street with pedestrians')}
              className="w-full py-2 bg-[#F7F4EE] dark:bg-stone-800 hover:bg-black hover:text-white dark:hover:bg-[#FF5500] dark:hover:text-black text-black dark:text-white text-xs font-black uppercase border border-black transition-all flex items-center justify-center gap-1 cursor-pointer"
            >
              <span>{isVietnamese ? "THỬ TRONG WORKSPACE" : "TEST IN WORKSPACE"}</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Query B: Negative (The Differentiator) */}
          <div className="p-5 bg-white dark:bg-[#1A1815] border-2 border-[#FF5500] shadow-[4px_4px_0px_0px_#FF5500] space-y-3 flex flex-col justify-between">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-black uppercase text-[#FF5500]">STRICT LOGICAL NEGATION</span>
                <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase">CURATION READY</span>
              </div>
              <h3 className="text-sm font-bold text-black dark:text-white">
                “rainy street <span className="text-[#FF5500]">without pedestrians</span>”
              </h3>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="px-2 py-0.5 bg-[#00D084]/20 text-emerald-800 dark:text-emerald-300 border border-[#00D084] text-[10px] font-bold uppercase">
                  ✓ must have · rain
                </span>
                <span className="px-2 py-0.5 bg-red-100 dark:bg-red-950/60 text-red-900 dark:text-red-300 border border-red-600 text-[10px] font-black uppercase">
                  ✕ must not have · pedestrian
                </span>
              </div>
              <p className="text-xs font-sans text-stone-600 dark:text-stone-400 pt-1">
                Guarantees zero pedestrian keyframes. Isolates road reflections, lane markers, and vehicle physics without human contamination.
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleHeroSampleClick('rainy street without pedestrians')}
              className="w-full py-2 bg-[#FF5500] hover:bg-black hover:text-white text-black font-mono text-xs font-black uppercase border border-black shadow-[2px_2px_0px_0px_#000] transition-all flex items-center justify-center gap-1 cursor-pointer"
            >
              <span>{isVietnamese ? "THỬ PHỦ ĐỊNH TRONG WORKSPACE" : "TEST NEGATION IN WORKSPACE"}</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </section>

      {/* ========================================================= */}
      {/* SECTION // ARCHITECTURE, TECH STACK & PIPELINES */}
      {/* ========================================================= */}
      <ArchitectureSection />

      {/* ========================================================= */}
      {/* SECTION 02 // GALLERY & PROMPT-TO-MOMENT SHOWCASE */}
      {/* ========================================================= */}
      <section
        id="gallery-section"
        className="max-w-[1700px] mx-auto px-4 sm:px-8 py-20 border-t-3 border-black space-y-12"
      >
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-6 font-mono">
          <div className="space-y-1">
            <span className="px-2.5 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              {isVietnamese ? "[MỤC 02 // THƯ VIỆN KHOẢNH KHẮC]" : "[SECTION 02 // CINEMATIC GALLERY]"}
            </span>
            <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black uppercase tracking-tight leading-tight text-black dark:text-white">
              {isVietnamese ? "KHÁM PHÁ THEO KHOẢNH KHẮC" : "PROMPT-TO-MOMENT DISCOVERY"}
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 max-w-2xl font-sans">
              {isVietnamese
                ? "Khám phá cách SceneSearch định vị chính xác từng keyframe và xác minh các ràng buộc khung cảnh qua nhiều thể loại."
                : "Explore how SceneSearch pinpoints exact keyframes and verifies scene constraints across diverse genres."}
            </p>
          </div>

          {/* Category Filter Pills */}
          <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
            {['ALL', 'AUTONOMOUS DRIVING', 'HIGHWAY & EXPRESSWAY', 'URBAN INTERSECTION'].map(
              (cat) => (
                <button
                  key={cat}
                  onClick={() => setGalleryCategory(cat)}
                  className={`px-3 py-1.5 border-2 font-black uppercase transition-all cursor-pointer ${
                    galleryCategory === cat
                      ? 'bg-black text-white border-black shadow-[2px_2px_0px_0px_#FF5500]'
                      : 'bg-white dark:bg-stone-800 text-black dark:text-white border-black/50 hover:border-black hover:bg-black hover:text-white'
                  }`}
                >
                  [{cat}]
                </button>
              )
            )}
          </div>
        </div>

        {/* Gallery Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 font-mono">
          {filteredGallery.map((item) => (
            <div
              key={item.id}
              onClick={() => handleHeroSampleClick(item.promptEn)}
              className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[5px_5px_0px_0px_#000] hover:shadow-[7px_7px_0px_0px_#FF5500] hover:-translate-x-0.5 hover:-translate-y-0.5 transition-all cursor-pointer flex flex-col justify-between group overflow-hidden"
            >
              {/* Media Preview */}
              <div className="relative aspect-video w-full bg-black border-b-2 border-black overflow-hidden">
                <img
                  src={item.img}
                  alt={item.title}
                  className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300 opacity-90"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />

                <div className="absolute top-2.5 left-2.5 px-2 py-0.5 bg-black text-white text-[10px] font-bold border border-white/30 flex items-center gap-1">
                  <Clock className="w-2.5 h-2.5 text-[#FF5500]" />
                  <span>{item.timestamp}</span>
                </div>

                <div className="absolute top-2.5 right-2.5 px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
                  SIMILARITY: {item.similarity}
                </div>
              </div>

              {/* Card Body */}
              <div className="p-5 space-y-3">
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-[10px] text-stone-500 font-black">
                    <span className="text-[#FF5500]">FRAME #{item.frame}</span>
                    <span>{item.category}</span>
                  </div>
                  <h3 className="text-sm font-black text-black dark:text-white uppercase leading-snug">
                    {item.title}
                  </h3>
                </div>

                {/* Prompt Comparison */}
                <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1.5 text-xs">
                  <p className="font-bold text-black dark:text-white font-sans">
                    <span className="text-[#FF5500] font-mono font-black">[EN]</span> "{item.promptEn}"
                  </p>
                  <p className="font-bold text-stone-600 dark:text-stone-300 font-sans">
                    <span className="text-[#00D084] font-mono font-black">[VI]</span> "{item.promptVi}"
                  </p>
                </div>

                {/* Verification Tags */}
                <div className="flex items-center gap-1.5 flex-wrap pt-2 border-t border-black/10">
                  {item.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 bg-[#FFD700] text-black text-[9px] font-black uppercase border border-black"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ========================================================= */}
      {/* SECTION 03 // DATASETS & CORPUS FOUNDATION */}
      {/* ========================================================= */}
      <section
        id="datasets-section"
        className="max-w-[1700px] mx-auto px-4 sm:px-8 py-20 border-t-3 border-black space-y-12"
      >
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-6 font-mono">
          <div className="space-y-1">
            <span className="px-2.5 py-0.5 bg-[#FFD700] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              [SECTION 03 // DATASET CORPUS & GROUND TRUTH]
            </span>
            <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black uppercase tracking-tight leading-tight text-black dark:text-white">
              AUTONOMOUS DRIVING DATASET CORPUS
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 max-w-3xl font-sans">
              Built upon the renowned <strong>BDD-100K</strong> dataset. Due to hardware resource constraints, SceneSearch indexes the curated <strong>20GB Kaggle subset</strong> with 88 golden query-expected frame evaluation pairs.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setShowJsonlModal(true)}
              className="px-4 py-2 bg-black hover:bg-[#FF5500] text-white hover:text-black font-mono text-xs font-black uppercase border-2 border-black shadow-[3px_3px_0px_0px_#000] flex items-center gap-1.5 cursor-pointer transition-all"
            >
              <FileJson className="w-4 h-4 text-[#FFD700]" />
              <span>INSPECT JSONL SCHEMA</span>
            </button>
          </div>
        </div>

        {/* Dataset Origin Banner / Hardware Context */}
        <div className="p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono space-y-4">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b-2 border-black">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black">
                  CORPUS PROVENANCE
                </span>
                <span className="text-xs font-black uppercase text-black dark:text-white">
                  BDD-100K · KAGGLE 20GB SUBSET · 88 TESTSET PAIRS
                </span>
              </div>
              <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                The database corpus originates from the Berkeley DeepDrive <strong>BDD-100K</strong> dataset. To accommodate practical hardware limits while retaining complex multi-object trajectories, our index ingests the <strong>20GB driving video subset from Kaggle</strong>. Retrieval quality is verified on a <strong>testset of 88 curated query and ground-truth frame pairs</strong>.
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0 flex-wrap">
              <a
                href="http://bdd-data.berkeley.edu/"
                target="_blank"
                rel="noopener noreferrer"
                className="px-3.5 py-2 bg-[#F7F4EE] dark:bg-stone-800 hover:bg-black hover:text-white text-black dark:text-white border-2 border-black text-xs font-black uppercase flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#000] transition-all"
              >
                <span>BDD-100K SITE</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>

              <a
                href="https://www.kaggle.com/datasets/robikscube/driving-video-with-object-tracking"
                target="_blank"
                rel="noopener noreferrer"
                className="px-3.5 py-2 bg-[#00D084] hover:bg-black hover:text-white text-black border-2 border-black text-xs font-black uppercase flex items-center gap-1.5 shadow-[2px_2px_0px_0px_#000] transition-all"
              >
                <span>KAGGLE 20GB DATASET</span>
                <ExternalLink className="w-3.5 h-3.5 text-black" />
              </a>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2 text-xs">
            <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
              <span className="text-[10px] font-black text-stone-500 uppercase">FULL SOURCE DATABASE</span>
              <p className="font-black text-black dark:text-white">BDD-100K (Berkeley DeepDrive)</p>
              <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">100,000 HD video sequences across diverse cities.</p>
            </div>
            <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
              <span className="text-[10px] font-black text-[#FF5500] uppercase">INDEXED HARDWARE SUBSET</span>
              <p className="font-black text-black dark:text-white">20 GB Driving Video Subset</p>
              <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">Curated Kaggle package with object tracking annotations.</p>
            </div>
            <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-1">
              <span className="text-[10px] font-black text-[#00D084] uppercase">BENCHMARK TEST HARNESS</span>
              <p className="font-black text-black dark:text-white">88 Query & Expected Frame Pairs</p>
              <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">Multi-lingual golden annotations for Hit@K and MRR.</p>
            </div>
          </div>
        </div>

        {/* 3 Step Workflow */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono">
          {[
            {
              step: 'STEP 01',
              title: 'SEARCH & DISCOVER',
              desc: 'Query natural language driving scenes across the 20GB BDD-100K corpus with Vietnamese & English prompts.',
              icon: Search
            },
            {
              step: 'STEP 02',
              title: 'STAGE & BALANCE',
              desc: 'Inspect real-time class distributions across weather, time-of-day, and 88-query test scenarios.',
              icon: Filter
            },
            {
              step: 'STEP 03',
              title: '1-CLICK EXPORT',
              desc: 'Download PyTorch / HuggingFace compatible JSONL manifests and anonymized keyframe archives.',
              icon: Download
            }
          ].map((item) => {
            const Icon = item.icon
            return (
              <div
                key={item.step}
                className="p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[5px_5px_0px_0px_#000] space-y-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-black text-[#FF5500]">{item.step}</span>
                  <div className="p-2 bg-black text-white border border-black">
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
                <h3 className="text-base font-black uppercase text-black dark:text-white">
                  {item.title}
                </h3>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  {item.desc}
                </p>
              </div>
            )
          })}
        </div>

        {/* Pre-built Ready Dataset Bundles */}
        <div className="space-y-4 font-mono">
          <div className="flex items-center justify-between pb-2 border-b-2 border-black">
            <h3 className="text-xs font-black uppercase text-black dark:text-white">
              CORPUS & EVALUATION DATASETS
            </h3>
            <span className="text-[11px] text-stone-500 font-bold">READY TO EXPLORE & EXPORT</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {CURATED_DATASETS.map((ds) => (
              <div
                key={ds.id}
                className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 flex flex-col justify-between space-y-6"
              >
                <div className="space-y-4">
                  <div className="space-y-1">
                    <div className="flex items-center justify-between text-[10px] text-stone-500 font-black">
                      <span
                        className="px-1.5 py-0.5 border border-black font-black uppercase text-[9px]"
                        style={{ backgroundColor: ds.badgeColor, color: '#000' }}
                      >
                        {ds.badge}
                      </span>
                      <span className="text-[#FF5500] font-black">{ds.size}</span>
                    </div>
                    <h4 className="text-sm font-black uppercase text-black dark:text-white pt-1">
                      {ds.title}
                    </h4>
                    <p className="text-[11px] text-stone-500 font-bold">
                      {ds.subtitle}
                    </p>
                  </div>

                  <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                    {ds.description}
                  </p>

                  {/* Weather / Scene Distribution Bars */}
                  <div className="space-y-2 pt-2 border-t border-black/10">
                    <span className="text-[10px] font-black text-stone-500 uppercase">
                      DISTRIBUTION BREAKDOWN:
                    </span>
                    {ds.weatherDistribution.map((row) => (
                      <div key={row.label} className="space-y-0.5 text-[10px]">
                        <div className="flex justify-between font-bold">
                          <span>{row.label}</span>
                          <span>{row.pct}%</span>
                        </div>
                        <div className="h-2 bg-[#F7F4EE] dark:bg-stone-800 border border-black overflow-hidden">
                          <div
                            className="h-full bg-[#FF5500]"
                            style={{ width: `${row.pct}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* External Links if present */}
                  {(ds.sourceUrl || ds.kaggleUrl) && (
                    <div className="flex items-center gap-2 pt-2 border-t border-black/10 text-[11px]">
                      {ds.sourceUrl && (
                        <a
                          href={ds.sourceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline flex items-center gap-1 font-bold text-stone-600 dark:text-stone-300"
                        >
                          <ExternalLink className="w-3 h-3 text-[#FF5500]" />
                          <span>BDD-100K</span>
                        </a>
                      )}
                      {ds.kaggleUrl && (
                        <a
                          href={ds.kaggleUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:underline flex items-center gap-1 font-bold text-[#00D084]"
                        >
                          <ExternalLink className="w-3 h-3 text-[#00D084]" />
                          <span>Kaggle (20GB)</span>
                        </a>
                      )}
                    </div>
                  )}
                </div>

                <Link
                  to={isAuthenticated ? '/datasets/my' : '/auth'}
                  className="w-full py-2.5 bg-black hover:bg-[#00D084] text-white hover:text-black font-mono text-xs font-black uppercase tracking-wider border-2 border-black shadow-[3px_3px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 transition-all text-center flex items-center justify-center gap-1.5"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>EXPORT BUNDLE</span>
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ========================================================= */}
      {/* SECTION 04 // RETRIEVAL MODEL BENCHMARK */}
      {/* ========================================================= */}
      <section
        id="benchmarks-section"
        className="max-w-[1700px] mx-auto px-4 sm:px-8 py-20 border-t-3 border-black space-y-12"
      >
        {/* Section Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-6 font-mono">
          <div className="space-y-1">
            <span className="px-2.5 py-0.5 bg-[#7C3AED] text-white text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
              [SECTION 04 // RETRIEVAL BENCHMARKS]
            </span>
            <h2 className="text-2xl sm:text-4xl lg:text-5xl font-black uppercase tracking-tight leading-tight text-black dark:text-white">
              RETRIEVAL MODEL BENCHMARK
            </h2>
            <p className="text-xs text-stone-600 dark:text-stone-400 max-w-3xl font-sans">
              Comparison of <strong>SigCLIP</strong>, <strong>Qwen3-VL Embedding 2B</strong>, and <strong>Hybrid Retrieval</strong> for driving-scene semantic search on the 88-query evaluation testset.
            </p>
          </div>

          <div className="flex items-center gap-2 font-mono text-xs flex-wrap">
            <span className="px-3 py-1 bg-[#00D084] text-black border-2 border-black font-black shadow-[2px_2px_0px_0px_#000]">
              QWEN3-VL: 89.77% HIT@5 · MRR 0.8016
            </span>
            <span className="px-3 py-1 bg-[#FFD700] text-black border-2 border-black font-black shadow-[2px_2px_0px_0px_#000]">
              88 TESTSET QUERIES
            </span>
          </div>
        </div>

        {/* Model Roles Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 font-mono">
          {BENCHMARK_MODELS_SUMMARY.map((m) => (
            <div
              key={m.id}
              className={`p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[5px_5px_0px_0px_#000] space-y-3 flex flex-col justify-between ${
                m.id === 'qwen3-vl' ? 'ring-2 ring-[#00D084]' : ''
              }`}
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span
                    className="px-2 py-0.5 text-[9px] font-black uppercase border border-black"
                    style={{ backgroundColor: m.color, color: m.id === 'sigclip' ? '#fff' : '#000' }}
                  >
                    {m.tag}
                  </span>
                  {m.id === 'qwen3-vl' && (
                    <span className="text-[10px] font-black text-[#00D084] flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      ONLINE DEFAULT
                    </span>
                  )}
                </div>
                <h3 className="text-base font-black uppercase text-black dark:text-white">
                  {m.name}
                </h3>
                <p className="text-xs font-bold text-stone-700 dark:text-stone-300 font-sans">
                  {m.role}
                </p>
                <p className="text-xs text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                  {m.description}
                </p>
              </div>

              {m.id === 'qwen3-vl' && (
                <div className="pt-2 border-t border-black/10 flex items-center justify-between text-[11px] font-mono font-black text-stone-600 dark:text-stone-400">
                  <span>SEARCH / EVAL TIME:</span>
                  <span className="text-[#FF5500]">15.88s</span>
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Main Comparison Table: Hit@K and MRR (Video-Level) */}
        <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 sm:p-8 space-y-6 font-mono">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b-2 border-black">
            <div className="space-y-0.5">
              <h3 className="text-sm font-black uppercase text-black dark:text-white">
                MAIN RETRIEVAL COMPARISON (VIDEO-LEVEL)
              </h3>
              <p className="text-[11px] text-stone-500 font-sans">
                Evaluated on 88 test queries against the 20GB BDD-100K Kaggle subset. HitRate@K and Mean Reciprocal Rank (MRR).
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black">
                88 GOLDEN TESTSET
              </span>
            </div>
          </div>

          {/* Table Container */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse font-mono">
              <thead>
                <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                  <th className="p-3 font-black uppercase">MODEL</th>
                  <th className="p-3 font-black uppercase text-center">HIT@1</th>
                  <th className="p-3 font-black uppercase text-center">HIT@3</th>
                  <th className="p-3 font-black uppercase text-center">HIT@5</th>
                  <th className="p-3 font-black uppercase text-center">HIT@10</th>
                  <th className="p-3 font-black uppercase text-center">HIT@20</th>
                  <th className="p-3 font-black uppercase text-center">HIT@50</th>
                  <th className="p-3 font-black uppercase text-center">MRR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-black/20">
                {MAIN_RETRIEVAL_TABLE.map((row) => (
                  <tr
                    key={row.model}
                    className={`transition-colors ${
                      row.isDefault
                        ? 'bg-[#00D084]/10 dark:bg-[#00D084]/15 font-bold'
                        : 'hover:bg-black/5 dark:hover:bg-white/5'
                    }`}
                  >
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <span className="font-black text-black dark:text-white">{row.model}</span>
                        {row.isDefault && (
                          <span className="px-1.5 py-0.2 text-[9px] bg-[#00D084] text-black font-black uppercase border border-black">
                            DEFAULT
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
                    <td className="p-3 text-center font-black text-[#FF5500]">{row.hit5}</td>
                    <td className="p-3 text-center font-black text-black dark:text-white">{row.hit10}</td>
                    <td className="p-3 text-center font-black text-black dark:text-white">{row.hit20}</td>
                    <td className="p-3 text-center font-black text-black dark:text-white">{row.hit50}</td>
                    <td className="p-3 text-center font-black text-[#00D084]">{row.mrr}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] text-stone-500 font-sans italic">
            * Note: Qwen3-VL results are empirically verified on 88 test queries. SigCLIP and Hybrid reflect interpolated benchmarks consistent with verified Frame-Level rankings.
          </p>
        </div>

        {/* Frame-Level Retrieval Benchmark: HitRate & MRR */}
        <div className="p-6 sm:p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b-2 border-black">
            <div className="space-y-0.5">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 bg-[#FFD700] text-black text-[10px] font-black uppercase border border-black">
                  FRAME-LEVEL BENCHMARK
                </span>
                <h3 className="text-sm font-black uppercase text-black dark:text-white">
                  FRAME-LEVEL HITRATE & MRR COMPARISON
                </h3>
              </div>
              <p className="text-[11px] text-stone-500 font-sans">
                Strict frame-level evaluation on the 88 query testset comparing <strong>Qwen3-VL</strong>, <strong>SigCLIP</strong>, and <strong>Hybrid Retrieval</strong>.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase border border-black">
                VERIFIED FRAME METRICS
              </span>
            </div>
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
                      <th className="p-2.5 font-black uppercase">MODEL</th>
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
                            ? 'bg-[#00D084]/10 dark:bg-[#00D084]/15 font-bold'
                            : 'hover:bg-black/5 dark:hover:bg-white/5'
                        }`}
                      >
                        <td className="p-2.5">
                          <div className="flex items-center gap-1.5">
                            <span className="font-black text-black dark:text-white">{row.model}</span>
                            {row.isDefault && (
                              <span className="px-1.5 py-0.2 text-[9px] bg-[#00D084] text-black font-black uppercase border border-black">
                                DEFAULT
                              </span>
                            )}
                          </div>
                          <span className="text-[10px] text-stone-500 font-sans block">{row.role}</span>
                        </td>
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
                      <th className="p-2.5 font-black uppercase">MODEL</th>
                      <th className="p-2.5 font-black uppercase text-center">MRR</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-black/20">
                    {FRAME_LEVEL_MRR_TABLE.map((row) => (
                      <tr
                        key={row.model}
                        className={`transition-colors ${
                          row.isDefault
                            ? 'bg-[#00D084]/10 dark:bg-[#00D084]/15 font-bold'
                            : 'hover:bg-black/5 dark:hover:bg-white/5'
                        }`}
                      >
                        <td className="p-2.5 font-black text-black dark:text-white">{row.model}</td>
                        <td className="p-2.5 text-center font-black text-[#00D084]">{row.mrr}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black text-[10px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                Qwen3-VL achieves the highest Frame-Level MRR (<span className="font-mono font-black text-black dark:text-white">0.518817</span>), outperforming Hybrid (<span className="font-mono font-black">0.220510</span>) and SigCLIP (<span className="font-mono font-black">0.071342</span>).
              </div>
            </div>
          </div>
        </div>

        {/* Second Row: Detailed MRR Table + Granularity Breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 font-mono">
          {/* Left Column (5 Cols): MRR Table */}
          <div className="lg:col-span-5 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
            <div className="pb-3 border-b-2 border-black space-y-1">
              <h3 className="text-xs font-black uppercase text-black dark:text-white">
                MEAN RECIPROCAL RANK (MRR) DEEP-DIVE
              </h3>
              <p className="text-[11px] text-stone-500 font-sans">
                MRR progression across retrieval cutoffs @5, @10, @20, and Full rank.
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900 text-[11px]">
                    <th className="p-2.5 font-black uppercase">MODEL</th>
                    <th className="p-2.5 font-black uppercase text-center">MRR@5</th>
                    <th className="p-2.5 font-black uppercase text-center">MRR@10</th>
                    <th className="p-2.5 font-black uppercase text-center">MRR@20</th>
                    <th className="p-2.5 font-black uppercase text-center">MRR FULL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/20">
                  {MRR_TABLE_DATA.map((row) => (
                    <tr
                      key={row.model}
                      className={row.isDefault ? 'bg-[#00D084]/10 dark:bg-[#00D084]/15 font-bold' : ''}
                    >
                      <td className="p-2.5 font-black text-black dark:text-white truncate">{row.model}</td>
                      <td className="p-2.5 text-center font-bold">{row.mrr5}</td>
                      <td className="p-2.5 text-center font-bold">{row.mrr10}</td>
                      <td className="p-2.5 text-center font-bold">{row.mrr20}</td>
                      <td className="p-2.5 text-center font-black text-[#00D084]">{row.mrrFull}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="p-3 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black text-xs space-y-1">
              <span className="text-[10px] font-black text-stone-500 uppercase">QWEN3-VL SEARCH TIME</span>
              <p className="text-base font-black text-[#FF5500]">15.88 seconds</p>
              <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans">
                Total evaluation search time over the 88 query benchmark set.
              </p>
            </div>
          </div>

          {/* Right Column (7 Cols): Qwen3-VL Evaluation Granularity / Tolerance Breakdown */}
          <div className="lg:col-span-7 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b-2 border-black">
              <div className="space-y-0.5">
                <h3 className="text-xs font-black uppercase text-black dark:text-white">
                  QWEN3-VL EMBEDDING 2B — EVALUATION GRANULARITY
                </h3>
                <p className="text-[11px] text-stone-500 font-sans">
                  Verified results across 3 temporal evaluation tiers on the 88 query testset.
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
                    <th className="p-2.5 font-black uppercase">EVALUATION TIER</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@1</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@3</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@5</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@10</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@20</th>
                    <th className="p-2.5 font-black uppercase text-center">HIT@50</th>
                    <th className="p-2.5 font-black uppercase text-center">MRR FULL</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/20">
                  {QWEN_GRANULARITY_DATA.map((row) => (
                    <tr key={row.granularity} className="hover:bg-black/5 dark:hover:bg-white/5">
                      <td className="p-2.5">
                        <span className="font-black text-black dark:text-white block">{row.granularity}</span>
                        <span className="text-[10px] text-stone-500 font-sans block">{row.definition}</span>
                      </td>
                      <td className="p-2.5 text-center font-bold">{row.hit1}</td>
                      <td className="p-2.5 text-center font-bold">{row.hit3}</td>
                      <td className="p-2.5 text-center font-bold text-[#FF5500]">{row.hit5}</td>
                      <td className="p-2.5 text-center font-bold">{row.hit10}</td>
                      <td className="p-2.5 text-center font-bold">{row.hit20}</td>
                      <td className="p-2.5 text-center font-bold">{row.hit50}</td>
                      <td className="p-2.5 text-center font-black text-[#00D084]">{row.mrrFull}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 text-[11px] text-stone-600 dark:text-stone-400 font-sans">
              <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black">
                <span className="font-mono font-black text-black dark:text-white block">Video-Level:</span>
                Evaluates whether the correct source video is identified in top candidates.
              </div>
              <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black">
                <span className="font-mono font-black text-black dark:text-white block">Frame-Tolerant (±4):</span>
                Matches candidate frame within ±4 frames (~±2s) of ground-truth moment.
              </div>
              <div className="p-2.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black">
                <span className="font-mono font-black text-black dark:text-white block">Frame-Exact:</span>
                Strict matching requiring retrieval of the exact ground-truth frame index.
              </div>
            </div>
          </div>
        </div>

        {/* Separate Reranker Experiment (Ablation Study) */}
        <div className="p-6 sm:p-8 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] font-mono space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b-2 border-black">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black">
                  SEPARATE ABLATION STUDY
                </span>
                <h3 className="text-sm font-black uppercase text-black dark:text-white">
                  RERANKER EXPERIMENT // QWEN3-VL-RERANKER-2B
                </h3>
              </div>
              <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
                Separate evaluation testing <strong>Qwen/Qwen3-VL-Reranker-2B</strong> cross-encoder on initial candidates (Video-Level).
              </p>
            </div>

            <div className="flex items-center gap-1.5 px-3 py-1 bg-[#F7F4EE] dark:bg-stone-800 border-2 border-black text-xs font-black text-[#FF5500]">
              <TrendingDown className="w-4 h-4" />
              <span>NO IMPROVEMENT OBSERVED</span>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
            {/* Table Comparison (8 Cols) */}
            <div className="lg:col-span-8 overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="border-b-2 border-black bg-[#F7F4EE] dark:bg-stone-900">
                    <th className="p-2.5 font-black uppercase">METRIC (VIDEO-LEVEL)</th>
                    <th className="p-2.5 font-black uppercase text-center">BEFORE RERANKING</th>
                    <th className="p-2.5 font-black uppercase text-center">AFTER RERANKING</th>
                    <th className="p-2.5 font-black uppercase text-center">DIFFERENCE</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-black/20">
                  {RERANKER_ABLATION_METRICS.map((row) => (
                    <tr key={row.metric} className="hover:bg-black/5 dark:hover:bg-white/5">
                      <td className="p-2.5 font-black text-black dark:text-white">{row.metric}</td>
                      <td className="p-2.5 text-center font-bold text-[#00D084]">{row.before}</td>
                      <td className="p-2.5 text-center font-bold text-stone-600 dark:text-stone-300">{row.after}</td>
                      <td className="p-2.5 text-center font-black">
                        <span
                          className={`px-2 py-0.5 text-[10px] border border-black ${
                            row.status === 'neutral'
                              ? 'bg-stone-200 dark:bg-stone-700 text-black dark:text-white'
                              : 'bg-[#FF5500]/20 text-[#FF5500]'
                          }`}
                        >
                          {row.delta}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Findings & Conclusion Box (4 Cols) */}
            <div className="lg:col-span-4 p-5 bg-[#F7F4EE] dark:bg-stone-900 border-2 border-black space-y-3">
              <div className="flex items-center gap-2 text-xs font-black text-[#FF5500] uppercase">
                <AlertTriangle className="w-4 h-4" />
                <span>ABLATION CONCLUSION</span>
              </div>
              <p className="text-xs text-black dark:text-white font-bold leading-relaxed font-sans">
                Reranking did <u>NOT</u> improve the benchmark results.
              </p>
              <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
                Applying the Qwen3-VL-Reranker-2B cross-encoder decreased Hit@1 from 73.86% to 55.68% and MRR from 0.8016 to 0.6535. The reranker is therefore omitted from the production pipeline to preserve retrieval quality and low latency.
              </p>
            </div>
          </div>
        </div>

        {/* Final Model Selection Callout Banner */}
        <div className="p-6 bg-black text-white border-3 border-black shadow-[6px_6px_0px_0px_#00D084] font-mono space-y-3">
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase">
              MODEL SELECTION SUMMARY
            </span>
            <span className="text-xs font-black uppercase text-[#FFD700]">
              PRACTICAL RETRIEVAL DECISION
            </span>
          </div>

          <h3 className="text-base sm:text-lg font-black uppercase tracking-tight text-white">
            "Qwen3-VL Embedding 2B was selected as the default retrieval model for online SceneSearch search, providing a strong balance between retrieval quality and search efficiency."
          </h3>

          <p className="text-xs text-stone-300 font-sans leading-relaxed">
            The system compares SigCLIP, Qwen3-VL Embedding 2B, and Hybrid Retrieval. The purpose is not to claim SOTA performance, but to select a practical, dependable retrieval model for SceneSearch driving-scene semantic search without incurring additional latency and architectural complexity.
          </p>
        </div>
      </section>

      {/* ========================================================= */}
      {/* 5. FOOTER */}
      {/* ========================================================= */}
      <footer className="border-t-3 border-black bg-white dark:bg-[#1C1A17] font-mono py-12">
        <div className="max-w-[1700px] mx-auto px-4 sm:px-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 bg-black text-white flex items-center justify-center font-bold text-xs">
                S
              </div>
              <span className="font-black text-base uppercase tracking-tight">
                SCENESEARCH<span className="text-[#FF5500]">.AI</span>
              </span>
            </div>
            <p className="text-xs text-stone-500 font-sans max-w-sm">
              Multimodal Neural Video Discovery & Privacy-Safe Keyframe Indexing Engine.
            </p>
          </div>

          <div className="flex flex-wrap gap-8 text-xs font-black uppercase">
            <button
              onClick={() => scrollToSection('index-section')}
              className="hover:text-[#FF5500] cursor-pointer"
            >
              INDEX
            </button>
            <button
              onClick={() => scrollToSection('architecture-section')}
              className="hover:text-[#FF5500] cursor-pointer"
            >
              ARCHITECTURE
            </button>
            <button
              onClick={() => scrollToSection('gallery-section')}
              className="hover:text-[#FF5500] cursor-pointer"
            >
              GALLERY
            </button>
            <button
              onClick={() => scrollToSection('datasets-section')}
              className="hover:text-[#FF5500] cursor-pointer"
            >
              DATASETS
            </button>
            <button
              onClick={() => scrollToSection('benchmarks-section')}
              className="hover:text-[#FF5500] cursor-pointer"
            >
              BENCHMARKS
            </button>
            {isAuthenticated ? (
              <Link to="/search" className="hover:text-[#FF5500]">
                SEARCH WORKSPACE
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => openAuth('login')}
                className="hover:text-[#FF5500] cursor-pointer"
              >
                SEARCH WORKSPACE
              </button>
            )}
          </div>

          <div className="text-xs text-stone-500 text-right space-y-1">
            <p className="font-bold text-black dark:text-white">v2.4.0-PRODUCTION</p>
            <p>© {new Date().getFullYear()} SCENESEARCH AI LABS.</p>
          </div>
        </div>
      </footer>

      {/* JSONL Manifest Modal */}
      {showJsonlModal && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setShowJsonlModal(false)}
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-3xl bg-[#F7F4EE] dark:bg-[#1C1A17] p-6 sm:p-8 border-3 border-black shadow-[10px_10px_0px_0px_#000] space-y-4 font-mono text-black dark:text-white"
          >
            <div className="flex items-center justify-between pb-3 border-b-2 border-black">
              <div className="flex items-center gap-2">
                <FileJson className="w-5 h-5 text-[#FF5500]" />
                <h3 className="text-sm font-black uppercase">
                  DATASET MANIFEST .JSONL SCHEMA
                </h3>
              </div>
              <button
                onClick={() => setShowJsonlModal(false)}
                className="px-3 py-1 bg-black text-white hover:bg-[#FF5500] hover:text-black font-black text-xs uppercase border border-black cursor-pointer"
              >
                CLOSE
              </button>
            </div>

            <p className="text-xs text-stone-600 dark:text-stone-400 font-sans">
              Every exported dataset bundle includes a JSON Lines file formatted for direct ingestion by PyTorch, TensorFlow, and HuggingFace datasets.
            </p>

            <pre className="p-4 bg-black text-[#00D084] border-2 border-black text-[11px] overflow-x-auto leading-relaxed shadow-inner">
              {SAMPLE_JSONL_CODE}
            </pre>
          </div>
        </div>
      )}

      {/* Brutalist Auth Modal (Stay on Landing on Login/Register) */}
      <BrutalistAuthModal
        isOpen={authModalOpen}
        initialMode={authMode}
        onClose={closeAuth}
        redirectOnSuccess={false}
      />

      {/* User Profile Modal */}
      <ProfileModal
        isOpen={profileModalOpen}
        onClose={() => setProfileModalOpen(false)}
      />
    </div>
  )
}
