import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';
import { ACL } from '@/packages/acl/acl';

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

  // Soft-deactivate flag. Set by admin "deactivate" action in a later slice.
  // Optional so existing user docs without the field continue to work.
  @prop({ default: false })
  public disabled?: boolean;

  // Numeric identifier embedded in Sepay transfer memos so the webhook can
  // route credits without needing the user's _id (which is too long for a
  // bank memo). Backfilled lazily on first /me/bank-info call when missing.
  @prop({ unique: true, sparse: true })
  public idcredit?: number;

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
    // Expose admin flags so the frontend can gate UI without a separate request.
    // Server-side enforcement still happens via requireAdmin/requireSuperAdmin middlewares.
    obj.is_admin = ACL.isAdmin(this as any);
    obj.is_super_admin = ACL.isSuperAdmin(this as any);
    return obj;
  }
}

export const UserModel = getModelForClass(User);
