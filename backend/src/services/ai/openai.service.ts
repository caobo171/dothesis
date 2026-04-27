import OpenAI from 'openai';
import { AIChatResult } from './ai.service.manager';

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });

export class OpenAIService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: {
      temperature?: number;
      maxTokens?: number;
      jsonMode?: boolean;
      presencePenalty?: number;
      frequencyPenalty?: number;
    } = {}
  ): Promise<AIChatResult> {
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
      // Decision: Added presence/frequency penalties for multi-agent humanizer pipeline.
      // presence_penalty encourages branching into new concepts.
      // frequency_penalty discourages word repetition, making text more dynamic.
      presence_penalty: options.presencePenalty ?? 0,
      frequency_penalty: options.frequencyPenalty ?? 0,
    });

    const text = response.choices[0]?.message?.content || '';
    return {
      text,
      usage: {
        inputTokens: response.usage?.prompt_tokens ?? 0,
        outputTokens: response.usage?.completion_tokens ?? 0,
      },
    };
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
