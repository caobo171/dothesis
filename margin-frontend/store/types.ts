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
