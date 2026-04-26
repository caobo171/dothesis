import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'documents', timestamps: true } })
export class Document {
  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public title!: string;

  @prop({ required: true })
  public content!: string;

  @prop({ required: true })
  public sourceType!: string;

  @prop()
  public sourceUrl?: string;

  @prop()
  public fileKey?: string;

  @prop({ default: 'text/plain' })
  public mimeType!: string;

  @prop({ default: 0 })
  public wordCount!: number;
}

export const DocumentModel = getModelForClass(Document);
