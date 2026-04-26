# Margin App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack academic writing workspace with AI Humanizer and Auto-Cite features, plus plagiarism checking, following Survify's architectural patterns.

**Architecture:** Monorepo with Express.js + TypeScript backend (port 8001) and Next.js 14 App Router frontend (port 8002). MongoDB + Redis via Docker. AI via OpenAI (primary) + Claude (fallback) using tryWithFallback pattern. SSE for humanizer streaming, Bull + Socket.io for auto-cite/plagiarism queues.

**Tech Stack:** Express.js, TypeScript, Typegoose/Mongoose, Passport.js, Bull, Socket.io, Next.js 14, React 19, Tailwind CSS, Redux Toolkit, SWR, OpenAI SDK, Anthropic SDK, AWS SDK, Stripe, mammoth, pdf-parse, cheerio

---

## File Structure

### Backend (`margin-backend/`)

```
margin-backend/
├── package.json
├── tsconfig.json
├── nodemon.json
├── .env.example
├── src/
│   ├── app.ts                          # Entry point: HTTP server + Socket.io + loaders
│   ├── Constants.ts                    # Roles, statuses, credit costs, error codes
│   ├── loaders/
│   │   ├── index.ts                    # Sequential loader chain
│   │   ├── express.ts                  # CORS, body-parser, session, routes
│   │   ├── mongoose.ts                 # MongoDB connection
│   │   └── passport.ts                # Local + JWT strategies
│   ├── api/
│   │   ├── index.ts                    # Route registration
│   │   └── routes/
│   │       ├── auth/
│   │       │   ├── auth.ts             # Auth route aggregator
│   │       │   ├── signin.ts           # Login
│   │       │   ├── signup.ts           # Register
│   │       │   └── google.ts           # Google OAuth
│   │       ├── me.ts                   # Current user profile
│   │       ├── humanize.ts            # Humanizer endpoints + SSE
│   │       ├── cite.ts                # Auto-cite endpoints
│   │       ├── plagiarism.ts          # Plagiarism check endpoints
│   │       ├── document.ts            # Document upload/import
│   │       ├── library.ts            # Citation library CRUD
│   │       ├── credit.ts             # Credit balance/history/purchase
│   │       └── webhook.ts            # Stripe webhook
│   ├── models/
│   │   ├── User.ts
│   │   ├── Credit.ts
│   │   ├── Document.ts
│   │   ├── HumanizeJob.ts
│   │   ├── Citation.ts
│   │   ├── CitationFolder.ts
│   │   ├── AutoCiteJob.ts
│   │   └── PlagiarismJob.ts
│   ├── services/
│   │   ├── ai/
│   │   │   ├── ai.service.manager.ts  # Primary/fallback provider
│   │   │   ├── openai.service.ts      # OpenAI implementation
│   │   │   └── claude.service.ts      # Claude implementation
│   │   ├── humanizer.service.ts       # Humanize logic + prompts
│   │   ├── citation.service.ts        # CrossRef + OpenAlex + Semantic Scholar
│   │   ├── plagiarism.service.ts      # Copyscape integration
│   │   ├── document.service.ts        # File parsing + URL scraping
│   │   └── credit.service.ts          # Balance check, deduct, refund
│   ├── queues/
│   │   ├── autocite.queue.ts          # Bull queue for auto-cite jobs
│   │   └── plagiarism.queue.ts        # Bull queue for plagiarism jobs
│   ├── packages/
│   │   ├── error/error.ts             # BaseError with codes
│   │   ├── crypto/crypto.ts           # Bcrypt helpers
│   │   └── valid/valid.ts             # Input validation
│   └── utils/
│       └── helper.ts                  # Shared utilities
```

### Frontend (`margin-frontend/`)

```
margin-frontend/
├── package.json
├── tsconfig.json
├── next.config.js
├── tailwind.config.ts
├── postcss.config.js
├── .env.example
├── public/
│   └── fonts/                         # Instrument Serif, DM Sans, JetBrains Mono
├── app/
│   ├── layout.tsx                     # Root: providers (Redux, SWR, Google OAuth)
│   ├── globals.css                    # Tailwind imports + custom fonts
│   ├── (auth)/
│   │   ├── layout.tsx                 # Auth layout (no sidebar)
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   └── (workspace)/
│       ├── layout.tsx                 # Sidebar + Topbar wrapper
│       ├── humanizer/page.tsx
│       ├── auto-cite/page.tsx
│       ├── library/page.tsx
│       └── history/page.tsx
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   └── Topbar.tsx
│   ├── humanizer/
│   │   ├── HumBoard.tsx               # Main humanizer UI container
│   │   ├── HumToolbar.tsx             # Tone, strength, length controls
│   │   ├── InputPane.tsx              # Paste/upload/URL tabs
│   │   ├── OutputPane.tsx             # Diff-highlighted output
│   │   └── InsightCards.tsx           # 4 stat cards
│   ├── cite/
│   │   ├── CiteBoard.tsx             # Auto-cite main container
│   │   ├── ClaimPopover.tsx           # Claim → source picker
│   │   ├── SourceList.tsx             # Bibliography panel
│   │   └── PlagiarismView.tsx         # Plagiarism results
│   ├── library/
│   │   ├── FolderSidebar.tsx
│   │   └── CitationRow.tsx
│   ├── common/
│   │   ├── ClientOnly.tsx
│   │   ├── DropZone.tsx
│   │   ├── FileCard.tsx
│   │   └── UrlImport.tsx
│   └── ui/
│       ├── AiMeter.tsx
│       ├── CreditPill.tsx
│       └── Toast.tsx
├── hooks/
│   ├── user.ts                        # useMe, useReloadMe
│   ├── humanizer.ts                   # useHumanizerHistory
│   ├── cite.ts                        # useCiteJob
│   ├── library.ts                     # useFolders, useCitations
│   └── credit.ts                      # useBalance, useCreditHistory
├── lib/
│   └── core/
│       ├── fetch/
│       │   ├── Fetch.ts               # Axios wrapper with access_token
│       │   └── Cookie.ts              # Cookie helpers
│       └── Constants.ts               # API_URL, SOCKET_URL, codes, costs
├── store/
│   ├── store.ts                       # Redux store
│   ├── rootReducer.ts                 # Combine slices
│   ├── types.ts                       # Shared TypeScript types
│   └── slices/
│       ├── authSlice.ts
│       ├── creditSlice.ts
│       ├── humanizerSlice.ts
│       ├── autoCiteSlice.ts
│       └── librarySlice.ts
```

---

## Phase 1: Project Setup & Configuration

### Task 1: Initialize Backend Project

**Files:**
- Create: `margin-backend/package.json`
- Create: `margin-backend/tsconfig.json`
- Create: `margin-backend/nodemon.json`
- Create: `margin-backend/.env.example`

- [ ] **Step 1: Create backend package.json**

```bash
mkdir -p margin-backend
```

Write `margin-backend/package.json`:

```json
{
  "name": "margin-backend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "nodemon",
    "build": "tsc && tsc-alias",
    "start": "tsc && tsc-alias && node dist/app.js",
    "test": "ts-node -r tsconfig-paths/register src/test.ts"
  },
  "dependencies": {
    "@typegoose/typegoose": "^12.0.0",
    "aws-sdk": "^2.1500.0",
    "bcrypt": "^5.1.1",
    "body-parser": "^1.20.2",
    "bull": "^4.12.0",
    "cheerio": "^1.0.0",
    "cors": "^2.8.5",
    "dotenv": "^16.3.1",
    "express": "^4.18.2",
    "express-session": "^1.17.3",
    "jsonwebtoken": "^9.0.2",
    "mammoth": "^1.6.0",
    "mongoose": "^8.0.0",
    "multer": "^1.4.5-lts.1",
    "openai": "^4.20.0",
    "@anthropic-ai/sdk": "^0.30.0",
    "passport": "^0.7.0",
    "passport-jwt": "^4.0.1",
    "passport-local": "^1.0.0",
    "pdf-parse": "^1.1.1",
    "socket.io": "^4.7.0",
    "stripe": "^14.0.0",
    "validator": "^13.11.0",
    "zod": "^3.22.4"
  },
  "devDependencies": {
    "@types/bcrypt": "^5.0.2",
    "@types/body-parser": "^1.19.5",
    "@types/cors": "^2.8.17",
    "@types/express": "^4.17.21",
    "@types/express-session": "^1.17.10",
    "@types/jsonwebtoken": "^9.0.5",
    "@types/multer": "^1.4.11",
    "@types/node": "^20.10.0",
    "@types/passport": "^1.0.16",
    "@types/passport-jwt": "^4.0.1",
    "@types/passport-local": "^1.0.38",
    "nodemon": "^3.0.2",
    "ts-node": "^10.9.1",
    "tsc-alias": "^1.8.8",
    "tsconfig-paths": "^4.2.0",
    "typescript": "^5.3.2"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

Write `margin-backend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "es6",
    "module": "commonjs",
    "lib": ["ESNext.String", "es6"],
    "outDir": "dist",
    "rootDir": "src",
    "strict": false,
    "esModuleInterop": true,
    "experimentalDecorators": true,
    "emitDecoratorMetadata": true,
    "resolveJsonModule": true,
    "sourceMap": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 3: Create nodemon.json**

Write `margin-backend/nodemon.json`:

```json
{
  "watch": ["src"],
  "ext": "ts",
  "exec": "ts-node -r tsconfig-paths/register src/app.ts"
}
```

- [ ] **Step 4: Create .env.example**

Write `margin-backend/.env.example`:

```env
PORT=8001
NODE_ENV=development
MONGO_URI=mongodb://localhost:27017/margin
REDIS_URL=redis://localhost:6379

JWT_SECRET=your-jwt-secret-here

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# OpenAI
OPENAI_API_KEY=

# Anthropic
ANTHROPIC_API_KEY=

# AWS S3
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
AWS_S3_BUCKET=

# Stripe
STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=

# Copyscape
COPYSCAPE_USERNAME=
COPYSCAPE_API_KEY=

# Semantic Scholar (optional, for higher rate)
SEMANTIC_SCHOLAR_API_KEY=

# Frontend URL (for CORS in production)
FRONTEND_URL=http://localhost:8002
```

- [ ] **Step 5: Install dependencies**

Run:
```bash
cd margin-backend && npm install
```

- [ ] **Step 6: Commit**

```bash
git add margin-backend/package.json margin-backend/tsconfig.json margin-backend/nodemon.json margin-backend/.env.example
git commit -m "feat(backend): initialize margin-backend project structure"
```

---

### Task 2: Backend Boilerplate (Entry Point + Loaders)

**Files:**
- Create: `margin-backend/src/app.ts`
- Create: `margin-backend/src/Constants.ts`
- Create: `margin-backend/src/loaders/index.ts`
- Create: `margin-backend/src/loaders/express.ts`
- Create: `margin-backend/src/loaders/mongoose.ts`
- Create: `margin-backend/src/packages/error/error.ts`
- Create: `margin-backend/src/packages/crypto/crypto.ts`
- Create: `margin-backend/src/packages/valid/valid.ts`
- Create: `margin-backend/src/utils/helper.ts`
- Create: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create Constants.ts**

Write `margin-backend/src/Constants.ts`:

```typescript
export const Code = {
  Success: 1,
  Error: 0,
  InvalidPassword: 2,
  InactiveAuth: 3,
  NotFound: 4,
  InvalidAuth: 5,
  InvalidInput: 6,
  InsufficientCredits: 7,
};

export const Roles = {
  User: 'User',
  Admin: 'Admin',
};

export const CreditDirection = {
  Inbound: 'inbound',
  Outbound: 'outbound',
};

export const CreditStatus = {
  Pending: 'pending',
  Completed: 'completed',
  Failed: 'failed',
};

export const CreditCosts = {
  HUMANIZE_PER_100_WORDS: 1,
  AUTOCITE_PER_ANALYSIS: 3,
  PLAGIARISM_PER_CHECK: 5,
  AI_SCORE_CHECK: 1,
};

export const FREE_SIGNUP_CREDITS = 30;

export const JobStatus = {
  Pending: 'pending',
  Processing: 'processing',
  Completed: 'completed',
  Done: 'done',
  Failed: 'failed',
};

export const HumanizerTones = ['academic', 'casual', 'persuasive'] as const;
export const LengthModes = ['match', 'shorter', 'longer'] as const;
export const CitationStyles = ['apa', 'mla', 'chicago', 'harvard', 'ieee'] as const;
export const SourceTypes = ['paste', 'upload', 'url'] as const;
```

- [ ] **Step 2: Create error package**

Write `margin-backend/src/packages/error/error.ts`:

```typescript
import { Code } from '@/Constants';

export class BaseError {
  message: string;
  code: number;

  constructor(message: string, code: number = Code.Error) {
    this.message = message;
    this.code = code;
  }

  release() {
    return { message: this.message, code: this.code };
  }
}
```

- [ ] **Step 3: Create crypto package**

Write `margin-backend/src/packages/crypto/crypto.ts`:

```typescript
import bcrypt from 'bcrypt';

export class Crypto {
  static hashUsernamePassword(password: string): string {
    const salt = bcrypt.genSaltSync(10);
    return bcrypt.hashSync(password, salt);
  }

  static checkCorrectPassword(password: string, hashed: string): boolean {
    return bcrypt.compareSync(password, hashed);
  }
}
```

- [ ] **Step 4: Create validation package**

Write `margin-backend/src/packages/valid/valid.ts`:

```typescript
export class Valid {
  static email(email: string): boolean {
    if (!email || email.length > 256) return false;
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  }

  static string(value: any, maxLength?: number): boolean {
    if (typeof value !== 'string' || value.trim().length === 0) return false;
    if (maxLength && value.length > maxLength) return false;
    return true;
  }

  static username(value: string): boolean {
    if (!value || value.trim().length === 0) return false;
    return /^[a-zA-Z0-9_ ]+$/.test(value);
  }
}
```

- [ ] **Step 5: Create helper utilities**

Write `margin-backend/src/utils/helper.ts`:

```typescript
import { Request, Response, NextFunction } from 'express';

export const wrapAsync = (fn: Function) => {
  return (req: Request, res: Response, next: NextFunction) => {
    fn(req, res, next).catch(next);
  };
};

export const safeParse = (str: string): any => {
  try {
    return JSON.parse(str);
  } catch {
    return null;
  }
};

export const clearDotsFromGmail = (email: string): string => {
  const [local, domain] = email.split('@');
  if (domain === 'gmail.com') {
    return local.replace(/\./g, '') + '@' + domain;
  }
  return email;
};
```

- [ ] **Step 6: Create mongoose loader**

Write `margin-backend/src/loaders/mongoose.ts`:

```typescript
import mongoose from 'mongoose';

export default async () => {
  const uri = process.env.MONGO_URI || 'mongodb://localhost:27017/margin';
  try {
    await mongoose.connect(uri);
    console.log('MongoDB connected');
  } catch (err) {
    console.error('MongoDB connection failed:', err);
    process.exit(1);
  }
};
```

- [ ] **Step 7: Create API route index (empty for now)**

Write `margin-backend/src/api/index.ts`:

```typescript
import { Router } from 'express';

export default () => {
  const router = Router();

  // Routes will be registered here as they are built
  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
```

- [ ] **Step 8: Create express loader**

Write `margin-backend/src/loaders/express.ts`:

```typescript
import express, { Application } from 'express';
import cors from 'cors';
import bodyParser from 'body-parser';
import session from 'express-session';
import routes from '@/api';

export default ({ app }: { app: Application }) => {
  app.use(cors({ origin: '*', methods: 'GET,HEAD,PUT,PATCH,POST,DELETE' }));

  app.use(
    bodyParser.json({
      limit: '50mb',
      verify: (req: any, res, buf) => {
        req.rawBody = buf;
      },
    })
  );
  app.use(bodyParser.urlencoded({ extended: true, limit: '50mb' }));

  app.use(
    session({
      secret: process.env.JWT_SECRET || 'margin_secret',
      resave: false,
      saveUninitialized: false,
    })
  );

  app.get('/status', (req, res) => res.send('OK'));

  const apiRoutes = routes();
  app.use('/api', apiRoutes);
};
```

- [ ] **Step 9: Create loader index**

Write `margin-backend/src/loaders/index.ts`:

```typescript
import { Application } from 'express';
import mongooseLoader from './mongoose';
import expressLoader from './express';

export default async ({ app }: { app: Application }) => {
  await mongooseLoader();
  console.log('Mongoose loaded');

  expressLoader({ app });
  console.log('Express loaded');
};
```

- [ ] **Step 10: Create app.ts entry point**

Write `margin-backend/src/app.ts`:

```typescript
import 'dotenv/config';
import express from 'express';
import http from 'http';
import { Server as SocketServer } from 'socket.io';
import loaders from '@/loaders';

const app = express();
const server = http.createServer(app);

const io = new SocketServer(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
});

// Make io accessible to routes
app.set('io', io);

io.on('connection', (socket) => {
  console.log('Socket connected:', socket.id);

  socket.on('join', (room: string) => {
    socket.join(room);
  });

  socket.on('disconnect', () => {
    console.log('Socket disconnected:', socket.id);
  });
});

const start = async () => {
  await loaders({ app });

  const port = process.env.PORT || 8001;
  server.listen(port, () => {
    console.log(`Margin backend running on port ${port}`);
  });
};

start();
```

- [ ] **Step 11: Verify backend starts**

Run:
```bash
cd margin-backend && npm run dev
```
Expected: "MongoDB connected", "Express loaded", "Margin backend running on port 8001"

- [ ] **Step 12: Commit**

```bash
git add margin-backend/src/
git commit -m "feat(backend): add entry point, loaders, and utility packages"
```

---

### Task 3: Docker Compose (MongoDB + Redis)

**Files:**
- Create: `docker/docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

```bash
mkdir -p docker
```

Write `docker/docker-compose.yml`:

```yaml
version: '3.8'
services:
  mongodb:
    image: mongo:6.0
    container_name: margin-mongodb
    ports:
      - "27017:27017"
    volumes:
      - margin_mongo_data:/data/db

  redis:
    image: redis:7-alpine
    container_name: margin-redis
    ports:
      - "6379:6379"
    volumes:
      - margin_redis_data:/data

volumes:
  margin_mongo_data:
  margin_redis_data:
```

- [ ] **Step 2: Start services**

Run:
```bash
docker-compose -f docker/docker-compose.yml up -d
```
Expected: Both containers running

- [ ] **Step 3: Commit**

```bash
git add docker/docker-compose.yml
git commit -m "feat: add Docker Compose for MongoDB and Redis"
```

---

### Task 4: Initialize Frontend Project

**Files:**
- Create: `margin-frontend/package.json`
- Create: `margin-frontend/tsconfig.json`
- Create: `margin-frontend/next.config.js`
- Create: `margin-frontend/tailwind.config.ts`
- Create: `margin-frontend/postcss.config.js`
- Create: `margin-frontend/app/globals.css`
- Create: `margin-frontend/.env.example`

- [ ] **Step 1: Create frontend package.json**

```bash
mkdir -p margin-frontend
```

Write `margin-frontend/package.json`:

```json
{
  "name": "margin-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -p 8002",
    "build": "next build",
    "start": "next start -p 8002",
    "lint": "eslint ."
  },
  "dependencies": {
    "@reduxjs/toolkit": "^2.6.1",
    "@react-oauth/google": "^0.13.4",
    "axios": "^1.6.2",
    "clsx": "^2.1.0",
    "framer-motion": "^11.5.4",
    "lucide-react": "^0.323.0",
    "next": "^14.2.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-dropzone": "^14.2.3",
    "react-redux": "^9.0.0",
    "react-toastify": "^10.0.4",
    "redux": "^5.0.0",
    "socket.io-client": "^4.8.1",
    "swr": "^2.2.4",
    "tailwind-merge": "^2.2.1"
  },
  "devDependencies": {
    "@types/node": "^20.10.1",
    "@types/react": "^19",
    "@types/react-dom": "^19",
    "autoprefixer": "^10.0.1",
    "postcss": "^8",
    "tailwindcss": "^3.4.1",
    "typescript": "^5.3.2"
  }
}
```

- [ ] **Step 2: Create tsconfig.json**

Write `margin-frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2015",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 3: Create next.config.js**

Write `margin-frontend/next.config.js`:

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.cloudfront.net' },
      { protocol: 'https', hostname: 'lh3.googleusercontent.com' },
    ],
  },
};

