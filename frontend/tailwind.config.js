import type { Config } from 'tailwindcss';

const withOpacityValue = (variable) => ({ opacityValue }) => {
  if (opacityValue !== undefined) {
    return `rgb(var(${variable}) / ${opacityValue})`;
  }
  return `rgb(var(${variable}))`;
};

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2563eb',
          foreground: '#ffffff',
        },
        surface: withOpacityValue('--surface'),
        foreground: withOpacityValue('--foreground'),
        card: withOpacityValue('--card'),
        border: withOpacityValue('--border'),
        muted: withOpacityValue('--muted'),
        'muted-foreground': withOpacityValue('--muted-foreground'),
      },
      boxShadow: {
        lg: '0 20px 30px -15px rgb(30 64 175 / 0.2)',
      },
    },
  },
  plugins: [],
};

export default config;
