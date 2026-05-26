import { render as rtlRender, RenderOptions } from "@testing-library/react";
import { ReactElement } from "react";
import { SWRConfig } from "swr";

export function render(ui: ReactElement, options?: RenderOptions) {
  return rtlRender(ui, {
    wrapper: ({ children }) => (
      <SWRConfig value={{ dedupingInterval: 0, provider: () => new Map() }}>
        {children}
      </SWRConfig>
    ),
    ...options,
  });
}

export * from "@testing-library/react";