module.exports = nextConfig;
```

- [ ] **Step 4: Create tailwind.config.ts with Margin design system**

Write `margin-frontend/tailwind.config.ts`:

```typescript
import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#0022FF',
        'primary-dark': '#001ACC',
        purple: '#6633FF',
        success: '#00B383',
        warn: '#E89C2C',
        error: '#E84C5A',
        ink: '#0A0E27',
        'ink-soft': '#3F4566',
        'ink-muted': '#8B91A8',
        rule: '#ECEDF3',
        'rule-strong': '#D8DAE5',
        'bg-soft': '#F7F8FC',
        'bg-blue': '#F0F3FF',
        'bg-purple': '#F4F0FF',
      },
      fontFamily: {
        serif: ['Instrument Serif', 'Georgia', 'serif'],
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 5: Create postcss.config.js**

Write `margin-frontend/postcss.config.js`:

```javascript
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 6: Create globals.css**

```bash
mkdir -p margin-frontend/app
```

Write `margin-frontend/app/globals.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=JetBrains+Mono:wght@400;500;600&display=swap');

body {
  font-family: 'DM Sans', system-ui, sans-serif;
  color: #0A0E27;
  background: #FFFFFF;
}
```

- [ ] **Step 7: Create .env.example**

Write `margin-frontend/.env.example`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8001
NEXT_PUBLIC_SOCKET_URL=http://localhost:8001
NEXT_PUBLIC_GOOGLE_CLIENT_ID=
```

- [ ] **Step 8: Install dependencies**

Run:
```bash
cd margin-frontend && npm install
```

- [ ] **Step 9: Commit**

```bash
git add margin-frontend/package.json margin-frontend/tsconfig.json margin-frontend/next.config.js margin-frontend/tailwind.config.ts margin-frontend/postcss.config.js margin-frontend/app/globals.css margin-frontend/.env.example
git commit -m "feat(frontend): initialize margin-frontend with Next.js + Tailwind design system"
```

---

### Task 5: Frontend Core (Store, Fetch, Constants, Root Layout)

**Files:**
- Create: `margin-frontend/lib/core/Constants.ts`
- Create: `margin-frontend/lib/core/fetch/Cookie.ts`
- Create: `margin-frontend/lib/core/fetch/Fetch.ts`
- Create: `margin-frontend/store/types.ts`
- Create: `margin-frontend/store/store.ts`
- Create: `margin-frontend/store/rootReducer.ts`
- Create: `margin-frontend/store/slices/authSlice.ts`
- Create: `margin-frontend/store/slices/creditSlice.ts`
- Create: `margin-frontend/components/common/ClientOnly.tsx`
- Create: `margin-frontend/app/layout.tsx`

- [ ] **Step 1: Create Constants**

```bash
mkdir -p margin-frontend/lib/core/fetch
```

Write `margin-frontend/lib/core/Constants.ts`:

```typescript
const isProd = process.env.NODE_ENV === 'production';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
export const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:8001';

export const Code = {
  Success: 1,
  Error: 0,
  InvalidPassword: 2,
  InactiveAuth: 3,
  NotFound: 4,
  InvalidAuth: 5,
  InvalidInput: 6,
  InsufficientCredits: 7,
};

export const CreditCosts = {
  HUMANIZE_PER_100_WORDS: 1,
  AUTOCITE_PER_ANALYSIS: 3,
  PLAGIARISM_PER_CHECK: 5,
  AI_SCORE_CHECK: 1,
};
```

- [ ] **Step 2: Create Cookie helper**

Write `margin-frontend/lib/core/fetch/Cookie.ts`:

```typescript
class Cookie {
  static fromDocument(name: string): string {
    if (typeof document === 'undefined') return '';
    const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
    return match ? decodeURIComponent(match[2]) : '';
  }

  static set(name: string, value: string, days: number = 365) {
    if (typeof document === 'undefined') return;
    const expires = new Date(Date.now() + days * 864e5).toUTCString();
    document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/`;
  }

  static remove(name: string) {
    if (typeof document === 'undefined') return;
    document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
  }
}

export default Cookie;
```

- [ ] **Step 3: Create Fetch class**

Write `margin-frontend/lib/core/fetch/Fetch.ts`:

```typescript
import axios, { AxiosPromise } from 'axios';
import Cookie from './Cookie';
import { API_URL } from '@/lib/core/Constants';

type AnyObject = Record<string, any>;

class Fetch {
  private __base_url: string = API_URL;

  async postWithAccessToken<ResponseType>(
    url: string,
    params: Object = {},
    context: { access_token: string } | null = null
  ): Promise<AxiosPromise<ResponseType>> {
    return this.post<ResponseType>(url, {
      ...params,
      access_token: context
        ? context.access_token
        : Cookie.fromDocument('access_token'),
    });
  }

  async get<ResponseType>(
    url: string,
    params: any = {}
  ): Promise<AxiosPromise<ResponseType>> {
    return axios.get(`${this.__base_url}${url}`, params);
  }

  async post<ResponseType>(
    url: string,
    params: any = {}
  ): Promise<AxiosPromise<ResponseType>> {
    if (typeof XMLHttpRequest === 'undefined') {
      // @ts-ignore
      return fetch(`${this.__base_url}${url}`, {
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(params),
        cache: 'no-store',
      }).then(async (e) => {
        if (e.status !== 200) {
          return { message: e.statusText, code: 0 };
        }
        return { data: await e.json() };
      });
    }

    if (typeof window !== 'undefined') {
      const form_data = new FormData();
      for (const k in params) {
        if (Array.isArray(params[k])) {
          for (let i = 0; i < params[k].length; i++) {
            form_data.append(`${k}[]`, params[k][i]);
          }
        } else if (params[k] != null && params[k] != undefined) {
          form_data.append(k, params[k]);
        }
      }
      return axios.post(`${this.__base_url}${url}`, form_data);
    }

    return axios.post(`${this.__base_url}${url}`, params);
  }

  async getFetcher(obj: string | [string, AnyObject | undefined | null]) {
    let url: string = typeof obj === 'string' ? obj : '';
    let args: AnyObject | undefined | null;

    if (Array.isArray(obj)) {
      [url, args] = obj;
    }

    const params: AnyObject = { ...args };
    const accessToken = args?.accessToken;

    if (typeof accessToken === 'string') {
      params.access_token = accessToken;
    } else if (typeof accessToken === 'undefined' || accessToken) {
      params.access_token = Cookie.fromDocument('access_token');
    }

    return this.post(url, params);
  }

  async postFetcher(url: string, options: { arg: { payload: AnyObject; accessToken?: boolean | string } }) {
    const { accessToken, payload } = options.arg;

    if (typeof accessToken === 'string') {
      payload.access_token = accessToken;
    } else if (typeof accessToken === 'undefined' || accessToken) {
      payload.access_token = Cookie.fromDocument('access_token');
    }

    return this.post(url, payload);
  }
}

export default new Fetch();
```

- [ ] **Step 4: Create store types**

```bash
mkdir -p margin-frontend/store/slices
```

Write `margin-frontend/store/types.ts`:

```typescript
export type RawUser = {
  id: string;
  _id: string;
  username: string;
  email: string;
  credit: number;
  plan: string;
  role: string;
  emailVerified: boolean;
  googleId?: string;
  createdAt: string;
  updatedAt: string;
};

export type RawCredit = {
  id: string;
  _id: string;
  amount: number;
  direction: string;
  owner: string;
  status: string;
  description: string;
  orderType: string;
  orderId: string;
  createdAt: string;
};

export type RawDocument = {
  id: string;
  _id: string;
  owner: string;
  title: string;
  content: string;
  sourceType: string;
  sourceUrl?: string;
  fileKey?: string;
  mimeType: string;
  wordCount: number;
  createdAt: string;
};

export type RawHumanizeJob = {
  id: string;
  _id: string;
  owner: string;
  documentId: string;
  inputText: string;
  outputHtml: string;
  outputText: string;
  tone: string;
  strength: number;
  lengthMode: string;
  aiScoreIn: number;
  aiScoreOut: number;
  changesCount: number;
  creditsUsed: number;
  status: string;
  createdAt: string;
};

export type ClaimCandidate = {
  sourceId: string;
  relevanceScore: number;
};

export type Claim = {
  text: string;
  sourceId: string | null;
  status: string;
  candidates: ClaimCandidate[];
};

export type CiteSource = {
  id: string;
  cite: string;
  authorShort: string;
  year: number;
  title: string;
  snippet: string;
  conf: number;
  sourceApi: string;
};

export type RawAutoCiteJob = {
  id: string;
  _id: string;
  owner: string;
  documentId: string;
  style: string;
  status: string;
  claims: Claim[];
  sources: CiteSource[];
  creditsUsed: number;
  createdAt: string;
};

export type PlagiarismMatch = {
  sourceTitle: string;
  sourceUrl: string;
  similarity: number;
  matchedText: string;
  severity: string;
};

export type RawPlagiarismJob = {
  id: string;
  _id: string;
  owner: string;
  documentId: string;
  overallScore: number;
  status: string;
  matches: PlagiarismMatch[];
  creditsUsed: number;
  createdAt: string;
};

export type RawCitation = {
  id: string;
  _id: string;
  owner: string;
  folderId: string | null;
  style: string;
  formattedText: string;
  author: string;
  year: number;
  title: string;
  journal: string | null;
  doi: string | null;
  url: string | null;
  sourceApi: string;
  createdAt: string;
};

export type RawCitationFolder = {
  id: string;
  _id: string;
  owner: string;
  name: string;
  color: string;
  createdAt: string;
};
```

- [ ] **Step 5: Create auth slice**

Write `margin-frontend/store/slices/authSlice.ts`:

```typescript
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { RawUser } from '@/store/types';

interface AuthState {
  profile: RawUser | null;
}

const initialState: AuthState = {
  profile: null,
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loadProfile(state, action: PayloadAction<RawUser | null>) {
      state.profile = action.payload;
    },
  },
});

export const { loadProfile } = authSlice.actions;
export default authSlice.reducer;
```

- [ ] **Step 6: Create credit slice**

Write `margin-frontend/store/slices/creditSlice.ts`:

```typescript
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface CreditState {
  balance: number;
}

const initialState: CreditState = {
  balance: 0,
};

const creditSlice = createSlice({
  name: 'credit',
  initialState,
  reducers: {
    setBalance(state, action: PayloadAction<number>) {
      state.balance = action.payload;
    },
  },
});

export const { setBalance } = creditSlice.actions;
export default creditSlice.reducer;
```

- [ ] **Step 7: Create rootReducer and store**

Write `margin-frontend/store/rootReducer.ts`:

```typescript
import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
```

Write `margin-frontend/store/store.ts`:

```typescript
import { configureStore } from '@reduxjs/toolkit';
import rootReducer from './rootReducer';

export const store = configureStore({
  reducer: rootReducer,
});

export type AppDispatch = typeof store.dispatch;
```

- [ ] **Step 8: Create ClientOnly component**

```bash
mkdir -p margin-frontend/components/common
```

Write `margin-frontend/components/common/ClientOnly.tsx`:

```tsx
'use client';

import { useEffect, useState } from 'react';

export function ClientOnly({ children }: { children: React.ReactNode }) {
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  if (!isClient) return null;
  return <>{children}</>;
}
```

- [ ] **Step 9: Create root layout**

Write `margin-frontend/app/layout.tsx`:

```tsx
'use client';

import './globals.css';
import React from 'react';
import { Provider } from 'react-redux';
import { SWRConfig } from 'swr';
import { GoogleOAuthProvider } from '@react-oauth/google';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import { store } from '@/store/store';
import Fetch from '@/lib/core/fetch/Fetch';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">
        <Provider store={store}>
          <SWRConfig
            value={{
              fetcher: (url: any) => Fetch.getFetcher(url).then((r: any) => r.data),
              revalidateOnFocus: false,
            }}
          >
            <GoogleOAuthProvider clientId={process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || ''}>
              {children}
              <ToastContainer position="bottom-center" autoClose={3000} />
            </GoogleOAuthProvider>
          </SWRConfig>
        </Provider>
      </body>
    </html>
  );
}
```

- [ ] **Step 10: Verify frontend starts**

Run:
```bash
cd margin-frontend && npm run dev
```
Expected: Next.js dev server starts on port 8002

- [ ] **Step 11: Commit**

```bash
git add margin-frontend/lib/ margin-frontend/store/ margin-frontend/components/common/ClientOnly.tsx margin-frontend/app/layout.tsx
git commit -m "feat(frontend): add store, fetch layer, constants, and root layout"
```

---

## Phase 2: Authentication

### Task 6: User Model

**Files:**
- Create: `margin-backend/src/models/User.ts`

- [ ] **Step 1: Create User model**

Write `margin-backend/src/models/User.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'users', timestamps: true } })
export class User {
  @prop({ required: true })
  public username!: string;

  @prop({ required: true, unique: true })
  public email!: string;

  @prop({ required: true })
  public password!: string;

  @prop()
  public googleId?: string;

  @prop({ default: false })
  public emailVerified!: boolean;

  @prop()
  public verificationToken?: string;

  @prop({ default: 0 })
  public credit!: number;

  @prop({ default: 'free' })
  public plan!: string;

  @prop({ default: 'User' })
  public role!: string;

  @prop()
  public version?: string;

  @prop()
  public lastLogin?: Date;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = obj._id;
    delete obj.password;
    delete obj.verificationToken;
    delete obj.__v;
    return obj;
  }
}

export const UserModel = getModelForClass(User);
```

- [ ] **Step 2: Commit**

```bash
git add margin-backend/src/models/User.ts
git commit -m "feat(backend): add User model with Typegoose"
```

---

### Task 7: Passport Strategies

**Files:**
- Create: `margin-backend/src/loaders/passport.ts`
- Modify: `margin-backend/src/loaders/index.ts`

- [ ] **Step 1: Create passport loader**

Write `margin-backend/src/loaders/passport.ts`:

```typescript
import { Application } from 'express';
import passport from 'passport';
import { Strategy as LocalStrategy } from 'passport-local';
import { Strategy as JwtStrategy, ExtractJwt } from 'passport-jwt';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';

export default ({ app }: { app: Application }) => {
  app.use(passport.initialize());
  app.use(passport.session());

  // Local Strategy for signin
  passport.use(
    'signin',
    new LocalStrategy(
      { usernameField: 'email', passwordField: 'password' },
      async (email, password, done) => {
        try {
          const user = await UserModel.findOne({
            $or: [{ email: email.toLowerCase() }, { username: email }],
          });
          if (!user) return done(null, false, { message: 'User not found' });
          if (!Crypto.checkCorrectPassword(password, user.password)) {
            return done(null, false, { message: 'Incorrect password' });
          }
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );

  // JWT Strategy
  passport.use(
    new JwtStrategy(
      {
        jwtFromRequest: (req) => {
          return req.body?.access_token || req.query?.access_token || null;
        },
        secretOrKey: process.env.JWT_SECRET || 'margin_secret',
      },
      async (payload, done) => {
        try {
          const user = await UserModel.findById(payload.id);
          if (!user) return done(null, false);
          return done(null, user);
        } catch (err) {
          return done(err);
        }
      }
    )
  );
};
```

- [ ] **Step 2: Add passport to loader chain**

Update `margin-backend/src/loaders/index.ts`:

```typescript
import { Application } from 'express';
import mongooseLoader from './mongoose';
import expressLoader from './express';
import passportLoader from './passport';

export default async ({ app }: { app: Application }) => {
  await mongooseLoader();
  console.log('Mongoose loaded');

  expressLoader({ app });
  console.log('Express loaded');

  passportLoader({ app });
  console.log('Passport loaded');
};
```

- [ ] **Step 3: Commit**

```bash
git add margin-backend/src/loaders/passport.ts margin-backend/src/loaders/index.ts
git commit -m "feat(backend): add Passport.js local + JWT strategies"
```

---

### Task 8: Auth Routes (Register, Login, Google OAuth, Me)

**Files:**
- Create: `margin-backend/src/api/routes/auth/signup.ts`
- Create: `margin-backend/src/api/routes/auth/signin.ts`
- Create: `margin-backend/src/api/routes/auth/google.ts`
- Create: `margin-backend/src/api/routes/auth/auth.ts`
- Create: `margin-backend/src/api/routes/me.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create signup route**

```bash
mkdir -p margin-backend/src/api/routes/auth
```

Write `margin-backend/src/api/routes/auth/signup.ts`:

```typescript
import { Router } from 'express';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';
import { Valid } from '@/packages/valid/valid';
import { Code, FREE_SIGNUP_CREDITS } from '@/Constants';
import jwt from 'jsonwebtoken';

const router = Router();

router.post('/signup', async (req, res) => {
  try {
    const { username, email, password, confirmPassword } = req.body;

    if (!Valid.string(username)) {
      return res.json({ code: Code.InvalidInput, message: 'Username is required' });
    }
    if (!Valid.email(email)) {
      return res.json({ code: Code.InvalidInput, message: 'Invalid email' });
    }
    if (!password || password.length < 6) {
      return res.json({ code: Code.InvalidInput, message: 'Password must be at least 6 characters' });
    }
    if (password !== confirmPassword) {
      return res.json({ code: Code.InvalidInput, message: 'Passwords do not match' });
    }

    const existingEmail = await UserModel.findOne({ email: email.toLowerCase() });
    if (existingEmail) {
      return res.json({ code: Code.InvalidInput, message: 'Email already exists' });
    }

    const existingUsername = await UserModel.findOne({ username });
    if (existingUsername) {
      return res.json({ code: Code.InvalidInput, message: 'Username already taken' });
    }

    const hashedPassword = Crypto.hashUsernamePassword(password);

    const user = await UserModel.create({
      username,
      email: email.toLowerCase(),
      password: hashedPassword,
      credit: FREE_SIGNUP_CREDITS,
      emailVerified: false,
      plan: 'free',
      role: 'User',
    });

    const token = jwt.sign(
      { id: user._id, email: user.email, username: user.username },
      process.env.JWT_SECRET || 'margin_secret',
      { expiresIn: '7d' }
    );

    return res.json({
      code: Code.Success,
      data: { token, user: user.secureRelease() },
    });
  } catch (err: any) {
    return res.json({ code: Code.Error, message: err.message });
  }
});

export default router;
```

- [ ] **Step 2: Create signin route**

Write `margin-backend/src/api/routes/auth/signin.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import jwt from 'jsonwebtoken';
import { Code } from '@/Constants';

const router = Router();

router.post('/signin', (req, res, next) => {
  passport.authenticate('signin', { session: false }, (err: any, user: any, info: any) => {
    if (err) return res.json({ code: Code.Error, message: err.message });
    if (!user) return res.json({ code: Code.InvalidPassword, message: info?.message || 'Login failed' });

    const token = jwt.sign(
      { id: user._id, email: user.email, username: user.username },
      process.env.JWT_SECRET || 'margin_secret',
      { expiresIn: req.body.keep_login ? '30d' : '7d' }
    );

    user.lastLogin = new Date();
    user.save();

    return res.json({
      code: Code.Success,
      data: { token, user: user.secureRelease() },
    });
  })(req, res, next);
});

export default router;
```

- [ ] **Step 3: Create Google OAuth route**

Write `margin-backend/src/api/routes/auth/google.ts`:

```typescript
import { Router } from 'express';
import { UserModel } from '@/models/User';
import { Crypto } from '@/packages/crypto/crypto';
import { Code, FREE_SIGNUP_CREDITS } from '@/Constants';
import jwt from 'jsonwebtoken';
import { v4 as uuidv4 } from 'uuid';

const router = Router();

router.post('/google', async (req, res) => {
  try {
    const { credential } = req.body;
    if (!credential) {
      return res.json({ code: Code.InvalidInput, message: 'Missing credential' });
    }

    // Decode the Google JWT (id_token) to get user info
    const payload = JSON.parse(
      Buffer.from(credential.split('.')[1], 'base64').toString()
    );

    const { sub: googleId, email, name } = payload;

    let user = await UserModel.findOne({
      $or: [{ googleId }, { email: email.toLowerCase() }],
    });

    if (!user) {
      user = await UserModel.create({
        username: name || email.split('@')[0],
        email: email.toLowerCase(),
        password: Crypto.hashUsernamePassword(uuidv4()),
        googleId,
        emailVerified: true,
        credit: FREE_SIGNUP_CREDITS,
        plan: 'free',
        role: 'User',
      });
    } else if (!user.googleId) {
      user.googleId = googleId;
      user.emailVerified = true;
      await user.save();
    }

    const token = jwt.sign(
      { id: user._id, email: user.email, username: user.username },
      process.env.JWT_SECRET || 'margin_secret',
      { expiresIn: '7d' }
    );

    user.lastLogin = new Date();
    await user.save();

    return res.json({
      code: Code.Success,
      data: { token, user: user.secureRelease() },
    });
  } catch (err: any) {
    return res.json({ code: Code.Error, message: err.message });
  }
});

export default router;
```

- [ ] **Step 4: Create auth route aggregator**

Write `margin-backend/src/api/routes/auth/auth.ts`:

```typescript
import { Router } from 'express';
import signup from './signup';
import signin from './signin';
import google from './google';

export default (router: Router) => {
  router.use('/auth', signup);
  router.use('/auth', signin);
  router.use('/auth', google);
};
```

- [ ] **Step 5: Create me route**

Write `margin-backend/src/api/routes/me.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';

export default (router: Router) => {
  router.post('/me', passport.authenticate('jwt', { session: false }), (req, res) => {
    const user = req.user as any;
    if (!user) return res.json({ code: Code.InvalidAuth, message: 'Not authenticated' });
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });
};
```

- [ ] **Step 6: Register auth and me routes**

Update `margin-backend/src/api/index.ts`:

```typescript
import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';

export default () => {
  const router = Router();

  auth(router);
  me(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
```

- [ ] **Step 7: Test auth endpoints**

Run backend:
```bash
cd margin-backend && npm run dev
```

Test signup:
```bash
curl -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@test.com","password":"123456","confirmPassword":"123456"}'
```
Expected: `{ "code": 1, "data": { "token": "...", "user": { ... } } }`

Test signin:
```bash
curl -X POST http://localhost:8001/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"test@test.com","password":"123456"}'
```
Expected: `{ "code": 1, "data": { "token": "...", "user": { ... } } }`

- [ ] **Step 8: Commit**

```bash
git add margin-backend/src/api/ margin-backend/src/models/User.ts
git commit -m "feat(backend): add auth routes (signup, signin, Google OAuth) and me endpoint"
```

---

### Task 9: Frontend Auth Pages + User Hook

**Files:**
- Create: `margin-frontend/hooks/user.ts`
- Create: `margin-frontend/app/(auth)/layout.tsx`
- Create: `margin-frontend/app/(auth)/login/page.tsx`
- Create: `margin-frontend/app/(auth)/register/page.tsx`

- [ ] **Step 1: Create user hooks**

```bash
mkdir -p margin-frontend/hooks
```

Write `margin-frontend/hooks/user.ts`:

```typescript
import useSWR from 'swr';
import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { loadProfile } from '@/store/slices/authSlice';
import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';
import { Code } from '@/lib/core/Constants';
import { useCallback, useEffect } from 'react';

export function useMe() {
  const dispatch = useDispatch();

  const { data, error, mutate } = useSWR(
    Cookie.fromDocument('access_token') ? ['/api/me', {}] : null,
    {
      onSuccess: (res: any) => {
        if (res?.code === Code.Success) {
          dispatch(loadProfile(res.data));
        }
      },
    }
  );

  return {
    data: data?.code === Code.Success ? data.data : null,
    error,
    isLoading: !data && !error,
    mutate,
  };
}

export function useReloadMe() {
  const { mutate } = useMe();
  return useCallback(() => mutate(), [mutate]);
}
```

- [ ] **Step 2: Create auth layout**

```bash
mkdir -p margin-frontend/app/\(auth\)/login margin-frontend/app/\(auth\)/register
```

Write `margin-frontend/app/(auth)/layout.tsx`:

```tsx
'use client';

import React from 'react';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-bg-soft flex items-center justify-center">
      <div className="w-full max-w-md">
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create login page**

Write `margin-frontend/app/(auth)/login/page.tsx`:

```tsx
'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GoogleLogin } from '@react-oauth/google';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';
import { Code } from '@/lib/core/Constants';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await Fetch.post<any>('/api/auth/signin', { email, password });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Login failed');
    }
    setLoading(false);
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      const res = await Fetch.post<any>('/api/auth/google', {
        credential: credentialResponse.credential,
      });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Google login failed');
    }
  };

  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule">
      <h1 className="font-serif text-3xl text-ink mb-2">Welcome back</h1>
      <p className="text-ink-muted mb-6">Sign in to continue to Margin</p>

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="you@university.edu"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="Enter password"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition disabled:opacity-50"
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>

      <div className="flex items-center gap-3 my-5">
        <div className="flex-1 h-px bg-rule" />
        <span className="text-xs text-ink-muted">or</span>
        <div className="flex-1 h-px bg-rule" />
      </div>

      <div className="flex justify-center">
        <GoogleLogin onSuccess={handleGoogleSuccess} onError={() => toast.error('Google login failed')} />
      </div>

      <p className="text-center text-sm text-ink-muted mt-6">
        Don't have an account?{' '}
        <Link href="/register" className="text-primary font-medium">Sign up</Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Create register page**

