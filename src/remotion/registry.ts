// The component registry (decision 9.2). registry.json is the checked-in list the
// style loader (008) cross-checks and the Node test asserts against these files. The
// six enter transitions (9.4, ticket 030) are registered like any component: each is a
// file that wraps a beat's picture; 060 adds the seventh, `flash`. 061 adds `text_pop`,
// the bold words pinned on the picture that land on the spoken word; 063 adds `bubble`,
// the speech and thought bubbles of the recording's own words.
import type React from "react";
import { Bubble } from "./components/bubble";
import { Captions } from "./components/captions";
import { Card } from "./components/card";
import { Chart } from "./components/chart";
import { Counter } from "./components/counter";
import { Cut } from "./components/cut";
import { Fade } from "./components/fade";
import { Finale } from "./components/finale";
import { Flash } from "./components/flash";
import { HookCards } from "./components/hook_cards";
import { Infographic } from "./components/infographic";
import { LabelFlyin } from "./components/label_flyin";
import { List } from "./components/list";
import { LowerThird } from "./components/lower_third";
import { MapBase } from "./components/map";
import { ObjectPath } from "./components/object_path";
import { Photo } from "./components/photo";
import { PinDrop } from "./components/pin_drop";
import { Pip } from "./components/pip";
import { RouteArrow } from "./components/route_arrow";
import { Split } from "./components/split";
import { Spring } from "./components/spring";
import { Stamp } from "./components/stamp";
import { TextPop } from "./components/text_pop";
import { Wall } from "./components/wall";
import { Whip } from "./components/whip";
import { Wipe } from "./components/wipe";
import { Zoom } from "./components/zoom";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const REGISTRY: Record<string, React.ComponentType<any>> = {
  bubble: Bubble,
  captions: Captions,
  card: Card,
  chart: Chart,
  counter: Counter,
  cut: Cut,
  fade: Fade,
  finale: Finale,
  flash: Flash,
  hook_cards: HookCards,
  infographic: Infographic,
  label_flyin: LabelFlyin,
  list: List,
  lower_third: LowerThird,
  map: MapBase,
  object_path: ObjectPath,
  photo: Photo,
  pin_drop: PinDrop,
  pip: Pip,
  route_arrow: RouteArrow,
  split: Split,
  spring: Spring,
  stamp: Stamp,
  text_pop: TextPop,
  wall: Wall,
  whip: Whip,
  wipe: Wipe,
  zoom: Zoom,
};
