import useSWR from 'swr';

export function useFolders() {
  const { data, mutate } = useSWR(['/api/library/folders/list', {}]);
  return {
    folders: data?.code === 1 ? data.data : [],
    mutate,
  };
}

export function useCitations(folderId: string | null) {
  const params: any = {};
  if (folderId) params.folderId = folderId;

  const { data, mutate } = useSWR(['/api/library/citations/list', params]);
  return {
    citations: data?.code === 1 ? data.data : [],
    mutate,
  };
}
