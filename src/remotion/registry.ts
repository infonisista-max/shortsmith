// The component registry (decision 9.2). registry.json is the checked-in list the
// style loader (008) cross-checks and the Node test asserts against these files.
import type React from "react";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Chart } from "./components/chart";
import { Counter } from "./components/counter";
import { Finale } from "./components/finale";
import { HookCards } from "./components/hook_cards";
import { Infographic } from "./components/infographic";
import { LabelFlyin } from "./components/label_flyin";
import { List } from "./components/list";
import { LowerThird } from "./components/lower_third";
import { MapBase } from "./components/map";
import { Photo } from "./components/photo";
import { Pip } from "./components/pip";
import { Split } from "./components/split";
import { Stamp } from "./components/stamp";
import { Wall } from "./components/wall";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const REGISTRY: Record<string, React.ComponentType<any>> = {
  captions: Captions,
  card: Card,
  chart: Chart,
  counter: Counter,
  finale: Finale,
  hook_cards: HookCards,
  infographic: Infographic,
  label_flyin: LabelFlyin,
  list: List,
  lower_third: LowerThird,
  map: MapBase,
  photo: Photo,
  pip: Pip,
  split: Split,
  stamp: Stamp,
  wall: Wall,
};
