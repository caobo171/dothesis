import { useSearchParams } from "next/navigation";
import { useCallback } from "react";

type ObjectParam = Record<string, string>;

/** Merge filter keys into the current URL search string (admin list screens). */
export function useQueryString() {
  const searchParams = useSearchParams();

  const createQueryString = useCallback(
    (name: string, value: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (value === "") params.delete(name);
      else params.set(name, value);
      return params.toString();
    },
    [searchParams],
  );

  const createMultipleQueryString = useCallback(
    (objectParam: ObjectParam) => {
      const params = new URLSearchParams(searchParams.toString());
      Object.entries(objectParam).forEach(([key, value]) => {
        if (value === "") params.delete(key);
        else params.set(key, value);
      });
      return params.toString();
    },
    [searchParams],
  );

  return { createQueryString, createMultipleQueryString };
}
