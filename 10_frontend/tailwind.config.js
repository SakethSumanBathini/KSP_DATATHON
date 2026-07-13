/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0A0D12',
          surface: '#12171F',
          secondary: '#181E27',
        },
        border: {
          subtle: '#2A313D',
        },
        text: {
          primary: '#F5F7FA',
          secondary: '#C5CCD6',
          muted: '#8892A0',
        },
        status: {
          success: '#22C55E',
          warning: '#F59E0B',
          critical: '#EF4444',
        },
        brand: {
          accent: '#2563EB',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      spacing: {
        '0': '0',
        '1': '8px',
        '2': '16px',
        '3': '24px',
        '4': '32px',
        '5': '40px',
        '6': '48px',
      },
    },
  },
  plugins: [],
}
