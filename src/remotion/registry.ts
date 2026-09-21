// The component registry (decision 9.2). registry.json is the checked-in list the
// style loader (008) cross-checks and the Node test asserts against these files.
import type React from "react";
import { Captions } from "./components/captions";
import { Pip } from "./components/pip";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const REGISTRY: Record<string, React.ComponentType<any>> = {
  captions: Captions,
  pip: Pip,
};
