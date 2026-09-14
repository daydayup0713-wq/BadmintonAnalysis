export default defineAppConfig({
  pages: ["pages/index/index", "pages/rallies/index"],
  window: {
    backgroundTextStyle: "light",
    navigationBarBackgroundColor: "#14201c",
    navigationBarTitleText: "CourtVision",
    navigationBarTextStyle: "white",
    backgroundColor: "#f4f5ef",
  },
  tabBar: {
    color: "#7a8580",
    selectedColor: "#174f3f",
    backgroundColor: "#ffffff",
    borderStyle: "white",
    list: [
      {
        pagePath: "pages/index/index",
        text: "任务",
      },
      {
        pagePath: "pages/rallies/index",
        text: "回合",
      }
    ],
  },
});
