import { GoogleGenAI } from '@google/genai';
import { AIChatResult } from './ai.service.manager';

const genai = new GoogleGenAI({ apiKey: process.env.GEMINI_API_KEY || '' });

export class GeminiService {
  static async chat(
    systemPrompt: string,
    userPrompt: string,
    options: { temperature?: number; maxTokens?: number; jsonMode?: boolean } = {}
  ): Promise<AIChatResult> {
    const response = await genai.models.generateContent({
      // Decision: Upgraded from gemini-2.5-pro to gemini-3-flash-preview (Gemini 3 series).
      // Pro-level intelligence at Flash speed/pricing. Model ID requires "-preview" suffix.
      model: 'gemini-3-flash-preview',
      contents: userPrompt,
      config: {
        systemInstruction: systemPrompt,
        temperature: options.temperature ?? 0.7,
        maxOutputTokens: options.maxTokens ?? 4096,
        responseMimeType: options.jsonMode ? 'application/json' : undefined,
      },
    });

    const text = response.text || '';
    return {
      text,
      usage: {
        inputTokens: (response as any).usageMetadata?.promptTokenCount ?? 0,
        outputTokens: (response as any).usageMetadata?.candidatesTokenCount ?? 0,
      },
    };
  }

  static async chatStream(
    systemPrompt: string,
    userPrompt: string,
    onChunk: (chunk: string) => void,
    options: { temperature?: number; maxTokens?: number } = {}
  ): Promise<string> {
    const response = await genai.models.generateContentStream({
      // Decision: Upgraded from gemini-2.5-pro to gemini-3-flash-preview (Gemini 3 series).
      // Pro-level intelligence at Flash speed/pricing. Model ID requires "-preview" suffix.
      model: 'gemini-3-flash-preview',
      contents: userPrompt,
      config: {
        systemInstruction: systemPrompt,
        temperature: options.temperature ?? 0.7,
        maxOutputTokens: options.maxTokens ?? 4096,
      },
    });

    let full = '';
    for await (const chunk of response) {
      const text = chunk.text || '';
      if (text) {
        full += text;
        onChunk(text);
      }
    }
    return full;
  }
}
