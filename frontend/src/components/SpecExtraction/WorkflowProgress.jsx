const STEPS = [
  { key: "rfq-intake", label: "RFQ Intake", state: "done" },
  { key: "spec-extraction", label: "Spec Extraction", state: "current" },
  { key: "similar-projects", label: "Similar Projects", state: "inactive" },
  { key: "draft-boq", label: "Draft BOQ", state: "inactive" },
  { key: "cost", label: "Cost", state: "inactive" },
  { key: "proposal", label: "Proposal", state: "inactive" },
];

export default function WorkflowProgress() {
  return (
    <div className="workflow-progress">
      {STEPS.map((step, i) => (
        <div className="workflow-step-wrap" key={step.key}>
          <div className={`workflow-step ${step.state}`}>
            <span className="workflow-step-dot">{step.state === "done" ? "✓" : i + 1}</span>
            <span className="workflow-step-label">{step.label}</span>
          </div>
          {i < STEPS.length - 1 && <span className="workflow-step-arrow">→</span>}
        </div>
      ))}
    </div>
  );
}