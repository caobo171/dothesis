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
