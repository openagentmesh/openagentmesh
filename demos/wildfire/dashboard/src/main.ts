import { mount } from "svelte";
import App from "./App.svelte";
import "./app.css";

const target = document.getElementById("app");
if (!target) {
  throw new Error("Wildfire dashboard: #app mount point not found in index.html");
}

const app = mount(App, { target });

export default app;
