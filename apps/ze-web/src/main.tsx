import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./globals.css";
import { applyConfig } from "@/lib/client";
import { App } from "@/app/App";

applyConfig();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
