import useSWR from 'swr';

export function useBalance() {
  const { data, mutate } = useSWR(['/api/credit/balance', {}]);
  return {
    balance: data?.code === 1 ? data.data.balance : 0,
    mutate,
  };
}

export function useCreditHistory() {
  const { data } = useSWR(['/api/credit/history', {}]);
  return { history: data?.code === 1 ? data.data : [] };
}
