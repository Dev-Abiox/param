import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import "@/index.css";
import App from "@/App";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="light" storageKey="clinomic-theme">
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>,
);
