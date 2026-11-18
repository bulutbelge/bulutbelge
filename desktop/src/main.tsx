import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { IlkAcilisKabul } from "./Hakkinda";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
    <IlkAcilisKabul />
  </React.StrictMode>,
);
