import useSWR from 'swr';

export function useCiteJob(jobId: string | null) {
  const { data, mutate } = useSWR(
    jobId ? ['/api/cite/get', { id: jobId }] : null,
    { refreshInterval: 0 }
  );

  return {
    job: data?.code === 1 ? data.data : null,
    mutate,
  };
}
