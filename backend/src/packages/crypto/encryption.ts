// backend/src/packages/crypto/encryption.ts
//
// Symmetric AES-256-GCM helpers for storing secret values at rest (e.g. AI
// provider API keys). The bcrypt-based Crypto class in crypto.ts is one-way
// and not suitable for values we need to send back to upstream providers.
//
// Key derivation: process.env.ENCRYPTION_KEY if set, otherwise the same
// JWT_SECRET used for tokens. We deliberately fall back so dev environments
// don't require a separate setting; production should configure ENCRYPTION_KEY
// to a 32-byte random hex string.
//
// Format: '<ivHex>:<authTagHex>:<ciphertextHex>'. We pin a single format so we
// can later detect and migrate ciphertexts if we ever rotate algorithms.

import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'crypto';

const ALGO = 'aes-256-gcm';
const IV_LENGTH = 12; // 96 bits is the GCM-recommended IV length.

const getKey = (): Buffer => {
  const source = process.env.ENCRYPTION_KEY || process.env.JWT_SECRET || 'dothesis_default_dev_secret';
  // Hash to a fixed-length 32-byte key regardless of the source's length.
  return createHash('sha256').update(source).digest();
};

export function encryptSecret(plaintext: string): string {
  if (!plaintext) return '';
  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGO, getKey(), iv);
  const enc = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `${iv.toString('hex')}:${tag.toString('hex')}:${enc.toString('hex')}`;
}

export function decryptSecret(ciphertext: string): string {
  if (!ciphertext) return '';
  const parts = ciphertext.split(':');
  if (parts.length !== 3) {
    // Tolerate legacy/unknown formats by returning empty rather than throwing —
    // the caller can detect a missing key via hasKey: boolean.
    return '';
  }
  try {
    const [ivHex, tagHex, encHex] = parts;
    const decipher = createDecipheriv(ALGO, getKey(), Buffer.from(ivHex, 'hex'));
    decipher.setAuthTag(Buffer.from(tagHex, 'hex'));
    const dec = Buffer.concat([decipher.update(Buffer.from(encHex, 'hex')), decipher.final()]);
    return dec.toString('utf8');
  } catch {
    return '';
  }
}