Write `margin-frontend/app/(auth)/register/page.tsx`:

```tsx
'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { GoogleLogin } from '@react-oauth/google';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';
import { Code } from '@/lib/core/Constants';

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    setLoading(true);
    try {
      const res = await Fetch.post<any>('/api/auth/signup', {
        username,
        email,
        password,
        confirmPassword,
      });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Registration failed');
    }
    setLoading(false);
  };

  const handleGoogleSuccess = async (credentialResponse: any) => {
    try {
      const res = await Fetch.post<any>('/api/auth/google', {
        credential: credentialResponse.credential,
      });
      if (res.data.code === Code.Success) {
        Cookie.set('access_token', res.data.data.token);
        router.push('/humanizer');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Google login failed');
    }
  };

  return (
    <div className="bg-white rounded-2xl p-8 shadow-sm border border-rule">
      <h1 className="font-serif text-3xl text-ink mb-2">Create account</h1>
      <p className="text-ink-muted mb-6">Start writing better with Margin</p>

      <form onSubmit={handleRegister} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Full name</label>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="Jane Smith"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="you@university.edu"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="At least 6 characters"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-ink-soft mb-1">Confirm password</label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
            placeholder="Repeat your password"
            required
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary-dark transition disabled:opacity-50"
        >
          {loading ? 'Creating account...' : 'Create account'}
        </button>
      </form>

      <div className="flex items-center gap-3 my-5">
        <div className="flex-1 h-px bg-rule" />
        <span className="text-xs text-ink-muted">or</span>
        <div className="flex-1 h-px bg-rule" />
      </div>

      <div className="flex justify-center">
        <GoogleLogin onSuccess={handleGoogleSuccess} onError={() => toast.error('Google login failed')} />
      </div>

      <p className="text-center text-sm text-ink-muted mt-6">
        Already have an account?{' '}
        <Link href="/login" className="text-primary font-medium">Sign in</Link>
      </p>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add margin-frontend/hooks/user.ts margin-frontend/app/\(auth\)/
git commit -m "feat(frontend): add auth pages (login, register) and user hook"
```

---

## Phase 3: Core Infrastructure

### Task 10: Credit Model + Endpoints

**Files:**
- Create: `margin-backend/src/models/Credit.ts`
- Create: `margin-backend/src/services/credit.service.ts`
- Create: `margin-backend/src/api/routes/credit.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create Credit model**

Write `margin-backend/src/models/Credit.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'credits', timestamps: true } })
export class Credit {
  @prop({ required: true })
  public amount!: number;

  @prop({ required: true })
  public direction!: string;

  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public status!: string;

  @prop()
  public description?: string;

  @prop()
  public orderType?: string;

  @prop()
  public orderId?: string;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = obj._id;
    delete obj.__v;
    return obj;
  }
}

export const CreditModel = getModelForClass(Credit);
```

- [ ] **Step 2: Create credit service**

```bash
mkdir -p margin-backend/src/services
```

Write `margin-backend/src/services/credit.service.ts`:

```typescript
import { UserModel } from '@/models/User';
import { CreditModel } from '@/models/Credit';
import { CreditDirection, CreditStatus } from '@/Constants';

export class CreditService {
  static async getBalance(userId: string): Promise<number> {
    const user = await UserModel.findById(userId);
    return user?.credit || 0;
  }

  static async hasEnough(userId: string, amount: number): Promise<boolean> {
    const balance = await this.getBalance(userId);
    return balance >= amount;
  }

  static async deduct(
    userId: string,
    amount: number,
    orderType: string,
    orderId: string,
    description: string
  ): Promise<boolean> {
    const user = await UserModel.findById(userId);
    if (!user || user.credit < amount) return false;

    user.credit -= amount;
    await user.save();

    await CreditModel.create({
      amount,
      direction: CreditDirection.Outbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });

    return true;
  }

  static async refund(
    userId: string,
    amount: number,
    orderType: string,
    orderId: string,
    description: string
  ): Promise<void> {
    await UserModel.findByIdAndUpdate(userId, { $inc: { credit: amount } });

    await CreditModel.create({
      amount,
      direction: CreditDirection.Inbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });
  }

  static async addCredits(
    userId: string,
    amount: number,
    description: string,
    orderType: string = 'purchase',
    orderId: string = ''
  ): Promise<void> {
    await UserModel.findByIdAndUpdate(userId, { $inc: { credit: amount } });

    await CreditModel.create({
      amount,
      direction: CreditDirection.Inbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });
  }

  static async getHistory(userId: string, limit = 50): Promise<any[]> {
    const credits = await CreditModel.find({ owner: userId })
      .sort({ createdAt: -1 })
      .limit(limit);
    return credits.map((c: any) => c.secureRelease());
  }
}
```

- [ ] **Step 3: Create credit routes**

Write `margin-backend/src/api/routes/credit.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { CreditService } from '@/services/credit.service';

export default (router: Router) => {
  router.post(
    '/credit/balance',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const balance = await CreditService.getBalance(user._id.toString());
      return res.json({ code: Code.Success, data: { balance } });
    }
  );

  router.post(
    '/credit/history',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const history = await CreditService.getHistory(user._id.toString());
      return res.json({ code: Code.Success, data: history });
    }
  );
};
```

- [ ] **Step 4: Register credit routes in API index**

Update `margin-backend/src/api/index.ts`:

```typescript
import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
```

- [ ] **Step 5: Commit**

```bash
git add margin-backend/src/models/Credit.ts margin-backend/src/services/credit.service.ts margin-backend/src/api/routes/credit.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add Credit model, credit service, and balance/history endpoints"
```

---

### Task 11: Document Model + Upload/Import Endpoints

**Files:**
- Create: `margin-backend/src/models/Document.ts`
- Create: `margin-backend/src/services/document.service.ts`
- Create: `margin-backend/src/api/routes/document.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create Document model**

Write `margin-backend/src/models/Document.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'documents', timestamps: true } })
export class Document {
  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public title!: string;

  @prop({ required: true })
  public content!: string;

  @prop({ required: true })
  public sourceType!: string;

  @prop()
  public sourceUrl?: string;

  @prop()
  public fileKey?: string;

  @prop({ default: 'text/plain' })
  public mimeType!: string;

  @prop({ default: 0 })
  public wordCount!: number;
}

export const DocumentModel = getModelForClass(Document);
```

- [ ] **Step 2: Create document service**

Write `margin-backend/src/services/document.service.ts`:

```typescript
import mammoth from 'mammoth';
import pdfParse from 'pdf-parse';
import * as cheerio from 'cheerio';
import axios from 'axios';
import AWS from 'aws-sdk';
import { DocumentModel } from '@/models/Document';

const s3 = new AWS.S3({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION,
});

export class DocumentService {
  static countWords(text: string): number {
    return text.trim().split(/\s+/).filter(Boolean).length;
  }

  static async parseFile(buffer: Buffer, mimeType: string): Promise<string> {
    if (mimeType === 'application/pdf') {
      const result = await pdfParse(buffer);
      return result.text;
    }
    if (
      mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ) {
      const result = await mammoth.extractRawText({ buffer });
      return result.value;
    }
    // txt, md
    return buffer.toString('utf-8');
  }

  static async uploadToS3(
    buffer: Buffer,
    key: string,
    mimeType: string
  ): Promise<string> {
    await s3
      .upload({
        Bucket: process.env.AWS_S3_BUCKET || '',
        Key: key,
        Body: buffer,
        ContentType: mimeType,
      })
      .promise();
    return key;
  }

  static async scrapeUrl(url: string): Promise<{ title: string; content: string }> {
    const { data: html } = await axios.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; MarginBot/1.0)' },
      timeout: 10000,
    });

    const $ = cheerio.load(html);

    // Remove nav, scripts, ads, headers, footers
    $('script, style, nav, header, footer, aside, .ads, .advertisement, .sidebar').remove();

    // Try to find main content
    let content = '';
    const selectors = ['article', 'main', '[role="main"]', '.post-content', '.entry-content'];
    for (const sel of selectors) {
      if ($(sel).length) {
        content = $(sel).first().text();
        break;
      }
    }
    if (!content) {
      content = $('body').text();
    }

    // Clean up whitespace
    content = content.replace(/\s+/g, ' ').trim();

    const title = $('title').text().trim() || $('h1').first().text().trim() || 'Untitled';

    return { title, content };
  }

  static async createFromText(
    owner: string,
    title: string,
    content: string,
    sourceType: string,
    sourceUrl?: string,
    fileKey?: string,
    mimeType?: string
  ) {
    return DocumentModel.create({
      owner,
      title,
      content,
      sourceType,
      sourceUrl,
      fileKey,
      mimeType: mimeType || 'text/plain',
      wordCount: this.countWords(content),
    });
  }
}
```

- [ ] **Step 3: Create document routes**

Write `margin-backend/src/api/routes/document.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import multer from 'multer';
import { v4 as uuidv4 } from 'uuid';
import { Code } from '@/Constants';
import { DocumentService } from '@/services/document.service';
import { DocumentModel } from '@/models/Document';

const upload = multer({ limits: { fileSize: 10 * 1024 * 1024 } }); // 10MB

const ALLOWED_MIMES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'text/plain',
  'text/markdown',
];

export default (router: Router) => {
  router.post(
    '/document/upload',
    passport.authenticate('jwt', { session: false }),
    upload.single('file'),
    async (req, res) => {
      try {
        const user = req.user as any;
        const file = req.file;
        if (!file) return res.json({ code: Code.InvalidInput, message: 'No file provided' });
        if (!ALLOWED_MIMES.includes(file.mimetype)) {
          return res.json({ code: Code.InvalidInput, message: 'Unsupported file type' });
        }

        const content = await DocumentService.parseFile(file.buffer, file.mimetype);
        const fileKey = `documents/${user._id}/${uuidv4()}-${file.originalname}`;
        await DocumentService.uploadToS3(file.buffer, fileKey, file.mimetype);

        const doc = await DocumentService.createFromText(
          user._id.toString(),
          file.originalname,
          content,
          'upload',
          undefined,
          fileKey,
          file.mimetype
        );

        return res.json({ code: Code.Success, data: doc });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );

  router.post(
    '/document/import-url',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      try {
        const user = req.user as any;
        const { url } = req.body;
        if (!url) return res.json({ code: Code.InvalidInput, message: 'URL required' });

        const { title, content } = await DocumentService.scrapeUrl(url);
        const doc = await DocumentService.createFromText(
          user._id.toString(),
          title,
          content,
          'url',
          url
        );

        return res.json({ code: Code.Success, data: doc });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );

  router.post(
    '/document/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const docs = await DocumentModel.find({ owner: user._id.toString() })
        .sort({ createdAt: -1 })
        .select('-content');
      return res.json({ code: Code.Success, data: docs });
    }
  );

  router.post(
    '/document/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const doc = await DocumentModel.findById(id);
      if (!doc) return res.json({ code: Code.NotFound, message: 'Document not found' });
      return res.json({ code: Code.Success, data: doc });
    }
  );
};
```

- [ ] **Step 4: Register document routes**

Update `margin-backend/src/api/index.ts` to add:

```typescript
import document from './routes/document';
```

And in the function body add:
```typescript
document(router);
```

- [ ] **Step 5: Commit**

```bash
git add margin-backend/src/models/Document.ts margin-backend/src/services/document.service.ts margin-backend/src/api/routes/document.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add Document model, file parsing, URL scraping, and upload endpoints"
```

---

### Task 12: AI Service Manager (OpenAI + Claude Fallback)

**Files:**
- Create: `margin-backend/src/services/ai/openai.service.ts`
- Create: `margin-backend/src/services/ai/claude.service.ts`
- Create: `margin-backend/src/services/ai/ai.service.manager.ts`

- [ ] **Step 1: Create OpenAI service**

```bash
mkdir -p margin-backend/src/services/ai
```

Write `margin-backend/src/services/ai/openai.service.ts`:

```typescript
import OpenAI from 'openai';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export class OpenAIService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number; jsonMode?: boolean } = {}
  ): Promise<string> {
    const response = await openai.chat.completions.create({
      model: 'gpt-4o',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxTokens ?? 4096,
      response_format: options.jsonMode ? { type: 'json_object' } : undefined,
    });

    return response.choices[0]?.message?.content || '';
  }

  static async chatStream(
    systemPrompt: string,
    userPrompt: string,
    onChunk: (chunk: string) => void,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<string> {
    const stream = await openai.chat.completions.create({
      model: 'gpt-4o',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: options.temperature ?? 0.7,
      max_tokens: options.maxTokens ?? 4096,
      stream: true,
    });

    let full = '';
    for await (const chunk of stream) {
      const content = chunk.choices[0]?.delta?.content || '';
      if (content) {
        full += content;
        onChunk(content);
      }
    }
    return full;
  }
}
```

- [ ] **Step 2: Create Claude service**

Write `margin-backend/src/services/ai/claude.service.ts`:

```typescript
import Anthropic from '@anthropic-ai/sdk';

const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });

export class ClaudeService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<string> {
    const response = await anthropic.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: options.maxTokens ?? 4096,
      system: systemPrompt,
      messages: [{ role: 'user', content: userPrompt }],
      temperature: options.temperature ?? 0.7,
    });

    const textBlock = response.content.find((b: any) => b.type === 'text');
    return textBlock ? (textBlock as any).text : '';
  }

  static async chatStream(
    systemPrompt: string,
    userPrompt: string,
    onChunk: (chunk: string) => void,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<string> {
    const stream = anthropic.messages.stream({
      model: 'claude-sonnet-4-20250514',
      max_tokens: options.maxTokens ?? 4096,
      system: systemPrompt,
      messages: [{ role: 'user', content: userPrompt }],
      temperature: options.temperature ?? 0.7,
    });

    let full = '';
    for await (const event of stream) {
      if (event.type === 'content_block_delta' && (event.delta as any).type === 'text_delta') {
        const text = (event.delta as any).text;
        full += text;
        onChunk(text);
      }
    }
    return full;
  }
}
```

- [ ] **Step 3: Create AI Service Manager**

Write `margin-backend/src/services/ai/ai.service.manager.ts`:

```typescript
import { OpenAIService } from './openai.service';
import { ClaudeService } from './claude.service';

type AIProvider = 'openai' | 'claude';

export class AIServiceManager {
  private static instance: AIServiceManager;
  private primaryProvider: AIProvider = 'openai';
  private secondaryProvider: AIProvider = 'claude';

  static getInstance(): AIServiceManager {
    if (!this.instance) {
      this.instance = new AIServiceManager();
    }
    return this.instance;
  }

  getService(provider?: AIProvider) {
    const p = provider || this.primaryProvider;
    return p === 'openai' ? OpenAIService : ClaudeService;
  }

  async tryWithFallback<T>(
    operation: string,
    fn: (service: typeof OpenAIService | typeof ClaudeService) => Promise<T>
  ): Promise<T> {
    try {
      const primaryService = this.getService(this.primaryProvider);
      return await fn(primaryService);
    } catch (err: any) {
      console.error(`[AI] ${operation} failed with ${this.primaryProvider}:`, err.message);
      console.log(`[AI] Falling back to ${this.secondaryProvider}`);
      const fallbackService = this.getService(this.secondaryProvider);
      return await fn(fallbackService);
    }
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add margin-backend/src/services/ai/
git commit -m "feat(backend): add AI service manager with OpenAI primary and Claude fallback"
```

---

## Phase 4: Humanizer Feature

### Task 13: HumanizeJob Model + Humanizer Service

**Files:**
- Create: `margin-backend/src/models/HumanizeJob.ts`
- Create: `margin-backend/src/services/humanizer.service.ts`

