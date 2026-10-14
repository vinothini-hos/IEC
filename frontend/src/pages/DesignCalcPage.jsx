import { useEffect, useState, useCallback } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import EquipmentTabs from "../components/SpecExtraction/EquipmentTabs";
import CalcTable from "../components/DesignCalc/CalcTable";

export default function DesignCalcPage() {
  const { threadId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const equipmentIndex = Number(searchParams.get("equipment_index") || 0);

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState(null);
  const [calcResult, setCalcResult] = useState(null);
  const [activeSheet, setActiveSheet] = useState(null);

  const runCalc = useCallback(async () => {
    setRunning(true);
    setRunError(null);
    try {
      const { result } = await api.runDesignCalc(threadId, equipmentIndex);
      setCalcResult(result);
    } catch (err) {
      setRunError(err.message);
    } finally {
      setRunning(false);
    }
  }, [threadId, equipmentIndex]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setCalcResult(null);
    setRunError(null);

    (async () => {
      const specData = await api.getSpecification(threadId);
      const equipmentItems = specData.result?.equipment_items || [];
      if (cancelled) return;
      setItems(equipmentItems);

      if (!equipmentItems[equipmentIndex]) {
        setLoading(false);
        return;
      }

      const cached = await api.getDesignCalc(threadId, equipmentIndex);
      if (cancelled) return;
      setLoading(false);

      if (cached.result) {
        setCalcResult(cached.result);
      } else {
        runCalc();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [threadId, equipmentIndex, runCalc]);

  const editCell = async (sheetKey, tableId, rowId, key, value) => {
    const { result } = await api.editDesignCalcCell(threadId, {
      equipment_index: equipmentIndex,
      sheet_key: sheetKey,
      table_id: tableId,
      row_id: rowId,
      key,
      value,
    });
    setCalcResult(result);
  };

  const sheets = calcResult?.sheets || [];
  const sheet = sheets.find((s) => s.key === activeSheet) || sheets[0];

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

  const errorCount = sheet ? Object.keys(sheet.errors || {}).length : 0;

  return (
    <div className="spec-extraction-page">
      <div className="spec-page-header">
        <div>
          <h1>
            Design Calculation ·{" "}
            <span className="spec-title-accent">
              {items[equipmentIndex].classification_label || items[equipmentIndex].equipment_name}
            </span>
          </h1>
          {calcResult?.ran_at && (
            <div className="spec-classification">
              Calculated {new Date(calcResult.ran_at).toLocaleString()}
              {calcResult.enquiry_file && (
                <>
                  {" "}· enquiry input: <strong>{calcResult.enquiry_file}</strong>
                </>
              )}
            </div>
          )}
        </div>
        <div className="spec-header-actions">
          <button
            type="button"
            className="btn-secondary"
            onClick={() => navigate(`/draft-boq/${threadId}?equipment_index=${equipmentIndex}`)}
          >
            Draft BOQ
          </button>
          <button type="button" className="btn-secondary" disabled={running} onClick={runCalc}>
            {running ? "Calculating…" : calcResult ? "Recalculate" : "Run calculation"}
          </button>
          {calcResult?.has_xlsx && (
            <a
              className="btn-primary calc-download"
              href={api.designCalcXlsxUrl(threadId, equipmentIndex)}
              download
              title="All sheets in one workbook, with live formulas"
            >
              Download Excel
            </a>
          )}
        </div>
      </div>

      <EquipmentTabs
        items={items}
        activeIndex={equipmentIndex}
        onSelect={(i) => setSearchParams({ equipment_index: String(i) })}
      />

      {runError && <div className="clarification-error">{runError}</div>}
      {calcResult?.xlsx_error && <div className="clarification-error">{calcResult.xlsx_error}</div>}

      {calcResult?.pending_recalc && (
        <div className="calc-pending-banner">
          <span>
            Values edited — cells that depend on them (and the Excel download) update when you
            recalculate.
          </span>
          <button type="button" className="btn-primary" disabled={running} onClick={runCalc}>
            {running ? "Calculating…" : "Recalculate"}
          </button>
        </div>
      )}

      {running && !calcResult && (
        <div className="card spec-empty-card">
          <p>Calculating…</p>
        </div>
      )}

      {sheet && (
        <>
          <div className="equipment-tabs">
            {sheets.map((s) => (
              <button
                type="button"
                key={s.key}
                className={"equipment-tab" + (s.key === sheet.key ? " active" : "")}
                onClick={() => setActiveSheet(s.key)}
              >
                {s.label}
                {(s.error || Object.keys(s.errors || {}).length > 0) && (
                  <span className="calc-tab-dot" title="Has errors" />
                )}
              </button>
            ))}
          </div>

          <div className="card">
            <div className="calc-sheet-header">
              <div>
                <div className="calc-sheet-title">{sheet.label}</div>
                <div className="spec-classification">
                  {sheet.error
                    ? "Sheet failed to calculate"
                    : errorCount
                      ? `${errorCount} cell${errorCount === 1 ? "" : "s"} could not be calculated`
                      : "All cells calculated"}
                </div>
              </div>
            </div>

            {sheet.error && <div className="clarification-error">{sheet.error}</div>}

            {sheet.tables.map((t, i) => (
              <CalcTable
                key={`${t.Table_id}-${i}`}
                table={t}
                errors={sheet.errors}
                onEditCell={(...args) => editCell(sheet.key, ...args)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
