import { UserModel } from '@/models/User';
import { CreditModel } from '@/models/Credit';
import { CreditDirection, CreditStatus } from '@/Constants';

export class CreditService {
  static async getBalance(userId: string): Promise<number> {
    const user = await UserModel.findById(userId);
    return user?.credit || 0;
  }

  static async hasEnough(userId: string, amount: number): Promise<boolean> {
    const balance = await this.getBalance(userId);
    return balance >= amount;
  }

  static async deduct(
    userId: string,
    amount: number,
    orderType: string,
    orderId: string,
    description: string
  ): Promise<boolean> {
    const user = await UserModel.findById(userId);
    if (!user || user.credit < amount) return false;

    user.credit -= amount;
    await user.save();

    await CreditModel.create({
      amount,
      direction: CreditDirection.Outbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });

    return true;
  }

  static async refund(
    userId: string,
    amount: number,
    orderType: string,
    orderId: string,
    description: string
  ): Promise<void> {
    await UserModel.findByIdAndUpdate(userId, { $inc: { credit: amount } });

    await CreditModel.create({
      amount,
      direction: CreditDirection.Inbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });
  }

  static async addCredits(
    userId: string,
    amount: number,
    description: string,
    orderType: string = 'purchase',
    orderId: string = ''
  ): Promise<void> {
    await UserModel.findByIdAndUpdate(userId, { $inc: { credit: amount } });

    await CreditModel.create({
      amount,
      direction: CreditDirection.Inbound,
      owner: userId,
      status: CreditStatus.Completed,
      description,
      orderType,
      orderId,
    });
  }

  static async getHistory(userId: string, limit = 50): Promise<any[]> {
    const credits = await CreditModel.find({ owner: userId })
      .sort({ createdAt: -1 })
      .limit(limit);
    return credits.map((c: any) => c.secureRelease());
  }
}