- [ ] **Step 1: Create HumanizeJob model**

Write `margin-backend/src/models/HumanizeJob.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'humanize_jobs', timestamps: true } })
export class HumanizeJob {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public documentId?: string;

  @prop({ required: true })
  public inputText!: string;

  @prop({ default: '' })
  public outputHtml!: string;

  @prop({ default: '' })
  public outputText!: string;

  @prop({ default: 'academic' })
  public tone!: string;

  @prop({ default: 50 })
  public strength!: number;

  @prop({ default: 'match' })
  public lengthMode!: string;

  @prop({ default: 0 })
  public aiScoreIn!: number;

  @prop({ default: 0 })
  public aiScoreOut!: number;

  @prop({ default: 0 })
  public changesCount!: number;

  @prop({ default: 0 })
  public creditsUsed!: number;

  @prop({ default: 'processing' })
  public status!: string;
}

export const HumanizeJobModel = getModelForClass(HumanizeJob);
```

- [ ] **Step 2: Create humanizer service with prompt builders**

Write `margin-backend/src/services/humanizer.service.ts`:

```typescript
import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { DocumentService } from '@/services/document.service';

const TONE_INSTRUCTIONS: Record<string, string> = {
  academic:
    'Write in a formal academic tone. Use discipline-appropriate vocabulary, passive voice where conventional, hedging language (e.g., "suggests", "may indicate"), and structured argumentation.',
  casual:
    'Write in a natural, conversational tone. Use contractions, first person, shorter sentences, and everyday vocabulary while keeping the content accurate.',
  persuasive:
    'Write in a compelling, persuasive tone. Use rhetorical questions, strong transitions, active voice, and confident assertions backed by evidence.',
};

const LENGTH_INSTRUCTIONS: Record<string, string> = {
  match: 'Keep the output approximately the same length as the input.',
  shorter: 'Make the output about 15% shorter than the input. Be more concise.',
  longer: 'Make the output about 15% longer. Add more detail and elaboration.',
};

function buildHumanizePrompt(tone: string, strength: number, lengthMode: string): string {
  const toneInstr = TONE_INSTRUCTIONS[tone] || TONE_INSTRUCTIONS.academic;
  const lengthInstr = LENGTH_INSTRUCTIONS[lengthMode] || LENGTH_INSTRUCTIONS.match;

  const strengthDesc =
    strength <= 30
      ? 'Make LIGHT edits only. Fix obviously robotic/AI-sounding phrases but preserve the original wording as much as possible.'
      : strength <= 70
        ? 'Make MODERATE edits. Rewrite sentences that sound AI-generated while preserving the core meaning and structure.'
        : 'Do a FULL rewrite. Completely rephrase all content to sound naturally human-written while preserving all factual claims and arguments.';

  return `You are a text humanizer. Your job is to rewrite AI-generated text so it reads as if written by a human student.

${toneInstr}

Strength level (${strength}/100): ${strengthDesc}

${lengthInstr}

IMPORTANT: Respond with valid JSON only. No markdown, no code fences. The JSON must have this structure:
{
  "rewrittenText": "the full rewritten text as plain text",
  "changes": [
    { "original": "phrase from input", "replacement": "rewritten phrase", "reason": "brief reason" }
  ]
}

List every changed phrase in the changes array. If a sentence was unchanged, do not include it.`;
}

function buildAiScorePrompt(): string {
  return `You are an AI text detector. Analyze the given text and estimate how likely it is to be AI-generated.

Respond with valid JSON only:
{
  "score": <number 0-100>,
  "reasoning": "brief explanation"
}

Score guide:
0-20: Very likely human-written
21-40: Mostly human with some AI-like patterns
41-60: Uncertain / mixed
61-80: Likely AI-generated
81-100: Almost certainly AI-generated`;
}

export class HumanizerService {
  static buildSystemPrompt(tone: string, strength: number, lengthMode: string): string {
    return buildHumanizePrompt(tone, strength, lengthMode);
  }

  static buildAiScoreSystemPrompt(): string {
    return buildAiScorePrompt();
  }

  static async checkAiScore(text: string): Promise<number> {
    const ai = AIServiceManager.getInstance();
    const result = await ai.tryWithFallback('ai-score', async (service) => {
      return service.chat(buildAiScorePrompt(), text, {
        temperature: 0.3,
        jsonMode: true,
      });
    });

    try {
      const parsed = JSON.parse(result);
      return Math.min(100, Math.max(0, parsed.score));
    } catch {
      return 50;
    }
  }

  static async humanize(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string
  ): Promise<{ rewrittenText: string; changes: Array<{ original: string; replacement: string; reason: string }> }> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    const result = await ai.tryWithFallback('humanize', async (service) => {
      return service.chat(systemPrompt, text, {
        temperature: 0.7,
        maxTokens: 4096,
        jsonMode: true,
      });
    });

    try {
      return JSON.parse(result);
    } catch {
      return { rewrittenText: result, changes: [] };
    }
  }

  static async humanizeStream(
    text: string,
    tone: string,
    strength: number,
    lengthMode: string,
    onChunk: (chunk: string) => void
  ): Promise<string> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = buildHumanizePrompt(tone, strength, lengthMode);

    return ai.tryWithFallback('humanize-stream', async (service) => {
      return service.chatStream(systemPrompt, text, onChunk, {
        temperature: 0.7,
        maxTokens: 4096,
      });
    });
  }

  static calculateCredits(wordCount: number): number {
    return Math.max(1, Math.ceil(wordCount / 100));
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add margin-backend/src/models/HumanizeJob.ts margin-backend/src/services/humanizer.service.ts
git commit -m "feat(backend): add HumanizeJob model and humanizer service with prompt builders"
```

---

### Task 14: Humanizer SSE Endpoint + History

**Files:**
- Create: `margin-backend/src/api/routes/humanize.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create humanize routes with SSE streaming**

Write `margin-backend/src/api/routes/humanize.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { HumanizerService } from '@/services/humanizer.service';
import { CreditService } from '@/services/credit.service';
import { DocumentService } from '@/services/document.service';

export default (router: Router) => {
  // SSE streaming humanize
  router.post(
    '/humanize/run',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text, tone = 'academic', strength = 50, lengthMode = 'match' } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      const wordCount = DocumentService.countWords(text);
      const creditCost = HumanizerService.calculateCredits(wordCount);

      if (!(await CreditService.hasEnough(user._id.toString(), creditCost))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      // Create job record
      const job = await HumanizeJobModel.create({
        owner: user._id.toString(),
        inputText: text,
        tone,
        strength,
        lengthMode,
        status: 'processing',
      });

      // Set up SSE
      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
        'X-Accel-Buffering': 'no',
      });

      try {
        // Get input AI score
        const aiScoreIn = await HumanizerService.checkAiScore(text);
        res.write(`data: ${JSON.stringify({ type: 'ai_score_in', score: aiScoreIn })}\n\n`);

        // Stream the humanized output
        let fullOutput = '';
        await HumanizerService.humanizeStream(
          text,
          tone,
          strength,
          lengthMode,
          (chunk: string) => {
            fullOutput += chunk;
            res.write(`data: ${JSON.stringify({ type: 'chunk', content: chunk })}\n\n`);
          }
        );

        // Parse the full JSON response
        let rewrittenText = fullOutput;
        let changes: any[] = [];
        try {
          const parsed = JSON.parse(fullOutput);
          rewrittenText = parsed.rewrittenText || fullOutput;
          changes = parsed.changes || [];
        } catch {
          // If streaming didn't produce valid JSON, use raw text
        }

        // Get output AI score
        const aiScoreOut = await HumanizerService.checkAiScore(rewrittenText);

        // Deduct credits
        await CreditService.deduct(
          user._id.toString(),
          creditCost,
          'humanize',
          job._id.toString(),
          `Humanize ${wordCount} words`
        );

        // Update job
        job.outputText = rewrittenText;
        job.outputHtml = rewrittenText; // Frontend builds diff from changes
        job.aiScoreIn = aiScoreIn;
        job.aiScoreOut = aiScoreOut;
        job.changesCount = changes.length;
        job.creditsUsed = creditCost;
        job.status = 'completed';
        await job.save();

        // Send final result
        res.write(
          `data: ${JSON.stringify({
            type: 'done',
            jobId: job._id,
            rewrittenText,
            changes,
            aiScoreIn,
            aiScoreOut,
            changesCount: changes.length,
            creditsUsed: creditCost,
          })}\n\n`
        );
      } catch (err: any) {
        // Refund on failure
        job.status = 'failed';
        await job.save();
        res.write(`data: ${JSON.stringify({ type: 'error', message: err.message })}\n\n`);
      }

      res.end();
    }
  );

  // Check AI score (standalone)
  router.post(
    '/humanize/check-score',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text } = req.body;
      if (!text) return res.json({ code: Code.InvalidInput, message: 'Text required' });

      const hasCreds = await CreditService.hasEnough(user._id.toString(), CreditCosts.AI_SCORE_CHECK);
      if (!hasCreds) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const score = await HumanizerService.checkAiScore(text);
      await CreditService.deduct(
        user._id.toString(),
        CreditCosts.AI_SCORE_CHECK,
        'ai_score',
        '',
        'AI detection score check'
      );

      return res.json({ code: Code.Success, data: { score } });
    }
  );

  // History
  router.post(
    '/humanize/history',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const jobs = await HumanizeJobModel.find({ owner: user._id.toString() })
        .sort({ createdAt: -1 })
        .select('-inputText -outputHtml -outputText')
        .limit(50);
      return res.json({ code: Code.Success, data: jobs });
    }
  );

  // Get single job
  router.post(
    '/humanize/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await HumanizeJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );
};
```

- [ ] **Step 2: Register humanize routes**

Update `margin-backend/src/api/index.ts` — add import and registration:

```typescript
import humanize from './routes/humanize';
```

In the function body:
```typescript
humanize(router);
```

- [ ] **Step 3: Commit**

```bash
git add margin-backend/src/api/routes/humanize.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add humanizer SSE endpoint, AI score check, and history routes"
```

---

### Task 15: Frontend Workspace Layout (Sidebar + Topbar)

**Files:**
- Create: `margin-frontend/components/layout/Sidebar.tsx`
- Create: `margin-frontend/components/layout/Topbar.tsx`
- Create: `margin-frontend/components/ui/CreditPill.tsx`
- Create: `margin-frontend/hooks/credit.ts`
- Create: `margin-frontend/app/(workspace)/layout.tsx`

- [ ] **Step 1: Create credit hook**

Write `margin-frontend/hooks/credit.ts`:

```typescript
import useSWR from 'swr';

export function useBalance() {
  const { data, mutate } = useSWR(['/api/credit/balance', {}]);
  return {
    balance: data?.code === 1 ? data.data.balance : 0,
    mutate,
  };
}

export function useCreditHistory() {
  const { data } = useSWR(['/api/credit/history', {}]);
  return { history: data?.code === 1 ? data.data : [] };
}
```

- [ ] **Step 2: Create CreditPill component**

```bash
mkdir -p margin-frontend/components/ui
```

Write `margin-frontend/components/ui/CreditPill.tsx`:

```tsx
'use client';

import { useBalance } from '@/hooks/credit';

export function CreditPill() {
  const { balance } = useBalance();

  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-blue rounded-full">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0022FF" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 6v12M8 10h8M8 14h8" />
      </svg>
      <span className="text-xs font-semibold text-primary font-mono">{balance}</span>
    </div>
  );
}
```

- [ ] **Step 3: Create Sidebar**

```bash
mkdir -p margin-frontend/components/layout
```

Write `margin-frontend/components/layout/Sidebar.tsx`:

```tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { useMe } from '@/hooks/user';

const NAV_ITEMS = [
  { href: '/humanizer', label: 'Humanizer', icon: 'H' },
  { href: '/auto-cite', label: 'Auto-Cite', icon: 'C' },
  { href: '/library', label: 'Library', icon: 'L' },
  { href: '/history', label: 'History', icon: 'R' },
];

export function Sidebar() {
  const pathname = usePathname();
  const { data: user } = useMe();

  return (
    <aside className="w-64 h-screen bg-white border-r border-rule flex flex-col fixed left-0 top-0">
      {/* Logo */}
      <div className="px-5 py-4 border-b border-rule">
        <Link href="/humanizer" className="font-serif text-2xl text-ink italic">
          Margin
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition',
                isActive
                  ? 'bg-bg-blue text-primary'
                  : 'text-ink-soft hover:bg-bg-soft'
              )}
            >
              <span
                className={clsx(
                  'w-7 h-7 rounded-md flex items-center justify-center text-xs font-bold',
                  isActive ? 'bg-primary text-white' : 'bg-bg-soft text-ink-muted'
                )}
              >
                {item.icon}
              </span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* User */}
      <div className="px-4 py-3 border-t border-rule">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-white text-xs font-bold">
            {user?.username?.charAt(0)?.toUpperCase() || '?'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-ink truncate">{user?.username || 'Guest'}</p>
            <p className="text-xs text-ink-muted truncate">{user?.email || ''}</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
```

- [ ] **Step 4: Create Topbar**

Write `margin-frontend/components/layout/Topbar.tsx`:

```tsx
'use client';

import { usePathname } from 'next/navigation';
import { CreditPill } from '@/components/ui/CreditPill';

const TITLES: Record<string, string> = {
  '/humanizer': 'Humanizer',
  '/auto-cite': 'Auto-Cite',
  '/library': 'Library',
  '/history': 'History',
};

export function Topbar() {
  const pathname = usePathname();
  const title = TITLES[pathname] || 'Margin';

  return (
    <header className="h-[58px] border-b border-rule bg-white flex items-center justify-between px-6">
      <h1 className="text-sm font-semibold text-ink">{title}</h1>
      <div className="flex items-center gap-3">
        <CreditPill />
      </div>
    </header>
  );
}
```

- [ ] **Step 5: Create workspace layout**

```bash
mkdir -p margin-frontend/app/\(workspace\)/humanizer margin-frontend/app/\(workspace\)/auto-cite margin-frontend/app/\(workspace\)/library margin-frontend/app/\(workspace\)/history
```

Write `margin-frontend/app/(workspace)/layout.tsx`:

```tsx
'use client';

import React from 'react';
import { useRouter } from 'next/navigation';
import { Sidebar } from '@/components/layout/Sidebar';
import { Topbar } from '@/components/layout/Topbar';
import { ClientOnly } from '@/components/common/ClientOnly';
import { useMe } from '@/hooks/user';
import Cookie from '@/lib/core/fetch/Cookie';
import { useEffect } from 'react';

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (!isLoading && !user && !Cookie.fromDocument('access_token')) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  return (
    <ClientOnly>
      <div className="min-h-screen bg-bg-soft">
        <Sidebar />
        <div className="ml-64">
          <Topbar />
          <main className="p-6">{children}</main>
        </div>
      </div>
    </ClientOnly>
  );
}
```

- [ ] **Step 6: Create placeholder pages**

Write `margin-frontend/app/(workspace)/humanizer/page.tsx`:

```tsx
'use client';

export default function HumanizerPage() {
  return <div>Humanizer — coming in Task 16</div>;
}
```

Write `margin-frontend/app/(workspace)/auto-cite/page.tsx`:

```tsx
'use client';

export default function AutoCitePage() {
  return <div>Auto-Cite — coming in Task 20</div>;
}
```

Write `margin-frontend/app/(workspace)/library/page.tsx`:

```tsx
'use client';

export default function LibraryPage() {
  return <div>Library — coming in Task 24</div>;
}
```

Write `margin-frontend/app/(workspace)/history/page.tsx`:

```tsx
'use client';

export default function HistoryPage() {
  return <div>History — coming in Task 25</div>;
}
```

- [ ] **Step 7: Verify layout renders**

Run:
```bash
cd margin-frontend && npm run dev
```

Open `http://localhost:8002/humanizer`. Expected: sidebar on left with nav items, topbar with credit pill, main area showing placeholder text.

- [ ] **Step 8: Commit**

```bash
git add margin-frontend/components/layout/ margin-frontend/components/ui/CreditPill.tsx margin-frontend/hooks/credit.ts margin-frontend/app/\(workspace\)/
git commit -m "feat(frontend): add workspace layout with sidebar, topbar, and placeholder pages"
```

---

### Task 16: Frontend Humanizer UI (HumBoard + HumToolbar + InputPane)

**Files:**
- Create: `margin-frontend/store/slices/humanizerSlice.ts`
- Modify: `margin-frontend/store/rootReducer.ts`
- Create: `margin-frontend/components/humanizer/HumToolbar.tsx`
- Create: `margin-frontend/components/humanizer/InputPane.tsx`
- Create: `margin-frontend/components/common/DropZone.tsx`
- Create: `margin-frontend/components/common/UrlImport.tsx`

- [ ] **Step 1: Create humanizer slice**

Write `margin-frontend/store/slices/humanizerSlice.ts`:

```typescript
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface HumanizerState {
  tone: string;
  strength: number;
  lengthMode: string;
  inputText: string;
  inputSource: 'paste' | 'upload' | 'url';
  outputText: string;
  changes: Array<{ original: string; replacement: string; reason: string }>;
  aiScoreIn: number;
  aiScoreOut: number;
  isProcessing: boolean;
  currentJobId: string | null;
}

const initialState: HumanizerState = {
  tone: 'academic',
  strength: 50,
  lengthMode: 'match',
  inputText: '',
  inputSource: 'paste',
  outputText: '',
  changes: [],
  aiScoreIn: 0,
  aiScoreOut: 0,
  isProcessing: false,
  currentJobId: null,
};

const humanizerSlice = createSlice({
  name: 'humanizer',
  initialState,
  reducers: {
    setTone(state, action: PayloadAction<string>) {
      state.tone = action.payload;
    },
    setStrength(state, action: PayloadAction<number>) {
      state.strength = action.payload;
    },
    setLengthMode(state, action: PayloadAction<string>) {
      state.lengthMode = action.payload;
    },
    setInputText(state, action: PayloadAction<string>) {
      state.inputText = action.payload;
    },
    setInputSource(state, action: PayloadAction<'paste' | 'upload' | 'url'>) {
      state.inputSource = action.payload;
    },
    setProcessing(state, action: PayloadAction<boolean>) {
      state.isProcessing = action.payload;
    },
    setResult(
      state,
      action: PayloadAction<{
        outputText: string;
        changes: Array<{ original: string; replacement: string; reason: string }>;
        aiScoreIn: number;
        aiScoreOut: number;
        jobId: string;
      }>
    ) {
      state.outputText = action.payload.outputText;
      state.changes = action.payload.changes;
      state.aiScoreIn = action.payload.aiScoreIn;
      state.aiScoreOut = action.payload.aiScoreOut;
      state.currentJobId = action.payload.jobId;
      state.isProcessing = false;
    },
    resetOutput(state) {
      state.outputText = '';
      state.changes = [];
      state.aiScoreIn = 0;
      state.aiScoreOut = 0;
      state.currentJobId = null;
    },
  },
});

export const {
  setTone,
  setStrength,
  setLengthMode,
  setInputText,
  setInputSource,
  setProcessing,
  setResult,
  resetOutput,
} = humanizerSlice.actions;
export default humanizerSlice.reducer;
```

- [ ] **Step 2: Add humanizer slice to rootReducer**

Update `margin-frontend/store/rootReducer.ts`:

```typescript
import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
```

- [ ] **Step 3: Create HumToolbar**

```bash
mkdir -p margin-frontend/components/humanizer
```

Write `margin-frontend/components/humanizer/HumToolbar.tsx`:

