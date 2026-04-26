import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

@modelOptions({ schemaOptions: { collection: 'users', timestamps: true } })
export class User {
  @prop({ required: true, unique: true })
  public username!: string;

  @prop({ required: true })
  public fullName!: string;

  @prop({ required: true, unique: true })
  public email!: string;

  @prop({ required: true })
  public password!: string;

  @prop()
  public googleId?: string;

  @prop({ default: false })
  public emailVerified!: boolean;

  @prop()
  public verificationToken?: string;

  @prop({ default: 0 })
  public credit!: number;

  @prop({ default: 'free' })
  public plan!: string;

  @prop({ default: 'User' })
  public role!: string;

  @prop()
  public version?: string;

  @prop()
  public lastLogin?: Date;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = obj._id;
    delete obj.password;
    delete obj.verificationToken;
    delete obj.__v;
    return obj;
  }
}

export const UserModel = getModelForClass(User);
