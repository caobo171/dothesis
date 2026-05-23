import type { ComponentType, SVGProps } from "react";

export type SidebarItem = {
  name: string;
  href: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  default?: boolean;
  count?: number;
  subitems?: SidebarItem[];
};

export type SidebarSection = {
  id: string;
  name: string;
  options: SidebarItem[];
};
