import ProjectList from "../components/SpecExtraction/ProjectList";

const include = (t) => t.has_design_calc;
const status = () => ({ label: "Calculated", className: "project-status-extracted" });

export default function DesignCalcPickerPage() {
  return (
    <ProjectList
      title="Design Calculations"
      include={include}
      status={status}
      basePath="/design-calc"
      emptyText={'No design calculations yet. Open an RFQ in Spec Extraction and click "Design calculation" to get started.'}
    />
  );
}
