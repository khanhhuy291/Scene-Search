import React, { createContext, useContext, useState, useEffect } from "react"

const LanguageContext = createContext(null)

export const TRANSLATIONS = {
  en: {
    // Header & Nav
    "nav.search": "SEARCH",
    "nav.draft": "DATASET DRAFT",
    "nav.datasets": "DATASETS",
    "nav.ingest": "INGEST",
    "nav.admin": "ADMIN",
    "nav.eval": "EVALUATION",
    "nav.login": "LOGIN",
    "nav.logout": "LOGOUT",
    "nav.profile": "PROFILE & SETTINGS",
    "nav.about": "ABOUT / OVERVIEW",
    "nav.workspace": "WORKSPACE",
    "nav.signup": "SIGN UP",
    "nav.online": "QDRANT HNSW // ONLINE",

    // Theme & Lang
    "theme.light": "Light Mode",
    "theme.dark": "Dark Mode",
    "theme.switch_to_light": "Switch to Light Mode",
    "theme.switch_to_dark": "Switch to Dark Mode",
    "lang.en": "English",
    "lang.vi": "Tiếng Việt",
    "lang.switch": "Chuyển sang Tiếng Việt",

    // Search Page
    "search.hero_badge": "MULTIMODAL NEURAL SEARCH // QDRANT HNSW + QWEN3-VL & SIGLIP",
    "search.hero_title": "SEMANTIC SCENE",
    "search.hero_title_accent": "SEARCH",
    "search.hero_desc": "Natural-language retrieval across driving footage. Query visual conditions, actions, and strict negations to curate balanced training slices.",
    "search.placeholder": "Describe a driving scene — e.g. rainy street without pedestrians...",
    "search.btn": "SEARCH",
    "search.try": "TRY:",
    "search.options": "Search Options",
    "search.signals": "SEARCH SIGNALS // ENCODER TOWERS",
    "search.results_per_page": "RESULTS PER PAGE",
    "search.workspace": "WORKSPACE",
    "search.show_overview": "Show overview",
    "search.collapse_header": "Collapse header",
    "search.system_ready": "[SYSTEM READY // AWAITING QUERY]",
    "search.system_ready_desc": "Enter a scene description above or click one of the suggested query chips to start neural search across ~30,000 keyframes.",
    "search.results_count": "RESULTS ({count} VIDEOS DISPLAYED)",
    "search.sort": "SORT:",
    "search.sort_relevance": "RELEVANCE",
    "search.sort_moments": "MATCHING MOMENTS",
    "search.sort_timestamp": "TIMESTAMP",
    "search.add_all": "ADD ALL",
    "search.rlhf_toggle": "RLHF RE-RANK",
    "search.rlhf_exit": "EXIT RLHF MODE",
    "search.scanning": "SCANNING QDRANT VECTOR SPACE...",
    "search.no_results": "[ZERO RESULTS MATCHED]",
    "search.below_threshold": "[NO FOOTAGE MATCHING THRESHOLD IN CORPUS]",
    "search.load_more": "LOAD MORE MATCHING VIDEOS ↵",

    // Interpretation Strip
    "strip.query": "QUERY:",
    "strip.soft_only": "soft only",
    "strip.degraded_warning": "DEGRADED RETRIEVAL MODE ACTIVE: Vision encoder fallback in effect. Text caption similarity is prioritizing results.",
    "strip.add_exclusion": "Add exclusion:",
    "strip.run_without_exclusion": "Run without exclusion:",
    "strip.server_latency": "server",

    // Draft Rail
    "rail.title": "DATASET DRAFT",
    "rail.empty": "NO MOMENTS SAVED YET",
    "rail.empty_desc": "Click \"KEEP\" or press \"A\" while inspecting clips to curate a balanced training slice.",
    "rail.export": "EXPORT JSONL",
    "rail.slice_balance": "SLICE BALANCE DISTRIBUTION",
    "rail.shortcuts": "KEYBOARD SHORTCUTS",

    // Scene Card
    "card.coverage": "coverage",
    "card.keep": "KEEP",
    "card.kept": "KEPT ✓",
    "card.keep_moment": "Keep this moment",
    "card.close": "Esc · Close"
  },
  vi: {
    // Header & Nav
    "nav.search": "TÌM KIẾM",
    "nav.draft": "BẢN NHÁP DATASET",
    "nav.datasets": "TẬP DỮ LIỆU",
    "nav.ingest": "NẠP VIDEO",
    "nav.admin": "QUẢN TRỊ",
    "nav.eval": "ĐÁNH GIÁ",
    "nav.login": "ĐĂNG NHẬP",
    "nav.logout": "ĐĂNG XUẤT",
    "nav.profile": "HỒ SƠ & CÀI ĐẶT",
    "nav.about": "GIỚI THIỆU",
    "nav.workspace": "KHÔNG GIAN LÀM VIỆC",
    "nav.signup": "ĐĂNG KÝ",
    "nav.online": "QDRANT HNSW // TRỰC TUYẾN",

    // Theme & Lang
    "theme.light": "Chế độ Sáng",
    "theme.dark": "Chế độ Tối",
    "theme.switch_to_light": "Chuyển sang Chế độ Sáng",
    "theme.switch_to_dark": "Chuyển sang Chế độ Tối",
    "lang.en": "English",
    "lang.vi": "Tiếng Việt",
    "lang.switch": "Switch to English",

    // Search Page
    "search.hero_badge": "TÌM KIẾM NEURAL ĐA PHƯƠNG THỨC // QDRANT HNSW + QWEN3-VL & SIGLIP",
    "search.hero_title": "TÌM KIẾM",
    "search.hero_title_accent": "NGỮ NGHĨA",
    "search.hero_desc": "Truy xuất ngôn ngữ tự nhiên trên kho video lái xe. Tìm kiếm theo điều kiện thị giác, hành vi và phủ định tuyệt đối để tạo slice dữ liệu huấn luyện cân bằng.",
    "search.placeholder": "Mô tả cảnh lái xe — ví dụ: đường mưa không có người đi bộ...",
    "search.btn": "TÌM KIẾM",
    "search.try": "GỢI Ý:",
    "search.options": "Tùy chọn tìm kiếm",
    "search.signals": "TÍN HIỆU TÌM KIẾM // BỘ MÃ HÓA ENCODER",
    "search.results_per_page": "KẾT QUẢ MỖI TRANG",
    "search.workspace": "KHÔNG GIAN LÀM VIỆC",
    "search.show_overview": "Hiện tổng quan",
    "search.collapse_header": "Thu gọn đầu trang",
    "search.system_ready": "[HỆ THỐNG SẴN SÀNG // CHỜ TRUY VẤN]",
    "search.system_ready_desc": "Nhập mô tả khung cảnh phía trên hoặc bấm vào gợi ý để bắt đầu tìm kiếm trên gần 30.000 keyframe.",
    "search.results_count": "KẾT QUẢ (HIỂN THỊ {count} VIDEO)",
    "search.sort": "SẮP XẾP:",
    "search.sort_relevance": "ĐỘ PHÙ HỢP",
    "search.sort_moments": "SỐ LƯỢNG KHỚP",
    "search.sort_timestamp": "THỜI GIAN",
    "search.add_all": "THÊM TẤT CẢ",
    "search.rlhf_toggle": "XẾP HẠNG RLHF",
    "search.rlhf_exit": "THOÁT RLHF",
    "search.scanning": "ĐANG QUÉT KHÔNG GIAN VECTOR QDRANT...",
    "search.no_results": "[KHÔNG TÌM THẤY KẾT QUẢ PHÙ HỢP]",
    "search.below_threshold": "[KHÔNG CÓ DỮ LIỆU ĐẠT NGƯỠNG TƯƠNG ĐỒNG]",
    "search.load_more": "TẢI THÊM VIDEO PHÙ HỢP ↵",

    // Interpretation Strip
    "strip.query": "TRUY VẤN:",
    "strip.soft_only": "chỉ tính điểm mềm",
    "strip.degraded_warning": "CHẾ ĐỘ DỰ PHÒNG (DEGRADED) ĐANG BẬT: Đang dùng độ tương đồng văn bản thay cho visual encoder chính.",
    "strip.add_exclusion": "Thêm phủ định:",
    "strip.run_without_exclusion": "Chạy không có phủ định:",
    "strip.server_latency": "máy chủ",

    // Draft Rail
    "rail.title": "BẢN NHÁP DATASET",
    "rail.empty": "CHƯA CÓ KHOẢNH KHẮC NÀO ĐƯỢC LƯU",
    "rail.empty_desc": "Bấm \"LƯU\" hoặc nhấn phím \"A\" khi xem video để tuyển chọn tập dữ liệu huấn luyện cân bằng.",
    "rail.export": "XUẤT FILE JSONL",
    "rail.slice_balance": "PHÂN BỔ LÁT CẮT (SLICE BALANCE)",
    "rail.shortcuts": "PHÍM TẮT BÀN PHÍM",

    // Scene Card
    "card.coverage": "độ phủ",
    "card.keep": "LƯU",
    "card.kept": "ĐÃ LƯU ✓",
    "card.keep_moment": "Lưu khoảnh khắc này",
    "card.close": "Esc · Đóng"
  }
}

