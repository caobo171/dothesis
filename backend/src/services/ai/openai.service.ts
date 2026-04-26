import OpenAI from 'openai';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export class OpenAIService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number; jsonMode?: boolean } = {}
  ): Promise<string> {
    const response = await openai.chat.completions.create({
      // Decision: Upgraded from gpt-4o to gpt-5.5 (released April 2026).
      // gpt-4o humanization output was too robotic — GPTZero flagged it for
      // "Mechanical Precision" and "Lacks Creative Grammar". gpt-5.5 follows
      // complex creative instructions much better.
      model: 'gpt-5.5',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: options.temperature ?? 0.7,
      // Decision: GPT-5.5 requires max_completion_tokens instead of max_tokens.
      max_completion_tokens: options.maxTokens ?? 4096,
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
      // Decision: Upgraded from gpt-4o to gpt-5.5 (released April 2026).
      // gpt-4o humanization output was too robotic — GPTZero flagged it for
      // "Mechanical Precision" and "Lacks Creative Grammar". gpt-5.5 follows
      // complex creative instructions much better.
      model: 'gpt-5.5',
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userPrompt },
      ],
      temperature: options.temperature ?? 0.7,
      // Decision: GPT-5.5 requires max_completion_tokens instead of max_tokens.
      max_completion_tokens: options.maxTokens ?? 4096,
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