```tsx
'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setTone, setStrength, setLengthMode } from '@/store/slices/humanizerSlice';
import { clsx } from 'clsx';

const TONES = [
  { value: 'academic', label: 'Academic' },
  { value: 'casual', label: 'Casual' },
  { value: 'persuasive', label: 'Persuasive' },
];

const LENGTHS = [
  { value: 'shorter', label: 'Shorter' },
  { value: 'match', label: 'Match' },
  { value: 'longer', label: 'Longer' },
];

export function HumToolbar() {
  const dispatch = useDispatch();
  const { tone, strength, lengthMode } = useSelector((s: RootState) => s.humanizer);

  return (
    <div className="flex items-center gap-6 px-5 py-3 border-b border-rule bg-white">
      {/* Tone pills */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted mr-1">Tone</span>
        {TONES.map((t) => (
          <button
            key={t.value}
            onClick={() => dispatch(setTone(t.value))}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition',
              tone === t.value
                ? 'bg-primary text-white'
                : 'bg-bg-soft text-ink-soft hover:bg-rule'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Strength slider */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted">Strength</span>
        <input
          type="range"
          min={0}
          max={100}
          value={strength}
          onChange={(e) => dispatch(setStrength(Number(e.target.value)))}
          className="w-24 accent-primary"
        />
        <span className="text-xs font-mono text-ink-soft w-8">{strength}%</span>
      </div>

      {/* Length toggle */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-ink-muted mr-1">Length</span>
        {LENGTHS.map((l) => (
          <button
            key={l.value}
            onClick={() => dispatch(setLengthMode(l.value))}
            className={clsx(
              'px-3 py-1 rounded-full text-xs font-medium transition',
              lengthMode === l.value
                ? 'bg-purple text-white'
                : 'bg-bg-soft text-ink-soft hover:bg-rule'
            )}
          >
            {l.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create DropZone component**

Write `margin-frontend/components/common/DropZone.tsx`:

```tsx
'use client';

import { useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { clsx } from 'clsx';

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'text/plain': ['.txt'],
  'text/markdown': ['.md'],
};

interface DropZoneProps {
  onFile: (file: File) => void;
  uploading?: boolean;
}

export function DropZone({ onFile, uploading }: DropZoneProps) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) onFile(accepted[0]);
    },
    [onFile]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: ACCEPT,
    maxSize: 10 * 1024 * 1024,
    multiple: false,
  });

  return (
    <div
      {...getRootProps()}
      className={clsx(
        'border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition',
        isDragActive ? 'border-primary bg-bg-blue' : 'border-rule hover:border-ink-muted',
        uploading && 'opacity-50 pointer-events-none'
      )}
    >
      <input {...getInputProps()} />
      <div className="text-ink-muted text-sm">
        {isDragActive ? (
          <p>Drop your file here</p>
        ) : (
          <>
            <p className="font-medium text-ink-soft">Drag & drop your file</p>
            <p className="mt-1 text-xs">PDF, DOCX, TXT, MD (max 10 MB)</p>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create UrlImport component**

Write `margin-frontend/components/common/UrlImport.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

interface UrlImportProps {
  onImport: (content: string, title: string) => void;
}

export function UrlImport({ onImport }: UrlImportProps) {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);

  const handleFetch = async () => {
    if (!url.trim()) return;
    setLoading(true);
    try {
      const res = await Fetch.postWithAccessToken<any>('/api/document/import-url', { url });
      if (res.data.code === Code.Success) {
        onImport(res.data.data.content, res.data.data.title);
        toast.success('Content imported');
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Failed to import URL');
    }
    setLoading(false);
  };

  return (
    <div className="flex gap-2">
      <input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="https://example.com/article"
        className="flex-1 px-4 py-2.5 rounded-lg border border-rule focus:border-primary focus:ring-1 focus:ring-primary outline-none text-sm"
      />
      <button
        onClick={handleFetch}
        disabled={loading || !url.trim()}
        className="px-4 py-2.5 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition disabled:opacity-50"
      >
        {loading ? 'Fetching...' : 'Fetch'}
      </button>
    </div>
  );
}
```

- [ ] **Step 6: Create InputPane**

Write `margin-frontend/components/humanizer/InputPane.tsx`:

```tsx
'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setInputText, setInputSource } from '@/store/slices/humanizerSlice';
import { DropZone } from '@/components/common/DropZone';
import { UrlImport } from '@/components/common/UrlImport';
import { clsx } from 'clsx';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

const TABS = [
  { value: 'paste' as const, label: 'Paste text' },
  { value: 'upload' as const, label: 'Upload file' },
  { value: 'url' as const, label: 'Import URL' },
];

export function InputPane() {
  const dispatch = useDispatch();
  const { inputText, inputSource } = useSelector((s: RootState) => s.humanizer);
  const [uploading, setUploading] = useState(false);

  const handleFile = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await Fetch.postWithAccessToken<any>('/api/document/upload', formData);
      if (res.data.code === Code.Success) {
        dispatch(setInputText(res.data.data.content));
        dispatch(setInputSource('paste'));
        toast.success(`Loaded ${res.data.data.wordCount} words`);
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Upload failed');
    }
    setUploading(false);
  };

  const handleUrlImport = (content: string) => {
    dispatch(setInputText(content));
    dispatch(setInputSource('paste'));
  };

  const wordCount = inputText.trim().split(/\s+/).filter(Boolean).length;

  return (
    <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-rule">
        {TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => dispatch(setInputSource(tab.value))}
            className={clsx(
              'px-4 py-2.5 text-xs font-medium transition border-b-2',
              inputSource === tab.value
                ? 'border-primary text-primary'
                : 'border-transparent text-ink-muted hover:text-ink-soft'
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 p-4">
        {inputSource === 'paste' && (
          <textarea
            value={inputText}
            onChange={(e) => dispatch(setInputText(e.target.value))}
            placeholder="Paste your text here..."
            className="w-full h-full min-h-[300px] resize-none outline-none text-sm text-ink leading-relaxed"
          />
        )}
        {inputSource === 'upload' && <DropZone onFile={handleFile} uploading={uploading} />}
        {inputSource === 'url' && <UrlImport onImport={handleUrlImport} />}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-rule flex items-center justify-between">
        <span className="text-xs text-ink-muted font-mono">{wordCount} words</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add margin-frontend/store/ margin-frontend/components/humanizer/ margin-frontend/components/common/
git commit -m "feat(frontend): add humanizer toolbar, input pane with paste/upload/URL, and redux slice"
```

---

### Task 17: Frontend Humanizer Output + Board Assembly

**Files:**
- Create: `margin-frontend/components/ui/AiMeter.tsx`
- Create: `margin-frontend/components/humanizer/OutputPane.tsx`
- Create: `margin-frontend/components/humanizer/InsightCards.tsx`
- Create: `margin-frontend/components/humanizer/HumBoard.tsx`
- Modify: `margin-frontend/app/(workspace)/humanizer/page.tsx`

- [ ] **Step 1: Create AiMeter component**

Write `margin-frontend/components/ui/AiMeter.tsx`:

```tsx
'use client';

import { clsx } from 'clsx';

interface AiMeterProps {
  score: number;
  label?: string;
}

export function AiMeter({ score, label }: AiMeterProps) {
  const color =
    score <= 30 ? 'bg-success' : score <= 60 ? 'bg-warn' : 'bg-error';
  const textColor =
    score <= 30 ? 'text-success' : score <= 60 ? 'text-warn' : 'text-error';

  return (
    <div className="flex items-center gap-2">
      {label && <span className="text-xs text-ink-muted">{label}</span>}
      <div className="w-20 h-2 bg-rule rounded-full overflow-hidden">
        <div className={clsx('h-full rounded-full transition-all', color)} style={{ width: `${score}%` }} />
      </div>
      <span className={clsx('text-xs font-mono font-semibold', textColor)}>{score}%</span>
    </div>
  );
}
```

- [ ] **Step 2: Create OutputPane**

Write `margin-frontend/components/humanizer/OutputPane.tsx`:

```tsx
'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { AiMeter } from '@/components/ui/AiMeter';

export function OutputPane() {
  const { outputText, changes, aiScoreIn, aiScoreOut, isProcessing } = useSelector(
    (s: RootState) => s.humanizer
  );

  if (isProcessing) {
    return (
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            <p className="text-sm text-ink-muted">Humanizing your text...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!outputText) {
    return (
      <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-ink-muted">Output will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-white rounded-xl border border-rule overflow-hidden">
      {/* Scores bar */}
      <div className="px-4 py-3 border-b border-rule flex items-center gap-6">
        <AiMeter score={aiScoreIn} label="Before" />
        <span className="text-ink-muted">→</span>
        <AiMeter score={aiScoreOut} label="After" />
      </div>

      {/* Rewritten text with diff highlights */}
      <div className="flex-1 p-4 overflow-auto">
        <div className="text-sm text-ink leading-relaxed whitespace-pre-wrap">
          {outputText}
        </div>

        {/* Changes list */}
        {changes.length > 0 && (
          <div className="mt-4 pt-4 border-t border-rule">
            <p className="text-xs font-semibold text-ink-soft mb-2">{changes.length} changes</p>
            <div className="space-y-2">
              {changes.slice(0, 10).map((c, i) => (
                <div key={i} className="text-xs">
                  <span className="line-through text-error/70">{c.original}</span>
                  <span className="mx-1 text-ink-muted">→</span>
                  <span className="text-success font-medium">{c.replacement}</span>
                </div>
              ))}
              {changes.length > 10 && (
                <p className="text-xs text-ink-muted">+{changes.length - 10} more changes</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t border-rule">
        <button
          onClick={() => navigator.clipboard.writeText(outputText)}
          className="text-xs text-primary font-medium hover:underline"
        >
          Copy to clipboard
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create InsightCards**

Write `margin-frontend/components/humanizer/InsightCards.tsx`:

```tsx
'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { clsx } from 'clsx';

export function InsightCards() {
  const { aiScoreIn, aiScoreOut, changes } = useSelector((s: RootState) => s.humanizer);

  const passedThreshold = aiScoreOut <= 30;
  const improvement = aiScoreIn - aiScoreOut;

  const cards = [
    {
      label: 'AI Score',
      value: `${aiScoreOut}%`,
      sub: aiScoreOut > 0 ? `was ${aiScoreIn}%` : '—',
      color: aiScoreOut <= 30 ? 'text-success' : aiScoreOut <= 60 ? 'text-warn' : 'text-error',
    },
    {
      label: 'Rewrites',
      value: `${changes.length}`,
      sub: 'phrases changed',
      color: 'text-primary',
    },
    {
      label: 'Improvement',
      value: improvement > 0 ? `−${improvement}%` : '—',
      sub: 'AI score drop',
      color: 'text-purple',
    },
    {
      label: 'Status',
      value: passedThreshold && aiScoreOut > 0 ? 'Pass' : aiScoreOut > 0 ? 'Needs work' : '—',
      sub: 'detection test',
      color: passedThreshold && aiScoreOut > 0 ? 'text-success' : 'text-warn',
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {cards.map((card) => (
        <div key={card.label} className="bg-white rounded-xl border border-rule p-4">
          <p className="text-xs text-ink-muted mb-1">{card.label}</p>
          <p className={clsx('text-2xl font-mono font-bold', card.color)}>{card.value}</p>
          <p className="text-xs text-ink-muted mt-0.5">{card.sub}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Create HumBoard (main container)**

Write `margin-frontend/components/humanizer/HumBoard.tsx`:

```tsx
'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { setProcessing, setResult, resetOutput } from '@/store/slices/humanizerSlice';
import { HumToolbar } from './HumToolbar';
import { InputPane } from './InputPane';
import { OutputPane } from './OutputPane';
import { InsightCards } from './InsightCards';
import { API_URL } from '@/lib/core/Constants';
import Cookie from '@/lib/core/fetch/Cookie';
import { toast } from 'react-toastify';
import { useBalance } from '@/hooks/credit';

export function HumBoard() {
  const dispatch = useDispatch();
  const { inputText, tone, strength, lengthMode, isProcessing, outputText } = useSelector(
    (s: RootState) => s.humanizer
  );
  const { mutate: refreshBalance } = useBalance();

  const handleHumanize = async () => {
    if (!inputText.trim()) {
      toast.error('Please enter some text first');
      return;
    }

    dispatch(setProcessing(true));
    dispatch(resetOutput());

    try {
      const response = await fetch(`${API_URL}/api/humanize/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: inputText,
          tone,
          strength,
          lengthMode,
          access_token: Cookie.fromDocument('access_token'),
        }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No stream reader');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));

            if (data.type === 'done') {
              dispatch(
                setResult({
                  outputText: data.rewrittenText,
                  changes: data.changes || [],
                  aiScoreIn: data.aiScoreIn,
                  aiScoreOut: data.aiScoreOut,
                  jobId: data.jobId,
                })
              );
              refreshBalance();
            } else if (data.type === 'error') {
              toast.error(data.message);
              dispatch(setProcessing(false));
            }
          } catch {
            // partial JSON, skip
          }
        }
      }
    } catch (err: any) {
      toast.error('Humanization failed');
      dispatch(setProcessing(false));
    }
  };

  return (
    <div className="space-y-4">
      <HumToolbar />

      <div className="flex gap-4" style={{ minHeight: 400 }}>
        <InputPane />
        <OutputPane />
      </div>

      {/* Action button */}
      <div className="flex justify-center">
        <button
          onClick={handleHumanize}
          disabled={isProcessing || !inputText.trim()}
          className="px-8 py-3 bg-primary text-white rounded-xl font-semibold text-sm hover:bg-primary-dark transition disabled:opacity-50 shadow-sm"
        >
          {isProcessing ? 'Humanizing...' : 'Humanize'}
        </button>
      </div>

      {/* Insight cards */}
      {outputText && <InsightCards />}
    </div>
  );
}
```

- [ ] **Step 5: Wire up humanizer page**

Update `margin-frontend/app/(workspace)/humanizer/page.tsx`:

```tsx
'use client';

import { HumBoard } from '@/components/humanizer/HumBoard';

export default function HumanizerPage() {
  return <HumBoard />;
}
```

- [ ] **Step 6: Commit**

```bash
git add margin-frontend/components/humanizer/ margin-frontend/components/ui/AiMeter.tsx margin-frontend/app/\(workspace\)/humanizer/page.tsx
git commit -m "feat(frontend): complete humanizer UI with SSE streaming, output pane, and insight cards"
```

---

## Phase 5: Auto-Cite Feature

### Task 18: Citation Models + Citation Search Service

**Files:**
- Create: `margin-backend/src/models/Citation.ts`
- Create: `margin-backend/src/models/CitationFolder.ts`
- Create: `margin-backend/src/models/AutoCiteJob.ts`
- Create: `margin-backend/src/services/citation.service.ts`

- [ ] **Step 1: Create Citation model**

Write `margin-backend/src/models/Citation.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'citations', timestamps: true } })
export class Citation {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public folderId?: string;

  @prop({ required: true })
  public style!: string;

  @prop({ required: true })
  public formattedText!: string;

  @prop({ required: true })
  public author!: string;

  @prop()
  public year?: number;

  @prop({ required: true })
  public title!: string;

  @prop()
  public journal?: string;

  @prop()
  public doi?: string;

  @prop()
  public url?: string;

  @prop()
  public sourceApi?: string;
}

export const CitationModel = getModelForClass(Citation);
```

- [ ] **Step 2: Create CitationFolder model**

Write `margin-backend/src/models/CitationFolder.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'citation_folders', timestamps: true } })
export class CitationFolder {
  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public name!: string;

  @prop({ default: '#0022FF' })
  public color!: string;
}

export const CitationFolderModel = getModelForClass(CitationFolder);
```

- [ ] **Step 3: Create AutoCiteJob model**

Write `margin-backend/src/models/AutoCiteJob.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

class ClaimCandidate {
  @prop()
  public sourceId!: string;

  @prop()
  public relevanceScore!: number;
}

class Claim {
  @prop()
  public text!: string;

  @prop()
  public sourceId?: string;

  @prop({ default: 'pending' })
  public status!: string;

  @prop({ type: () => [ClaimCandidate], default: [] })
  public candidates!: ClaimCandidate[];
}

class CiteSource {
  @prop()
  public id!: string;

  @prop()
  public cite!: string;

  @prop()
  public authorShort!: string;

  @prop()
  public year!: number;

  @prop()
  public title!: string;

  @prop()
  public snippet!: string;

  @prop()
  public conf!: number;

  @prop()
  public sourceApi!: string;
}

@modelOptions({ schemaOptions: { collection: 'autocite_jobs', timestamps: true } })
export class AutoCiteJob {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public documentId?: string;

  @prop({ default: 'apa' })
  public style!: string;

  @prop({ default: 'pending' })
  public status!: string;

  @prop({ type: () => [Claim], default: [] })
  public claims!: Claim[];

  @prop({ type: () => [CiteSource], default: [] })
  public sources!: CiteSource[];

  @prop({ default: 0 })
  public creditsUsed!: number;
}

export const AutoCiteJobModel = getModelForClass(AutoCiteJob);
```

- [ ] **Step 4: Create citation search service**

Write `margin-backend/src/services/citation.service.ts`:

```typescript
import axios from 'axios';
import { AIServiceManager } from '@/services/ai/ai.service.manager';
import { v4 as uuidv4 } from 'uuid';

interface RawCitationResult {
  id: string;
  title: string;
  authors: string;
  year: number;
  doi: string | null;
  url: string | null;
  journal: string | null;
  snippet: string;
  sourceApi: string;
}

export class CitationSearchService {
  static async searchCrossRef(query: string): Promise<RawCitationResult[]> {
    try {
      const { data } = await axios.get('https://api.crossref.org/works', {
        params: { query, rows: 5 },
        timeout: 10000,
      });

      return (data.message?.items || []).map((item: any) => ({
        id: uuidv4(),
        title: item.title?.[0] || 'Untitled',
        authors: (item.author || []).map((a: any) => `${a.given || ''} ${a.family || ''}`).join(', '),
        year: item.published?.['date-parts']?.[0]?.[0] || 0,
        doi: item.DOI || null,
        url: item.URL || null,
        journal: item['container-title']?.[0] || null,
        snippet: (item.abstract || '').replace(/<[^>]*>/g, '').slice(0, 200),
        sourceApi: 'crossref',
      }));
    } catch {
      return [];
    }
  }

  static async searchOpenAlex(query: string): Promise<RawCitationResult[]> {
    try {
      const { data } = await axios.get('https://api.openalex.org/works', {
        params: { search: query, per_page: 5 },
        timeout: 10000,
      });

      return (data.results || []).map((item: any) => ({
        id: uuidv4(),
        title: item.display_name || 'Untitled',
        authors: (item.authorships || [])
          .map((a: any) => a.author?.display_name || '')
          .filter(Boolean)
          .join(', '),
        year: item.publication_year || 0,
        doi: item.doi ? item.doi.replace('https://doi.org/', '') : null,
        url: item.doi || item.id || null,
        journal: item.primary_location?.source?.display_name || null,
        snippet: '',
        sourceApi: 'openalex',
      }));
    } catch {
      return [];
    }
  }

  static async searchSemanticScholar(query: string): Promise<RawCitationResult[]> {
    try {
      const headers: any = {};
      if (process.env.SEMANTIC_SCHOLAR_API_KEY) {
        headers['x-api-key'] = process.env.SEMANTIC_SCHOLAR_API_KEY;
      }

      const { data } = await axios.get(
        'https://api.semanticscholar.org/graph/v1/paper/search',
        {
          params: { query, limit: 5, fields: 'title,authors,year,externalIds,abstract,journal' },
          headers,
          timeout: 10000,
        }
      );

      return (data.data || []).map((item: any) => ({
        id: uuidv4(),
        title: item.title || 'Untitled',
        authors: (item.authors || []).map((a: any) => a.name || '').join(', '),
        year: item.year || 0,
        doi: item.externalIds?.DOI || null,
        url: item.externalIds?.DOI ? `https://doi.org/${item.externalIds.DOI}` : null,
        journal: item.journal?.name || null,
        snippet: (item.abstract || '').slice(0, 200),
        sourceApi: 'semanticscholar',
      }));
    } catch {
      return [];
    }
  }

  static async searchAll(query: string): Promise<RawCitationResult[]> {
    const [cr, oa, ss] = await Promise.all([
      this.searchCrossRef(query),
      this.searchOpenAlex(query),
      this.searchSemanticScholar(query),
    ]);

    // Merge and deduplicate by DOI
    const allResults = [...cr, ...oa, ...ss];
    const seen = new Set<string>();
    const deduped: RawCitationResult[] = [];

    for (const r of allResults) {
      const key = r.doi || `${r.title}-${r.year}`;
      if (!seen.has(key)) {
        seen.add(key);
        deduped.push(r);
      }
    }

    return deduped;
  }

  static async extractClaims(text: string): Promise<string[]> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = `You are an academic writing assistant. Extract all factual claims from the following essay that should be supported by academic citations.

Return valid JSON only:
{
  "claims": ["claim text 1", "claim text 2", ...]
}

Only include claims that make factual assertions. Skip opinions, transitions, and thesis statements that don't cite facts.`;

    const result = await ai.tryWithFallback('extract-claims', async (service) => {
      return service.chat(systemPrompt, text, { temperature: 0.3, jsonMode: true });
    });

