import { defineConfig } from "@tarojs/cli";

export default defineConfig({
  projectName: "courtvision-mini",
  date: "2026-06-14",
  designWidth: 750,
  deviceRatio: {
    750: 1,
  },
  sourceRoot: "src",
  outputRoot: "dist",
  framework: "react",
  compiler: "webpack5",
  cache: {
    enable: true,
  },
  mini: {
    postcss: {
      pxtransform: {
        enable: true,
        config: {},
      },
      cssModules: {
        enable: false,
      },
    },
  },
});
