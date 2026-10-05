import { useState } from "react";

const VALUE_KEYS = ["value1", "value2", "value"];

/**
 * A table whose "columns" list has value columns beyond value1/value2 (steam
 * pipe line: value1, value2, value3; piping gas tables: max_value, min_value)
 * is shown as Row | Description | Unit | <those columns, in that order>.
 * Returns them as [{key, label}], or null for the standard
 * Value / Unit / Value 2 / Unit 2 layout.
 */
const UNIT_KEYS = ["description", "unit", "unit1", "unit2", "notes"];

function ownValueColumns(table) {
  const seen = new Set();
  const own = (table.columns || []).filter(
    (c) => !UNIT_KEYS.includes(c.key) && !seen.has(c.key) && seen.add(c.key)
  );
  if (!own.some((c) => !VALUE_KEYS.includes(c.key))) return null;
  return own.map((c) => ({ key: c.key, label: c.display_name || c.key }));
}

function formatValue(v) {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "number") {
    return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
  }
  return String(v);
}

function describeOriginal(raw) {
  if (raw === null || raw === undefined || raw === "") return "empty";
  return String(raw);
}

/**
 * One value cell: shows the computed value with an edit button; editing
 * saves the typed value via onEdit (an empty value reverts the cell). An
 * edited cell is highlighted and has a revert button.
 */
function ValueCell({ row, cellKey, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const raw = row[cellKey];
  const computed = (row.computed || {})[cellKey];
  const edited = row.edited && cellKey in row.edited;
  const isMissing = !edited && typeof raw === "string" && raw.trim() === "???";
  const isFormula = !edited && typeof raw === "string" && raw.startsWith("=");

  const save = async (value) => {
    setSaving(true);
    setError(null);
    try {
      await onEdit(row.id, cellKey, value);
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
            className="calc-edit-input"
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

  const title = edited
    ? `Edited — original: ${describeOriginal(row.edited[cellKey])}`
    : isMissing
      ? "Missing input"
      : isFormula
        ? raw
        : undefined;

  return (
    <td
      className={
        "num calc-value-cell" +
        (isMissing ? " calc-missing" : "") +
        (isFormula ? " calc-formula" : "") +
        (edited ? " calc-edited" : "")
      }
      title={title}
    >
      <span>{isMissing && computed == null ? "???" : formatValue(computed)}</span>
      {edited && (
        <button
          type="button"
          className="calc-icon-btn"
          disabled={saving}
          onClick={() => save(null)}
          title="Revert to the original value"
        >
          ↺
        </button>
      )}
      <button
        type="button"
        className="calc-icon-btn calc-edit-btn"
        onClick={() => {
          setDraft(computed == null ? "" : String(computed));
          setError(null);
          setEditing(true);
        }}
        title="Edit value"
      >
        ✎
      </button>
    </td>
  );
}

/**
 * One calc-engine table (e.g. "@T1"): a row per Excel row with its computed
 * values. Hovering a value shows the formula it came from; rows with an
 * engine error (missing '???' input, unmapped cell, ...) are flagged inline.
 * Every value can be edited (onEditCell); dependent cells update on the next
 * recalculation.
 */
export default function CalcTable({ table, errors, onEditCell }) {
  const tid = table.Table_id;
  // Extra columns (wall thick's "ultimate tensile strength" etc.) - any
  // computed key that isn't a standard value column.
  const extraKeys = [];
  table.rows.forEach((r) =>
    Object.keys(r.computed || {}).forEach((k) => {
      if (!VALUE_KEYS.includes(k) && !extraKeys.includes(k)) extraKeys.push(k);
    })
  );
  const hasValue2 = table.rows.some((r) => "value2" in r);
  const onEdit = (rowId, key, value) => onEditCell(tid, rowId, key, value);
  const ownColumns = ownValueColumns(table);
  const rowError = (r) =>
    Object.entries(errors || {})
      .filter(([k]) => k.startsWith(`${tid}.${r.id}.`))
      .map(([k, msg]) => `${k.slice(tid.length + r.id.length + 2)}: ${msg}`);

  if (ownColumns) {
    // Rows without these keys (e.g. "Process Fluid" with value1/value2) show
    // their values under the table's columns in order.
    const fallback = ["value1" in table.rows[0] ? "value1" : "value", "value2"];
    const hasUnit2 = table.rows.some((r) => r.unit2 && r.unit2 !== "-");
    return (
      <div className="calc-table-wrap">
        <div className="calc-table-title">
          {table.Table_name || tid} <span className="calc-table-id">{tid}</span>
        </div>
        <table className="calc-table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Description</th>
              <th>Unit</th>
              {ownColumns.map((c) => (
                <th key={c.key} className="num">{c.label}</th>
              ))}
              {hasUnit2 && <th>Unit 2</th>}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((r) => {
              const rowErrors = rowError(r);
              const computed = r.computed || {};
              return [
                <tr key={r.id} className={rowErrors.length ? "calc-row-error" : ""}>
                  <td className="calc-row-id">{r.id}</td>
                  <td>{r.description}</td>
                  <td className="calc-unit">{r.unit1 ?? r.unit ?? ""}</td>
                  {ownColumns.map((c, i) => {
                    const key = c.key in computed ? c.key
                      : i === 0 && "value" in computed ? "value"
                      : fallback[i] in computed ? fallback[i] : null;
                    return key ? (
                      <ValueCell key={c.key} row={r} cellKey={key} onEdit={onEdit} />
                    ) : (
                      <td key={c.key} className="num">—</td>
                    );
                  })}
                  {hasUnit2 && <td className="calc-unit">{r.unit2 ?? ""}</td>}
                </tr>,
                rowErrors.length > 0 && (
                  <tr key={`${r.id}-err`} className="calc-error-line">
                    <td />
                    <td colSpan={2 + ownColumns.length + (hasUnit2 ? 1 : 0)}>{rowErrors.join(" · ")}</td>
                  </tr>
                ),
              ];
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="calc-table-wrap">
      <div className="calc-table-title">
        {table.Table_name || tid} <span className="calc-table-id">{tid}</span>
      </div>
      <table className="calc-table">
        <thead>
          <tr>
            <th>Row</th>
            <th>Description</th>
            <th className="num">Value</th>
            <th>Unit</th>
            {hasValue2 && <th className="num">Value 2</th>}
            {hasValue2 && <th>Unit 2</th>}
            {extraKeys.map((k) => (
              <th key={k} className="num">{k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((r) => {
            const rowErrors = rowError(r);
            const cell = (key) =>
              key in (r.computed || {}) ? (
                <ValueCell key={key} row={r} cellKey={key} onEdit={onEdit} />
              ) : (
                <td key={key} className="num">—</td>
              );
            return [
              <tr key={r.id} className={rowErrors.length ? "calc-row-error" : ""}>
                <td className="calc-row-id">{r.id}</td>
                <td>{r.description}</td>
                {cell("value1" in r ? "value1" : "value")}
                <td className="calc-unit">{r.unit1 ?? r.unit ?? ""}</td>
                {hasValue2 && cell("value2")}
                {hasValue2 && <td className="calc-unit">{r.unit2 ?? ""}</td>}
                {extraKeys.map((k) => cell(k))}
              </tr>,
              rowErrors.length > 0 && (
                <tr key={`${r.id}-err`} className="calc-error-line">
                  <td />
                  <td colSpan={3 + (hasValue2 ? 2 : 0) + extraKeys.length}>
                    {rowErrors.join(" · ")}
                  </td>
                </tr>
              ),
            ];
          })}
        </tbody>
      </table>
    </div>
  );
}
