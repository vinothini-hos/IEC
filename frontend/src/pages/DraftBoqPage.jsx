import { useEffect, useRef, useState, useCallback } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import EquipmentTabs from "../components/SpecExtraction/EquipmentTabs";

const ACCEPT = ".dwg,.dxf,.svg";

/** Components grouped by legend table category, keeping legend order. */
/** The server's own message ("detail") from an API error, e.g. a duplicate upload. */
function apiErrorMessage(err) {
  const match = /\{.*\}$/s.exec(err.message || "");
  try {
    return (match && JSON.parse(match[0]).detail) || err.message;
  } catch {
    return err.message;
  }
}

function groupByCategory(components) {
  const groups = [];
  for (const c of components) {
    const last = groups[groups.length - 1];
    if (last && last.category === c.category) last.items.push(c);
    else groups.push({ category: c.category, items: [c] });
  }
  return groups;
}

/**
 * A drawing's count with an edit button (Design Calc style). Saving an empty
 * value, or the revert button, goes back to the count found in the drawing.
 */
function CountCell({ component, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const edited = component.detected_count !== undefined;

  const save = async (value) => {
    let count = null;
    if (value !== null && String(value).trim() !== "") {
      count = Number(value);
      if (!Number.isInteger(count) || count < 0) {
        setError("Enter a whole number (0 or more)");
        return;
      }
    }
    setSaving(true);
    setError(null);
    try {
      await onEdit(component._index, count);
      setEditing(false);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <td className="num calc-editing">
        <form
          className="calc-edit-form"
          onSubmit={(e) => {
            e.preventDefault();
            save(draft);
          }}
        >
          <input
            autoFocus
            className="calc-edit-input cc-count-input"
            inputMode="numeric"
            value={draft}
            disabled={saving}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
          />
          <button type="submit" className="calc-icon-btn" disabled={saving} title="Save">
            ✓
          </button>
          <button
            type="button"
            className="calc-icon-btn"
            disabled={saving}
            onClick={() => setEditing(false)}
            title="Cancel"
          >
            ✕
          </button>
        </form>
        {error && <div className="calc-edit-error">{error}</div>}
      </td>
    );
  }

  return (
    <td
      className={"num calc-value-cell" + (edited ? " calc-edited" : "")}
      title={edited ? `Edited — found in drawing: ${component.detected_count}` : undefined}
    >
      <span>{component.count}</span>
      {edited && (
        <button
          type="button"
          className="calc-icon-btn"
          disabled={saving}
          onClick={() => save(null)}
          title="Revert to the count found in the drawing"
        >
          ↺
        </button>
      )}
      <button
        type="button"
        className="calc-icon-btn calc-edit-btn"
        onClick={() => {
          setDraft(String(component.count));
          setError(null);
          setEditing(true);
        }}
        title="Edit count"
      >
        ✎
      </button>
    </td>
  );
}

/** Counts table; with onEdit(index, count) every count gets an edit button. */
function ComponentTable({ components, onEdit }) {
  const groups = groupByCategory(components.map((c, i) => ({ ...c, _index: i })));
  const hasCategories = groups.some((g) => g.category);
  return (
    <table className="calc-table">
      <thead>
        <tr>
          <th>Component</th>
          <th className="num">Count</th>
        </tr>
      </thead>
      <tbody>
        {groups.map((g, gi) => [
          hasCategories && (
            <tr key={`cat-${gi}`} className="cc-category-row">
              <td colSpan={2}>{g.category || "Other"}</td>
            </tr>
          ),
          ...g.items.map((c, i) => (
            <tr key={`${gi}-${i}`} className={c.count === 0 ? "cc-zero" : ""}>
              <td>{c.component}</td>
              {onEdit ? (
                <CountCell component={c} onEdit={onEdit} />
              ) : (
                <td className="num">{c.count}</td>
              )}
            </tr>
          )),
        ])}
      </tbody>
    </table>
  );
}

export default function DraftBoqPage() {
  const { threadId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const equipmentIndex = Number(searchParams.get("equipment_index") || 0);
  const inputRef = useRef(null);

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [boq, setBoq] = useState(null); // { drawings }
  const [view, setView] = useState(null); // run_id of the drawing shown (null = none open)
  const [uploading, setUploading] = useState(null); // file name being counted
  const [error, setError] = useState(null);
  const [dragOver, setDragOver] = useState(false);

  const loadBoq = useCallback(async () => {
    const data = await api.getDraftBoq(threadId, equipmentIndex);
    setBoq(data);
    return data;
  }, [threadId, equipmentIndex]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setBoq(null);
    setError(null);
    setView(null);

    (async () => {
      const specData = await api.getSpecification(threadId);
      const equipmentItems = specData.result?.equipment_items || [];
      if (cancelled) return;
      setItems(equipmentItems);
      if (equipmentItems[equipmentIndex]) {
        const data = await api.getDraftBoq(threadId, equipmentIndex);
        if (cancelled) return;
        setBoq(data);
        // open the most recently counted drawing (the list is oldest first)
        setView(data.drawings.length ? data.drawings[data.drawings.length - 1].run_id : null);
      }
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [threadId, equipmentIndex]);

  const upload = async (file) => {
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!ACCEPT.split(",").includes(ext)) {
      setError(`Unsupported file type "${ext}" — upload a .dwg, .dxf or .svg drawing`);
      return;
    }
    setUploading(file.name);
    setError(null);
    try {
      const { result } = await api.uploadDraftBoqDrawing(threadId, equipmentIndex, file);
      await loadBoq();
      setView(result.run_id); // show the drawing just uploaded
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setUploading(null);
    }
  };

  const editCount = async (drawing, index, count) => {
    await api.editDraftBoqCount(threadId, drawing.run_id, index, count);
    await loadBoq();
  };

  const removeDrawing = async (drawing) => {
    if (!window.confirm(`Remove ${drawing.file_name} from this equipment's BOQ?`)) return;
    setError(null);
    try {
      await api.deleteDraftBoqDrawing(threadId, drawing.run_id);
      await loadBoq();
      setView(null);
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) {
    return <div className="empty-state">Loading…</div>;
  }

  if (!items[equipmentIndex]) {
    return (
      <div className="spec-extraction-page">
        <div className="card spec-empty-card">
          <p>No extracted specification found for this RFQ yet — run Spec Extraction first.</p>
        </div>
      </div>
    );
  }

  const drawings = boq?.drawings || [];
  // only the drawing the user clicked (or just uploaded) is shown in detail
  const drawing = drawings.find((d) => d.run_id === view) || null;
  const preview = drawing?.files?.includes("check.svg")
    ? "check.svg"
    : drawing?.files?.includes("check.png")
      ? "check.png"
      : null;

  return (
    <div className="spec-extraction-page">
      <div className="spec-page-header">
        <div>
          <h1>
            Draft BOQ ·{" "}
            <span className="spec-title-accent">
              {items[equipmentIndex].classification_label || items[equipmentIndex].equipment_name}
            </span>
          </h1>
          <div className="spec-classification">
            {drawings.length
              ? `${drawings.length} drawing${drawings.length === 1 ? "" : "s"}`
              : "Upload this equipment's P&ID drawings — components are counted against each drawing's own legend tables"}
          </div>
        </div>
        <div className="spec-header-actions">
          {drawings.length > 0 && (
            <button
              type="button"
              className="btn-primary"
              disabled={!!uploading}
              onClick={() => inputRef.current?.click()}
            >
              {uploading ? "Counting…" : "Add drawing"}
            </button>
          )}
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />

      <EquipmentTabs
        items={items}
        activeIndex={equipmentIndex}
        onSelect={(i) => setSearchParams({ equipment_index: String(i) })}
      />

      {error && <div className="clarification-error">{error}</div>}

      {(uploading || drawings.length === 0) && (
        <div
          className={"card cc-dropzone" + (dragOver ? " drag-over" : "")}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            if (!uploading) upload(e.dataTransfer.files?.[0]);
          }}
        >
          {uploading ? (
            <>
              <div className="cc-spinner" />
              <div className="cc-dropzone-title">Counting components in {uploading}…</div>
              <div className="cc-dropzone-hint">
                Still working — large drawings can take several minutes. Keep this page open and
                don't upload the file again.
              </div>
            </>
          ) : (
            <>
              <div className="cc-dropzone-title">Drop a drawing here</div>
              <div className="cc-dropzone-hint">
                AutoCAD .dwg, .dxf or .svg — the sheet must include its legend tables. Add more
                sheets afterwards if this equipment has several drawings.
              </div>
              <button type="button" className="btn-primary" onClick={() => inputRef.current?.click()}>
                Choose file
              </button>
            </>
          )}
        </div>
      )}

      {drawing && (
        <div className={"cc-grid" + (preview ? "" : " single")}>
          <div className="card">
            <div className="cc-card-header">
              <div>
                <div className="calc-sheet-title">{drawing.file_name}</div>
                <div className="spec-classification">
                  Counted {new Date(drawing.ran_at).toLocaleString()}
                </div>
              </div>
              <div className="cc-card-actions">
                {drawing.ok && <span className="cc-total">Total {drawing.total}</span>}
                <button type="button" className="btn-secondary" onClick={() => setView(null)}>
                  Close
                </button>
              </div>
            </div>
            {drawing.ok ? (
              <ComponentTable
                components={drawing.components}
                onEdit={(index, count) => editCount(drawing, index, count)}
              />
            ) : (
              <div className="clarification-error">{drawing.error || "Counting failed"}</div>
            )}
          </div>

          {preview && (
            <div className="card">
              <div className="cc-card-header">
                <div className="calc-sheet-title">Check drawing</div>
                <a
                  className="cc-link"
                  href={api.draftBoqFileUrl(threadId, drawing.run_id, preview)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open full size ↗
                </a>
              </div>
              <a href={api.draftBoqFileUrl(threadId, drawing.run_id, preview)} target="_blank" rel="noreferrer">
                <img
                  className="cc-preview"
                  src={api.draftBoqFileUrl(threadId, drawing.run_id, preview)}
                  alt="Drawing with every counted component boxed"
                />
              </a>
              <div className="cc-legend-key">
                {drawing.counted_by === "dxf"
                  ? "Boxes: red = found by shape, blue = by label, green = by block"
                  : "Boxes: red = found by shape, green = by code letters, blue = ignored areas"}
              </div>
            </div>
          )}
        </div>
      )}

      {drawings.length > 0 && (
        <div className="card">
          <div className="cc-card-header">
            <div className="calc-sheet-title">Uploaded drawings</div>
            {!drawing && <span className="spec-classification">Click a drawing to see its counted components</span>}
          </div>
          <table className="calc-table">
            <thead>
              <tr>
                <th>Drawing</th>
                <th>Type</th>
                <th>Counted</th>
                <th className="num">Components</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {drawings.map((d) => (
                <tr
                  key={d.run_id}
                  className={"cc-drawing-row" + (d.run_id === drawing?.run_id ? " active" : "")}
                  onClick={() => setView(d.run_id === drawing?.run_id ? null : d.run_id)}
                >
                  <td>{d.file_name}</td>
                  <td>{d.file_type?.toUpperCase()}</td>
                  <td>{new Date(d.ran_at).toLocaleString()}</td>
                  <td className="num">{d.ok ? d.total : <span className="cc-failed">Failed</span>}</td>
                  <td className="num">
                    <button
                      type="button"
                      className="btn-secondary cc-remove-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeDrawing(d);
                      }}
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
