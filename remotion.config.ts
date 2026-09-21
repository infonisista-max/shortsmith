// Remotion CLI config (used by `npm run studio` and `remotion bundle`); the Python
// bridge renders through src/remotion/driver.mjs, which passes the same settings to
// @remotion/renderer explicitly: concurrency 2 and bt709 (decision 9.1).
import { Config } from "@remotion/cli/config";

Config.setPublicDir("./assets"); // Poppins under assets/fonts/, loaded via staticFile()
Config.setColorSpace("bt709");
Config.setConcurrency(2);
Config.setVideoImageFormat("jpeg");
