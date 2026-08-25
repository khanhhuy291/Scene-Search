import React from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

const StatusRow = ({ ok, label, detail }) => (
  <div className="flex items-start gap-3 py-3 border-b-2 border-black/20 last:border-0 font-mono">
    {ok ? (
      <CheckCircle2 className="w-4 h-4 text-[#00D084] shrink-0 mt-0.5" />
    ) : (
      <AlertCircle className="w-4 h-4 text-[#FF5500] shrink-0 mt-0.5" />
    )}
    <div>
      <p className="text-xs font-black uppercase text-black dark:text-white">
        {label}
      </p>
      <p className="text-[11px] text-stone-600 dark:text-stone-400 mt-0.5">{detail}</p>
    </div>
  </div>
)

const LabelBars = ({ title, rows }) => {
  const list = rows || []
  const max = Math.max(1, ...list.map((r) => r.count))
  return (
    <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-3 font-mono">
      <div className="flex items-center justify-between pb-2 border-b border-black">
        <h3 className="text-xs font-black uppercase tracking-wider text-black dark:text-white">
          {title}
        </h3>
        <span className="text-[10px] text-[#FF5500] font-bold">COUNT</span>
      </div>

      {list.length === 0 ? (
        <p className="text-xs text-stone-500">[NO LABELS RECORDED]</p>
      ) : (
        <div className="space-y-2">
          {list.map((row) => (
            <div
              key={row.name}
              className="grid grid-cols-[5.5rem_1fr_2rem] gap-2 items-center text-xs"
            >
              <span className="uppercase text-black dark:text-white font-bold truncate">{row.name}</span>
              <div className="h-3 bg-[#F7F4EE] dark:bg-stone-800 border border-black overflow-hidden">
                <div
                  className="h-full bg-[#FF5500]"
                  style={{ width: `${(row.count / max) * 100}%` }}
                />
              </div>
              <span className="tabular-nums font-black text-right text-black dark:text-white">
                {row.count}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export const CorpusHealth = ({ telemetry }) => {
  const h = telemetry?.corpus
  if (!h) {
    return (
      <div className="p-6 bg-white dark:bg-[#1C1A17] border-2 border-black font-mono text-xs text-black dark:text-white">
        [LOADING CORPUS COVERAGE TELEMETRY...]
      </div>
    )
  }

  const fogCount = (h.labels?.weather || []).reduce((sum, row) => {
    return /fog/.test(row.name) ? sum + row.count : sum
  }, 0)

  return (
    <div className="space-y-6 font-sans animate-fadeIn">
      {/* Header Info */}
      <div className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] flex flex-col sm:flex-row sm:items-center justify-between gap-4 font-mono">
        <div className="space-y-1">
          <span className="px-2 py-0.5 bg-[#FF5500] text-black text-[10px] font-black uppercase border border-black">
            CATALOG INDEX STATUS
          </span>
          <h2 className="text-xl font-black uppercase tracking-tight text-black dark:text-white">
            WHAT CAN THIS INDEX ANSWER?
          </h2>
        </div>
        <div className="text-right">
          <p className="text-sm font-black text-black dark:text-white">
            {h.videos.toLocaleString()} VIDEOS · {h.keyframes.toLocaleString()} KEYFRAMES
          </p>
          <span className="text-[10px] text-[#00D084] font-bold uppercase">● LIVE CATALOG SYNCHRONIZED</span>
        </div>
      </div>

      {/* 3 Metric Tiles */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 font-mono">
        {[
          { label: 'MEDIA COVERAGE', value: `${h.media_coverage_pct}%`, color: '#FF5500' },
          { label: 'CAPTION COVERAGE', value: `${h.caption_coverage_pct}%`, color: '#00D084' },
          { label: 'EMBEDDING COVERAGE', value: `${h.embedding_coverage_pct}%`, color: '#FFD700' }
        ].map((card) => (
          <div
            key={card.label}
            className="p-5 bg-white dark:bg-[#1C1A17] border-2 border-black shadow-[4px_4px_0px_0px_#000] space-y-1"
          >
            <span className="text-stone-500 uppercase tracking-widest text-[10px] font-black">
              {card.label}
            </span>
            <p className="text-3xl font-black text-black dark:text-white tracking-tight" style={{ color: card.color }}>
              {card.value}
            </p>
          </div>
        ))}
      </div>

      {/* Diagnostics List */}
      <div className="p-6 bg-white dark:bg-[#1C1A17] border-3 border-black shadow-[6px_6px_0px_0px_#000]">
        <StatusRow
          ok={h.caption_tower_installed}
          label="CAPTION ENCODER TOWER"
          detail={
            h.caption_tower_installed
              ? `Installed (${h.caption_tower_name}) — text ANN search is online`
              : 'Not installed — lexical retrieval available; visual search online'
          }
        />
        <StatusRow
          ok={h.media_coverage_pct >= 80}
          label="RENDERABLE MEDIA ASSETS"
          detail={`${h.media_coverage_pct}% of indexed keyframes possess a thumbnail object key in storage`}
        />
        <StatusRow
          ok={fogCount >= 5}
          label="FOG SCENE COVERAGE"
          detail={
            fogCount >= 5
              ? `${fogCount} fog-labelled keyframes cataloged in live index`
              : `Only ${fogCount} fog-labelled keyframes — fog queries will broaden until more clips are ingested`
          }
        />
      </div>

      {/* Label Distribution Charts */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <LabelBars title="Weather Labels" rows={h.labels?.weather} />
        <LabelBars title="Time of Day" rows={h.labels?.time_of_day} />
        <LabelBars title="Road & Scene Type" rows={h.labels?.scene} />
      </div>
    </div>
  )
}
