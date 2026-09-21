// Poppins 500-900 from assets/fonts/ (the public dir), loaded locally; no network
// fonts anywhere in the renderer (decisions 6.2, 13.1).
import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

const WEIGHTS: Record<string, string> = {
  "500": "Poppins-Medium.ttf",
  "600": "Poppins-SemiBold.ttf",
  "700": "Poppins-Bold.ttf",
  "800": "Poppins-ExtraBold.ttf",
  "900": "Poppins-Black.ttf",
};

export const FONT_FAMILY = "Poppins";

export const fontsReady: Promise<void> = Promise.all(
  Object.entries(WEIGHTS).map(([weight, file]) =>
    loadFont({ family: FONT_FAMILY, url: staticFile(`fonts/${file}`), weight }),
  ),
).then(() => undefined);
