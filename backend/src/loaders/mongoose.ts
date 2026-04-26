import mongoose from 'mongoose';

export default async () => {
  const uri = process.env.MONGO_URI || 'mongodb://localhost:27017/margin';
  try {
    await mongoose.connect(uri);
    console.log('MongoDB connected');
  } catch (err) {
    console.error('MongoDB connection failed:', err);
    process.exit(1);
  }
};
