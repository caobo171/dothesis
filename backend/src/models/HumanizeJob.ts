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

  // Track how many pipeline iterations ran for this humanization job
  @prop({ default: 0 })
  public iterations!: number;

  // Track token usage per step (model names like gemini-3-flash-preview, gpt-5.5) for cost analysis
  @prop({
    type: () => Object,
    default: () => ({ steps: [], totalInputTokens: 0, totalOutputTokens: 0 }),
  })
  public tokenUsage!: {
    steps: Array<{
      step: string;
      model: string;
      iteration: number;
      inputTokens: number;
      outputTokens: number;
    }>;
    totalInputTokens: number;
    totalOutputTokens: number;
  };
}

export const HumanizeJobModel = getModelForClass(HumanizeJob);
