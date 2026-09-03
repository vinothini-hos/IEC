export default function EquipmentTabs({ items, activeIndex, onSelect }) {
  if (!items || items.length <= 1) return null;

  return (
    <div className="equipment-tabs">
      {items.map((item, i) => (
        <button
          type="button"
          key={i}
          className={"equipment-tab" + (i === activeIndex ? " active" : "")}
          onClick={() => onSelect(i)}
        >
          {item.classification_label || item.equipment_name}
        </button>
      ))}
    </div>
  );
}