import useSWR from 'swr';

export function useHumanizerHistory() {
  const { data, mutate } = useSWR(['/api/humanize/history', {}]);
  return {
    jobs: data?.code === 1 ? data.data : [],
    mutate,
  };
}

export function useHumanizerJob(id: string | null) {
  const { data } = useSWR(id ? ['/api/humanize/get', { id }] : null);
  return {
    job: data?.code === 1 ? data.data : null,
  };
}
