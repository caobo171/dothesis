import bcrypt from 'bcrypt';

export class Crypto {
  static hashUsernamePassword(password: string): string {
    const salt = bcrypt.genSaltSync(10);
    return bcrypt.hashSync(password, salt);
  }

  static checkCorrectPassword(password: string, hashed: string): boolean {
    return bcrypt.compareSync(password, hashed);
  }
}
