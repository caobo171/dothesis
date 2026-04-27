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

    // Decision: Destructure { text: result } because chat() now returns AIChatResult
    // with { text, usage } instead of a plain string.
    const { text: result } = await ai.tryWithFallback('extract-claims', async (service) => {
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

    // Decision: Destructure { text: result } because chat() now returns AIChatResult
    // with { text, usage } instead of a plain string.
    const { text: result } = await ai.tryWithFallback('rank-candidates', async (service) => {
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

    // Decision: Destructure { text } because chat() now returns AIChatResult
    // with { text, usage } instead of a plain string.
    const { text } = await ai.tryWithFallback('format-citation', async (service) => {
      return service.chat(systemPrompt, userPrompt, { temperature: 0.1 });
    });
    return text;
  }
}
