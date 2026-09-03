import { Routes, Route } from "react-router-dom";
import Header from "./components/Layout/Header";
import Sidebar from "./components/Layout/Sidebar";
import InboxPage from "./pages/InboxPage";
import SpecExtractionPickerPage from "./pages/SpecExtractionPickerPage";
import SpecExtractionPage from "./pages/SpecExtractionPage";
import SimilarProjectsPickerPage from "./pages/SimilarProjectsPickerPage";
import SimilarProjectsPage from "./pages/SimilarProjectsPage";

export default function App() {
  return (
    <div className="app-shell">
      <Header />
      <div className="app-body">
        <Sidebar />
        <Routes>
          <Route path="/" element={<InboxPage />} />
          <Route path="/threads/:threadId" element={<InboxPage />} />
          <Route path="/spec-extraction" element={<SpecExtractionPickerPage />} />
          <Route path="/spec-extraction/:threadId" element={<SpecExtractionPage />} />
          <Route path="/similar-projects" element={<SimilarProjectsPickerPage />} />
          <Route path="/similar-projects/:threadId" element={<SimilarProjectsPage />} />
        </Routes>
      </div>
    </div>
  );
}
