// `cut` (decision 9.4): the beat's picture is simply there from its first frame. The
// default enter, and the only one with no numbers.
import React from "react";
import { AbsoluteFill } from "remotion";
import type { EnterProps } from "./transitions";

export const Cut: React.FC<EnterProps> = ({ children }) => <AbsoluteFill>{children}</AbsoluteFill>;
