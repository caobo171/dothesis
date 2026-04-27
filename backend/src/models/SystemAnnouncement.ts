// backend/src/models/SystemAnnouncement.ts
//
// Admin-managed in-app announcement banner. The public endpoint
// /api/announcements/active returns only enabled announcements whose
// startsAt..endsAt window overlaps now (open-ended on either side).
//
// audience options:
//   'all'   — all signed-in users
//   'free'  — users on the free plan only
//   'paid'  — users on a paid plan only
//
// Filtering by audience is a frontend concern for now; the active endpoint
// returns all enabled-and-current rows and the workspace layout decides which
// to render based on the current user's plan.

import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';

export type AnnouncementAudience = 'all' | 'free' | 'paid';

@modelOptions({ schemaOptions: { collection: 'system_announcements', timestamps: true } })
export class SystemAnnouncement {
  @prop({ required: true })
  public title!: string;

  // Markdown by convention. Rich text deferred until/unless requested.
  @prop({ required: true, default: '' })
  public content!: string;

  @prop({ required: true, default: 'all' })
  public audience!: AnnouncementAudience;

  @prop({ default: false })
  public enabled!: boolean;

  @prop()
  public startsAt?: Date;

  @prop()
  public endsAt?: Date;

  @prop({ default: '' })
  public createdBy!: string;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = String(obj._id);
    delete obj.__v;
    return obj;
  }
}

export const SystemAnnouncementModel = getModelForClass(SystemAnnouncement);
