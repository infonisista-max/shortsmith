// The component registry (decision 9.2). registry.json is the checked-in list the
// style loader (008) cross-checks and the Node test asserts against these files. The
// six enter transitions (9.4, ticket 030) are registered like any component: each is a
// file that wraps a beat's picture.
import type React from "react";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Chart } from "./components/chart";
import { Counter } from "./components/counter";
import { Cut } from "./components/cut";
import { Fade } from "./components/fade";
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
import { Spring } from "./components/spring";
import { Stamp } from "./components/stamp";
import { Wall } from "./components/wall";
import { Whip } from "./components/whip";
import { Wipe } from "./components/wipe";
import { Zoom } from "./components/zoom";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const REGISTRY: Record<string, React.ComponentType<any>> = {
  captions: Captions,
  card: Card,
  chart: Chart,
  counter: Counter,
  cut: Cut,
  fade: Fade,
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
  spring: Spring,
  stamp: Stamp,
  wall: Wall,
  whip: Whip,
  wipe: Wipe,
  zoom: Zoom,
};
