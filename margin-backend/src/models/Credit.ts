import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'credits', timestamps: true } })
export class Credit {
  @prop({ required: true })
  public amount!: number;

  @prop({ required: true })
  public direction!: string;

  @prop({ required: true })
  public owner!: string;

  @prop({ required: true })
  public status!: string;

  @prop()
  public description?: string;

  @prop()
  public orderType?: string;

  @prop()
  public orderId?: string;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = obj._id;
    delete obj.__v;
    return obj;
  }
}

export const CreditModel = getModelForClass(Credit);
