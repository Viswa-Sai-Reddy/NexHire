# NexHire Frontend

React 18 · TypeScript · Vite · Tailwind · shadcn/ui · TanStack Query · React Router · MSAL.

## Layout

```
src/
├─ main.tsx                 # entry; renders <App />
├─ index.css                # Tailwind + design tokens (locked from UI sample)
├─ vite-env.d.ts            # ImportMetaEnv typing
│
├─ app/                     # app shell, providers, router
│  ├─ App.tsx
│  ├─ providers/            # QueryClientProvider, MsalProvider, ThemeProvider
│  └─ routes/               # role-based route definitions
│
├─ lib/                     # axios instance, msal config, utils
│
├─ shared/                  # cross-feature components/hooks/types
│  ├─ components/
│  │  └─ ui/                # shadcn/ui primitives (Button, Card, ...)
│  ├─ hooks/
│  └─ types.ts
│
└─ modules/                 # feature modules
   ├─ auth/
   ├─ referral/
   ├─ mentor/
   ├─ onboarding/
   ├─ dashboard/
   └─ admin/
```

## Commands

```bash
pnpm install           # install deps
pnpm dev               # vite dev server (5173) with API proxy → 8000
pnpm build             # tsc -b && vite build
pnpm typecheck         # tsc -b --noEmit
pnpm lint              # eslint
pnpm format            # prettier
pnpm test              # vitest
```

## Design tokens

Color palette, typography, and the stage-color palette are defined once in
[`tailwind.config.ts`](tailwind.config.ts) and [`src/index.css`](src/index.css).
Changes require an ADR — these are visual contract.
