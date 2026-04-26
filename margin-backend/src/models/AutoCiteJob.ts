import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

class ClaimCandidate {
  @prop()
  public sourceId!: string;

  @prop()
  public relevanceScore!: number;
}

class Claim {
  @prop()
  public text!: string;

  @prop()
  public sourceId?: string;

  @prop({ default: 'pending' })
  public status!: string;

  @prop({ type: () => [ClaimCandidate], default: [] })
  public candidates!: ClaimCandidate[];
}

class CiteSource {
  @prop()
  public id!: string;

  @prop()
  public cite!: string;

  @prop()
  public authorShort!: string;

  @prop()
  public year!: number;

  @prop()
  public title!: string;

  @prop()
  public snippet!: string;

  @prop()
  public conf!: number;

  @prop()
  public sourceApi!: string;
}

@modelOptions({ schemaOptions: { collection: 'autocite_jobs', timestamps: true } })
export class AutoCiteJob {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public documentId?: string;

  @prop({ default: 'apa' })
  public style!: string;

  @prop({ default: 'pending' })
  public status!: string;

  @prop({ type: () => [Claim], default: [] })
  public claims!: Claim[];

  @prop({ type: () => [CiteSource], default: [] })
  public sources!: CiteSource[];

  @prop({ default: 0 })
  public creditsUsed!: number;
}

export const AutoCiteJobModel = getModelForClass(AutoCiteJob);
