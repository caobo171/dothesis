import { SESv2Client, SendEmailCommand } from "@aws-sdk/client-sesv2";

let sesClient: SESv2Client;

export class Mailer {
  static async init() {
    sesClient = new SESv2Client({
      region: process.env.AWS_REGION || 'ap-southeast-1',
      credentials: {
        accessKeyId: process.env.AWS_SES_ACCESS_KEY || process.env.AWS_ACCESS_KEY_ID || '',
        secretAccessKey: process.env.AWS_SES_SECRET_KEY || process.env.AWS_SECRET_ACCESS_KEY || '',
      },
    });
  }

  static async sendVerificationEmail(email: string, username: string, token: string) {
    const link = `${process.env.FRONTEND_URL || 'http://localhost:8002'}/verify?token=${token}&email=${encodeURIComponent(email)}`;

    const html = `
      <div style="font-family: 'DM Sans', Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px;">
        <h2 style="color: #0A0E27; margin-bottom: 8px;">Welcome to DoThesis</h2>
        <p style="color: #6B7280; font-size: 14px;">Hi <strong>${username}</strong>,</p>
        <p style="color: #6B7280; font-size: 14px;">
          Click the button below to verify your email and activate your account:
        </p>
        <a href="${link}" style="display: inline-block; padding: 12px 24px; background: #0022FF; color: #fff; text-decoration: none; border-radius: 8px; font-size: 14px; font-weight: 600; margin: 16px 0;">
          Verify my account
        </a>
        <p style="color: #9CA3AF; font-size: 12px; margin-top: 24px;">
          Or copy this link: <a href="${link}" style="color: #0022FF;">${link}</a>
        </p>
        <p style="color: #9CA3AF; font-size: 12px;">This link expires in 24 hours.</p>
      </div>
    `;

    try {
      const cmd = new SendEmailCommand({
        FromEmailAddress: `DoThesis <${process.env.SES_FROM_EMAIL || 'noreply@dothesis.app'}>`,
        Destination: { ToAddresses: [email] },
        Content: {
          Simple: {
            Subject: { Data: '[DoThesis] Verify your email', Charset: 'UTF-8' },
            Body: { Html: { Data: html, Charset: 'UTF-8' } },
          },
        },
      });

      await sesClient.send(cmd);
    } catch (err: any) {
      console.error('SES error:', err?.message || err);
    }
  }
}
