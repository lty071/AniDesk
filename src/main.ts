import { createApp } from "vue";
import { createPinia } from "pinia";
import App from "./App.vue";
import ReminderOverlay from "./components/ReminderOverlay.vue";
import { isTauri } from "./services/platform";
import "./styles.css";

let RootComponent = App;
if (isTauri()) {
  const { getCurrentWindow } = await import("@tauri-apps/api/window");
  if (getCurrentWindow().label === "reminder") RootComponent = ReminderOverlay;
}

createApp(RootComponent).use(createPinia()).mount("#app");