    try {
      const parsed = JSON.parse(result);
      return parsed.claims || [];
    } catch {
      return [];
    }
  }

  static async rankCandidates(
    claim: string,
    candidates: RawCitationResult[]
  ): Promise<Array<{ id: string; relevanceScore: number }>> {
    if (candidates.length === 0) return [];

    const ai = AIServiceManager.getInstance();
    const systemPrompt = `You are a citation matcher. Given a claim and a list of academic papers, rank how relevant each paper is to supporting the claim.

Return valid JSON:
{
  "rankings": [{ "id": "paper_id", "score": 0.0-1.0 }]
}

Score 0.0 = completely irrelevant, 1.0 = perfect match. Return top 3 only.`;

    const userPrompt = `Claim: "${claim}"

Papers:
${candidates.map((c) => `- ID: ${c.id} | Title: "${c.title}" | Authors: ${c.authors} | Year: ${c.year} | Snippet: ${c.snippet}`).join('\n')}`;

    const result = await ai.tryWithFallback('rank-candidates', async (service) => {
      return service.chat(systemPrompt, userPrompt, { temperature: 0.3, jsonMode: true });
    });

    try {
      const parsed = JSON.parse(result);
      return (parsed.rankings || []).slice(0, 3);
    } catch {
      return candidates.slice(0, 3).map((c) => ({ id: c.id, relevanceScore: 0.5 }));
    }
  }

  static async formatCitation(
    paper: RawCitationResult,
    style: string
  ): Promise<string> {
    const ai = AIServiceManager.getInstance();
    const systemPrompt = `Format the following academic paper metadata into a proper ${style.toUpperCase()} citation. Return ONLY the formatted citation string, nothing else.`;

    const userPrompt = `Author(s): ${paper.authors}
Title: ${paper.title}
Year: ${paper.year}
Journal: ${paper.journal || 'N/A'}
DOI: ${paper.doi || 'N/A'}
URL: ${paper.url || 'N/A'}`;

    return ai.tryWithFallback('format-citation', async (service) => {
      return service.chat(systemPrompt, userPrompt, { temperature: 0.1 });
    });
  }
}
```

- [ ] **Step 5: Commit**

```bash
git add margin-backend/src/models/Citation.ts margin-backend/src/models/CitationFolder.ts margin-backend/src/models/AutoCiteJob.ts margin-backend/src/services/citation.service.ts
git commit -m "feat(backend): add citation models and search service (CrossRef, OpenAlex, Semantic Scholar)"
```

---

### Task 19: Auto-Cite Bull Queue + Socket.io Progress + Routes

**Files:**
- Create: `margin-backend/src/queues/autocite.queue.ts`
- Create: `margin-backend/src/api/routes/cite.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create auto-cite Bull queue**

```bash
mkdir -p margin-backend/src/queues
```

Write `margin-backend/src/queues/autocite.queue.ts`:

```typescript
import Bull from 'bull';
import { Server as SocketServer } from 'socket.io';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { CitationSearchService } from '@/services/citation.service';
import { CreditService } from '@/services/credit.service';
import { CreditCosts } from '@/Constants';

const autociteQueue = new Bull('autocite', process.env.REDIS_URL || 'redis://localhost:6379');

export function initAutoCiteQueue(io: SocketServer) {
  autociteQueue.process(async (job) => {
    const { jobId, userId, text, style } = job.data;
    const room = `autocite:${jobId}`;

    const emitProgress = (status: string, data: any = {}) => {
      io.to(room).emit('autocite:progress', { jobId, status, ...data });
    };

    try {
      // Step 1: Extract claims
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'extracting' });
      emitProgress('extracting');

      const claimTexts = await CitationSearchService.extractClaims(text);
      const claims = claimTexts.map((t) => ({
        text: t,
        sourceId: null,
        status: 'pending',
        candidates: [],
      }));

      await AutoCiteJobModel.findByIdAndUpdate(jobId, { claims });
      emitProgress('searching', { claimCount: claims.length });

      // Step 2: Search for sources for each claim
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'searching' });
      const allSources: any[] = [];

      for (let i = 0; i < claims.length; i++) {
        const results = await CitationSearchService.searchAll(claims[i].text);

        for (const r of results) {
          if (!allSources.find((s) => s.id === r.id)) {
            allSources.push({
              id: r.id,
              cite: '',
              authorShort: r.authors.split(',')[0]?.trim() || 'Unknown',
              year: r.year,
              title: r.title,
              snippet: r.snippet,
              conf: 0,
              sourceApi: r.sourceApi,
            });
          }
        }

        emitProgress('searching', { claimIndex: i + 1, claimCount: claims.length });
      }

      // Step 3: Rank candidates for each claim
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'matching' });
      emitProgress('matching');

      for (let i = 0; i < claims.length; i++) {
        const results = await CitationSearchService.searchAll(claims[i].text);
        const rankings = await CitationSearchService.rankCandidates(claims[i].text, results);
        claims[i].candidates = rankings.map((r) => ({
          sourceId: r.id,
          relevanceScore: r.score,
        }));

        // Update sources with ranking scores
        for (const ranking of rankings) {
          const src = allSources.find((s) => s.id === ranking.id);
          if (src) src.conf = Math.max(src.conf, ranking.score);
        }
      }

      // Step 4: Format citations
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'formatting' });
      emitProgress('formatting');

      // Get unique source results for formatting
      const searchResults = await CitationSearchService.searchAll(claimTexts[0] || text.slice(0, 200));
      for (const src of allSources) {
        const rawResult = searchResults.find((r) => r.id === src.id) || {
          authors: src.authorShort,
          title: src.title,
          year: src.year,
          journal: null,
          doi: null,
          url: null,
        };
        src.cite = await CitationSearchService.formatCitation(rawResult as any, style);
      }

      // Finalize
      await AutoCiteJobModel.findByIdAndUpdate(jobId, {
        status: 'done',
        claims,
        sources: allSources,
        creditsUsed: CreditCosts.AUTOCITE_PER_ANALYSIS,
      });

      await CreditService.deduct(
        userId,
        CreditCosts.AUTOCITE_PER_ANALYSIS,
        'autocite',
        jobId,
        'Auto-cite analysis'
      );

      emitProgress('done', { claims, sources: allSources });
    } catch (err: any) {
      await AutoCiteJobModel.findByIdAndUpdate(jobId, { status: 'failed' });
      emitProgress('failed', { error: err.message });
    }
  });

  return autociteQueue;
}

export default autociteQueue;
```

- [ ] **Step 2: Create cite routes**

Write `margin-backend/src/api/routes/cite.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { CreditService } from '@/services/credit.service';
import autociteQueue from '@/queues/autocite.queue';

export default (router: Router) => {
  // Submit essay for analysis
  router.post(
    '/cite/analyze',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text, style = 'apa' } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      if (!(await CreditService.hasEnough(user._id.toString(), CreditCosts.AUTOCITE_PER_ANALYSIS))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const job = await AutoCiteJobModel.create({
        owner: user._id.toString(),
        style,
        status: 'pending',
      });

      await autociteQueue.add({
        jobId: job._id.toString(),
        userId: user._id.toString(),
        text,
        style,
      });

      return res.json({ code: Code.Success, data: { jobId: job._id } });
    }
  );

  // Accept a source for a claim
  router.post(
    '/cite/accept',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, claimIndex, sourceId } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      if (claimIndex >= 0 && claimIndex < job.claims.length) {
        job.claims[claimIndex].sourceId = sourceId;
        job.claims[claimIndex].status = 'cited';
        await job.save();
      }

      return res.json({ code: Code.Success, data: job });
    }
  );

  // Remove citation from a claim
  router.post(
    '/cite/remove',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, claimIndex } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      if (claimIndex >= 0 && claimIndex < job.claims.length) {
        job.claims[claimIndex].sourceId = undefined;
        job.claims[claimIndex].status = 'pending';
        await job.save();
      }

      return res.json({ code: Code.Success, data: job });
    }
  );

  // Get job status
  router.post(
    '/cite/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await AutoCiteJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );

  // Export bibliography
  router.post(
    '/cite/export',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { jobId, format = 'txt' } = req.body;

      const job = await AutoCiteJobModel.findById(jobId);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });

      const citedSources = job.claims
        .filter((c) => c.sourceId && c.status === 'cited')
        .map((c) => job.sources.find((s) => s.id === c.sourceId))
        .filter(Boolean);

      const bibliography = citedSources.map((s: any) => s.cite).join('\n\n');

      if (format === 'txt') {
        res.setHeader('Content-Type', 'text/plain');
        res.setHeader('Content-Disposition', 'attachment; filename=bibliography.txt');
        return res.send(bibliography);
      }

      return res.json({ code: Code.Success, data: { bibliography } });
    }
  );
};
```

- [ ] **Step 3: Initialize queue in app.ts**

Update `margin-backend/src/app.ts` — add after `const io = ...`:

```typescript
import { initAutoCiteQueue } from '@/queues/autocite.queue';
```

After `await loaders({ app });` add:

```typescript
initAutoCiteQueue(io);
console.log('Auto-cite queue initialized');
```

- [ ] **Step 4: Register cite routes in API index**

Update `margin-backend/src/api/index.ts` — add import and registration:

```typescript
import cite from './routes/cite';
```

In the function body:
```typescript
cite(router);
```

- [ ] **Step 5: Commit**

```bash
git add margin-backend/src/queues/autocite.queue.ts margin-backend/src/api/routes/cite.ts margin-backend/src/app.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add auto-cite Bull queue with Socket.io progress and cite endpoints"
```

---

### Task 20: Frontend Auto-Cite UI (CiteBoard + ClaimPopover + SourceList)

**Files:**
- Create: `margin-frontend/store/slices/autoCiteSlice.ts`
- Modify: `margin-frontend/store/rootReducer.ts`
- Create: `margin-frontend/hooks/cite.ts`
- Create: `margin-frontend/components/cite/CiteBoard.tsx`
- Create: `margin-frontend/components/cite/ClaimPopover.tsx`
- Create: `margin-frontend/components/cite/SourceList.tsx`
- Modify: `margin-frontend/app/(workspace)/auto-cite/page.tsx`

- [ ] **Step 1: Create auto-cite slice**

Write `margin-frontend/store/slices/autoCiteSlice.ts`:

```typescript
import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Claim, CiteSource } from '@/store/types';

interface AutoCiteState {
  jobId: string | null;
  status: string;
  style: string;
  claims: Claim[];
  sources: CiteSource[];
  inputText: string;
}

const initialState: AutoCiteState = {
  jobId: null,
  status: 'idle',
  style: 'apa',
  claims: [],
  sources: [],
  inputText: '',
};

const autoCiteSlice = createSlice({
  name: 'autoCite',
  initialState,
  reducers: {
    setStyle(state, action: PayloadAction<string>) {
      state.style = action.payload;
    },
    setCiteInput(state, action: PayloadAction<string>) {
      state.inputText = action.payload;
    },
    startJob(state, action: PayloadAction<string>) {
      state.jobId = action.payload;
      state.status = 'pending';
      state.claims = [];
      state.sources = [];
    },
    updateStatus(state, action: PayloadAction<string>) {
      state.status = action.payload;
    },
    setResults(state, action: PayloadAction<{ claims: Claim[]; sources: CiteSource[] }>) {
      state.claims = action.payload.claims;
      state.sources = action.payload.sources;
      state.status = 'done';
    },
    acceptClaim(state, action: PayloadAction<{ claimIndex: number; sourceId: string }>) {
      const claim = state.claims[action.payload.claimIndex];
      if (claim) {
        claim.sourceId = action.payload.sourceId;
        claim.status = 'cited';
      }
    },
    removeClaim(state, action: PayloadAction<number>) {
      const claim = state.claims[action.payload];
      if (claim) {
        claim.sourceId = null;
        claim.status = 'pending';
      }
    },
    resetCite(state) {
      Object.assign(state, initialState);
    },
  },
});

export const {
  setStyle,
  setCiteInput,
  startJob,
  updateStatus,
  setResults,
  acceptClaim,
  removeClaim,
  resetCite,
} = autoCiteSlice.actions;
export default autoCiteSlice.reducer;
```

- [ ] **Step 2: Add autoCite slice to rootReducer**

Update `margin-frontend/store/rootReducer.ts`:

```typescript
import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';
import autoCiteReducer from './slices/autoCiteSlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
  autoCite: autoCiteReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
```

- [ ] **Step 3: Create cite hook**

Write `margin-frontend/hooks/cite.ts`:

```typescript
import useSWR from 'swr';

export function useCiteJob(jobId: string | null) {
  const { data, mutate } = useSWR(
    jobId ? ['/api/cite/get', { id: jobId }] : null,
    { refreshInterval: 0 }
  );

  return {
    job: data?.code === 1 ? data.data : null,
    mutate,
  };
}
```

- [ ] **Step 4: Create ClaimPopover**

```bash
mkdir -p margin-frontend/components/cite
```

Write `margin-frontend/components/cite/ClaimPopover.tsx`:

```tsx
'use client';

import { Claim, CiteSource } from '@/store/types';
import { clsx } from 'clsx';

interface ClaimPopoverProps {
  claim: Claim;
  claimIndex: number;
  sources: CiteSource[];
  onAccept: (claimIndex: number, sourceId: string) => void;
  onRemove: (claimIndex: number) => void;
}

export function ClaimPopover({ claim, claimIndex, sources, onAccept, onRemove }: ClaimPopoverProps) {
  const citedSource = claim.sourceId ? sources.find((s) => s.id === claim.sourceId) : null;
  const candidates = claim.candidates
    .map((c) => ({ ...c, source: sources.find((s) => s.id === c.sourceId) }))
    .filter((c) => c.source);

  if (citedSource) {
    return (
      <div className="p-3 bg-bg-blue rounded-lg border border-primary/20">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-primary">{citedSource.authorShort} ({citedSource.year})</p>
            <p className="text-xs text-ink-soft mt-0.5 truncate">{citedSource.title}</p>
          </div>
          <button
            onClick={() => onRemove(claimIndex)}
            className="text-xs text-error hover:underline shrink-0"
          >
            Remove
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="p-3 bg-white rounded-lg border border-rule">
      <p className="text-xs text-ink-muted mb-2">Suggested sources:</p>
      <div className="space-y-2">
        {candidates.length === 0 && (
          <p className="text-xs text-ink-muted italic">No candidates found</p>
        )}
        {candidates.map((c) => (
          <button
            key={c.sourceId}
            onClick={() => onAccept(claimIndex, c.sourceId)}
            className="w-full text-left p-2 rounded-md hover:bg-bg-soft transition border border-rule"
          >
            <p className="text-xs font-medium text-ink">{c.source!.authorShort} ({c.source!.year})</p>
            <p className="text-xs text-ink-muted truncate">{c.source!.title}</p>
            <div className="flex items-center gap-1 mt-1">
              <div className="w-12 h-1 bg-rule rounded-full overflow-hidden">
                <div
                  className="h-full bg-success rounded-full"
                  style={{ width: `${(c.relevanceScore || 0) * 100}%` }}
                />
              </div>
              <span className="text-[10px] text-ink-muted">
                {Math.round((c.relevanceScore || 0) * 100)}%
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create SourceList**

Write `margin-frontend/components/cite/SourceList.tsx`:

```tsx
'use client';

import { CiteSource, Claim } from '@/store/types';

interface SourceListProps {
  sources: CiteSource[];
  claims: Claim[];
}

