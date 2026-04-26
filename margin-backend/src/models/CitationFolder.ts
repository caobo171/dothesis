import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'citation_folders', timestamps: true } })
export class CitationFolder {
  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public name!: string;

  @prop({ default: '#0022FF' })
  public color!: string;
}

export const CitationFolderModel = getModelForClass(CitationFolder);
