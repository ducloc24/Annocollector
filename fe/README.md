# Annocollector — Frontend (Next.js)

Next.js 16 (App Router) + TypeScript + Tailwind CSS v4.

## Structure

```
src/
├── app/                  # App Router: layout, pages, global styles
├── components/           # UI components ("use client" only where needed)
└── lib/api.ts            # Typed client for the FastAPI backend
```

## Setup

```bash
# from the repo root
npm install --prefix fe
copy fe\.env.example fe\.env.local
npm run dev --prefix fe
```

App runs at http://localhost:3000 and expects the API at
`NEXT_PUBLIC_API_URL` (default `http://localhost:8000/api/v1`).

## Scripts

```bash
npm run dev      # dev server (Turbopack)
npm run build    # production build
npm run start    # serve the production build
npm run lint     # ESLint
```

## Adding a page

Create `src/app/<route>/page.tsx`. Server components fetch data on the server;
mark a file `"use client"` only when you need state, effects or browser APIs.
Keep HTTP calls in `src/lib/api.ts` so every screen shares the same types.