export function SourceList({ sources, claims }: SourceListProps) {
  const citedSourceIds = claims.filter((c) => c.status === 'cited').map((c) => c.sourceId);
  const citedSources = sources.filter((s) => citedSourceIds.includes(s.id));

  if (citedSources.length === 0) {
    return (
      <div className="p-6 text-center text-sm text-ink-muted">
        Accept sources from claims to build your bibliography
      </div>
    );
  }

  return (
    <div className="divide-y divide-rule">
      <div className="px-4 py-3 bg-bg-soft">
        <h3 className="text-xs font-semibold text-ink-soft">
          Bibliography ({citedSources.length} source{citedSources.length !== 1 ? 's' : ''})
        </h3>
      </div>
      {citedSources.map((source, i) => (
        <div key={source.id} className="px-4 py-3 hover:bg-bg-soft transition">
          <p className="text-xs text-ink-muted mb-0.5">[{i + 1}]</p>
          <p className="text-sm text-ink leading-relaxed">{source.cite || `${source.authorShort} (${source.year}). ${source.title}`}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Create CiteBoard**

Write `margin-frontend/components/cite/CiteBoard.tsx`:

```tsx
'use client';

import { useSelector, useDispatch } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import {
  setStyle,
  setCiteInput,
  startJob,
  updateStatus,
  setResults,
  acceptClaim,
  removeClaim,
} from '@/store/slices/autoCiteSlice';
import { ClaimPopover } from './ClaimPopover';
import { SourceList } from './SourceList';
import { clsx } from 'clsx';
import { toast } from 'react-toastify';
import { useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code, SOCKET_URL } from '@/lib/core/Constants';
import { useBalance } from '@/hooks/credit';

const STYLES = ['apa', 'mla', 'chicago', 'harvard', 'ieee'];

const STATUS_LABELS: Record<string, string> = {
  pending: 'Starting...',
  extracting: 'Extracting claims...',
  searching: 'Searching databases...',
  matching: 'Matching sources...',
  formatting: 'Formatting citations...',
  done: 'Complete',
  failed: 'Failed',
};

export function CiteBoard() {
  const dispatch = useDispatch();
  const { jobId, status, style, claims, sources, inputText } = useSelector(
    (s: RootState) => s.autoCite
  );
  const { mutate: refreshBalance } = useBalance();
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;

    socket.on('autocite:progress', (data: any) => {
      if (data.status === 'done') {
        dispatch(setResults({ claims: data.claims, sources: data.sources }));
        refreshBalance();
      } else if (data.status === 'failed') {
        dispatch(updateStatus('failed'));
        toast.error(data.error || 'Analysis failed');
      } else {
        dispatch(updateStatus(data.status));
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [dispatch, refreshBalance]);

  useEffect(() => {
    if (jobId && socketRef.current) {
      socketRef.current.emit('join', `autocite:${jobId}`);
    }
  }, [jobId]);

  const handleAnalyze = async () => {
    if (!inputText.trim()) {
      toast.error('Please enter your essay text');
      return;
    }

    try {
      const res = await Fetch.postWithAccessToken<any>('/api/cite/analyze', {
        text: inputText,
        style,
      });

      if (res.data.code === Code.Success) {
        dispatch(startJob(res.data.data.jobId));
      } else {
        toast.error(res.data.message);
      }
    } catch {
      toast.error('Failed to start analysis');
    }
  };

  const handleAccept = async (claimIndex: number, sourceId: string) => {
    dispatch(acceptClaim({ claimIndex, sourceId }));
    await Fetch.postWithAccessToken('/api/cite/accept', { jobId, claimIndex, sourceId });
  };

  const handleRemove = async (claimIndex: number) => {
    dispatch(removeClaim(claimIndex));
    await Fetch.postWithAccessToken('/api/cite/remove', { jobId, claimIndex });
  };

  const isProcessing = ['pending', 'extracting', 'searching', 'matching', 'formatting'].includes(status);

  return (
    <div className="space-y-4">
      {/* Style selector + analyze button */}
      <div className="flex items-center gap-4 bg-white rounded-xl border border-rule px-5 py-3">
        <span className="text-xs font-medium text-ink-muted">Citation style</span>
        <div className="flex gap-1">
          {STYLES.map((s) => (
            <button
              key={s}
              onClick={() => dispatch(setStyle(s))}
              className={clsx(
                'px-3 py-1 rounded-full text-xs font-medium uppercase transition',
                style === s ? 'bg-primary text-white' : 'bg-bg-soft text-ink-soft hover:bg-rule'
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {/* Input + results layout */}
      <div className="grid grid-cols-2 gap-4" style={{ minHeight: 400 }}>
        {/* Left: Input / Claims */}
        <div className="bg-white rounded-xl border border-rule overflow-hidden flex flex-col">
          {status === 'idle' ? (
            <>
              <div className="p-4 flex-1">
                <textarea
                  value={inputText}
                  onChange={(e) => dispatch(setCiteInput(e.target.value))}
                  placeholder="Paste your essay here to find citations..."
                  className="w-full h-full min-h-[300px] resize-none outline-none text-sm text-ink leading-relaxed"
                />
              </div>
              <div className="px-4 py-3 border-t border-rule">
                <button
                  onClick={handleAnalyze}
                  disabled={!inputText.trim()}
                  className="px-6 py-2 bg-primary text-white rounded-lg text-sm font-medium hover:bg-primary-dark transition disabled:opacity-50"
                >
                  Analyze & Find Citations
                </button>
              </div>
            </>
          ) : isProcessing ? (
            <div className="flex-1 flex items-center justify-center">
              <div className="text-center">
                <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <p className="text-sm text-ink-soft font-medium">{STATUS_LABELS[status] || status}</p>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-auto p-4 space-y-3">
              <p className="text-xs font-semibold text-ink-soft mb-2">
                {claims.length} claims found
              </p>
              {claims.map((claim, i) => (
                <div key={i} className="space-y-2">
                  <p className={clsx(
                    'text-sm leading-relaxed px-2 py-1 rounded',
                    claim.status === 'cited' ? 'bg-bg-blue' : 'bg-bg-soft'
                  )}>
                    {claim.text}
                  </p>
                  <ClaimPopover
                    claim={claim}
                    claimIndex={i}
                    sources={sources}
                    onAccept={handleAccept}
                    onRemove={handleRemove}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Bibliography */}
        <div className="bg-white rounded-xl border border-rule overflow-hidden">
          <SourceList sources={sources} claims={claims} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Wire up auto-cite page**

Update `margin-frontend/app/(workspace)/auto-cite/page.tsx`:

```tsx
'use client';

import { CiteBoard } from '@/components/cite/CiteBoard';

export default function AutoCitePage() {
  return <CiteBoard />;
}
```

- [ ] **Step 8: Commit**

```bash
git add margin-frontend/store/slices/autoCiteSlice.ts margin-frontend/store/rootReducer.ts margin-frontend/hooks/cite.ts margin-frontend/components/cite/ margin-frontend/app/\(workspace\)/auto-cite/page.tsx
git commit -m "feat(frontend): add auto-cite UI with Socket.io progress, claim popovers, and bibliography"
```

---

## Phase 6: Library & History

### Task 21: Library CRUD Endpoints

**Files:**
- Create: `margin-backend/src/api/routes/library.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create library routes**

Write `margin-backend/src/api/routes/library.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { CitationModel } from '@/models/Citation';
import { CitationFolderModel } from '@/models/CitationFolder';

export default (router: Router) => {
  // ---- FOLDERS ----

  router.post(
    '/library/folders/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const folders = await CitationFolderModel.find({ owner: user._id.toString() }).sort({ createdAt: -1 });

      // Add citation counts
      const foldersWithCounts = await Promise.all(
        folders.map(async (f: any) => {
          const count = await CitationModel.countDocuments({ folderId: f._id.toString() });
          return { ...f.toObject(), id: f._id, citationCount: count };
        })
      );

      return res.json({ code: Code.Success, data: foldersWithCounts });
    }
  );

  router.post(
    '/library/folders/create',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { name, color = '#0022FF' } = req.body;
      if (!name) return res.json({ code: Code.InvalidInput, message: 'Name required' });

      const folder = await CitationFolderModel.create({
        owner: user._id.toString(),
        name,
        color,
      });

      return res.json({ code: Code.Success, data: folder });
    }
  );

  router.post(
    '/library/folders/update',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id, name, color } = req.body;
      const update: any = {};
      if (name) update.name = name;
      if (color) update.color = color;

      const folder = await CitationFolderModel.findByIdAndUpdate(id, update, { new: true });
      return res.json({ code: Code.Success, data: folder });
    }
  );

  router.post(
    '/library/folders/delete',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      await CitationFolderModel.findByIdAndDelete(id);
      // Move citations to unfiled
      await CitationModel.updateMany({ folderId: id }, { folderId: null });
      return res.json({ code: Code.Success });
    }
  );

  // ---- CITATIONS ----

  router.post(
    '/library/citations/list',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId } = req.body;
      const filter: any = { owner: user._id.toString() };
      if (folderId) filter.folderId = folderId;

      const citations = await CitationModel.find(filter).sort({ createdAt: -1 });
      return res.json({ code: Code.Success, data: citations });
    }
  );

  router.post(
    '/library/citations/save',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId, style, formattedText, author, year, title, journal, doi, url, sourceApi } =
        req.body;

      const citation = await CitationModel.create({
        owner: user._id.toString(),
        folderId: folderId || null,
        style,
        formattedText,
        author,
        year,
        title,
        journal,
        doi,
        url,
        sourceApi,
      });

      return res.json({ code: Code.Success, data: citation });
    }
  );

  router.post(
    '/library/citations/update',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id, ...updates } = req.body;
      const citation = await CitationModel.findByIdAndUpdate(id, updates, { new: true });
      return res.json({ code: Code.Success, data: citation });
    }
  );

  router.post(
    '/library/citations/delete',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      await CitationModel.findByIdAndDelete(id);
      return res.json({ code: Code.Success });
    }
  );

  // Export folder bibliography
  router.post(
    '/library/export',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { folderId } = req.body;
      const filter: any = { owner: user._id.toString() };
      if (folderId) filter.folderId = folderId;

      const citations = await CitationModel.find(filter).sort({ author: 1 });
      const text = citations.map((c: any) => c.formattedText).join('\n\n');

      res.setHeader('Content-Type', 'text/plain');
      res.setHeader('Content-Disposition', 'attachment; filename=bibliography.txt');
      return res.send(text);
    }
  );
};
```

- [ ] **Step 2: Register library routes**

Update `margin-backend/src/api/index.ts` — add import and registration:

```typescript
import library from './routes/library';
```

In the function body:
```typescript
library(router);
```

- [ ] **Step 3: Commit**

```bash
git add margin-backend/src/api/routes/library.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add library CRUD endpoints for folders and citations"
```

---

### Task 22: Frontend Library Page

**Files:**
- Create: `margin-frontend/store/slices/librarySlice.ts`
- Modify: `margin-frontend/store/rootReducer.ts`
- Create: `margin-frontend/hooks/library.ts`
- Create: `margin-frontend/components/library/FolderSidebar.tsx`
- Create: `margin-frontend/components/library/CitationRow.tsx`
- Modify: `margin-frontend/app/(workspace)/library/page.tsx`

- [ ] **Step 1: Create library slice**

Write `margin-frontend/store/slices/librarySlice.ts`:

```typescript
import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface LibraryState {
  selectedFolderId: string | null;
}

const initialState: LibraryState = {
  selectedFolderId: null,
};

const librarySlice = createSlice({
  name: 'library',
  initialState,
  reducers: {
    selectFolder(state, action: PayloadAction<string | null>) {
      state.selectedFolderId = action.payload;
    },
  },
});

export const { selectFolder } = librarySlice.actions;
export default librarySlice.reducer;
```

- [ ] **Step 2: Add library slice to rootReducer**

Update `margin-frontend/store/rootReducer.ts`:

```typescript
import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';
import autoCiteReducer from './slices/autoCiteSlice';
import libraryReducer from './slices/librarySlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
  autoCite: autoCiteReducer,
  library: libraryReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
```

- [ ] **Step 3: Create library hooks**

Write `margin-frontend/hooks/library.ts`:

```typescript
import useSWR from 'swr';

export function useFolders() {
  const { data, mutate } = useSWR(['/api/library/folders/list', {}]);
  return {
    folders: data?.code === 1 ? data.data : [],
    mutate,
  };
}

export function useCitations(folderId: string | null) {
  const params: any = {};
  if (folderId) params.folderId = folderId;

  const { data, mutate } = useSWR(['/api/library/citations/list', params]);
  return {
    citations: data?.code === 1 ? data.data : [],
    mutate,
  };
}
```

- [ ] **Step 4: Create FolderSidebar**

Write `margin-frontend/components/library/FolderSidebar.tsx`:

```tsx
'use client';

import { useDispatch, useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { selectFolder } from '@/store/slices/librarySlice';
import { useFolders } from '@/hooks/library';
import { clsx } from 'clsx';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

export function FolderSidebar() {
  const dispatch = useDispatch();
  const { selectedFolderId } = useSelector((s: RootState) => s.library);
  const { folders, mutate } = useFolders();
  const [newFolderName, setNewFolderName] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!newFolderName.trim()) return;
    setCreating(true);
    const res = await Fetch.postWithAccessToken<any>('/api/library/folders/create', {
      name: newFolderName,
    });
    if (res.data.code === Code.Success) {
      mutate();
      setNewFolderName('');
    } else {
      toast.error(res.data.message);
    }
    setCreating(false);
  };

  return (
    <div className="w-56 border-r border-rule bg-white flex flex-col">
      <div className="p-3 border-b border-rule">
        <h3 className="text-xs font-semibold text-ink-soft">Folders</h3>
      </div>

      <div className="flex-1 overflow-auto p-2 space-y-0.5">
        <button
          onClick={() => dispatch(selectFolder(null))}
          className={clsx(
            'w-full text-left px-3 py-2 rounded-lg text-sm transition',
            selectedFolderId === null ? 'bg-bg-blue text-primary font-medium' : 'text-ink-soft hover:bg-bg-soft'
          )}
        >
          All citations
        </button>

        {folders.map((folder: any) => (
          <button
            key={folder._id}
            onClick={() => dispatch(selectFolder(folder._id))}
            className={clsx(
              'w-full text-left px-3 py-2 rounded-lg text-sm transition flex items-center gap-2',
              selectedFolderId === folder._id
                ? 'bg-bg-blue text-primary font-medium'
                : 'text-ink-soft hover:bg-bg-soft'
            )}
          >
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: folder.color }} />
            <span className="truncate flex-1">{folder.name}</span>
            <span className="text-xs text-ink-muted">{folder.citationCount || 0}</span>
          </button>
        ))}
      </div>

      <div className="p-3 border-t border-rule">
        <div className="flex gap-1">
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            placeholder="New folder..."
            className="flex-1 px-2 py-1.5 rounded border border-rule text-xs outline-none focus:border-primary"
          />
          <button
            onClick={handleCreate}
            disabled={creating || !newFolderName.trim()}
            className="px-2 py-1.5 bg-primary text-white rounded text-xs disabled:opacity-50"
          >
            +
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create CitationRow**

Write `margin-frontend/components/library/CitationRow.tsx`:

```tsx
'use client';

import { RawCitation } from '@/store/types';
import Fetch from '@/lib/core/fetch/Fetch';
import { toast } from 'react-toastify';

interface CitationRowProps {
  citation: RawCitation;
  onDeleted: () => void;
}

export function CitationRow({ citation, onDeleted }: CitationRowProps) {
  const handleDelete = async () => {
    await Fetch.postWithAccessToken('/api/library/citations/delete', { id: citation._id });
    onDeleted();
    toast.success('Citation deleted');
  };

  const handleCopy = () => {
    navigator.clipboard.writeText(citation.formattedText);
    toast.success('Copied to clipboard');
  };

  return (
    <div className="px-4 py-3 hover:bg-bg-soft transition group">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-ink leading-relaxed">{citation.formattedText}</p>
          <div className="flex items-center gap-3 mt-1.5">
            <span className="text-[10px] text-ink-muted uppercase font-medium">{citation.style}</span>
            {citation.doi && (
              <span className="text-[10px] text-ink-muted">DOI: {citation.doi}</span>
            )}
          </div>
        </div>
        <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition">
          <button onClick={handleCopy} className="text-xs text-primary hover:underline">
            Copy
          </button>
          <button onClick={handleDelete} className="text-xs text-error hover:underline">
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Wire up library page**

Update `margin-frontend/app/(workspace)/library/page.tsx`:

```tsx
'use client';

import { useSelector } from 'react-redux';
import { RootState } from '@/store/rootReducer';
import { FolderSidebar } from '@/components/library/FolderSidebar';
import { CitationRow } from '@/components/library/CitationRow';
import { useCitations } from '@/hooks/library';

export default function LibraryPage() {
  const { selectedFolderId } = useSelector((s: RootState) => s.library);
  const { citations, mutate } = useCitations(selectedFolderId);

  return (
    <div className="flex bg-white rounded-xl border border-rule overflow-hidden" style={{ minHeight: 500 }}>
      <FolderSidebar />
      <div className="flex-1">
        <div className="px-4 py-3 border-b border-rule">
          <h2 className="text-sm font-semibold text-ink">
            {citations.length} citation{citations.length !== 1 ? 's' : ''}
          </h2>
        </div>
        <div className="divide-y divide-rule">
          {citations.length === 0 && (
            <div className="p-8 text-center text-sm text-ink-muted">
              No citations yet. Use Auto-Cite to find sources.
            </div>
          )}
          {citations.map((c: any) => (
            <CitationRow key={c._id} citation={c} onDeleted={mutate} />
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
git add margin-frontend/store/slices/librarySlice.ts margin-frontend/store/rootReducer.ts margin-frontend/hooks/library.ts margin-frontend/components/library/ margin-frontend/app/\(workspace\)/library/page.tsx
git commit -m "feat(frontend): add library page with folder sidebar and citation management"
```

---

### Task 23: Frontend History Page

**Files:**
- Create: `margin-frontend/hooks/humanizer.ts`
- Modify: `margin-frontend/app/(workspace)/history/page.tsx`

- [ ] **Step 1: Create humanizer hooks**

Write `margin-frontend/hooks/humanizer.ts`:

```typescript
import useSWR from 'swr';

export function useHumanizerHistory() {
  const { data, mutate } = useSWR(['/api/humanize/history', {}]);
  return {
    jobs: data?.code === 1 ? data.data : [],
    mutate,
  };
}

export function useHumanizerJob(id: string | null) {
  const { data } = useSWR(id ? ['/api/humanize/get', { id }] : null);
  return {
    job: data?.code === 1 ? data.data : null,
  };
}
```

- [ ] **Step 2: Implement history page**

Update `margin-frontend/app/(workspace)/history/page.tsx`:

```tsx
'use client';

import { useHumanizerHistory, useHumanizerJob } from '@/hooks/humanizer';
import { AiMeter } from '@/components/ui/AiMeter';
import { useState } from 'react';
import { clsx } from 'clsx';

export default function HistoryPage() {
  const { jobs } = useHumanizerHistory();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { job: selectedJob } = useHumanizerJob(selectedId);

  return (
    <div className="flex gap-4" style={{ minHeight: 500 }}>
      {/* Job list */}
      <div className="w-80 bg-white rounded-xl border border-rule overflow-hidden">
        <div className="px-4 py-3 border-b border-rule">
          <h2 className="text-sm font-semibold text-ink">History</h2>
        </div>
        <div className="divide-y divide-rule overflow-auto" style={{ maxHeight: 'calc(100vh - 200px)' }}>
          {jobs.length === 0 && (
            <div className="p-6 text-center text-sm text-ink-muted">No humanize runs yet</div>
          )}
          {jobs.map((job: any) => (
            <button
              key={job._id}
              onClick={() => setSelectedId(job._id)}
              className={clsx(
                'w-full text-left px-4 py-3 hover:bg-bg-soft transition',
                selectedId === job._id && 'bg-bg-blue'
              )}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-ink capitalize">{job.tone}</span>
                <span className={clsx(
                  'text-xs px-1.5 py-0.5 rounded',
                  job.status === 'completed' ? 'bg-success/10 text-success' : 'bg-error/10 text-error'
                )}>
                  {job.status}
                </span>
              </div>
              <div className="flex items-center gap-3 mt-1">
                <span className="text-[10px] text-ink-muted">
                  Score: {job.aiScoreIn}% → {job.aiScoreOut}%
                </span>
                <span className="text-[10px] text-ink-muted">
                  {new Date(job.createdAt).toLocaleDateString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Detail panel */}
      <div className="flex-1 bg-white rounded-xl border border-rule overflow-hidden">
        {!selectedJob ? (
          <div className="h-full flex items-center justify-center text-sm text-ink-muted">
            Select a run to view details
          </div>
        ) : (
          <div className="p-6 space-y-4">
            <div className="flex items-center gap-6">
              <AiMeter score={selectedJob.aiScoreIn} label="Before" />
              <span className="text-ink-muted">→</span>
              <AiMeter score={selectedJob.aiScoreOut} label="After" />
              <span className="text-xs text-ink-muted ml-auto">
                {selectedJob.changesCount} changes | {selectedJob.creditsUsed} credits
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <h3 className="text-xs font-semibold text-ink-soft mb-2">Original</h3>
                <div className="p-3 bg-bg-soft rounded-lg text-sm text-ink leading-relaxed max-h-96 overflow-auto">
                  {selectedJob.inputText}
                </div>
              </div>
              <div>
                <h3 className="text-xs font-semibold text-ink-soft mb-2">Humanized</h3>
                <div className="p-3 bg-bg-blue rounded-lg text-sm text-ink leading-relaxed max-h-96 overflow-auto">
                  {selectedJob.outputText}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add margin-frontend/hooks/humanizer.ts margin-frontend/app/\(workspace\)/history/page.tsx
git commit -m "feat(frontend): add history page with job list and detail panel"
```

---

## Phase 7: Plagiarism

### Task 24: PlagiarismJob Model + Copyscape Service

**Files:**
- Create: `margin-backend/src/models/PlagiarismJob.ts`
- Create: `margin-backend/src/services/plagiarism.service.ts`

- [ ] **Step 1: Create PlagiarismJob model**

Write `margin-backend/src/models/PlagiarismJob.ts`:

```typescript
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

class PlagiarismMatch {
  @prop()
  public sourceTitle!: string;

  @prop()
  public sourceUrl!: string;

  @prop()
  public similarity!: number;

  @prop()
  public matchedText!: string;

  @prop()
  public severity!: string;
}

@modelOptions({ schemaOptions: { collection: 'plagiarism_jobs', timestamps: true } })
export class PlagiarismJob {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public documentId?: string;

  @prop({ default: 0 })
  public overallScore!: number;

  @prop({ default: 'pending' })
  public status!: string;

  @prop({ type: () => [PlagiarismMatch], default: [] })
  public matches!: PlagiarismMatch[];

  @prop({ default: 0 })
  public creditsUsed!: number;
}

export const PlagiarismJobModel = getModelForClass(PlagiarismJob);
```

- [ ] **Step 2: Create plagiarism service**

Write `margin-backend/src/services/plagiarism.service.ts`:

```typescript
import axios from 'axios';

interface CopyscapeMatch {
  sourceTitle: string;
  sourceUrl: string;
  similarity: number;
  matchedText: string;
  severity: string;
}

export class PlagiarismService {
  static async checkWithCopyscape(text: string): Promise<{
    overallScore: number;
    matches: CopyscapeMatch[];
  }> {
    const username = process.env.COPYSCAPE_USERNAME;
    const apiKey = process.env.COPYSCAPE_API_KEY;

    if (!username || !apiKey) {
      throw new Error('Copyscape API not configured');
    }

    const { data } = await axios.post(
      'https://www.copyscape.com/api/',
      null,
      {
        params: {
          u: username,
          o: apiKey,
          t: text,
          f: 'json',
          c: 5, // max results
        },
        timeout: 30000,
      }
    );

    if (data.error) {
      throw new Error(data.error);
    }

    const results = data.result || [];
    const matches: CopyscapeMatch[] = results.map((r: any) => {
      const similarity = parseFloat(r.percentmatched) || 0;
      return {
        sourceTitle: r.title || 'Unknown source',
        sourceUrl: r.url || '',
        similarity,
        matchedText: r.textmatched || '',
        severity: similarity >= 80 ? 'high' : similarity >= 40 ? 'medium' : 'low',
      };
    });

    // Overall score = highest individual match percentage
    const overallScore = matches.length > 0
      ? Math.round(Math.max(...matches.map((m) => m.similarity)))
      : 0;

    return { overallScore, matches };
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add margin-backend/src/models/PlagiarismJob.ts margin-backend/src/services/plagiarism.service.ts
git commit -m "feat(backend): add PlagiarismJob model and Copyscape service"
```

---

### Task 25: Plagiarism Bull Queue + Routes

**Files:**
- Create: `margin-backend/src/queues/plagiarism.queue.ts`
- Create: `margin-backend/src/api/routes/plagiarism.ts`
- Modify: `margin-backend/src/app.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Create plagiarism Bull queue**

Write `margin-backend/src/queues/plagiarism.queue.ts`:

```typescript
import Bull from 'bull';
import { Server as SocketServer } from 'socket.io';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { PlagiarismService } from '@/services/plagiarism.service';
import { CreditService } from '@/services/credit.service';
import { CreditCosts } from '@/Constants';

const plagiarismQueue = new Bull('plagiarism', process.env.REDIS_URL || 'redis://localhost:6379');

export function initPlagiarismQueue(io: SocketServer) {
  plagiarismQueue.process(async (job) => {
    const { jobId, userId, text } = job.data;
    const room = `plagiarism:${jobId}`;

    const emitProgress = (status: string, data: any = {}) => {
      io.to(room).emit('plagiarism:progress', { jobId, status, ...data });
    };

    try {
      await PlagiarismJobModel.findByIdAndUpdate(jobId, { status: 'processing' });
      emitProgress('processing');

      const result = await PlagiarismService.checkWithCopyscape(text);

      await PlagiarismJobModel.findByIdAndUpdate(jobId, {
        status: 'done',
        overallScore: result.overallScore,
        matches: result.matches,
        creditsUsed: CreditCosts.PLAGIARISM_PER_CHECK,
      });

      await CreditService.deduct(
        userId,
        CreditCosts.PLAGIARISM_PER_CHECK,
        'plagiarism',
        jobId,
        'Plagiarism check'
      );

      emitProgress('done', { overallScore: result.overallScore, matches: result.matches });
    } catch (err: any) {
      await PlagiarismJobModel.findByIdAndUpdate(jobId, { status: 'failed' });
      emitProgress('failed', { error: err.message });
    }
  });

  return plagiarismQueue;
}

export default plagiarismQueue;
```

- [ ] **Step 2: Create plagiarism routes**

Write `margin-backend/src/api/routes/plagiarism.ts`:

```typescript
import { Router } from 'express';
import passport from 'passport';
import { Code, CreditCosts } from '@/Constants';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { CreditService } from '@/services/credit.service';
import plagiarismQueue from '@/queues/plagiarism.queue';

export default (router: Router) => {
  router.post(
    '/plagiarism/check',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { text } = req.body;

      if (!text || text.trim().length === 0) {
        return res.json({ code: Code.InvalidInput, message: 'Text is required' });
      }

      if (!(await CreditService.hasEnough(user._id.toString(), CreditCosts.PLAGIARISM_PER_CHECK))) {
        return res.json({ code: Code.InsufficientCredits, message: 'Insufficient credits' });
      }

      const job = await PlagiarismJobModel.create({
        owner: user._id.toString(),
        status: 'pending',
      });

      await plagiarismQueue.add({
        jobId: job._id.toString(),
        userId: user._id.toString(),
        text,
      });

      return res.json({ code: Code.Success, data: { jobId: job._id } });
    }
  );

  router.post(
    '/plagiarism/get',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const { id } = req.body;
      const job = await PlagiarismJobModel.findById(id);
      if (!job) return res.json({ code: Code.NotFound, message: 'Job not found' });
      return res.json({ code: Code.Success, data: job });
    }
  );
};
```

- [ ] **Step 3: Initialize plagiarism queue in app.ts**

Add to `margin-backend/src/app.ts` imports:

```typescript
import { initPlagiarismQueue } from '@/queues/plagiarism.queue';
```

After `initAutoCiteQueue(io);` add:

```typescript
initPlagiarismQueue(io);
console.log('Plagiarism queue initialized');
```

- [ ] **Step 4: Register plagiarism routes**

Update `margin-backend/src/api/index.ts` — add import and registration:

```typescript
import plagiarism from './routes/plagiarism';
```

In the function body:
```typescript
plagiarism(router);
```

- [ ] **Step 5: Commit**

```bash
git add margin-backend/src/queues/plagiarism.queue.ts margin-backend/src/api/routes/plagiarism.ts margin-backend/src/app.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add plagiarism check queue and routes with Copyscape integration"
```

---

### Task 26: Frontend Plagiarism View

**Files:**
- Create: `margin-frontend/components/cite/PlagiarismView.tsx`
- Modify: `margin-frontend/app/(workspace)/auto-cite/page.tsx` (add plagiarism tab)

- [ ] **Step 1: Create PlagiarismView component**

Write `margin-frontend/components/cite/PlagiarismView.tsx`:

```tsx
'use client';

import { useState, useEffect, useRef } from 'react';
import { io, Socket } from 'socket.io-client';
import { toast } from 'react-toastify';
import { clsx } from 'clsx';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code, SOCKET_URL } from '@/lib/core/Constants';
import { PlagiarismMatch } from '@/store/types';
import { useBalance } from '@/hooks/credit';

export function PlagiarismView() {
  const [text, setText] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>('idle');
  const [overallScore, setOverallScore] = useState(0);
  const [matches, setMatches] = useState<PlagiarismMatch[]>([]);
  const socketRef = useRef<Socket | null>(null);
  const { mutate: refreshBalance } = useBalance();

  useEffect(() => {
    const socket = io(SOCKET_URL);
    socketRef.current = socket;

    socket.on('plagiarism:progress', (data: any) => {
      if (data.status === 'done') {
        setStatus('done');
        setOverallScore(data.overallScore);
        setMatches(data.matches);
        refreshBalance();
      } else if (data.status === 'failed') {
        setStatus('failed');
        toast.error(data.error || 'Check failed');
      } else {
        setStatus(data.status);
      }
    });

    return () => {
      socket.disconnect();
    };
  }, [refreshBalance]);

  useEffect(() => {
    if (jobId && socketRef.current) {
      socketRef.current.emit('join', `plagiarism:${jobId}`);
    }
  }, [jobId]);

  const handleCheck = async () => {
    if (!text.trim()) {
      toast.error('Enter text to check');
      return;
    }
    setStatus('pending');
    setMatches([]);
    setOverallScore(0);

    const res = await Fetch.postWithAccessToken<any>('/api/plagiarism/check', { text });
    if (res.data.code === Code.Success) {
      setJobId(res.data.data.jobId);
    } else {
      toast.error(res.data.message);
      setStatus('idle');
    }
  };

  const isProcessing = ['pending', 'processing'].includes(status);

  const scoreColor = overallScore >= 80 ? 'text-error' : overallScore >= 40 ? 'text-warn' : 'text-success';
  const scoreBg = overallScore >= 80 ? 'stroke-error' : overallScore >= 40 ? 'stroke-warn' : 'stroke-success';

  return (
    <div className="space-y-4">
      {/* Input */}
      <div className="bg-white rounded-xl border border-rule overflow-hidden">
        <div className="p-4">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Paste your text to check for plagiarism..."
            className="w-full min-h-[200px] resize-none outline-none text-sm text-ink leading-relaxed"
          />
        </div>
        <div className="px-4 py-3 border-t border-rule">
          <button
            onClick={handleCheck}
            disabled={isProcessing || !text.trim()}
            className="px-6 py-2 bg-purple text-white rounded-lg text-sm font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            {isProcessing ? 'Checking...' : 'Check Plagiarism (5 credits)'}
          </button>
        </div>
      </div>

      {/* Loading */}
      {isProcessing && (
        <div className="bg-white rounded-xl border border-rule p-8 text-center">
          <div className="w-8 h-8 border-2 border-purple border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p className="text-sm text-ink-soft">Checking for plagiarism...</p>
        </div>
      )}

      {/* Results */}
      {status === 'done' && (
        <div className="grid grid-cols-3 gap-4">
          {/* Score circle */}
          <div className="bg-white rounded-xl border border-rule p-6 flex flex-col items-center justify-center">
            <svg width="120" height="120" viewBox="0 0 120 120">
              <circle cx="60" cy="60" r="50" fill="none" stroke="#ECEDF3" strokeWidth="8" />
              <circle
                cx="60"
                cy="60"
                r="50"
                fill="none"
                className={scoreBg}
                strokeWidth="8"
                strokeDasharray={`${(overallScore / 100) * 314} 314`}
                strokeLinecap="round"
                transform="rotate(-90 60 60)"
              />
            </svg>
            <p className={clsx('text-3xl font-mono font-bold mt-2', scoreColor)}>{overallScore}%</p>
            <p className="text-xs text-ink-muted mt-1">similarity score</p>
          </div>

          {/* Matches list */}
          <div className="col-span-2 bg-white rounded-xl border border-rule overflow-hidden">
            <div className="px-4 py-3 border-b border-rule">
              <h3 className="text-xs font-semibold text-ink-soft">
                {matches.length} match{matches.length !== 1 ? 'es' : ''} found
              </h3>
            </div>
            <div className="divide-y divide-rule max-h-96 overflow-auto">
              {matches.length === 0 && (
                <div className="p-6 text-center text-sm text-ink-muted">No matches found</div>
              )}
              {matches.map((match, i) => (
                <div key={i} className="px-4 py-3">
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={clsx(
                        'text-[10px] font-bold uppercase px-1.5 py-0.5 rounded',
                        match.severity === 'high'
                          ? 'bg-error/10 text-error'
                          : match.severity === 'medium'
                            ? 'bg-warn/10 text-warn'
                            : 'bg-success/10 text-success'
                      )}
                    >
                      {match.severity}
                    </span>
                    <span className="text-xs font-mono text-ink-soft">{match.similarity}%</span>
                  </div>
                  <p className="text-sm text-ink">{match.sourceTitle}</p>
                  {match.sourceUrl && (
                    <a
                      href={match.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary hover:underline"
                    >
                      {match.sourceUrl}
                    </a>
                  )}
                  {match.matchedText && (
                    <p className="text-xs text-ink-muted mt-1 italic">"{match.matchedText.slice(0, 150)}..."</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add plagiarism tab to auto-cite page**

Update `margin-frontend/app/(workspace)/auto-cite/page.tsx`:

```tsx
'use client';

import { useState } from 'react';
import { CiteBoard } from '@/components/cite/CiteBoard';
import { PlagiarismView } from '@/components/cite/PlagiarismView';
import { clsx } from 'clsx';

const TABS = [
  { value: 'cite', label: 'Auto-Cite' },
  { value: 'plagiarism', label: 'Plagiarism Check' },
];

export default function AutoCitePage() {
  const [tab, setTab] = useState('cite');

  return (
    <div>
      <div className="flex gap-1 mb-4 bg-white rounded-lg border border-rule p-1 w-fit">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx(
              'px-4 py-2 rounded-md text-sm font-medium transition',
              tab === t.value ? 'bg-primary text-white' : 'text-ink-soft hover:bg-bg-soft'
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'cite' ? <CiteBoard /> : <PlagiarismView />}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add margin-frontend/components/cite/PlagiarismView.tsx margin-frontend/app/\(workspace\)/auto-cite/page.tsx
git commit -m "feat(frontend): add plagiarism check view with score circle and match list"
```

---

## Phase 8: Credits & Payments

### Task 27: Stripe Integration + Webhook

**Files:**
- Create: `margin-backend/src/api/routes/webhook.ts`
- Modify: `margin-backend/src/api/routes/credit.ts`
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Add purchase endpoint to credit routes**

Update `margin-backend/src/api/routes/credit.ts` — add the Stripe checkout endpoint after existing routes:

```typescript
import Stripe from 'stripe';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
  apiVersion: '2023-10-16' as any,
});

// Add this route inside the default export function:

  router.post(
    '/credit/purchase',
    passport.authenticate('jwt', { session: false }),
    async (req, res) => {
      const user = req.user as any;
      const { amount } = req.body; // credit amount to purchase

      if (!amount || amount < 10) {
        return res.json({ code: Code.InvalidInput, message: 'Minimum 10 credits' });
      }

      // $1 = 10 credits
      const priceInCents = Math.round((amount / 10) * 100);

      try {
        const session = await stripe.checkout.sessions.create({
          payment_method_types: ['card'],
          line_items: [
            {
              price_data: {
                currency: 'usd',
                product_data: { name: `${amount} Margin Credits` },
                unit_amount: priceInCents,
              },
              quantity: 1,
            },
          ],
          mode: 'payment',
          success_url: `${process.env.FRONTEND_URL || 'http://localhost:8002'}/humanizer?purchase=success`,
          cancel_url: `${process.env.FRONTEND_URL || 'http://localhost:8002'}/humanizer?purchase=cancel`,
          metadata: {
            userId: user._id.toString(),
            credits: amount.toString(),
          },
        });

        return res.json({ code: Code.Success, data: { url: session.url } });
      } catch (err: any) {
        return res.json({ code: Code.Error, message: err.message });
      }
    }
  );
```

- [ ] **Step 2: Create webhook route**

Write `margin-backend/src/api/routes/webhook.ts`:

```typescript
import { Router } from 'express';
import Stripe from 'stripe';
import { CreditService } from '@/services/credit.service';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY || '', {
  apiVersion: '2023-10-16' as any,
});

export default (router: Router) => {
  router.post('/webhook/stripe', async (req: any, res) => {
    const sig = req.headers['stripe-signature'];
    const webhookSecret = process.env.STRIPE_WEBHOOK_SECRET;

    let event: Stripe.Event;

    try {
      if (webhookSecret && sig) {
        event = stripe.webhooks.constructEvent(req.rawBody, sig, webhookSecret);
      } else {
        event = req.body;
      }
    } catch (err: any) {
      console.error('Webhook signature verification failed:', err.message);
      return res.status(400).send(`Webhook Error: ${err.message}`);
    }

    if (event.type === 'checkout.session.completed') {
      const session = event.data.object as Stripe.Checkout.Session;
      const userId = session.metadata?.userId;
      const credits = parseInt(session.metadata?.credits || '0', 10);

      if (userId && credits > 0) {
        await CreditService.addCredits(
          userId,
          credits,
          `Purchased ${credits} credits via Stripe`,
          'purchase',
          session.id
        );
        console.log(`Added ${credits} credits to user ${userId}`);
      }
    }

    return res.json({ received: true });
  });
};
```

- [ ] **Step 3: Register webhook route**

Update `margin-backend/src/api/index.ts` — add import and registration:

```typescript
import webhook from './routes/webhook';
```

In the function body:
```typescript
webhook(router);
```

- [ ] **Step 4: Commit**

```bash
git add margin-backend/src/api/routes/credit.ts margin-backend/src/api/routes/webhook.ts margin-backend/src/api/index.ts
git commit -m "feat(backend): add Stripe checkout and webhook for credit purchases"
```

---

### Task 28: Final API Index Assembly

**Files:**
- Modify: `margin-backend/src/api/index.ts`

- [ ] **Step 1: Verify final API index has all routes**

The final `margin-backend/src/api/index.ts` should look like:

```typescript
import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';
import document from './routes/document';
import humanize from './routes/humanize';
import cite from './routes/cite';
import library from './routes/library';
import plagiarism from './routes/plagiarism';
import webhook from './routes/webhook';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);
  document(router);
  humanize(router);
  cite(router);
  library(router);
  plagiarism(router);
  webhook(router);

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
```

- [ ] **Step 2: Verify final app.ts has all queue initializations**

The final `margin-backend/src/app.ts` should include:

```typescript
import 'dotenv/config';
import express from 'express';
import http from 'http';
import { Server as SocketServer } from 'socket.io';
import loaders from '@/loaders';
import { initAutoCiteQueue } from '@/queues/autocite.queue';
import { initPlagiarismQueue } from '@/queues/plagiarism.queue';

const app = express();
const server = http.createServer(app);

const io = new SocketServer(server, {
  cors: { origin: '*', methods: ['GET', 'POST'] },
});

app.set('io', io);

io.on('connection', (socket) => {
  console.log('Socket connected:', socket.id);
  socket.on('join', (room: string) => {
    socket.join(room);
  });
  socket.on('disconnect', () => {
    console.log('Socket disconnected:', socket.id);
  });
});

const start = async () => {
  await loaders({ app });

  initAutoCiteQueue(io);
  console.log('Auto-cite queue initialized');

  initPlagiarismQueue(io);
  console.log('Plagiarism queue initialized');

  const port = process.env.PORT || 8001;
  server.listen(port, () => {
    console.log(`Margin backend running on port ${port}`);
  });
};

start();
```

- [ ] **Step 3: Test full backend startup**

Run:
```bash
cd margin-backend && npm run dev
```
Expected: All loaders and queues initialize without errors.

- [ ] **Step 4: Commit**

```bash
git add margin-backend/src/api/index.ts margin-backend/src/app.ts
git commit -m "feat(backend): finalize API route registration and queue initialization"
```

---

### Task 29: Frontend rootReducer Final Assembly + Credit Purchase UI

**Files:**
- Modify: `margin-frontend/store/rootReducer.ts` (verify final state)

- [ ] **Step 1: Verify final rootReducer**

The final `margin-frontend/store/rootReducer.ts`:

```typescript
import { combineReducers } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import creditReducer from './slices/creditSlice';
import humanizerReducer from './slices/humanizerSlice';
import autoCiteReducer from './slices/autoCiteSlice';
import libraryReducer from './slices/librarySlice';

const rootReducer = combineReducers({
  auth: authReducer,
  credit: creditReducer,
  humanizer: humanizerReducer,
  autoCite: autoCiteReducer,
  library: libraryReducer,
});

export type RootState = ReturnType<typeof rootReducer>;
export default rootReducer;
```

- [ ] **Step 2: Add buy credits to CreditPill**

Update `margin-frontend/components/ui/CreditPill.tsx`:

```tsx
'use client';

import { useBalance } from '@/hooks/credit';
import { useState } from 'react';
import { toast } from 'react-toastify';
import Fetch from '@/lib/core/fetch/Fetch';
import { Code } from '@/lib/core/Constants';

export function CreditPill() {
  const { balance } = useBalance();
  const [showBuy, setShowBuy] = useState(false);

  const handleBuy = async (amount: number) => {
    const res = await Fetch.postWithAccessToken<any>('/api/credit/purchase', { amount });
    if (res.data.code === Code.Success && res.data.data.url) {
      window.location.href = res.data.data.url;
    } else {
      toast.error(res.data.message || 'Failed to create checkout');
    }
    setShowBuy(false);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowBuy(!showBuy)}
        className="flex items-center gap-1.5 px-3 py-1.5 bg-bg-blue rounded-full hover:bg-primary/10 transition"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#0022FF" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 6v12M8 10h8M8 14h8" />
        </svg>
        <span className="text-xs font-semibold text-primary font-mono">{balance}</span>
      </button>

      {showBuy && (
        <div className="absolute right-0 top-full mt-2 bg-white rounded-xl border border-rule shadow-lg p-4 w-48 z-50">
          <p className="text-xs font-semibold text-ink mb-2">Buy credits</p>
          <div className="space-y-1.5">
            {[
              { credits: 50, price: '$5' },
              { credits: 100, price: '$10' },
              { credits: 500, price: '$50' },
            ].map((pkg) => (
              <button
                key={pkg.credits}
                onClick={() => handleBuy(pkg.credits)}
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg hover:bg-bg-soft transition text-sm"
              >
                <span className="font-mono font-medium text-ink">{pkg.credits}</span>
                <span className="text-ink-muted">{pkg.price}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add margin-frontend/store/rootReducer.ts margin-frontend/components/ui/CreditPill.tsx
git commit -m "feat(frontend): finalize store and add credit purchase dropdown"
```

---

### Task 30: End-to-End Smoke Test

- [ ] **Step 1: Start all services**

Terminal 1:
```bash
docker-compose -f docker/docker-compose.yml up -d
```

Terminal 2:
```bash
cd margin-backend && npm run dev
```

Terminal 3:
```bash
cd margin-frontend && npm run dev
```

- [ ] **Step 2: Test auth flow**

1. Open `http://localhost:8002/register`
2. Create account with email/password
3. Expected: Redirects to `/humanizer` with sidebar + topbar visible

- [ ] **Step 3: Test humanizer flow**

1. On `/humanizer`, paste text in input pane
2. Select tone, adjust strength
3. Click "Humanize"
4. Expected: Spinner → output appears with AI score before/after → insight cards show

- [ ] **Step 4: Test auto-cite flow**

1. Navigate to `/auto-cite`
2. Paste essay text
3. Click "Analyze & Find Citations"
4. Expected: Progress indicator → claims appear → source candidates → bibliography panel

- [ ] **Step 5: Test library**

1. Navigate to `/library`
2. Create a folder
3. Expected: Folder appears in sidebar with color dot

- [ ] **Step 6: Test history**

1. Navigate to `/history`
2. Expected: Previous humanize runs listed with scores

- [ ] **Step 7: Commit final state**

```bash
git add -A
git commit -m "feat: complete Margin app MVP with humanizer, auto-cite, plagiarism, and library"
```
