import React from "react"
import { motion } from "framer-motion"
import {
  ExternalLink,
  Sliders,
  Activity
} from "lucide-react"
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
  ReactLogo
} from "./TechLogos"
import { useTheme } from "../../context/ThemeContext"
import { useLanguage } from "../../context/LanguageContext"

// Core Tech Platforms
const FEATURED_BRANDS = [
  { name: "Google SigLIP", category: "768d Visual", Logo: SigLIPLogo },
  { name: "Qwen3-VL 2B", category: "2048d VLM", Logo: QwenLogo },
  { name: "Qdrant HNSW", category: "Vector DB", Logo: QdrantLogo },
  { name: "MinIO S3", category: "Dual Storage", Logo: MinIOLogo },
  { name: "NVIDIA NIM", category: "TensorRT", Logo: NvidiaLogo },
  { name: "PyTorch 2", category: "CUDA / MPS", Logo: PyTorchLogo },
  { name: "FastAPI", category: "Async REST", Logo: FastAPILogo },
  { name: "PostgreSQL 16", category: "ACID DB", Logo: PostgresLogo },
  { name: "Redis 7", category: "Task Queue", Logo: RedisLogo },
  { name: "React 19", category: "Vite SPA", Logo: ReactLogo }
]

export function ArchitectureSection() {
  const { isDark } = useTheme()
  const { language } = useLanguage()

  return (
    <section
      id="architecture-section"
      className="max-w-[1700px] mx-auto px-4 sm:px-8 py-10 sm:py-14 border-t-3 border-black space-y-6"
    >
      {/* 1. Concise Section Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b-2 border-black pb-4 font-mono">
        <div className="space-y-1">
          <span className="px-2.5 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black shadow-[1.5px_1.5px_0px_0px_#000]">
            {language === "vi" ? "[MÔ HÌNH HỆ THỐNG // KIẾN TRÚC & CÔNG NGHỆ]" : "[SECTION // SYSTEM ARCHITECTURE & DESIGN]"}
          </span>
          <h2 className="text-2xl sm:text-4xl font-black uppercase tracking-tight text-black dark:text-white">
            {language === "vi" ? "KIẾN TRÚC & CÔNG NGHỆ" : "ARCHITECTURE & TECHNOLOGY"}
          </h2>
          <p className="text-xs text-stone-600 dark:text-stone-400 max-w-2xl font-sans font-medium">
            {language === "vi"
              ? "Hạ tầng tìm kiếm neural phân tán kết hợp Google SigLIP (768d) & Alibaba Qwen3-VL (2048d), lập chỉ mục đồ thị HNSW trên Qdrant và lưu trữ đối tượng MinIO."
              : "Distributed neural search infrastructure integrating Google SigLIP (768d) & Alibaba Qwen3-VL (2048d), Qdrant HNSW vector graph, and MinIO dual object storage."}
          </p>
        </div>

        {/* Action button */}
        <div className="flex items-center gap-2 font-mono">
          <a
            href={`/architecture.html?theme=${isDark ? "dark" : "light"}`}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 bg-[#FF5500] text-black border-2 border-black text-xs font-black uppercase hover:bg-black hover:text-white transition-all shadow-[2px_2px_0px_0px_#000] hover:shadow-none hover:translate-x-0.5 hover:translate-y-0.5 flex items-center gap-1.5 cursor-pointer"
            title={language === "vi" ? "Mở bản đồ kiến trúc toàn màn hình" : "Open full architecture blueprint"}
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>{language === "vi" ? "MỞ BẢN ĐỒ CHI TIẾT" : "FULL BLUEPRINT"}</span>
          </a>
        </div>
      </div>

      {/* 2. Concise Core Technology Platforms Strip */}
      <div className="p-3 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[3px_3px_0px_0px_#000] font-mono">
        <div className="flex items-center justify-between pb-2 border-b border-black/15 text-[10px] font-black uppercase text-stone-500">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-[#00D084] animate-pulse" />
            <span>{language === "vi" ? "CÁC NỀN TẢNG CÔNG NGHỆ TÍCH HỢP CỐT LÕI" : "CORE INTEGRATED TECH PLATFORMS"}</span>
          </div>
          <span className="hidden sm:inline">10 STACK MODULES</span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2 pt-2">
          {FEATURED_BRANDS.map((item) => {
            const Logo = item.Logo
            return (
              <div
                key={item.name}
                className="p-1.5 bg-[#F7F4EE] dark:bg-stone-900 border border-black flex flex-col items-center text-center gap-1 hover:-translate-y-0.5 hover:shadow-[1.5px_1.5px_0px_0px_#000] transition-all group"
              >
                <div className="w-6 h-6 rounded shrink-0 flex items-center justify-center p-0.5 bg-white dark:bg-black border border-black shadow-xs group-hover:scale-110 transition-transform">
                  <Logo className="w-4 h-4" />
                </div>
                <div className="overflow-hidden w-full">
                  <p className="font-black text-[9px] text-black dark:text-white truncate">
                    {item.name}
                  </p>
                  <p className="text-[8px] text-stone-500 uppercase font-bold truncate">
                    {item.category}
                  </p>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* 3. Sơ đồ hệ thống Architecture (Nhúng gọn gàng, hiển thị luồng di chuyển sẵn) */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="space-y-5 font-mono"
      >
        <div className="bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000] overflow-hidden">
          {/* Top Control Bar of Diagram */}
          <div className="px-3 py-2 sm:px-4 sm:py-2.5 bg-[#F7F4EE] dark:bg-stone-900 border-b-2 border-black flex flex-wrap items-center justify-between gap-2.5">
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-[#00D084] animate-ping" />
                <span className="font-mono font-black text-xs uppercase text-black dark:text-white tracking-wider">
                  {language === "vi" ? "SƠ ĐỒ HỆ THỐNG KIẾN TRÚC // ARCHITECTURE" : "SYSTEM ARCHITECTURE // DYNAMIC STREAM"}
                </span>
              </div>
              <span className="hidden md:inline text-stone-400">•</span>
              <span className="hidden md:inline-flex items-center gap-1 px-2 py-0.5 bg-[#00D084] text-black text-[10px] font-black uppercase shadow-[1px_1px_0px_0px_#000]">
                <Activity className="w-3 h-3" />
                {language === "vi" ? "LUỒNG DỮ LIỆU ĐANG DI CHUYỂN" : "ACTIVE SIGNAL FLOW"}
              </span>
              <span className="hidden lg:inline px-2 py-0.5 bg-black text-white text-[10px] font-bold">
                {language === "vi" ? "ĐỒNG BỘ DARK MODE" : "THEME SYNCED"}
              </span>
            </div>

            <div className="flex items-center gap-2">
              <a
                href={`/architecture.html?present=1&theme=${isDark ? "dark" : "light"}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-2.5 py-1 bg-white dark:bg-stone-800 text-black dark:text-white border border-black text-[10px] font-bold uppercase hover:bg-black hover:text-white transition-all shadow-[1px_1px_0px_0px_#000] flex items-center gap-1.5 cursor-pointer"
                title={language === "vi" ? "Mở chế độ thuyết trình" : "Open presentation mode"}
              >
                <Sliders className="w-3 h-3 text-[#00D084]" />
                <span className="hidden sm:inline">{language === "vi" ? "Thuyết trình" : "Present"}</span>
              </a>

              <a
                href={`/architecture.html?theme=${isDark ? "dark" : "light"}`}
                target="_blank"
                rel="noopener noreferrer"
                className="px-2.5 py-1 bg-[#FF5500] text-black border border-black text-[10px] font-bold uppercase hover:bg-black hover:text-white transition-all shadow-[1px_1px_0px_0px_#000] flex items-center gap-1.5 cursor-pointer"
                title={language === "vi" ? "Mở riêng toàn màn hình" : "Open full diagram"}
              >
                <ExternalLink className="w-3 h-3" />
                <span>{language === "vi" ? "Toàn màn hình" : "Fullscreen"}</span>
              </a>
            </div>
          </div>

          {/* Clean Embedded Diagram - Compact height with dynamic active flow */}
          <div className="relative w-full bg-[#020617] h-[420px] sm:h-[480px] md:h-[530px] lg:h-[570px]">
            <iframe
              title="SceneSearch System Architecture Blueprint"
              src={`/architecture.html?embed=1&theme=${isDark ? "dark" : "light"}`}
              className="w-full h-full border-0"
              loading="lazy"
            />
          </div>

          {/* Bottom Help Bar */}
          <div className="px-3 py-2 bg-[#F7F4EE] dark:bg-stone-900 border-t-2 border-black flex flex-wrap items-center justify-between gap-2 text-[11px] font-sans text-stone-600 dark:text-stone-400">
            <div className="flex items-center gap-2 font-mono">
              <span className="font-black text-black dark:text-white uppercase">
                {language === "vi" ? "TƯƠNG TÁC:" : "CONTROLS:"}
              </span>
              <span>
                {language === "vi"
                  ? "Cuộn chuột để Phóng to / Thu nhỏ • Kéo để Di chuyển • Bấm vào từng khối để xem chi tiết"
                  : "Scroll to Zoom • Drag to Pan • Click nodes for details"}
              </span>
            </div>
            <div className="font-mono text-[10px] font-bold text-stone-500">
              QDRANT • QWEN3-VL • SIGLIP • FASTAPI • MINIO
            </div>
          </div>
        </div>

        {/* 4. Core Architecture Decisions Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-3.5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[2.5px_2.5px_0px_0px_#000] space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-[#FF5500] border border-black" />
              <h4 className="font-black text-[11px] uppercase text-black dark:text-white">ADR-0001 // HYBRID MPS/CUDA</h4>
            </div>
            <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
              Decoupled container architecture: backing infra runs containerized, while ML encoding executes on NVIDIA Tensor Cores or Apple Metal MPS.
            </p>
          </div>

          <div className="p-3.5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[2.5px_2.5px_0px_0px_#000] space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-[#00D084] border border-black" />
              <h4 className="font-black text-[11px] uppercase text-black dark:text-white">ADR-0003 // PRIVACY ANONYMIZATION</h4>
            </div>
            <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
              Raw footage resides in restricted isolation. Only privacy-filtered frames (faces & license plates masked via YOLOv8) are indexed or exposed.
            </p>
          </div>

          <div className="p-3.5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[2.5px_2.5px_0px_0px_#000] space-y-1">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-[#FFD700] border border-black" />
              <h4 className="font-black text-[11px] uppercase text-black dark:text-white">ADR-0005 // SINGLE-CORPUS PRECISION</h4>
            </div>
            <p className="text-[11px] text-stone-600 dark:text-stone-400 font-sans leading-relaxed">
              Keyframe-level granularity indexing 29,742+ curated moments. NegEx constraints are evaluated per-keyframe to prevent false rejections.
            </p>
          </div>
        </div>
      </motion.div>
    </section>
  )
}
