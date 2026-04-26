# Survify

A full-stack survey and research data management platform with advanced statistical analysis capabilities. Build surveys, collect responses, and run PLS-SEM and SPSS-like analyses — all in one place.

## Features

- **Form Builder** — Create surveys with drag-and-drop, import from Google Forms, or generate with AI
- **Data Collection** — Multiple collection modes: autofill, prefill, AI-powered agent responses
- **Statistical Analysis** — PLS-SEM (SmartPLS-compatible) and SPSS-like analysis with EFA, Cronbach's alpha, bootstrapping
- **Data Generation** — Generate synthetic research data based on PLS structural models with configurable fit presets
- **Real-time Updates** — Live progress tracking via WebSocket
- **Payment System** — Credit-based with Stripe, PayPal, and LemonSqueezy integration
- **Affiliate Program** — 15% commission tracking and payouts
- **Admin Dashboard** — User, form, order, and model management

## Architecture

```
survify/
├── survify-backend/          # Express.js + TypeScript API (port 7001)
├── survify-frontend/         # Next.js 14 App Router (port 7002)
└── survify-backend/
    └── survify-analyser/     # Python statistical analysis engine (port 4002)
```

## Prerequisites

- Node.js 18+
- Python 3.9+
- Docker (for MongoDB)

## Getting Started

### 1. Start the Database

```bash
docker-compose -f survify-backend/docker/docker-compose.yml up -d
```

### 2. Configure Environment

```bash
cp survify-backend/.env.example survify-backend/.env
```

Edit `.env` with your credentials for:
- MongoDB connection
- JWT secrets
- Payment providers (Stripe, LemonSqueezy, PayPal)
- AWS S3 (file storage)
- Email service (Mailgun or Gmail)

### 3. Backend

```bash
cd survify-backend
npm install
npm run dev
```

### 4. Frontend

```bash
cd survify-frontend
npm install
npm run dev
```

### 5. Python Analyser

```bash
cd survify-backend/survify-analyser
./setup_venv.sh          # or setup_venv.bat on Windows
source venv/bin/activate
pip install -r requirements.txt
python main.py           # starts FastAPI server on port 4002
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, React 19, Tailwind CSS, Redux Toolkit, SWR |
| Backend | Express.js, TypeScript, Typegoose/Mongoose |
| Database | MongoDB 6.0 |
| Analysis | Python (pandas, numpy, scipy, scikit-learn, plspm) |
| Auth | Passport.js (JWT, Local, HTTP Bearer) |
| Queue | Bull (Redis-backed job processing) |
| Real-time | Socket.io |
| Storage | AWS S3 + CloudFront CDN |
| Payments | Stripe, PayPal, LemonSqueezy |

## Scripts

### Backend

| Command | Description |
|---------|-------------|
| `npm run dev` | Start with hot reload (nodemon) |
| `npm run build` | Compile TypeScript |
| `npm start` | Run compiled app |
| `npm run test` | Run test suite |

### Frontend

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server (port 7002) |
| `npm run build` | Production build |
| `npm run lint` | Run ESLint |

## Statistical Analysis

The platform supports two analysis modes:

**SPSS Mode** — Descriptive statistics, Cronbach's alpha, Exploratory Factor Analysis (EFA), correlation matrices, linear regression

**SmartPLS Mode** — PLS-SEM path modeling, outer/inner model evaluation, bootstrapping, HTMT, Fornell-Larcker criterion, VIF analysis

See [`survify-backend/survify-analyser/README.md`](survify-backend/survify-analyser/README.md) for detailed analysis documentation.

## License

Proprietary. All rights reserved.
