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
