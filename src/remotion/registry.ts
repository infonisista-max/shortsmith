// The component registry (decision 9.2). registry.json is the checked-in list the
// style loader (008) cross-checks and the Node test asserts against these files.
import type React from "react";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Finale } from "./components/finale";
import { HookCards } from "./components/hook_cards";
import { LowerThird } from "./components/lower_third";
import { Photo } from "./components/photo";
import { Pip } from "./components/pip";
import { Stamp } from "./components/stamp";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const REGISTRY: Record<string, React.ComponentType<any>> = {
  captions: Captions,
  card: Card,
  finale: Finale,
  hook_cards: HookCards,
  lower_third: LowerThird,
  photo: Photo,
  pip: Pip,
  stamp: Stamp,
};
