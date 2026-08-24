import { Routes, Route } from "react-router-dom";
import Header from "./components/Layout/Header";
import Sidebar from "./components/Layout/Sidebar";
import InboxPage from "./pages/InboxPage";

export default function App() {
  return (
    <div className="app-shell">
      <Header />
      <div className="app-body">
        <Sidebar />
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/threads/:threadId" element={<InboxPage />} />
        </Routes>
      </div>
    </div>
  );
}
