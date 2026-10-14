import ProjectList from "../components/SpecExtraction/ProjectList";

const include = (t) => t.draft_boq_drawings > 0;
const status = (t) => ({
  label: `${t.draft_boq_drawings} drawing${t.draft_boq_drawings === 1 ? "" : "s"}`,
  className: "project-status-extracted",
});

export default function DraftBoqPickerPage() {
  return (
    <ProjectList
      title="Draft BOQs"
      include={include}
      status={status}
      basePath="/draft-boq"
      emptyText={'No draft BOQs yet. Open an RFQ in Design Calc and click "Draft BOQ" to upload its drawings.'}
    />
  );
}
