export class Valid {
  static email(email: string): boolean {
    if (!email || email.length > 256) return false;
    const regex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return regex.test(email);
  }

  static string(value: any, maxLength?: number): boolean {
    if (typeof value !== 'string' || value.trim().length === 0) return false;
    if (maxLength && value.length > maxLength) return false;
    return true;
  }

  static username(value: string): boolean {
    if (!value || value.trim().length === 0) return false;
    return /^[a-zA-Z0-9_ ]+$/.test(value);
  }
}
