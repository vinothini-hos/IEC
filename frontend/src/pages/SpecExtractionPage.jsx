import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import PageHeader from "../components/SpecExtraction/PageHeader";
import WorkflowProgress from "../components/SpecExtraction/WorkflowProgress";
import EquipmentTabs from "../components/SpecExtraction/EquipmentTabs";
import SpecificationCard from "../components/SpecExtraction/SpecificationCard";
import ClarificationCard from "../components/SpecExtraction/ClarificationCard";

function getHeaderTitle(thread) {
  if (!thread) return "";
  if (thread.subject) return thread.subject;
  const first = (thread.participants || "").split(",")[0]?.trim();
  if (!first) return "";
  const nameMatch = first.match(/^"?([^"<]+)"?\s*<.*>$/);
  return nameMatch ? nameMatch[1].trim() : first;
}

export default function SpecExtractionPage() {
  const { threadId } = useParams();
  const navigate = useNavigate();

  const [thread, setThread] = useState(null);
  const [specResult, setSpecResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [extracting, setExtracting] = useState(false);
  const [extractError, setExtractError] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const [sendingClarification, setSendingClarification] = useState(false);
  const [clarificationError, setClarificationError] = useState(null);
  const [sentIndices, setSentIndices] = useState(new Set());

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setActiveIndex(0);
    setSentIndices(new Set());
    Promise.all([api.getThread(threadId), api.getSpecification(threadId)]).then(
      ([threadData, specData]) => {
        if (cancelled) return;
        setThread(threadData);
        setSpecResult(specData.result);
        setLoading(false);
      }
    );
    return () => {
      cancelled = true;
    };
  }, [threadId]);

  const handleExtract = async () => {
    setExtracting(true);
    setExtractError(null);
    try {
      const { result } = await api.runExtraction(threadId);
      setSpecResult(result);
      setActiveIndex(0);
      setSentIndices(new Set());
      setClarificationError(null);
    } catch (err) {
      setExtractError(err.message);
    } finally {
      setExtracting(false);
    }
  };

  const handleSendClarification = async () => {
    setSendingClarification(true);
    setClarificationError(null);
    try {
      await api.sendClarification(threadId, activeIndex);
      setSentIndices((prev) => new Set(prev).add(activeIndex));
    } catch (err) {
      setClarificationError(err.message);
    } finally {
      setSendingClarification(false);
    }
  };

  if (loading) {
    return <div className="empty-state">Loading…</div>;
  }

  const items = specResult?.equipment_items || [];
  const activeItem = items[activeIndex];
  const needsClarification =
    !!activeItem &&
    Object.values(activeItem.fields || {}).some(
      (f) => f.status === "needs_clarification" || f.status === "missing"
    );

  return (
    <div className="spec-extraction-page">
      <PageHeader
        title={getHeaderTitle(thread)}
        classificationLabel={activeItem?.classification_label}
        hasClarificationNeeded={needsClarification && !sentIndices.has(activeIndex)}
        onSendClarification={handleSendClarification}
        sendingClarification={sendingClarification}
        onExtract={handleExtract}
        extracting={extracting}
        onFindSimilarProjects={() =>
          navigate(`/similar-projects/${threadId}?equipment_index=${activeIndex}`)
        }
      />

      <WorkflowProgress />

      {extractError && <div className="clarification-error">{extractError}</div>}

      {!activeItem && (
        <div className="card spec-empty-card">
          <p>
            {extracting
              ? "Extracting…"
              : "No specification extracted yet for this RFQ — click \"Extract Specification\" above."}
          </p>
        </div>
      )}

      {activeItem && (
        <>
          <EquipmentTabs items={items} activeIndex={activeIndex} onSelect={setActiveIndex} />
          <div className="spec-main-grid">
            <div className="spec-main-col">
              <SpecificationCard fields={activeItem.fields} completion={activeItem.completion} />
            </div>
            <div className="spec-side-col">
              {needsClarification ? (
                <ClarificationCard
                  item={activeItem}
                  sending={sendingClarification}
                  sent={sentIndices.has(activeIndex)}
                  error={clarificationError}
                  onSend={handleSendClarification}
                />
              ) : (
                <div className="card clarification-clear-card">
                  <div className="clarification-clear-icon">✓</div>
                  <div>All mandatory fields are confirmed — no clarification needed.</div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}