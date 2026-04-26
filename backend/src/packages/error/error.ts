import { Code } from '@/Constants';

export class BaseError {
  message: string;
  code: number;

  constructor(message: string, code: number = Code.Error) {
    this.message = message;
    this.code = code;
  }

  release() {
    return { message: this.message, code: this.code };
  }
}
