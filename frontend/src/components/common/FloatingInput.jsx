import React, { useState } from 'react'
import { Eye, EyeOff, CheckCircle, AlertCircle } from 'lucide-react'

export const FloatingInput = ({
  id,
  name,
  type = 'text',
  label,
  value,
  onChange,
  error,
  success,
  icon: Icon,
  required = false,
  autoComplete
}) => {
  const [isFocused, setIsFocused] = useState(false)
  const [showPassword, setShowPassword] = useState(false)

  const isFloating = isFocused || (value && value.toString().length > 0)
  const isPassword = type === 'password'
  const currentType = isPassword ? (showPassword ? 'text' : 'password') : type

  return (
    <div className="relative mb-5 group">
      <div className="relative">
        {Icon && (
          <div className="absolute left-4 top-1/2 -translate-y-1/2 text-stone-400 dark:text-[#847970] group-focus-within:text-orange-700 dark:group-focus-within:text-[#789b86] transition-colors pointer-events-none z-10">
            <Icon className="w-4 h-4" />
          </div>
        )}

        <input
          id={id}
          name={name}
          type={currentType}
          value={value}
          onChange={onChange}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setIsFocused(false)}
          required={required}
          autoComplete={autoComplete}
          className={`w-full bg-white dark:bg-[#181512] text-stone-950 dark:text-[#f3ece4] text-sm rounded-2xl border transition-all duration-200 outline-none ${
            Icon ? 'pl-11' : 'pl-4'
          } ${isPassword ? 'pr-11' : 'pr-4'} pt-6 pb-2 ${
            error
              ? 'border-rose-400 dark:border-[#6b3e3e] focus:border-rose-600 focus:ring-1 focus:ring-rose-600'
              : success
              ? 'border-emerald-500'
              : 'border-stone-300 dark:border-[#403933] focus:border-stone-950 dark:focus:border-[#789b86] focus:ring-1 focus:ring-stone-950 dark:focus:ring-[#315c49]/20'
          }`}
        />

        <label
          htmlFor={id}
          className={`absolute left-0 pointer-events-none transition-all duration-200 z-10 ${
            Icon ? 'left-11' : 'left-4'
          } ${
            isFloating
              ? 'top-2 text-[10px] font-bold tracking-widest uppercase text-orange-700 dark:text-[#789b86]'
              : 'top-1/2 -translate-y-1/2 text-sm text-stone-500 dark:text-[#a99d92]'
          } ${error ? 'text-rose-600 dark:text-[#c98d89]' : ''}`}
        >
          {label} {required && <span className="text-rose-500">*</span>}
        </label>

        {isPassword && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-4 top-1/2 -translate-y-1/2 text-stone-400 dark:text-[#847970] hover:text-stone-700 dark:hover:text-stone-300 transition-colors p-1 rounded-md"
            aria-label="Toggle password visibility"
          >
            {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        )}
      </div>

      {error && (
        <div className="flex items-center gap-1.5 mt-1.5 text-xs text-rose-600 dark:text-[#c98d89] font-medium">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {!error && success && (
        <div className="flex items-center gap-1.5 mt-1.5 text-xs text-emerald-700 dark:text-[#789b86] font-medium">
          <CheckCircle className="w-3.5 h-3.5 shrink-0" />
          <span>{success}</span>
        </div>
      )}
    </div>
  )
}
