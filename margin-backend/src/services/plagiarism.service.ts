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
