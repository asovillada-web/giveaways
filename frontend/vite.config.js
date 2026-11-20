import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

function isAnonKey(key) {
  if (key.startsWith('sb_publishable_')) return true
  try {
    const payload = Buffer.from(key.split('.')[1], 'base64url').toString('utf8')
    return JSON.parse(payload).role === 'anon'
  } catch {
    return false
  }
}

export default defineConfig(({ mode }) => {
  const key = loadEnv(mode, process.cwd(), 'VITE_SUPABASE_').VITE_SUPABASE_ANON_KEY
  if (key && !isAnonKey(key)) {
    throw new Error('VITE_SUPABASE_ANON_KEY must be a Supabase publishable key or a legacy anon JWT.')
  }
  return { plugins: [react(), tailwindcss()] }
})
