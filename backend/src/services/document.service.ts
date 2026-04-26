import mammoth from 'mammoth';
import pdfParse from 'pdf-parse';
import * as cheerio from 'cheerio';
import axios from 'axios';
import AWS from 'aws-sdk';
import { DocumentModel } from '@/models/Document';

const s3 = new AWS.S3({
  accessKeyId: process.env.AWS_ACCESS_KEY_ID,
  secretAccessKey: process.env.AWS_SECRET_ACCESS_KEY,
  region: process.env.AWS_REGION,
});

export class DocumentService {
  static countWords(text: string): number {
    return text.trim().split(/\s+/).filter(Boolean).length;
  }

  static async parseFile(buffer: Buffer, mimeType: string): Promise<string> {
    if (mimeType === 'application/pdf') {
      const result = await pdfParse(buffer);
      return result.text;
    }
    if (
      mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    ) {
      const result = await mammoth.extractRawText({ buffer });
      return result.value;
    }
    // txt, md
    return buffer.toString('utf-8');
  }

  static async uploadToS3(
    buffer: Buffer,
    key: string,
    mimeType: string
  ): Promise<string> {
    await s3
      .upload({
        Bucket: process.env.AWS_S3_BUCKET || '',
        Key: key,
        Body: buffer,
        ContentType: mimeType,
      })
      .promise();
    return key;
  }

  static async scrapeUrl(url: string): Promise<{ title: string; content: string }> {
    const { data: html } = await axios.get(url, {
      headers: { 'User-Agent': 'Mozilla/5.0 (compatible; DoThesisBot/1.0)' },
      timeout: 10000,
    });

    const $ = cheerio.load(html);

    // Remove nav, scripts, ads, headers, footers
    $('script, style, nav, header, footer, aside, .ads, .advertisement, .sidebar').remove();

    // Try to find main content
    let content = '';
    const selectors = ['article', 'main', '[role="main"]', '.post-content', '.entry-content'];
    for (const sel of selectors) {
      if ($(sel).length) {
        content = $(sel).first().text();
        break;
      }
    }
    if (!content) {
      content = $('body').text();
    }

    // Clean up whitespace
    content = content.replace(/\s+/g, ' ').trim();

    const title = $('title').text().trim() || $('h1').first().text().trim() || 'Untitled';

    return { title, content };
  }

  static async createFromText(
    owner: string,
    title: string,
    content: string,
    sourceType: string,
    sourceUrl?: string,
    fileKey?: string,
    mimeType?: string
  ) {
    return DocumentModel.create({
      owner,
      title,
      content,
      sourceType,
      sourceUrl,
      fileKey,
      mimeType: mimeType || 'text/plain',
      wordCount: this.countWords(content),
    });
  }
}