export const LanguageProvider = ({ children }) => {
  const [language, setLanguageState] = useState(() => {
    return localStorage.getItem("scenesearch_lang") || "en"
  })

  useEffect(() => {
    localStorage.setItem("scenesearch_lang", language)
    document.documentElement.lang = language
  }, [language])

  const setLanguage = (lang) => {
    if (lang === "en" || lang === "vi") {
      setLanguageState(lang)
    }
  }

  const toggleLanguage = () => {
    setLanguageState((prev) => (prev === "en" ? "vi" : "en"))
  }

  const t = (key, params = {}, fallback = "") => {
    const langDict = TRANSLATIONS[language] || TRANSLATIONS.en
    let str = langDict[key] || TRANSLATIONS.en[key] || fallback || key
    if (params && typeof params === "object") {
      Object.keys(params).forEach((paramKey) => {
        str = str.replace(new RegExp(`\\{${paramKey}\\}`, "g"), params[paramKey])
      })
    }
    return str
  }

  return (
    <LanguageContext.Provider value={{ language, isVietnamese: language === "vi", setLanguage, toggleLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export const useLanguage = () => {
  const context = useContext(LanguageContext)
  if (!context) {
    return {
      language: "en",
      isVietnamese: false,
      setLanguage: () => {},
      toggleLanguage: () => {},
      t: (key, params = {}, fallback = "") => {
        const dict = TRANSLATIONS.en || {}
        let str = dict[key] || fallback || key
        if (params && typeof params === "object") {
          Object.keys(params).forEach((k) => {
            str = str.replace(new RegExp(`\\\\{${k}\\\\}`, "g"), params[k])
          })
        }
        return str
      }
    }
  }
  return context
}
