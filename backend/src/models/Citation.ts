import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'citations', timestamps: true } })
export class Citation {
  @prop({ required: true })
  public owner!: string;

  @prop()
  public folderId?: string;

  @prop({ required: true })
  public style!: string;

  @prop({ required: true })
  public formattedText!: string;

  @prop({ required: true })
  public author!: string;

  @prop()
  public year?: number;

  @prop({ required: true })
  public title!: string;

  @prop()
  public journal?: string;

  @prop()
  public doi?: string;

  @prop()
  public url?: string;

  @prop()
  public sourceApi?: string;
}

export const CitationModel = getModelForClass(Citation);
