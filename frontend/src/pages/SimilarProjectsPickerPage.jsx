import ProjectList from "../components/SpecExtraction/ProjectList";

const include = (t) => t.has_similar_projects;
const status = () => ({ label: "Projects found", className: "project-status-extracted" });

export default function SimilarProjectsPickerPage() {
  return (
    <ProjectList
      title="Similar Projects"
      include={include}
      status={status}
      basePath="/similar-projects"
      emptyText={'No similar projects found yet. Open an RFQ in Spec Extraction and click "Find similar projects" to get started.'}
    />
  );
}
